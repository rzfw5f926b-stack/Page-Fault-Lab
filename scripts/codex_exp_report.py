#!/usr/bin/env python3
"""把 Codex總攬 題目的一輪結果整理成「每次嘗試一行 jsonl」（格式見 Codex總攬 的測試需求「結果格式」）。

用法：scripts/codex_exp_report.py <結果檔> [--set hard|regression] [--config '<json>'] > out.jsonl
  結果檔：~/Claude/Codex總攬/exp/accept_results_{hard,k3}_llama_<模型>[_TAG].txt
  每次嘗試的細節從 exp/llama_logs/<結果檔名>/{h|t}<題>/r<輪>/ 讀；資源從 logs/resources.csv 依時間窗取。
只讀 Codex總攬 的檔案，不改。輸出的路徑一律用 ~。
"""
import csv, datetime as dt, glob, json, os, re, sys

HOME = os.path.expanduser("~")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tilde(s):
    return s.replace(HOME, "~") if isinstance(s, str) else s


def parse_results(path):
    """回傳每次嘗試的 dict：round、task、start、result_line、check、time_s、tries、changed。"""
    out, cur = [], None
    day = None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        m = re.match(r"start .* (\w{3} \w{3} +\d+ [\d:]+ \w+ \d{4})$", line)
        if m:
            day = dt.datetime.strptime(re.sub(" +", " ", m.group(1)).replace(" CST", ""), "%a %b %d %H:%M:%S %Y").date()
            continue
        # 回歸組（accept_k3.sh）的標題沒有時間，開始時間改從 exec.jsonl 取（見 main）
        m = re.match(r"== r(\d+) [ht](\d+)(?: (\d\d:\d\d:\d\d))?\s*$", line)
        if m:
            start = (dt.datetime.combine(day, dt.time.fromisoformat(m.group(3)))
                     if m.group(3) and day else None)
            cur = {"round": int(m.group(1)), "task": int(m.group(2)), "start": start}
            out.append(cur)
            continue
        if cur is None:
            continue
        if re.match(r"^(OK|FAIL|PASS)", line) and "status" not in cur:
            cur["status"] = line
        elif line.startswith("check:"):
            m = re.search(r"exit (\d+)", line)
            cur["check_rc"] = int(m.group(1)) if m else None
        elif line.startswith("time:"):
            m = re.search(r"(\d+)s，跑了 (\d+) 次", line)
            if m:
                cur["seconds"], cur["tries"] = int(m.group(1)), int(m.group(2))
        elif line.startswith("changed:"):
            v = line.split(":", 1)[1].strip()
            cur["changed"] = [] if v.startswith("-") else [x.strip() for x in v.split(",")]
    # 跨午夜：開始時間比前一筆早就加一天
    for a, b in zip(out, out[1:]):
        while a["start"] and b["start"] and b["start"] < a["start"]:
            b["start"] += dt.timedelta(days=1)
    return out


def load_resources():
    rows = []
    with open(os.path.join(ROOT, "logs", "resources.csv")) as f:
        for r in csv.DictReader(f):
            try:
                rows.append((dt.datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S"), r))
            except (ValueError, KeyError):
                pass
    return rows


def window(rows, t0, t1):
    w = [r for t, r in rows if t0 <= t <= t1]
    if not w:
        return None, None, None
    num = lambda r, k: float(r[k]) if r.get(k) not in (None, "") else None
    sw = [num(r, "swap_used_MB") for r in w if num(r, "swap_used_MB") is not None]
    fr = [num(r, "mem_free_pct") for r in w if num(r, "mem_free_pct") is not None]
    th = [num(r, "thermal") for r in w if num(r, "thermal") is not None]
    return (round(sw[-1] - sw[0]) if sw else None, min(fr) if fr else None, int(max(th)) if th else None)


def max_turn_wait(exec_path):
    """exec.jsonl 相鄰事件的最大間隔（秒），近似最長一回合等待。"""
    ts = []
    try:
        for line in open(exec_path, encoding="utf-8"):
            try:
                t = json.loads(line).get("timestamp")
            except ValueError:
                continue
            if t:
                ts.append(t)
    except OSError:
        return None
    return round(max((b - a for a, b in zip(ts, ts[1:])), default=0) / 1000) if ts else None


def first_ts(exec_path):
    """exec.jsonl 第一個事件的時間（本機時間），找不到回傳 None。"""
    try:
        for line in open(exec_path, encoding="utf-8"):
            try:
                t = json.loads(line).get("timestamp")
            except ValueError:
                continue
            if t:
                return dt.datetime.fromtimestamp(t / 1000)
    except OSError:
        pass
    return None


def classify(a, att, check_rc):
    """對應測試需求的 result：ok／wrong／budget／timeout／stall／ctx_overflow／crash／too_many_lines／touched_other_files。"""
    st = a.get("status", "")
    reason = (att or {}).get("reason") or ""
    if st.startswith("OK"):
        return "ok"
    if "逾時" in st or "逾時" in reason:
        return "timeout"
    if "停滯" in st or "停滯" in reason:
        return "stall"
    if "context" in reason or "exceed" in reason:
        return "ctx_overflow"
    if "行數" in st or "超過上限" in st or "改動過大" in st:
        return "too_many_lines"
    if "其他檔" in st or "不允許" in st:
        return "touched_other_files"
    if "執行錯誤" in st or "執行錯誤" in reason:
        return "crash"
    return "wrong" if check_rc not in (None, 0) else "crash"


def main():
    args = sys.argv[1:]
    res = args[0]
    sset = "hard" if "_hard_" in os.path.basename(res) else "regression"
    config = {}
    if "--set" in args:
        sset = args[args.index("--set") + 1]
    if "--config" in args:
        config = json.loads(args[args.index("--config") + 1])
    restarts = config.pop("server_restarts", 0)  # 每題前重啟（3-1）時傳 1
    model = re.search(r"_llama_(.+?)(_[a-z0-9]+)?\.txt$", os.path.basename(res))
    base = os.path.splitext(os.path.basename(res))[0]
    logdir = os.path.join(os.path.dirname(res), "llama_logs", base)
    rows = load_resources()
    pfx = "h" if sset == "hard" else "t"
    for a in parse_results(res):
        if "status" not in a:  # 還在跑或被中止，沒有結果
            continue
        d =os.path.join(logdir, f"{pfx}{a['task']}", f"r{a['round']}")
        atts = sorted(glob.glob(os.path.join(d, "llama", "attempt*.json")),
                      key=lambda p: int(re.search(r"attempt(\d+)", p).group(1)))
        cfgf = os.path.join(d, "llama", "config.json")
        cfg = dict(config)
        if os.path.exists(cfgf):
            c = json.load(open(cfgf))
            cfg.update({k: c.get(k) for k in ("ctx", "output", "steps", "stall", "effort")})
            argv = c.get("argv", [])
            if "--timeout" in argv:
                cfg["timeout"] = int(argv[argv.index("--timeout") + 1])
        checks = {}
        cf = os.path.join(d, "llama", "checks.jsonl")
        if os.path.exists(cf):
            for line in open(cf, encoding="utf-8"):
                try:
                    c = json.loads(line)
                    checks[c.get("attempt")] = c.get("rc")
                except ValueError:
                    pass
        # dispatch.log 記了每次被重試的原因，例如「第 1 次：改動過大（+10 -1），已還原，重試」
        retry_reason = {}
        try:
            for line in open(os.path.join(d, "dispatch.log"), encoding="utf-8"):
                m = re.match(r"第 (\d+) 次：([^（，]+)", line)
                if m:
                    retry_reason[int(m.group(1))] = m.group(2).strip()
        except OSError:
            pass
        t0 = a["start"] or first_ts(os.path.join(d, "exec.jsonl"))
        for i, af in enumerate(atts or [None]):
          att = json.load(open(af)) if af else {}
          n = att.get("attempt", i + 1)
          final = i == len(atts) - 1 if atts else True
          rc = checks.get(n, a.get("check_rc") if final else None)
          if final:
              result = classify(a, att, rc)
          elif att.get("reason") or retry_reason.get(n):
              result = classify({"status": "FAIL:" + (att.get("reason") or retry_reason[n])}, att, rc)
          else:
              result = "ok" if rc == 0 else "wrong"
          secs = att.get("seconds") or (a.get("seconds") if final else None)
          t1 = t0 + dt.timedelta(seconds=secs or 0) if t0 else None
          swap_d, minfree, thmax = window(rows, t0, t1) if t0 else (None, None, None)
          t0 = t1
          shell = att.get("shell_cmds") or []
          last = att.get("last_text") or ""
          if sset == "hard":
              spec = None if rc is None else rc not in (10, 11)
              hidden = None if rc is None else rc == 0
          else:
              spec = None if rc is None else rc == 0
              hidden = None
          exj = [os.path.join(d, att["exec"])] if att.get("exec") else []
          # 步數用到上限（opencode 在倒數第 1 步就停）還沒過，是做不完，不是說完成卻做錯
          steps = att.get("steps")
          exhausted = bool(steps and cfg.get("steps") and steps >= cfg["steps"] - 1 and result != "ok")
          print(json.dumps({
            "model": model.group(1) if model else None,
            "config": cfg, "set": sset, "task": f"{pfx.upper()}{a['task']}",
            "round": a["round"], "attempt": n, "final_attempt": final,
            "result": result, "check_rc": rc, "spec_pass": spec, "hidden_pass": hidden,
            "claimed_done": bool(last) and not att.get("reason") and not exhausted,
            "steps": steps, "steps_exhausted": exhausted,
            "ran_tests": any("pytest" in s for s in shell),
            "extra_files": [],  # dispatch 會還原允許清單外的改動；被擋時 result 為 touched_other_files
            "think_tokens": att.get("tokens_reasoning") or None,
            "total_tokens": (att.get("tokens_input") or 0) + (att.get("tokens_output") or 0) + (att.get("tokens_reasoning") or 0) or None,
            "output_tokens": att.get("tokens_output"), "cache_read": att.get("cache_read"),
            "ctx_peak": att.get("max_step_input") or None,
            "seconds": secs, "max_turn_wait": max_turn_wait(exj[-1]) if exj else None,
            "swap_delta_mb": swap_d, "min_free_mem_pct": minfree, "thermal_max": thmax,
            "server_restarts": restarts,
            "fail_detail": tilde(att.get("reason") or retry_reason.get(n)
                                 or (a.get("status") if final else None)) if result != "ok" else None,
            "changed": a.get("changed") if final else None,
          }, ensure_ascii=False))


if __name__ == "__main__":
    main()
