#!/usr/bin/env python3
"""Flashback 代理負載量測：模擬 opencode 寫程式代理的多輪對話。

第 1 輪：約 2,945 token 的長提示詞（系統規則 + 工具定義 + 讀檔結果 + 任務）
第 2、3 輪：在同一段對話後面追加工具輸出（約 206 / 323 token），開啟前綴快取，
            只需處理新增的部分。每輪都產生 --n 個 token。

用法：python3 -I scripts/agent_bench.py --label agent_ub512 --n 64 [--erase]
"""
import argparse, json, os, signal, subprocess, sys, threading, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import ROOT, ssd_whole_disk, disk_read_stats, vm_pageins, post  # noqa: E402

TURNS = [("t1_long", "agent_turn1.txt"), ("t2_followup", "agent_turn2_add.txt"),
         ("t3_followup", "agent_turn3_add.txt")]


def harmony(user_text):
    return f"<|start|>user<|message|>{user_text}<|end|><|start|>assistant"


def chatml(user_text):  # 第 7 項：Qwen3-Coder 的對話格式
    return f"<|im_start|>user\n{user_text}<|im_end|>\n<|im_start|>assistant\n"


def thermal_level():
    out = subprocess.run(["notifyutil", "-g", "com.apple.system.thermalpressurelevel"],
                         capture_output=True, text=True).stdout.split()
    return int(out[-1]) if out else 0


def rest(seconds):
    print(f"  rest {seconds}s", flush=True)
    time.sleep(seconds)
    waited = 0
    while thermal_level() >= 1:
        time.sleep(30); waited += 30
        if waited >= 1800:
            raise SystemExit("熱壓力 30 分鐘未回到 0，停止")


class DiskSampler(threading.Thread):
    """每秒記錄硬碟累計位元組，用來把生成階段和提示詞階段的讀取量分開。"""

    def __init__(self, disk):
        super().__init__(daemon=True)
        self.disk, self.samples, self.done = disk, [], threading.Event()

    def run(self):
        while not self.done.wait(1.0):
            try:
                self.samples.append((time.time(), disk_read_stats(self.disk)[0]))
            except (OSError, ValueError, IndexError):
                pass


def bytes_at(samples, t):
    """線性內插 t 時的累計位元組。"""
    prev = samples[0]
    for cur in samples:
        if cur[0] >= t:
            if cur[0] == prev[0]:
                return cur[1]
            return prev[1] + (cur[1] - prev[1]) * (t - prev[0]) / (cur[0] - prev[0])
        prev = cur
    return samples[-1][1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--label", required=True)
    ap.add_argument("--n", type=int, default=64)
    ap.add_argument("--turns", default="t1_long,t2_followup,t3_followup")
    ap.add_argument("--t1", default="agent_turn1.txt", help="第 1 輪提示詞檔（prompts/ 底下），例如 agent_long.txt")
    ap.add_argument("--fmt", default="harmony", choices=["harmony", "chatml"])
    ap.add_argument("--erase", action="store_true", help="開始前清掉伺服器的前綴快取（KV）")
    ap.add_argument("--pause", type=int, default=0,
                    help="每輪之間休息的秒數；休息後還要等熱壓力回到 0 才繼續（前綴快取會保留）")
    args = ap.parse_args()

    # 被熱保護 pkill（SIGTERM）時也要跑 finally，否則背景 iostat／vm_stat 會變成孤兒程序
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))

    if args.erase:
        try:
            post(args.url + "/slots/0?action=erase", {})
        except Exception as e:  # 舊版或停用 slots 時忽略
            print("erase 失敗（忽略）:", e)

    disk = ssd_whole_disk()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base = f"{ROOT}/logs/{args.label}_{stamp}"
    bg = [subprocess.Popen(["iostat", "-d", "-w", "1", disk], stdout=open(base + "_iostat.log", "w")),
          subprocess.Popen(["vm_stat", "1"], stdout=open(base + "_vmstat.log", "w")),
          subprocess.Popen(["/bin/sh", "-c", "while true; do date '+%T'; pmset -g therm | grep -v '^$'; "
                            "memory_pressure | tail -1; sleep 10; done"],
                           stdout=open(base + "_therm.log", "w"))]
    print(f"SSD = {disk}, log = {base}.jsonl", flush=True)
    wanted = args.turns.split(",")
    convo = ""
    first = True
    try:
        with open(base + ".jsonl", "w") as f:
            for name, fn in TURNS:
                if name == "t1_long":
                    fn = args.t1
                convo += open(f"{ROOT}/prompts/{fn}").read()
                if name not in wanted:
                    continue
                if not first and args.pause:
                    rest(args.pause)
                first = False
                payload = {"prompt": (chatml if args.fmt == "chatml" else harmony)(convo), "n_predict": args.n, "ignore_eos": True,
                           "cache_prompt": True, "temperature": 0.0, "seed": 42}
                d0, v0, t0 = disk_read_stats(disk), vm_pageins(), time.time()
                sampler = DiskSampler(disk)
                sampler.start()
                try:
                    r = post(args.url + "/completion", payload)
                finally:
                    sampler.done.set()
                d1, v1, t1 = disk_read_stats(disk), vm_pageins(), time.time()
                sampler.join(5)
                t = r["timings"]
                samples = [(t0, d0[0])] + sampler.samples + [(t1, d1[0])]
                gen_bytes = max(0, d1[0] - bytes_at(samples, t1 - t["predicted_ms"] / 1000))
                rec = {"label": args.label, "turn": name, "t1_file": args.t1, "start": time.strftime("%T", time.localtime(t0)),
                       "wall_s": round(t1 - t0, 2),
                       "prompt_total_tokens": r.get("tokens_evaluated"),
                       "prompt_cached": t.get("cache_n"), "prompt_n": t["prompt_n"],
                       "prompt_ms": t["prompt_ms"], "prompt_tps": t["prompt_per_second"],
                       "gen_n": t["predicted_n"], "gen_ms": t["predicted_ms"],
                       "gen_tps": t["predicted_per_second"],
                       "ssd_read_MB": round((d1[0] - d0[0]) / 1e6, 1), "ssd_read_ops": d1[1] - d0[1],
                       "pageins": v1["pageins"] - v0["pageins"],
                       "swapouts": v1["swapouts"] - v0["swapouts"], "text": r.get("content", "")}
                rec["avg_read_KB"] = round(rec["ssd_read_MB"] * 1000 / max(rec["ssd_read_ops"], 1), 1)
                rec["ssd_read_gen_MB"] = round(gen_bytes / 1e6, 1)
                rec["ssd_MB_per_gen_token"] = round(gen_bytes / 1e6 / max(t["predicted_n"], 1), 1)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
                print(f"{name:12s} prompt {rec['prompt_n']} new (+{rec['prompt_cached']} cached) "
                      f"in {rec['prompt_ms']/1000:.0f}s | gen {rec['gen_n']} @ {rec['gen_tps']:.2f} t/s | "
                      f"SSD {rec['ssd_read_MB']} MB ({rec['avg_read_KB']} KB/op)，生成 {rec['ssd_MB_per_gen_token']} MB/token | wall {rec['wall_s']}s "
                      f"| swapouts {rec['swapouts']}", flush=True)
    finally:
        for p in bg:
            p.terminate()


if __name__ == "__main__":
    main()
