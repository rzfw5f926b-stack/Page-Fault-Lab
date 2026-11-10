#!/usr/bin/env python3
"""Ollama 對照組：和 stream_bench.py 同樣的提示詞、生成長度和 num_ctx，改走 Ollama 的 /api/chat。

用來比較 Ollama 和 llama-server 的差距。每次請求在生成途中記錄 `ollama ps`（PROCESSOR、CONTEXT、RUNNER），
開頭記下 Ollama 版本和模型資訊。Ollama 沒有 ignore_eos，所以模型提早結束時要看 done_reason 和 gen_tokens。

開始前 `ollama ps` 必須是空的，否則離開（結束碼 3）；結束時只把自己載入的模型卸載（keep_alive=0）。
不會刪除模型，也不會動 OLLAMA_MODELS。

用法：python3 -I scripts/ollama_bench.py --label mini_20b_ollama --model gpt-oss:latest --num-ctx 8192
"""
import argparse, json, os, re, secrets, signal, subprocess, sys, threading, time, urllib.error, urllib.request

ROOT = os.environ.get("FLASHBACK_ROOT", "/Volumes/LLM SSD/Flashback")
KEEP_ALIVE = "30m"


def thermal_level():
    """讀不到或讀到非數字時回傳 1：看不到熱壓力就當作不安全，呼叫端會等待，等太久就停止。"""
    try:
        out = subprocess.run(["notifyutil", "-g", "com.apple.system.thermalpressurelevel"],
                             capture_output=True, text=True, timeout=10).stdout.split()
        return int(out[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return 1


def rest(seconds):
    time.sleep(seconds)
    waited = 0
    while thermal_level() >= 1:
        time.sleep(30); waited += 30
        if waited >= 1800:
            raise SystemExit("熱壓力 30 分鐘未回到 0，停止")


def post_json(url, payload, timeout=1800):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def ollama_ps():
    """解析 `ollama ps`。用表頭的欄位位置切，某一欄空白時才不會錯位。"""
    out = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=30).stdout
    lines = [l for l in out.splitlines() if l.strip()]
    if not lines:
        return []
    starts = [m.start() for m in re.finditer(r"\S+", lines[0])]
    names = lines[0].split()
    ends = starts[1:] + [None]
    return [{n: l[s:e].strip() for n, s, e in zip(names, starts, ends)} for l in lines[1:]]


def stream_chat(url, model, messages, n, num_ctx):
    payload = {"model": model, "messages": messages, "stream": True, "keep_alive": KEEP_ALIVE,
               "options": {"num_ctx": num_ctx, "num_predict": n, "temperature": 0.0, "seed": 42}}
    req = urllib.request.Request(url + "/api/chat", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    first = last = None
    chunks = 0
    parts, final, sample = [], None, []
    sampler = None
    with urllib.request.urlopen(req, timeout=7200) as r:
        for raw in r:
            if not raw.strip():
                continue
            obj = json.loads(raw)
            if obj.get("error"):
                raise ValueError(obj["error"])
            now = time.perf_counter()
            msg = obj.get("message") or {}
            text = (msg.get("thinking") or "") + (msg.get("content") or "")
            if text:
                first = first if first is not None else now
                last = now
                chunks += 1
                parts.append(text)
                if sampler is None:  # 放在另一個執行緒，不拖慢串流的讀取
                    sampler = threading.Thread(target=lambda: sample.extend(ollama_ps()), daemon=True)
                    sampler.start()
            if obj.get("done"):
                final = obj
    end = time.perf_counter()
    if sampler is not None:
        sampler.join(30)
    e = final or {}
    gen = e.get("eval_count") or chunks
    span = (last - first) if first is not None and last is not None else 0
    eval_ns, prompt_ns = e.get("eval_duration") or 0, e.get("prompt_eval_duration") or 0
    prompt_n = e.get("prompt_eval_count")
    return {"ttft_s": round(first - t0, 3) if first is not None else None, "total_s": round(end - t0, 3),
            "gen_tokens": gen, "chunks": chunks, "gen_tps": round((gen - 1) / span, 2) if span > 0 and gen > 1 else None,
            "server_gen_tps": round(gen / eval_ns * 1e9, 2) if eval_ns else None,
            "prompt_tokens": prompt_n, "server_prompt_ms": round(prompt_ns / 1e6, 1),
            "server_prompt_tps": round(prompt_n / prompt_ns * 1e9, 1) if prompt_ns and prompt_n else None,
            "load_ms": round((e.get("load_duration") or 0) / 1e6, 1), "done_reason": e.get("done_reason"),
            "ps": sample, "text": "".join(parts)}


def describe(name, r, num_ctx):
    p = r["ps"][0] if r["ps"] else {}
    ctx = p.get("CONTEXT", "（無此欄）")
    warn = "" if ctx == str(num_ctx) else f" ⚠ CONTEXT 不是 {num_ctx}"
    return (f"{name}: prompt {r['prompt_tokens']} | 首 token {r['ttft_s']}s | 生成 {r['gen_tokens']} @ {r['gen_tps']} t/s"
            f" | 總 {r['total_s']}s | 伺服器 prompt {r['server_prompt_ms'] / 1000:.2f}s、{r['server_gen_tps']} t/s"
            f" | {r['done_reason']} | PROCESSOR={p.get('PROCESSOR', '（無此欄）')} CONTEXT={ctx}"
            f" RUNNER={p.get('RUNNER', '（無此欄）')}{warn}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="gpt-oss:latest")
    ap.add_argument("--label", required=True)
    ap.add_argument("--n", type=int, default=96)
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--prompts", default="code.txt,spec_rewrite.txt,agent_turn1.txt,agent_long.txt")
    ap.add_argument("--settle", type=int, default=300, help="模型載入後、開始量測前的冷卻秒數")
    ap.add_argument("--pause", type=int, default=60, help="請求之間休息秒數，之後還要等熱壓力回到 0")
    a = ap.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))

    before = ollama_ps()
    if before:
        print(f"{a.label}: 不開始，ollama ps 不是空的：{[p.get('NAME') for p in before]}", flush=True)
        return 3
    add = open(f"{ROOT}/prompts/agent_turn2_add.txt").read()
    path = f"{ROOT}/logs/{a.label}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    cli = subprocess.run(["ollama", "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    with urllib.request.urlopen(a.url + "/api/version", timeout=30) as r:
        api = json.loads(r.read().decode()).get("version")
    show = post_json(a.url + "/api/show", {"model": a.model})
    print(f"Ollama：{cli}（API {api}）| {a.model} {show.get('details')}", flush=True)

    errors = other = 0
    try:
        t = time.time()
        post_json(a.url + "/api/generate", {"model": a.model, "keep_alive": KEEP_ALIVE, "options": {"num_ctx": a.num_ctx}})
        loaded = ollama_ps()
        print(f"載入 {time.time() - t:.1f}s | ollama ps：{loaded}", flush=True)
        with open(path, "w") as f:
            f.write(json.dumps({"label": a.label, "kind": "meta", "ollama_cli": cli, "ollama_api": api, "model": a.model,
                                "num_ctx": a.num_ctx, "num_predict": a.n, "details": show.get("details"),
                                "capabilities": show.get("capabilities"), "parameters": show.get("parameters"),
                                "ps_after_load": loaded}, ensure_ascii=False) + "\n"); f.flush()
            rest(a.settle)
            first_request = True
            for name in a.prompts.split(","):
                user = f"Request id: {secrets.token_hex(8)}\n\n" + open(f"{ROOT}/prompts/{name}").read()
                messages = [{"role": "user", "content": user}]
                for phase in ("cold", "followup"):
                    if not first_request:
                        rest(a.pause)
                    first_request = False
                    rec = {"label": a.label, "prompt": name, "phase": phase}
                    try:
                        r = stream_chat(a.url, a.model, messages, a.n, a.num_ctx)
                    except (urllib.error.URLError, OSError, ValueError) as e:
                        body = e.read().decode("utf-8", "replace")[:300] if isinstance(e, urllib.error.HTTPError) else ""
                        rec["error"] = f"{e!r} {body}"
                        errors += 1
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
                        print(f"{name} {phase}: 失敗 {rec['error']}", flush=True)
                        break
                    rec.update(r)
                    # 這台機器共用，生成途中出現別的模型就標記，這筆的記憶體和速度都不乾淨
                    rec["other_models"] = [p.get("NAME") for p in r["ps"] if p.get("NAME") != a.model]
                    other += bool(rec["other_models"])
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
                    print(describe(f"{name} {phase}", r, a.num_ctx), flush=True)
                    messages = messages + [{"role": "assistant", "content": r["text"]}, {"role": "user", "content": add}]
    finally:
        try:
            post_json(a.url + "/api/generate", {"model": a.model, "keep_alive": 0}, timeout=60)
        except (urllib.error.URLError, OSError, ValueError) as e:
            print(f"卸載失敗：{e!r}", flush=True)
    print(f"{a.label}: 完成 | 失敗 {errors} | 有其他模型的請求 {other} | {path}", flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
