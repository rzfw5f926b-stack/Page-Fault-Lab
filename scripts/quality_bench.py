#!/usr/bin/env python3
"""第 7 項：寫程式品質小測驗。用 /v1/chat/completions（伺服器套用模型自己的對話模板），
請模型寫 6 個函式／類別，取出回答裡的 python 程式碼，再用固定的測試案例在子程序裡執行，計算通過數。

- 溫度 0，每題 max_tokens 預設 4096（gpt-oss 會先推理，需要較多 token）。思考型模型用 --max-tokens 放寬，
  伺服器的 ctx 要大於提示加 max_tokens。
- 沒過的題目記 failure_type：budget（finish_reason=length，額度用完）、no_code（回答沒有程式碼）、
  timeout（測試逾時）、wrong（有程式碼但測試沒過）。budget 不能當成答錯。
- 測試在 logs/quality_work/ 底下的暫存檔執行，用 python3 -I，逾時 20 秒。
- 題目之間休息 --pause 秒，並等熱壓力回到 0。
- 結果寫到 logs/<label>_<時間>.jsonl（含完整回答，方便事後檢查）。

用法：python3 -I scripts/quality_bench.py --label q30_quality
"""
import argparse, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import ROOT, post  # noqa: E402

TASKS = [
    ("parse_duration",
     "Write a Python function parse_duration(s: str) -> int that converts a duration string like "
     "'1h30m15s', '45m', '2h', '90s' or '1h5s' into total seconds. Units are h, m, s, each appearing at most "
     "once and in that order. Raise ValueError for an empty string, unknown units, wrong order, repeated "
     "units, or missing numbers.",
     """
assert parse_duration('1h30m15s') == 5415
assert parse_duration('45m') == 2700
assert parse_duration('2h') == 7200
assert parse_duration('90s') == 90
assert parse_duration('1h5s') == 3605
for bad in ['', '5x', 'm', '1s1h', '1h1h', 'h5']:
    try:
        parse_duration(bad)
    except ValueError:
        pass
    else:
        raise AssertionError('no ValueError for ' + repr(bad))
"""),
    ("merge_intervals",
     "Write a Python function merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]] "
     "that merges overlapping or touching closed intervals and returns them sorted by start. "
     "The input may be unsorted and must not be modified.",
     """
data = [(5, 7), (1, 3), (2, 4), (8, 10), (10, 12)]
copy = list(data)
assert merge_intervals(data) == [(1, 4), (5, 7), (8, 12)]
assert data == copy
assert merge_intervals([]) == []
assert merge_intervals([(1, 10), (2, 3)]) == [(1, 10)]
assert merge_intervals([(3, 3)]) == [(3, 3)]
"""),
    ("LRUCache",
     "Write a Python class LRUCache with __init__(self, capacity: int), get(self, key) which returns the "
     "value or -1 if missing, and put(self, key, value). When capacity is exceeded, evict the least recently "
     "used key. Both get and put count as a use. Updating an existing key must not evict anything.",
     """
c = LRUCache(2)
c.put(1, 1); c.put(2, 2)
assert c.get(1) == 1
c.put(3, 3)
assert c.get(2) == -1
c.put(1, 10)
c.put(4, 4)
assert c.get(3) == -1
assert c.get(1) == 10 and c.get(4) == 4
d = LRUCache(1)
d.put('a', 1); d.put('a', 2)
assert d.get('a') == 2
"""),
    ("topo_sort",
     "Write a Python function topo_sort(deps: dict[str, list[str]]) -> list[str]. deps maps each item to "
     "the items it depends on; dependencies must come before the item in the result. Items that appear only "
     "as dependencies must also be included. Among items that are ready at the same time, output them in "
     "alphabetical order. Raise ValueError if there is a cycle.",
     """
assert topo_sort({'b': ['a'], 'c': ['b'], 'a': []}) == ['a', 'b', 'c']
assert topo_sort({'app': ['lib', 'util'], 'lib': ['util']}) == ['util', 'lib', 'app']
assert topo_sort({'z': [], 'y': [], 'x': ['z']}) == ['y', 'z', 'x']
try:
    topo_sort({'a': ['b'], 'b': ['a']})
except ValueError:
    pass
else:
    raise AssertionError('cycle not detected')
"""),
    ("roman",
     "Write two Python functions: to_roman(n: int) -> str for 1 <= n <= 3999 (raise ValueError otherwise), "
     "and from_roman(s: str) -> int that parses standard roman numerals and raises ValueError for invalid "
     "ones such as 'IIII', 'IC', 'VV' or ''.",
     """
assert to_roman(1994) == 'MCMXCIV'
assert to_roman(3999) == 'MMMCMXCIX'
assert to_roman(4) == 'IV'
for n in range(1, 4000):
    assert from_roman(to_roman(n)) == n
for bad in [0, 4000]:
    try:
        to_roman(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(bad)
for bad in ['IIII', 'IC', 'VV', '']:
    try:
        from_roman(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(bad)
"""),
    ("fix_bug",
     "This function should return the k most frequent words in text (case-insensitive, words are runs of "
     "letters a-z), ordered by count descending and then alphabetically for ties. It has bugs. "
     "Return the corrected complete function.\n\n```python\nimport re\n\ndef top_words(text, k):\n"
     "    counts = {}\n    for w in re.findall(r'[a-z]+', text):\n        counts[w] = counts.get(w, 0) + 1\n"
     "    items = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)\n    return [w for w, _ in items[:k-1]]\n```",
     """
assert top_words('b a B c a b', 2) == ['b', 'a']
assert top_words('Dog cat dog CAT bird', 3) == ['cat', 'dog', 'bird']
assert top_words('x', 5) == ['x']
assert top_words('', 3) == []
"""),
]


def thermal_level():
    """讀不到或讀到非數字時回傳 1：看不到熱壓力就當作不安全，呼叫端會等待，等太久就停止。"""
    try:
        out = subprocess.run(["notifyutil", "-g", "com.apple.system.thermalpressurelevel"],
                             capture_output=True, text=True, timeout=10).stdout.split()
        return int(out[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return 1


def extract_code(text):
    """逐行配對 ``` 的開頭和結尾。標成 python/py 的區塊全部接起來；
    沒有的話取最後一個沒標語言的區塊；都沒有就整段當程式碼。其他語言的區塊不取。"""
    blocks, lang, buf = [], None, []
    for line in text.splitlines():
        s = line.strip()
        if lang is None:
            if s.startswith("```"):
                lang, buf = s[3:].strip().lower(), []
        elif s == "```":
            blocks.append((lang, "\n".join(buf)))
            lang = None
        else:
            buf.append(line)
    if lang is not None:  # 回答被截斷、最後一個區塊沒有結尾
        blocks.append((lang, "\n".join(buf)))
    py =[b for l, b in blocks if l in ("python", "py", "python3")]
    if py:
        return "\n\n".join(py)
    plain = [b for l, b in blocks if l == ""]
    return plain[-1] if plain else text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--label", required=True)
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--pause", type=int, default=60)
    a = ap.parse_args()
    work = f"{ROOT}/logs/quality_work"
    os.makedirs(work, exist_ok=True)
    out = f"{ROOT}/logs/{a.label}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    passed = 0
    counts = {}
    with open(out, "w") as f:
        for i, (name, ask, tests) in enumerate(TASKS):
            if i:
                time.sleep(a.pause)
                waited = 0
                while thermal_level() >= 1:
                    time.sleep(30); waited += 30
                    if waited >= 1800:
                        raise SystemExit("熱壓力 30 分鐘未回到 0，停止")
            prompt = ask + "\nReply with a single python code block containing only the code (imports included)."
            t0 = time.time()
            r = post(a.url + "/v1/chat/completions",
                     {"messages": [{"role": "user", "content": prompt}], "max_tokens": a.max_tokens,
                      "temperature": 0.0, "seed": 42, "cache_prompt": False})
            msg = r["choices"][0]["message"]
            content = msg.get("content") or ""
            code = extract_code(content)
            path = f"{work}/{a.label}_{name}.py"
            open(path, "w").write(code + "\n\n" + tests + "\nprint('PASS')\n")
            try:
                p = subprocess.run([sys.executable, "-I", path], capture_output=True, text=True,
                                   timeout=20, cwd=work)
                ok = p.returncode == 0 and "PASS" in p.stdout
                err = (p.stderr or "")[-400:]
            except subprocess.TimeoutExpired:
                ok, err = False, "timeout"
            passed += ok
            finish = r["choices"][0].get("finish_reason")
            # 額度用完和答錯要分開：思考型模型可能把 max_tokens 全花在思考，回答是空的
            if ok:
                ftype = None
            elif finish == "length":
                ftype = "budget"
            elif not content.strip() or not re.search(r"^\s*(def|class) ", code, re.M):
                ftype = "no_code"
            elif err == "timeout":
                ftype = "timeout"
            else:
                ftype = "wrong"
            counts[ftype] = counts.get(ftype, 0) + (ftype is not None)
            t = r.get("timings", {})
            usage = r.get("usage") or {}  # MLX 沒有 timings，只有 usage
            rec = {"label": a.label, "task": name, "pass": ok, "failure_type": ftype, "max_tokens": a.max_tokens, "error": err, "wall_s": round(time.time() - t0, 1),
                   "gen_n": t.get("predicted_n") or usage.get("completion_tokens"), "gen_tps": t.get("predicted_per_second"),
                   "prompt_n": t.get("prompt_n") or usage.get("prompt_tokens"), "finish_reason": finish,
                   # llama.cpp 用 reasoning_content，mlx-lm 用 reasoning
                   "reasoning_chars": len(msg.get("reasoning_content") or msg.get("reasoning") or ""), "content": content}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            tps = f"{rec['gen_tps']:.1f} t/s" if rec["gen_tps"] else "速度未回報"
            empty = f" | 內容是空的，思考 {rec['reasoning_chars']} 字" if not content.strip() else ""
            print(f"{name}: {'PASS' if ok else 'FAIL ' + ftype} | gen {rec['gen_n']} @ {tps} | "
                  f"wall {rec['wall_s']}s | finish {rec['finish_reason']}{empty}" + ("" if ok else f" | {err[-150:]!r}"),
                  flush=True)
    fails = ", ".join(f"{k} {v}" for k, v in counts.items() if k and v)
    print(f"{a.label}: {passed}/{len(TASKS)} passed{' | 失敗：' + fails if fails else ''}"
          f" | max_tokens {a.max_tokens} | {out}", flush=True)


if __name__ == "__main__":
    main()
