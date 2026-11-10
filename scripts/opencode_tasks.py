#!/usr/bin/env python3
"""第 5 項：用 opencode 跑 tasks/ 底下的多檔案題目，判定對錯並記錄每輪等待時間。

opencode 和推論伺服器之間放一個本機記錄代理（預設 8081 → 8080），每個請求記錄首個位元組時間、總時間、
訊息數、工具定義數、是否回傳 tool_calls。這樣就不依賴 opencode 的輸出格式，官方文件沒有列出那個格式。

判定：opencode 結束後，把 tests/ 換回原始版本並加上 hidden/ 的測試再執行，模型改測試或寫死答案都騙不過。
每題用 --timeout 限時。opencode 在 repo 外的暫存目錄執行（OPENCODE_WORK，預設系統暫存目錄下的 flashback_opencode_work），
bash 是全部允許加黑名單，放在 repo 外，模型下錯指令（例如 git clean）也碰不到還沒 commit 的紀錄。
每題結束後把工作目錄和原始輸出複製回 logs/opencode_work/<label>/<題目>/，摘要寫到 logs/<label>_<時間>.jsonl。

用法：
  python3 -I scripts/opencode_tasks.py --validate       驗證題目：原始狀態要失敗，套上參考解答要全過（不需要模型）
  python3 -I scripts/opencode_tasks.py --label mini_oc_qwen
環境變數 OPENCODE_EXTRA_ARGS 可追加 opencode run 的參數。
"""
import argparse, http.client, http.server, json, os, re, shlex, shutil, signal, socketserver, subprocess, sys, tempfile, threading, time

ROOT = os.environ.get("FLASHBACK_ROOT", "/Volumes/LLM SSD/Flashback")
TASKS = f"{ROOT}/tasks"
# 用系統暫存目錄（路徑不含帳號名稱），不放在 repo 裡
WORK_BASE = os.environ.get("OPENCODE_WORK") or os.path.join(tempfile.gettempdir(), "flashback_opencode_work")
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

    def tool_turns(self):
        with self.lock:
            return sum(1 for r in self.rows if r.get("tools") and r.get("tool_calls"))


def summarize_body(body):
    text = body.decode("utf-8", "replace")
    info = {"tool_calls": '"tool_calls"' in text and not re.search(r'"tool_calls":\s*(null|\[\])', text)}
    finish = re.findall(r'"finish_reason":\s*"(\w+)"', text)
    info["finish_reason"] = finish[-1] if finish else None
    # 解析串流內容：伺服器沒解析出工具呼叫時，標記會留在文字裡（Qwen 的 <tool_call>、<function=...>）
    content, names = [], []
    for line in text.splitlines():
        if not line.startswith("data:") or line[5:].strip() == "[DONE]":
            continue
        try:
            obj = json.loads(line[5:])
        except ValueError:
            continue
        for choice in obj.get("choices") or []:
            delta = choice.get("delta") or {}
            content.append(delta.get("content") or "")
            names += [c["function"]["name"] for c in delta.get("tool_calls") or [] if (c.get("function") or {}).get("name")]
    joined = "".join(content)
    info["tool_names"] = names
    info["raw_tool_markup"] = bool(re.search(r"<tool_call>|</tool_call>|<function=|</function>", joined))
    for key in ("timings", "usage"):
        for m in re.finditer(rf'"{key}":\s*(\{{.*?\}})', text):
            try:
                info[key] = json.loads(m.group(1))
            except ValueError:
                pass
    return info


def make_proxy(target_host, target_port, rec, keep_body=False):
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
                           request_bytes=length, stream=bool(req.get("stream")),
                           temperature=req.get("temperature"), seed=req.get("seed"))
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
                    # llama-server 處理提示詞時會送 SSE 心跳（只有 ":"），要等到第一筆 data: 才算模型開始回應
                    if first is None and (b"data:" in chunk or not row.get("stream")):
                        first = time.time()
                    seen += chunk
                    self.wfile.write(b"%x\r\n" % len(chunk) + chunk + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                row["first_byte_s"] = round(first - t0, 3) if first else None
                row.update(summarize_body(bytes(seen)))
                if keep_body:
                    row["body_head"] = bytes(seen[:20000]).decode("utf-8", "replace")
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


NO_CODE_MODE = [False]  # 有 --standalone 表示 opencode 2.x，要關掉 Code Mode


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
    if NO_CODE_MODE[0]:
        # 2.x 的系統提示會叫模型透過 execute 呼叫工具，但 execute 沙盒裡沒有 shell，模型因此跑不了測試
        cfg["permission"]["execute"] = "deny"
    json.dump(cfg, open(f"{work}/opencode.json", "w"), indent=2)


def opencode_args(exe):
    """官方文件沒有列 opencode run 的參數，所以看 --help 有什麼就用什麼。"""
    try:
        p = subprocess.run([exe, "run", "--help"], capture_output=True, text=True, timeout=60)
        help_text = p.stdout + p.stderr
    except (OSError, subprocess.TimeoutExpired):
        help_text = ""
    args = []
    # 2.x 預設交給背景服務執行，逾時只殺得到前端，模型會繼續佔用伺服器；有這個參數就用私有 server
    if "--standalone" in help_text:
        args += ["--standalone"]
    if "--model" in help_text:
        args += ["--model", f"local/{MODEL_ID}"]
    if "--format" in help_text:
        args += ["--format", "json"]
    return args + shlex.split(os.environ.get("OPENCODE_EXTRA_ARGS", ""))


def thermal_level():
    """讀不到或讀到非數字時回傳 1：看不到熱壓力就當作不安全，呼叫端會等待，等太久就停止。"""
    try:
        out = subprocess.run(["notifyutil", "-g", "com.apple.system.thermalpressurelevel"],
                             capture_output=True, text=True, timeout=10).stdout.split()
        return int(out[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return 1


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


def count_tools(path):
    """從 opencode 的輸出統計工具結果，例如 {'read:completed': 2}。"""
    out = {}
    for line in open(path, errors="replace"):
        try:
            part = json.loads(line).get("part") or {}
        except ValueError:
            continue
        if part.get("tool"):
            key = f"{part['tool']}:{(part.get('state') or {}).get('status')}"
            out[key] = out.get(key, 0) + 1
    return out


def run_one(name, a, rec, extra, rep=1):
    # 每題只跑一次時沿用舊路徑
    sub = f"{a.label}/{name}" + (f"_r{rep}" if a.repeats > 1 else "")
    work = f"{WORK_BASE}/{sub}"
    keep = f"{ROOT}/logs/opencode_work/{sub}"  # 結束後複製回這裡，和以前的路徑相同
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
    timed_out = stopped = False
    with open(out_path, "w") as out:
        # opencode 用 PWD 找專案設定，只設 cwd 會讀不到工作目錄的 opencode.json
        p = subprocess.Popen(cmd, cwd=work, env={**os.environ, "PWD": work}, stdin=subprocess.DEVNULL,
                             stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        CURRENT[0] = p
        deadline = t0 + a.timeout
        stop_at = None  # 只驗格式時，達到輪數後再等幾秒，讓 opencode 寫完工具結果
        while True:
            try:
                rc = p.wait(timeout=2)
                break
            except subprocess.TimeoutExpired:
                now = time.time()
                if a.stop_after_tool_turns and stop_at is None and rec.tool_turns() >= a.stop_after_tool_turns:
                    stop_at = now + 5
                if (stop_at is not None and now >= stop_at) or now >= deadline:
                    stopped, timed_out = stop_at is not None and now >= stop_at, stop_at is None
                    os.killpg(p.pid, signal.SIGKILL)
                    rc = p.wait()
                    break
        CURRENT[0] = None
    wall = time.time() - t0
    calls = rec.take()
    git(work, "add", "-A")
    changed = subprocess.run(["git", "diff", "--cached", "--name-only", "HEAD"], cwd=work, capture_output=True, text=True).stdout.split()
    changed = [f for f in changed if f != "opencode.json"]
    # 只驗格式時題目沒做完，判對錯沒有意義
    passed, n, bad, tail = (None, 0, 0, "") if a.stop_after_tool_turns else grade(name, work)
    shutil.rmtree(f"{work}/.git", ignore_errors=True)  # 留著的話，外層 repo 會把工作目錄當成內嵌 repo，內容進不了 git
    shutil.rmtree(keep, ignore_errors=True)
    shutil.copytree(work, keep, symlinks=True)
    shutil.copy2(out_path, f"{keep}.stdout")
    agent = [c for c in calls if c.get("tools")]  # 沒帶工具的是 opencode 產生標題的請求，不算一輪
    waits = [c.get("first_byte_s") for c in agent if c.get("first_byte_s") is not None]
    totals = [c["total_s"] for c in agent]
    timing = [c.get("timings") or {} for c in agent]
    gen_n = sum(t.get("predicted_n") or 0 for t in timing)
    gen_ms = sum(t.get("predicted_ms") or 0 for t in timing)
    tools = count_tools(out_path)
    http_errors = sum(1 for c in calls if c.get("error") or (c.get("status") or 200) >= 400)
    # 工具本身沒跑起來時，測試結果不代表模型的能力，要和「模型沒寫對」分開。逾時是模型太慢，不算工具失敗
    tool_failure = []
    if not timed_out and not stopped:
        if not agent:
            tool_failure.append("沒有任何代理請求")
        if rc != 0:
            tool_failure.append(f"opencode exit={rc}")
        if any(c.get("tool_calls") for c in agent) and not tools:
            tool_failure.append("模型有呼叫工具，但 opencode 的輸出解析不到工具結果")
    if http_errors:
        tool_failure.append(f"HTTP 錯誤 {http_errors} 次")
    stdout_tail = open(out_path, errors="replace").read()[-600:] if tool_failure else ""
    return {"label": a.label, "task": name, "repeat": rep, "pass": passed, "tests": n, "failed": bad, "wall_s": round(wall, 1),
            "exit": rc, "timed_out": timed_out, "stopped_after_tool_turns": stopped, "turns": len(agent),
            "turns_with_tool_calls": sum(1 for c in agent if c.get("tool_calls")),
            "turns_with_raw_tool_markup": sum(1 for c in agent if c.get("raw_tool_markup")),
            "tool_names": [n for c in agent for n in c.get("tool_names", [])], "tool_results": tools,
            "http_errors": http_errors, "tool_failure": tool_failure, "stdout_tail": stdout_tail,
            "first_byte_s_max": max(waits, default=None), "turn_total_s_max": max(totals, default=None),
            "gen_tokens": gen_n, "gen_ms": round(gen_ms, 1), "gen_tps": round(gen_n / gen_ms * 1000, 2) if gen_ms else None,
            "draft_n": sum(t.get("draft_n") or 0 for t in timing),
            "draft_accepted": sum(t.get("draft_n_accepted") or 0 for t in timing),
            "changed_files": changed, "test_tail": tail if passed is False else "", "cmd_args": extra, "calls": calls}


def summarize(label, name, runs):
    walls = [r["wall_s"] for r in runs]
    turns = [r["turns"] for r in runs]
    tps = [r["gen_tps"] for r in runs if r["gen_tps"]]
    passes = sum(1 for r in runs if r["pass"])
    return {"label": label, "kind": "summary", "task": name, "runs": len(runs), "passes": passes,
            "pass_rate": round(passes / len(runs), 3), "results": [r["pass"] for r in runs],
            "failed_tests": [r["failed"] for r in runs], "timed_out": sum(r["timed_out"] for r in runs),
            "tool_failures": sum(1 for r in runs if r["tool_failure"]),
            "wall_s": walls, "wall_s_mean": round(sum(walls) / len(walls), 1), "turns": turns,
            "gen_tps": tps, "first_byte_s_max": max((r["first_byte_s_max"] or 0 for r in runs), default=None)}


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
    ap.add_argument("--repeats", type=int, default=1, help="每題跑幾次；依序把所有題目跑完一輪再跑下一輪")
    ap.add_argument("--stop-after-tool-turns", type=int, default=0,
                    help="只驗工具呼叫格式：達到這個輪數就停止，不判對錯；保留回應內容")
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
    Server, Handler = make_proxy("127.0.0.1", a.server_port, rec, keep_body=bool(a.stop_after_tool_turns))
    proxy = Server(("127.0.0.1", a.proxy_port), Handler)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    names = a.tasks.split(",") if a.tasks else task_names()
    extra = opencode_args(a.opencode)
    NO_CODE_MODE[0] = "--standalone" in extra
    os.makedirs(f"{ROOT}/logs/opencode_work/{a.label}", exist_ok=True)
    os.makedirs(f"{WORK_BASE}/{a.label}", exist_ok=True)
    path = f"{ROOT}/logs/{a.label}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    runs = {n: [] for n in names}
    format_bad = 0
    with open(path, "w") as f:
        first = True
        for rep in range(1, a.repeats + 1):  # 一輪一輪跑：中途停掉時，每題的次數仍然平均
            for name in names:
                if not first:
                    wait_cool(a.pause)
                first = False
                r = run_one(name, a, rec, extra, rep)
                runs[name].append(r)
                f.write(json.dumps(r, ensure_ascii=False) + "\n"); f.flush()
                tag = f"#{rep} " if a.repeats > 1 else ""
                if a.stop_after_tool_turns:
                    ok = r["turns_with_tool_calls"] >= a.stop_after_tool_turns and not r["turns_with_raw_tool_markup"] and r["tool_results"]
                    format_bad += not ok
                    print(f"{name}: 工具呼叫格式 {'OK' if ok else 'NG'} | wall {r['wall_s']}s | turns {r['turns']} "
                          f"(tool {r['turns_with_tool_calls']}，文字殘留標記 {r['turns_with_raw_tool_markup']}) | "
                          f"工具 {r['tool_names']} | 結果 {r['tool_results']} | max wait {r['first_byte_s_max']}s"
                          + (" | TIMEOUT" if r["timed_out"] else ""), flush=True)
                    continue
                print(f"{name} {tag}: {'PASS' if r['pass'] else 'FAIL'} | {r['tests']} tests, {r['failed']} bad | "
                      f"wall {r['wall_s']}s | turns {r['turns']} (tool {r['turns_with_tool_calls']}) | "
                      f"max wait {r['first_byte_s_max']}s | {r['gen_tps']} t/s | draft {r['draft_accepted']}/{r['draft_n']} | "
                      f"http errors {r['http_errors']}" + (" | TIMEOUT" if r["timed_out"] else "")
                      + (f" | 工具失敗：{'、'.join(r['tool_failure'])}" if r["tool_failure"] else ""), flush=True)
        if a.stop_after_tool_turns:
            print(f"{a.label}: 工具呼叫格式 {'OK' if not format_bad else 'NG'} | {path}", flush=True)
            return 1 if format_bad else 0
        for name in names:
            s = summarize(a.label, name, runs[name])
            f.write(json.dumps(s, ensure_ascii=False) + "\n"); f.flush()
            print(f"{name}: 通過 {s['passes']}/{s['runs']} | 結果 {s['results']} | wall 平均 {s['wall_s_mean']}s "
                  f"{s['wall_s']} | 輪數 {s['turns']} | t/s {s['gen_tps']}", flush=True)
    total = sum(len(v) for v in runs.values())
    passed = sum(1 for v in runs.values() for r in v if r["pass"])
    tool_bad = sum(1 for v in runs.values() for r in v if r["tool_failure"])
    print(f"{a.label}: {passed}/{total} passed | 工具失敗 {tool_bad} 次 | {path}", flush=True)
    return 2 if tool_bad else 0


if __name__ == "__main__":
    sys.exit(main())
