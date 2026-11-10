#!/usr/bin/env python3
"""通用測速工具：用 OpenAI 相容的串流 API，從客戶端量首個 token 時間和生成速度，llama.cpp 和 MLX 用同一把尺。

每個提示跑兩次請求：
  cold     ：開頭加隨機編號，確保前綴快取沒有命中，首個 token 時間就是整段提示的處理時間
  followup ：接著同一段對話追加約 200 token 的工具輸出，看前綴快取能省多少（模擬代理的下一輪）

生成 token 數優先用伺服器回報的 usage，沒有就用收到的文字片段數。
ignore_eos 只有 llama.cpp 支援；MLX 可能提早結束，所以紀錄裡有 requested_n，生成數不足時 console 會標出來。
伺服器有回報 timings（llama.cpp）時一併記下，並印出和客戶端量測的差距，用來對帳。

用法：python3 -I scripts/stream_bench.py --url http://127.0.0.1:8080 --label air_20b_stream
"""
import argparse, json, os, secrets, signal, subprocess, sys, time, urllib.error, urllib.request

ROOT = os.environ.get("FLASHBACK_ROOT", "/Volumes/LLM SSD/Flashback")


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


def stream_chat(url, messages, n):
    payload = {"messages": messages, "max_tokens": n, "temperature": 0.0, "seed": 42, "stream": True,
               "stream_options": {"include_usage": True}, "cache_prompt": True, "ignore_eos": True}
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    first = last = None
    chunks = 0
    parts, usage, timings, finish = [], None, None, None
    with urllib.request.urlopen(req, timeout=7200) as r:
        for raw in r:
            if not raw.startswith(b"data:"):
                continue
            data = raw[5:].strip()
            if data == b"[DONE]":
                break
            obj = json.loads(data)
            now = time.perf_counter()
            usage = obj.get("usage") or usage
            timings = obj.get("timings") or timings
            for choice in obj.get("choices") or []:
                finish = choice.get("finish_reason") or finish
                delta = choice.get("delta") or {}
                text = (delta.get("content") or "") + (delta.get("reasoning_content") or "") + (delta.get("reasoning") or "")
                if text:
                    first = first if first is not None else now
                    last = now
                    chunks += 1
                    parts.append(text)
    end = time.perf_counter()
    gen = (usage or {}).get("completion_tokens") or chunks
    # gen_tps 假設每個 token 都會串流出來。harmony 開頭有 3 個不串流的頻道 token，
    # 所以 gpt-oss 在 n=96 時會比伺服器數字高約 3.3%；Qwen 沒有這段，不受影響。
    span = (last - first) if first is not None and last is not None else 0
    return {"ttft_s": round(first - t0, 3) if first is not None else None, "total_s": round(end - t0, 3),
            "gen_tokens": gen, "chunks": chunks, "gen_tps": round((gen - 1) / span, 2) if span > 0 and gen > 1 else None,
            "prompt_tokens": (usage or {}).get("prompt_tokens") or (timings or {}).get("prompt_n"),
            "finish_reason": finish, "usage": usage, "timings": timings, "text": "".join(parts)}


def describe(name, r):
    line = (f"{name}: prompt {r['prompt_tokens']} | 首 token {r['ttft_s']}s | 生成 {r['gen_tokens']} @ {r['gen_tps']} t/s"
            f" | 總 {r['total_s']}s")
    t = r.get("timings")
    if t and r["gen_tps"]:
        server = t.get("predicted_per_second") or 0
        gap = (r["gen_tps"] / server - 1) * 100 if server else 0
        line += f" | 伺服器 prompt {t.get('prompt_ms', 0) / 1000:.2f}s、{server:.2f} t/s（客戶端差 {gap:+.1f}%）"
    return line


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--label", required=True)
    ap.add_argument("--n", type=int, default=96)
    ap.add_argument("--prompts", default="code.txt,spec_rewrite.txt,agent_turn1.txt,agent_long.txt", help="prompts/ 底下的檔案")
    ap.add_argument("--pause", type=int, default=60, help="請求之間休息秒數，之後還要等熱壓力回到 0")
    a = ap.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    add = open(f"{ROOT}/prompts/agent_turn2_add.txt").read()
    path = f"{ROOT}/logs/{a.label}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    first_request = True
    with open(path, "w") as f:
        for name in a.prompts.split(","):
            user = f"Request id: {secrets.token_hex(8)}\n\n" + open(f"{ROOT}/prompts/{name}").read()
            messages = [{"role": "user", "content": user}]
            for phase in ("cold", "followup"):
                if not first_request:
                    rest(a.pause)
                first_request = False
                rec = {"label": a.label, "prompt": name, "phase": phase}
                try:
                    r = stream_chat(a.url, messages, a.n)
                except (urllib.error.URLError, OSError, ValueError) as e:
                    body = e.read().decode("utf-8", "replace")[:300] if isinstance(e, urllib.error.HTTPError) else ""
                    rec["error"] = f"{e!r} {body}"
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
                    print(f"{name} {phase}: 失敗 {rec['error']}", flush=True)
                    break
                rec.update(r)
                rec["requested_n"] = a.n
                f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
                short = f"（少於要求的 {a.n}，finish={r['finish_reason']}）" if (r["gen_tokens"] or 0) < a.n else ""
                print(describe(f"{name} {phase}", r) + short, flush=True)
                messages = messages + [{"role": "assistant", "content": r["text"]}, {"role": "user", "content": add}]
    print(f"{a.label}: 完成 | {path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
