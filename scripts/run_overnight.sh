#!/bin/sh
# 通宵排程 v3（2026-11-08 02:40）。使用者要求：不過熱優先於實驗成功。
# 順序：B（-ub 2048，長提示詞較短、持續發熱時間短）→ A'（-ub 512）→ C（-t 8、-t 2，用較快的 ubatch）。
# - 每段開始前：冷卻 20 分鐘，且熱壓力必須回到 0
# - 伺服器啟動（會預讀整個模型）後冷卻 5 分鐘、等熱壓力 0
# - 每輪 t1/t2/t3 之間休息 5 分鐘、等熱壓力 0（agent_bench --pause；前綴快取保留，不影響量測）
# - scripts/thermal_guard.sh：熱壓力 >=1 立即停止量測與伺服器（SIGKILL）；跳脫後冷卻 30 分鐘；累計 3 次就全部停止
# - 冷啟動：無法 sudo purge，改讀 24GB scratch/evict.bin 擠出快取（近似）
# - swapouts 增加超過 1GB 就全部停止
ROOT="/Volumes/LLM SSD/Flashback"
cd "$ROOT" || exit 1
LOG="$ROOT/logs/overnight.log"
log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
swapouts() { vm_stat | awk '/Swapouts/ {gsub("\\.","",$2); print $2}'; }
S0=$(swapouts)
level() { notifyutil -g com.apple.system.thermalpressurelevel | awk '{print $2}'; }
trips() { ls "$ROOT"/logs/THERMAL_TRIP_* 2>/dev/null | wc -l | tr -d ' '; }
stop_server() {
  pkill -9 -f "llama-server -m" 2>/dev/null
  i=0; while pgrep -f "llama-server -m" >/dev/null && [ $i -lt 600 ]; do sleep 1; i=$((i+1)); done
  log "server stopped"
}
finish() { stop_server; touch "$ROOT/logs/overnight_done"; log "overnight end: $1"; exit 0; }
check_swap() {
  d=$(( $(swapouts) - S0 )); log "swapouts since start: +$d pages"
  [ "$d" -gt 65536 ] && finish "swap 增加過多，中止"
}
ensure_cool() {
  [ "$(trips)" -ge 3 ] && finish "熱保護累計跳脫 3 次，停止所有測試"
  i=0; while [ "$(level)" -ge 1 ]; do
    [ $i -ge 2700 ] && finish "熱壓力 45 分鐘未回到 0，停止"
    sleep 30; i=$((i+30)); done
}
cool() { log "cooldown $1 s"; sleep "$1"; ensure_cool; log "cool ok, level=$(level)"; }
wait_ready() {
  i=0
  while [ $i -lt 600 ]; do
    [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/health)" = 200 ] && { log "server ready after ${i}s"; return 0; }
    pgrep -f "llama-server -m" >/dev/null || { log "server died during load"; return 1; }
    sleep 1; i=$((i+1))
  done
  log "server not ready in 600s"; return 1
}
evict() {
  mkdir -p "$ROOT/scratch"
  if [ ! -f "$ROOT/scratch/evict.bin" ]; then
    log "creating 24GB evict file"; dd if=/dev/zero of="$ROOT/scratch/evict.bin" bs=16m count=1536 2>>"$LOG"
    cool 300
  fi
  log "evicting cache by reading evict file"; dd if="$ROOT/scratch/evict.bin" of=/dev/null bs=16m 2>>"$LOG"
}
run_cfg() {  # $1=label $2=threads $3=ubatch
  cool 1200
  T0=$(trips)
  stop_server
  scripts/start_server.sh "$1" "$2" "$3" &
  if ! wait_ready; then stop_server; log "$1 skipped (load failed/tripped)"; [ "$(trips)" -gt "$T0" ] && cool 1800; return; fi
  cool 300
  evict
  cool 120
  log "start bench $1 (t=$2 ub=$3)"
  python3 -I scripts/agent_bench.py --label "$1" --n 64 --pause 300 > "logs/$1_console.log" 2>&1
  log "bench $1 exit=$? : $(tr '\n' ' ' < logs/$1_console.log)"
  stop_server
  check_swap
  [ "$(trips)" -gt "$T0" ] && { log "$1 因熱保護中止"; cool 1800; }
}

rm -f "$ROOT/logs/overnight_done"
pgrep -f thermal_guard.sh >/dev/null || scripts/thermal_guard.sh &
log "overnight v3 start (trips so far: $(trips))"

run_cfg agent_ub2048 -1 2048
run_cfg agent_ub512 -1 512

UB=$(python3 -I - <<'PY'
import glob, json
def t1(label):
    for f in sorted(glob.glob(f"/Volumes/LLM SSD/Flashback/logs/{label}_2*.jsonl"), reverse=True):
        for l in open(f):
            r = json.loads(l)
            if r["turn"] == "t1_long":
                return r["prompt_ms"]
    return None
a, b = t1("agent_ub512"), t1("agent_ub2048")
print(512 if (a is not None and (b is None or a < b)) else 2048)
PY
)
log "chosen ubatch for C: $UB"
for T in 8 2; do
  run_cfg "agent_t${T}_ub${UB}" "$T" "$UB"
done
finish "全部完成"
