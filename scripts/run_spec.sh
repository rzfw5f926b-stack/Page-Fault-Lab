#!/bin/sh
# 第 3 項（n-gram 推測解碼）＋第 6 項前半（EAGLE3、20b 草稿模型）。不過熱優先。
# 等 download_extra.sh 結束才開始。每組：重啟伺服器（-c 8192 -ub 2048）→ 冷卻 5 分 → spec_bench（生成 96 token（白天兩次在 8 分鐘內跳脫，縮短連續負載））
# 組間冷卻 20 分且熱壓力 0；熱壓力 >=1 由 thermal_guard 立即 SIGKILL；本輪跳脫 2 次全部停止；swap +1GB 停止。
ROOT="/Volumes/LLM SSD/Flashback"
cd "$ROOT" || exit 1
LOG="$ROOT/logs/spec.log"
M="$ROOT/models"
log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
swapouts() { vm_stat | awk '/Swapouts/ {gsub("\\.","",$2); print $2}'; }
level() { notifyutil -g com.apple.system.thermalpressurelevel | awk '{print $2}'; }
trips() { ls "$ROOT"/logs/THERMAL_TRIP_* 2>/dev/null | wc -l | tr -d ' '; }
stop_server() {
  pkill -9 -f "llama-server -m" 2>/dev/null
  i=0; while pgrep -f "llama-server -m" >/dev/null && [ $i -lt 600 ]; do sleep 1; i=$((i+1)); done
}
finish() { stop_server; touch "$ROOT/logs/overnight_done"; log "end: $1"; exit 0; }
while pgrep -f "download_extra.sh|run_ubatch.sh" >/dev/null; do sleep 60; done
S0=$(swapouts); TRIP0=$(trips)
check_swap() { d=$(( $(swapouts) - S0 )); log "swapouts since start: +$d pages"; [ "$d" -gt 65536 ] && finish "swap 增加過多，中止"; }
ensure_cool() {
  [ $(( $(trips) - TRIP0 )) -ge 2 ] && finish "熱保護本輪跳脫 2 次，停止"
  i=0; while [ "$(level)" -ge 1 ]; do [ $i -ge 2700 ] && finish "熱壓力 45 分鐘未回到 0"; sleep 30; i=$((i+30)); done
}
cool() { log "cooldown $1 s"; sleep "$1"; ensure_cool; log "cool ok, level=$(level)"; }
wait_ready() {
  i=0
  while [ $i -lt 900 ]; do
    [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/health)" = 200 ] && { log "server ready after ${i}s"; return 0; }
    pgrep -f "llama-server -m" >/dev/null || { log "server died during load"; return 1; }
    sleep 1; i=$((i+1))
  done
  log "server not ready in 900s"; return 1
}
run_cfg() {  # $1=label $2=前置冷卻 $3=額外參數
  cool "$2"
  T0=$(trips); stop_server
  log "start server $1 EXTRA=[$3]"
  EXTRA="$3" CTX=8192 BATCH=2048 scripts/start_server.sh "$1" -1 2048 &
  if ! wait_ready; then stop_server; log "$1 skipped; server log tail: $(tail -5 "$(ls -t logs/server_$1_*.log | head -1)" | tr '\n' ' ')"; return; fi
  log "footprint: $(footprint -p $(pgrep -f 'llama-server -m' | head -1) 2>/dev/null | grep -i 'phys_footprint:' | head -1)"
  cool 300
  python3 -I scripts/spec_bench.py --label "$1" --n 96 > "logs/$1_console.log" 2>&1
  log "bench $1 exit=$? : $(tr '\n' ' ' < logs/$1_console.log)"
  stop_server; check_swap
  [ "$(trips)" -gt "$T0" ] && { log "$1 因熱保護中止"; cool 1800; }
}
rm -f "$ROOT/logs/overnight_done"
pgrep -f thermal_guard.sh >/dev/null || scripts/thermal_guard.sh &
log "spec test start"
run_cfg spec_none 1200 ""
run_cfg spec_ngram_simple 1200 "--spec-type ngram-simple"
run_cfg spec_ngram_mod 1200 "--spec-type ngram-mod"
run_cfg spec_eagle3 1200 "--spec-type draft-eagle3 -md models/eagle3-gpt-oss-120b-Q8_0.gguf"
run_cfg spec_draft20b 1200 "--spec-type draft-simple -md models/gpt-oss-20b-MXFP4.gguf -ngld all"
finish "全部完成"
