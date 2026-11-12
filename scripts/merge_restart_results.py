#!/usr/bin/env python3
"""把 RESTART_EACH=1（每題之前重啟 server）拆開的結果檔合併成一份，給 codex_exp_report.py 轉檔。

run_codex_exp.sh 每題每輪各呼叫一次 accept.sh（K=1），結果檔是
  <exp>/accept_results_k1_llama_<model>_<TAG>_r<輪>t<題>.txt
紀錄在各自的 <exp>/llama_logs/<同名>/t<題>/r1/。這支：
  1. 依輪、題排序，取每個檔 "== r1 tN" 到 "rc=" 那一段，標題改成 "== r<輪> tN"，串成 <out>/accept_results_k1_llama_<model>_<TAG>.txt
  2. 建 <out>/llama_logs/<合併檔名>/t<題>/r<輪>，symlink 指到各自的 r1
只讀 Codex總攬 的檔案，輸出寫到 <out>。

用法：python3 -I scripts/merge_restart_results.py <exp 目錄> <合併檔名，不含 .txt> <輸出目錄>
例：python3 -I scripts/merge_restart_results.py ~/Claude/Codex總攬/exp accept_results_k1_llama_qwen3.6-35b-a3b_night4r /tmp/n4
"""
import glob
import os
import re
import sys


def main():
    exp, base, out = sys.argv[1:4]
    exp = os.path.abspath(os.path.expanduser(exp))  # symlink 用絕對路徑，相對路徑會指錯地方
    pat = re.compile(re.escape(base) + r"_r(\d+)t(\d+)\.txt$")
    files = []
    for p in glob.glob(os.path.join(exp, base + "_r*t*.txt")):
        m = pat.search(os.path.basename(p))
        if m:
            files.append((int(m.group(1)), int(m.group(2)), p))
    if not files:
        sys.exit(f"找不到 {base}_r*t*.txt")
    files.sort()
    os.makedirs(out, exist_ok=True)
    lines = []
    for r, t, p in files:
        block, on = [], False
        for line in open(p, encoding="utf-8"):
            if re.match(r"== r1 t\d+\s*$", line):
                on, line = True, f"== r{r} t{t}\n"
            if on:
                block.append(line)
                if line.startswith("rc="):
                    break
        if not block or not block[-1].startswith("rc="):
            print(f"警告：{os.path.basename(p)} 沒有完整的結果段落（還在跑或被中止），跳過", file=sys.stderr)
            continue
        lines += block
        src = os.path.join(exp, "llama_logs", os.path.basename(p)[:-4], f"t{t}", "r1")
        dst = os.path.join(out, "llama_logs", base, f"t{t}", f"r{r}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.islink(dst):
            os.remove(dst)
        os.symlink(src, dst)
    res = os.path.join(out, base + ".txt")
    with open(res, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(res)


if __name__ == "__main__":
    main()
