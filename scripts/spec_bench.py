#!/usr/bin/env python3
"""第 3／6 項：推測解碼量測。讓模型「改兩個預設值並輸出整個檔案」——輸出大多是照抄輸入，
推測解碼（n-gram、EAGLE3、草稿模型）在這種情況下最有機會加速。
直接預填 harmony 的 final 頻道和 ```python 開頭，跳過推理段，讓輸出就是程式碼。

用法：python3 -I scripts/spec_bench.py --label spec_none --n 160
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import ROOT, ssd_whole_disk, disk_read_stats, vm_pageins, post  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:8080")
ap.add_argument("--label", required=True)
ap.add_argument("--n", type=int, default=160)
ap.add_argument("--fmt", default="harmony", choices=["harmony", "chatml"], help="第 7 項：Qwen 用 chatml")
a = ap.parse_args()
user = open(f"{ROOT}/prompts/spec_rewrite.txt").read()
if a.fmt == "chatml":
    prompt = f"<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n```python\n"
else:
    prompt = (f"<|start|>user<|message|>{user}<|end|>"
              f"<|start|>assistant<|channel|>final<|message|>```python\n")
disk = ssd_whole_disk()
d0, v0, t0 = disk_read_stats(disk), vm_pageins(), time.time()
r = post(a.url + "/completion", {"prompt": prompt, "n_predict": a.n, "ignore_eos": True,
                                  "cache_prompt": True, "temperature": 0.0, "seed": 42})
d1, v1, t1 = disk_read_stats(disk), vm_pageins(), time.time()
t = r["timings"]
rec = {"label": a.label, "start": time.strftime("%T", time.localtime(t0)), "wall_s": round(t1 - t0, 1),
       "prompt_n": t["prompt_n"], "prompt_ms": t["prompt_ms"], "gen_n": t["predicted_n"],
       "gen_ms": t["predicted_ms"], "gen_tps": t["predicted_per_second"],
       "draft_n": t.get("draft_n"), "draft_accepted": t.get("draft_n_accepted"),
       "ssd_read_MB": round((d1[0] - d0[0]) / 1e6, 1), "ssd_read_ops": d1[1] - d0[1],
       "swapouts": v1["swapouts"] - v0["swapouts"], "timings": t, "text": r.get("content", "")}
gen_frac = t["predicted_ms"] / max(t["prompt_ms"] + t["predicted_ms"], 1)
rec["gen_MB_per_token_est"] = round(rec["ssd_read_MB"] * gen_frac / max(rec["gen_n"], 1), 1)
out = f"{ROOT}/logs/{a.label}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
open(out, "w").write(json.dumps(rec, ensure_ascii=False) + "\n")
print(f"{a.label}: prompt {rec['prompt_n']} in {rec['prompt_ms']/1000:.0f}s | gen {rec['gen_n']} @ "
      f"{rec['gen_tps']:.3f} t/s | draft {rec['draft_n']} acc {rec['draft_accepted']} | "
      f"SSD {rec['ssd_read_MB']} MB | swapouts {rec['swapouts']} | {out}", flush=True)
