#!/usr/bin/env python3
"""Flashback 硬碟隨機讀取延遲量測：對模型檔做隨機 pread（F_NOCACHE 繞過快取，也不污染快取）。

用排隊深度（同時讀取的執行緒數）× 讀取大小的組合，量 IOPS、MB/s 與平均延遲，
用來驗證「生成速度由單次讀取延遲 ÷ 排隊深度決定」的假設。
每組之間檢查熱壓力，>=1 就停止。

用法：python3 -I scripts/randread.py [--secs 10]
輸出：logs/randread_<時間>.jsonl
"""
import argparse, fcntl, json, os, random, subprocess, threading, time

ROOT = "/Volumes/LLM SSD/Flashback"
MODEL = f"{ROOT}/models/gpt-oss-120b-MXFP4.gguf"
F_NOCACHE = getattr(fcntl, "F_NOCACHE", 48)


def thermal_level():
    out = subprocess.run(["notifyutil", "-g", "com.apple.system.thermalpressurelevel"],
                         capture_output=True, text=True).stdout.split()
    return int(out[-1]) if out else 0


def run(size, qd, secs):
    fsize = os.path.getsize(MODEL)
    stop = time.time() + secs
    stats = []

    def worker(seed):
        fd = os.open(MODEL, os.O_RDONLY)
        fcntl.fcntl(fd, F_NOCACHE, 1)
        rng = random.Random(seed)
        n, lat = 0, 0.0
        maxoff = (fsize - size) // 4096
        while time.time() < stop:
            off = rng.randrange(maxoff) * 4096
            t = time.perf_counter()
            os.pread(fd, size, off)
            lat += time.perf_counter() - t
            n += 1
        os.close(fd)
        stats.append((n, lat))

    t0 = time.time()
    ths = [threading.Thread(target=worker, args=(i * 7919 + size,)) for i in range(qd)]
    for t in ths: t.start()
    for t in ths: t.join()
    el = time.time() - t0
    n = sum(s[0] for s in stats); lat = sum(s[1] for s in stats)
    return {"size_KB": size // 1024, "qd": qd, "secs": round(el, 2), "ops": n,
            "iops": round(n / el), "MB_s": round(n * size / el / 1e6, 1),
            "avg_lat_ms": round(lat / max(n, 1) * 1000, 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secs", type=float, default=10)
    ap.add_argument("--sizes", default="4,24,48,128,1024")
    ap.add_argument("--qds", default="1,2,4,8,16,32")
    a = ap.parse_args()
    out = f"{ROOT}/logs/randread_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    print("log =", out, flush=True)
    with open(out, "w") as f:
        for kb in [int(x) for x in a.sizes.split(",")]:
            for qd in [int(x) for x in a.qds.split(",")]:
                if thermal_level() >= 1:
                    print("熱壓力 >=1，停止", flush=True); return
                r = run(kb * 1024, qd, a.secs)
                r["thermal"] = thermal_level()
                f.write(json.dumps(r) + "\n"); f.flush()
                print(f"{kb:5d}KB QD{qd:2d}: {r['iops']:6d} IOPS {r['MB_s']:7.1f} MB/s "
                      f"lat {r['avg_lat_ms']:.3f} ms", flush=True)
                time.sleep(2)


if __name__ == "__main__":
    main()
