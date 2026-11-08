#!/bin/sh
# 第 2 項：加大 ubatch + 16k 上下文（2026-11-08）。不過熱優先於實驗成功。
# 長提示詞 prompts/agent_long.txt（約 6k token）+ t2 追加。每組 -c 16384 -b 8192，只改 -ub：
#   8192（掃 1 次）→ 4096（掃 2 次）→ 2048（掃 3～4 次，連續負載最長，放最後）
# - 每段前冷卻 20 分鐘且熱壓力 0；伺服器載入後冷卻 5 分鐘；t1/t2 之間休息 5 分鐘
# - thermal_guard.sh：熱壓力 >=1 立即 SIGKILL；累計跳脫（本輪新增）2 次就全部停止
# - 不再做 evict（檔案已刪）：每組都是「重啟伺服器、載入預讀後」的相同狀態，組間可比
# - swapouts 增加超過 1GB 就停止
ROOT="/Volumes/LLM SSD/Flashback"
cd "$ROOT" || exit 1
LOG="$ROOT/logs/ubatch.log"
log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
swapouts() { vm_stat | awk '/Swapouts/ {gsub("\\.","",$2); print $2}'; }
S0=$(swapouts)
level() { notifyutil -g com.apple.system.thermalpressurelevel | awk '{print $2}'; }
trips() { ls "$ROOT"/logs/THERMAL_TRIP_* 2>/dev/null | wc -l | tr -d ' '; }
TRIP0=$(trips)
stop_server() {
  pkill -9 -f "llama-server -m" 2>/dev/null
  i=0; while pgrep -f "llama-server -m" >/dev/null && [ $i -lt 600 ]; do sleep 1; i=$((i+1)); done
}
finish() { stop_server; touch "$ROOT/logs/overnight_done"; log "end: $1"; exit 0; }
check_swap() {
  d=$(( $(swapouts) - S0 )); log "swapouts since start: +$d pages"
  [ "$d" -gt 65536 ] && finish "swap 增加過多，中止"
}
ensure_cool() {
  [ $(( $(trips) - TRIP0 )) -ge 2 ] && finish "熱保護本輪跳脫 2 次，停止"
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
run_cfg() {  # $1=ubatch $2=前置冷卻秒數
  L="ub_c16k_ub$1"
  cool "$2"
  T0=$(trips)
  stop_server
  CTX=16384 BATCH=8192 scripts/start_server.sh "$L" -1 "$1" &
  if ! wait_ready; then stop_server; log "$L skipped (load failed)"; [ "$(trips)" -gt "$T0" ] && cool 1800; return; fi
  grep -iE "compute buffer|KV self size|kv.*MiB" "$(ls -t logs/server_${L}_*.log | head -1)" | head -8 >> "$LOG"
  log "footprint: $(footprint -p $(pgrep -f 'llama-server -m' | head -1) 2>/dev/null | grep -i 'phys_footprint:' | head -1)"
  cool 300
  log "start bench $L"
  python3 -I scripts/agent_bench.py --label "$L" --t1 agent_long.txt --turns t1_long,t2_followup \
    --n 32 --pause 300 > "logs/${L}_console.log" 2>&1
  log "bench $L exit=$? : $(tr '\n' ' ' < logs/${L}_console.log)"
  stop_server
  check_swap
  [ "$(trips)" -gt "$T0" ] && { log "$L 因熱保護中止"; cool 1800; }
}

rm -f "$ROOT/logs/overnight_done"
pgrep -f thermal_guard.sh >/dev/null || scripts/thermal_guard.sh &
log "ubatch test start (trips so far: $(trips))"
run_cfg 8192 600
run_cfg 4096 1200
run_cfg 2048 1200
finish "全部完成"
