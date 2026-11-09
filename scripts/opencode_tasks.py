#!/usr/bin/env python3
"""第 5 項：用 opencode 跑 tasks/ 底下的多檔案題目，判定對錯並記錄每輪等待時間。

opencode 和推論伺服器之間放一個本機記錄代理（預設 8081 → 8080），每個請求記錄首個位元組時間、總時間、
訊息數、工具定義數、是否回傳 tool_calls。這樣就不依賴 opencode 的輸出格式，官方文件沒有列出那個格式。

判定：opencode 結束後，把 tests/ 換回原始版本並加上 hidden/ 的測試再執行，模型改測試或寫死答案都騙不過。
每題用 --timeout 限時。工作目錄和原始輸出在 logs/opencode_work/<label>/<題目>/，摘要寫到 logs/<label>_<時間>.jsonl。

用法：
  python3 -I scripts/opencode_tasks.py --validate       驗證題目：原始狀態要失敗，套上參考解答要全過（不需要模型）
  python3 -I scripts/opencode_tasks.py --label mini_oc_qwen
環境變數 OPENCODE_EXTRA_ARGS 可追加 opencode run 的參數。
"""
import argparse, http.client, http.server, json, os, re, shlex, shutil, signal, socketserver, subprocess, sys, threading, time

ROOT = os.environ.get("FLASHBACK_ROOT", "/Volumes/LLM SSD/Flashback")
TASKS = f"{ROOT}/tasks"
MODEL_ID = "local-model"
UNITTEST = [sys.executable, "-I", "-m", "unittest", "discover", "-s", "tests", "-t", "."]


def task_names():
    return sorted(d for d in os.listdir(TASKS) if os.path.isfile(f"{TASKS}/{d}/TASK.md"))


def overlay(src, dst):
    shutil.copytree(src, dst, dirs_exist_ok=True)


def run_tests(work, timeout=60):
    """回傳 (全過與否, 測試數, 失敗加錯誤數, 輸出結尾)。"""
    try:
        p = subprocess.run(UNITTEST, cwd=work, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, 0, -1, "timeout"
    out = p.stderr
    ran = re.search(r"Ran (\d+) test", out)
    bad = sum(int(n) for n in re.findall(r"(?:failures|errors)=(\d+)", out))
    n = int(ran.group(1)) if ran else 0
    return p.returncode == 0 and n > 0, n, bad, out[-1500:]


def grade(name, work):
    """換回原始測試、加上隱藏測試後判定。"""
    shutil.rmtree(f"{work}/tests", ignore_errors=True)
    overlay(f"{TASKS}/{name}/repo/tests", f"{work}/tests")
    overlay(f"{TASKS}/{name}/hidden", f"{work}/tests")
    return run_tests(work)


def validate():
    base = f"{ROOT}/logs/task_validate"
    ok = True
    for name in task_names():
        work = f"{base}/{name}"
        shutil.rmtree(work, ignore_errors=True)
        shutil.copytree(f"{TASKS}/{name}/repo", work)
        visible = run_tests(work)
        hidden = grade(name, work)
        overlay(f"{TASKS}/{name}/solution", work)
        solved = grade(name, work)
        good = not visible[0] and not hidden[0] and solved[0]
        ok &= good
        print(f"{name}: 原始 visible {'過' if visible[0] else '敗'}（{visible[1]} 題錯 {visible[2]}）| "
              f"原始＋hidden {'過' if hidden[0] else '敗'} | 參考解答 {'過' if solved[0] else '敗'}"
              f"（{solved[1]} 題）| {'OK' if good else 'NG'}")
        if not solved[0]:
            print(solved[3])
    shutil.rmtree(base, ignore_errors=True)
    print("全部成立" if ok else "有題目不成立")
    return 0 if ok else 1


class Recorder:
    def __init__(self):
        self.lock = threading.Lock()
        self.rows = []

    def add(self, row):
        with self.lock:
            self.rows.append(row)

    def take(self):
        with self.lock:
            rows, self.rows = self.rows, []
        return rows


def summarize_body(body):
    text = body.decode("utf-8", "replace")
    info = {"tool_calls": '"tool_calls"' in text and not re.search(r'"tool_calls":\s*(null|\[\])', text)}
    finish = re.findall(r'"finish_reason":\s*"(\w+)"', text)
    info["finish_reason"] = finish[-1] if finish else None
    for key in ("timings", "usage"):
        for m in re.finditer(rf'"{key}":\s*(\{{.*?\}})', text):
            try:
                info[key] = json.loads(m.group(1))
            except ValueError:
                pass
    return info


def make_proxy(target_host, target_port, rec):
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def forward(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            t0 = time.time()
            row = {"path": self.path, "t_start": round(t0, 3)}
            try:
                req = json.loads(body) if body else {}
                row.update(messages=len(req.get("messages", [])), tools=len(req.get("tools", []) or []),
                           request_bytes=length, stream=bool(req.get("stream")))
            except ValueError:
                pass
            conn = http.client.HTTPConnection(target_host, target_port, timeout=7200)
            try:
                headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "connection", "accept-encoding")}
                conn.request(self.command, self.path, body=body, headers=headers)
                resp = conn.getresponse()
                row["status"] = resp.status
                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                        self.send_header(k, v)
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                seen = bytearray()
                first = None
                while True:
                    chunk = resp.read1(65536)
                    if not chunk:
                        break
                    if first is None:
                        first = time.time()
                    seen += chunk
                    self.wfile.write(b"%x\r\n" % len(chunk) + chunk + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                row["first_byte_s"] = round(first - t0, 3) if first else None
                row.update(summarize_body(bytes(seen)))
            except OSError as e:
                row["error"] = repr(e)
                self.close_connection = True
            finally:
                conn.close()
                row["total_s"] = round(time.time() - t0, 3)
                if "/chat/completions" in self.path:
                    rec.add(row)

        do_GET = do_POST = forward

    class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        allow_reuse_address = True
    return Server, Handler


def write_config(work, port):
    """opencode V1 設定（npm 的 opencode-ai 1.19.5 實測只收 V1，官方文件寫的 V2 格式會被拒絕）。
    不用 ask，避免非互動模式卡住。bash 規則是後面的優先。"""
    bash = {"*": "allow"}
    bash.update({p: "deny" for p in ("sudo *", "curl *", "wget *", "pip *", "pip3 *", "brew *", "npm *",
                                     "git push *", "git remote *", "ssh *", "rm -rf /*", "rm -rf ~*")})
    cfg = {"$schema": "https://opencode.ai/config.json",
           "provider": {"local": {"npm": "@ai-sdk/openai-compatible", "name": "local",
                                  "options": {"baseURL": f"http://127.0.0.1:{port}/v1", "timeout": False},
                                  "models": {MODEL_ID: {"name": MODEL_ID, "tool_call": True,
                                                        "limit": {"context": 32768, "output": 8192}}}}},
           "permission": {"edit": "allow", "bash": bash, "external_directory": "deny", "webfetch": "deny",
                          "websearch": "deny", "task": "deny"}}
    json.dump(cfg, open(f"{work}/opencode.json", "w"), indent=2)


def opencode_args(exe):
    """官方文件沒有列 opencode run 的參數，所以看 --help 有什麼就用什麼。"""
    try:
        p = subprocess.run([exe, "run", "--help"], capture_output=True, text=True, timeout=60)
        help_text = p.stdout + p.stderr
    except (OSError, subprocess.TimeoutExpired):
        help_text = ""
    args = []
    if "--model" in help_text:
        args += ["--model", f"local/{MODEL_ID}"]
    if "--format" in help_text:
        args += ["--format", "json"]
    return args + shlex.split(os.environ.get("OPENCODE_EXTRA_ARGS", ""))


def thermal_level():
    out = subprocess.run(["notifyutil", "-g", "com.apple.system.thermalpressurelevel"],
                         capture_output=True, text=True).stdout.split()
    return int(out[-1]) if out else 0


def wait_cool(seconds):
    time.sleep(seconds)
    waited = 0
    while thermal_level() >= 1:
        time.sleep(30); waited += 30
        if waited >= 1800:
            raise SystemExit("熱壓力 30 分鐘未回到 0，停止")


def git(work, *a):
    subprocess.run(["git", "-c", "user.name=bench", "-c", "user.email=bench@localhost", *a], cwd=work,
                   capture_output=True)


CURRENT = [None]


def run_one(name, a, rec, extra):
    work = f"{ROOT}/logs/opencode_work/{a.label}/{name}"
    shutil.rmtree(os.path.dirname(work) + f"/{name}.stdout", ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(f"{TASKS}/{name}/repo", work)
    write_config(work, a.proxy_port)
    git(work, "init", "-q"); git(work, "add", "-A"); git(work, "commit", "-q", "-m", "start")
    prompt = (open(f"{TASKS}/{name}/TASK.md").read() + "\nRun the tests with `python3 -m unittest discover -s tests -t .` "
              "and keep working until they pass. Edit only the code; do not change the tests.")
    cmd = [a.opencode, "run", *extra, prompt]
    out_path = f"{work}.stdout"
    rec.take()
    t0 = time.time()
    timed_out = False
    with open(out_path, "w") as out:
        # opencode 用 PWD 找專案設定，只設 cwd 會讀不到工作目錄的 opencode.json
        p = subprocess.Popen(cmd, cwd=work, env={**os.environ, "PWD": work}, stdin=subprocess.DEVNULL,
                             stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        CURRENT[0] = p
        try:
            rc = p.wait(timeout=a.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(p.pid, signal.SIGKILL)
            rc = p.wait()
        CURRENT[0] = None
    wall = time.time() - t0
    calls = rec.take()
    git(work, "add", "-A")
    changed = subprocess.run(["git", "diff", "--cached", "--name-only", "HEAD"], cwd=work, capture_output=True, text=True).stdout.split()
    changed = [f for f in changed if f != "opencode.json"]
    passed, n, bad, tail = grade(name, work)
    shutil.rmtree(f"{work}/.git", ignore_errors=True)  # 留著的話，外層 repo 會把工作目錄當成內嵌 repo，內容進不了 git
    agent = [c for c in calls if c.get("tools")]  # 沒帶工具的是 opencode 產生標題的請求，不算一輪
    waits = [c.get("first_byte_s") for c in agent if c.get("first_byte_s") is not None]
    totals = [c["total_s"] for c in agent]
    return {"label": a.label, "task": name, "pass": passed, "tests": n, "failed": bad, "wall_s": round(wall, 1),
            "exit": rc, "timed_out": timed_out, "turns": len(agent),
            "turns_with_tool_calls": sum(1 for c in agent if c.get("tool_calls")),
            "http_errors": sum(1 for c in calls if c.get("error") or (c.get("status") or 200) >= 400),
            "first_byte_s_max": max(waits, default=None), "turn_total_s_max": max(totals, default=None),
            "changed_files": changed, "test_tail": tail if not passed else "", "cmd_args": extra, "calls": calls}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--label")
    ap.add_argument("--tasks", default="", help="逗號分隔，預設全部")
    ap.add_argument("--timeout", type=int, default=1800, help="每題秒數上限")
    ap.add_argument("--pause", type=int, default=120, help="題目之間休息秒數，之後還要等熱壓力回到 0")
    ap.add_argument("--server-port", type=int, default=8080)
    ap.add_argument("--proxy-port", type=int, default=8081)
    ap.add_argument("--opencode", default="opencode")
    a = ap.parse_args()
    if a.validate:
        return validate()
    if not a.label:
        ap.error("需要 --label")

    def on_term(*_):
        if CURRENT[0] is not None:
            try:
                os.killpg(CURRENT[0].pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        sys.exit(143)
    signal.signal(signal.SIGTERM, on_term)

    rec = Recorder()
    Server, Handler = make_proxy("127.0.0.1", a.server_port, rec)
    proxy = Server(("127.0.0.1", a.proxy_port), Handler)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    names = a.tasks.split(",") if a.tasks else task_names()
    extra = opencode_args(a.opencode)
    os.makedirs(f"{ROOT}/logs/opencode_work/{a.label}", exist_ok=True)
    path = f"{ROOT}/logs/{a.label}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    passed = 0
    with open(path, "w") as f:
        for i, name in enumerate(names):
            if i:
                wait_cool(a.pause)
            r = run_one(name, a, rec, extra)
            passed += r["pass"]
            f.write(json.dumps(r, ensure_ascii=False) + "\n"); f.flush()
            print(f"{name}: {'PASS' if r['pass'] else 'FAIL'} | {r['tests']} tests, {r['failed']} bad | "
                  f"wall {r['wall_s']}s | turns {r['turns']} (tool {r['turns_with_tool_calls']}) | "
                  f"max wait {r['first_byte_s_max']}s | http errors {r['http_errors']}"
                  + (" | TIMEOUT" if r["timed_out"] else ""), flush=True)
    print(f"{a.label}: {passed}/{len(names)} passed | {path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
