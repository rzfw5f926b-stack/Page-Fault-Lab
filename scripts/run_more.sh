#!/bin/sh
# 第 4 項：把前幾層的專家權重固定在 GPU（2026-11-08 晚上，外加風扇：Air 和 SSD 放在清淨機出風口上）。
# 問題：Mac mini 多出來的 8GB，拿來固定部分專家層，會不會比交給系統當檔案快取更有用？
# 提示詞和設定都和 spec_none 一樣（prompts/spec_rewrite.txt，-c 8192 -b 2048 -ub 2048，生成 96 token），結果可以直接比較。
# 三組，記憶體用量由少到多：
#   pin_res_base：RESIDENCY=1，不固定（單獨看 residency 的影響，對照 spec_none 的 NO_RESIDENCY）
#   pin_res_2   ：RESIDENCY=1，第 0、1 層專家放 MTL0（約 3.3GB）
#   pin_res_4   ：RESIDENCY=1，第 0～3 層專家放 MTL0（約 6.7GB）
# 安全規則（不過熱、不過載優先）：
# - 組間冷卻 20 分鐘且熱壓力 0；載入後冷卻 5 分鐘；thermal_guard 熱壓力 >=1 立即 SIGKILL；本輪跳脫 2 次全部停止
# - 記憶體保護：伺服器執行期間每 5 秒檢查，系統可用記憶體 <12% 或 swap 已用比開始時多 1GB，就立即 SIGKILL 並留下 logs/MEM_TRIP_*；
#   一旦觸發，後面記憶體用得更多的組別都不跑
ROOT="/Volumes/LLM SSD/Flashback"
cd "$ROOT" || exit 1
LOG="$ROOT/logs/pin.log"
log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
swapouts() { vm_stat | awk '/Swapouts/ {gsub("\\.","",$2); print $2}'; }
swapused() { sysctl -n vm.swapusage | awk '{gsub("M","",$6); print int($6)}'; }
memfree() { memory_pressure | awk -F': ' '/free percentage/ {gsub("%","",$2); print $2}'; }
level() { notifyutil -g com.apple.system.thermalpressurelevel | awk '{print $2}'; }
trips() { ls "$ROOT"/logs/THERMAL_TRIP_* 2>/dev/null | wc -l | tr -d ' '; }
stop_server() {
  pkill -9 -f "llama-server -m" 2>/dev/null
  i=0; while pgrep -f "llama-server -m" >/dev/null && [ $i -lt 600 ]; do sleep 1; i=$((i+1)); done
}
finish() { kill "$MG" 2>/dev/null; stop_server; touch "$ROOT/logs/overnight_done"; log "end: $1"; exit 0; }
S0=$(swapouts); SW0=$(swapused); TRIP0=$(trips)
check_swap() { d=$(( $(swapouts) - S0 )); log "swapouts since start: +$d pages, swap used $(swapused) MB (start $SW0)"; [ "$d" -gt 65536 ] && finish "swap 增加過多，中止"; }
ensure_cool() {
  [ $(( $(trips) - TRIP0 )) -ge 2 ] && finish "熱保護本輪跳脫 2 次，停止"
  i=0; while [ "$(level)" -ge 1 ]; do [ $i -ge 2700 ] && finish "熱壓力 45 分鐘未回到 0"; sleep 30; i=$((i+30)); done
}
cool() { log "cooldown $1 s"; sleep "$1"; ensure_cool; log "cool ok, level=$(level)"; }
mem_guard() {  # 背景：伺服器在跑時檢查記憶體
  while :; do
    if pgrep -f "llama-server -m" >/dev/null; then
      F=$(memfree); U=$(swapused)
      if [ "${F:-100}" -lt 12 ] || [ $(( ${U:-0} - SW0 )) -gt 1024 ]; then
        T=$(date +%H%M%S); echo "free=${F}% swap=${U}MB" > "$ROOT/logs/MEM_TRIP_$T"
        pkill -9 -f "llama-server -m"; pkill -9 -f spec_bench.py
        echo "$(date '+%F %T') MEM_TRIP free=${F}% swap=${U}MB (start ${SW0}MB)" >> "$LOG"
      fi
    fi
    sleep 5
  done
}
memtrips() { ls "$ROOT"/logs/MEM_TRIP_* 2>/dev/null | wc -l | tr -d ' '; }
wait_ready() {
  i=0
  while [ $i -lt 900 ]; do
    [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/health)" = 200 ] && { log "server ready after ${i}s"; return 0; }
    pgrep -f "llama-server -m" >/dev/null || { log "server died during load"; return 1; }
    sleep 1; i=$((i+1))
  done
  log "server not ready in 900s"; return 1
}
run_cfg() {  # $1=label $2=前置冷卻 $3=PIN_OT 規則（空字串＝不固定）
  [ "$(memtrips)" -gt "$MT0" ] && finish "記憶體保護已觸發，記憶體用得更多的組別不跑"
  cool "$2"
  T0=$(trips); stop_server
  log "start server $1 RESIDENCY=1 PIN_OT=[$3] (wired before: $(top -l 1 -n 0 | awk '/PhysMem/ {print $4}'), free $(memfree)%)"
  PIN_OT="$3" RESIDENCY=1 CTX=8192 BATCH=2048 scripts/start_server.sh "$1" -1 2048 &
  if ! wait_ready; then stop_server; log "$1 skipped; server log tail: $(tail -5 "$(ls -t logs/server_$1_*.log | head -1)" | tr '\n' ' ')"; return; fi
  log "footprint: $(footprint -p $(pgrep -f 'llama-server -m' | head -1) 2>/dev/null | grep -i 'phys_footprint:' | head -1); wired: $(top -l 1 -n 0 | awk '/PhysMem/ {print $4}'); free $(memfree)%"
  grep -iE "override|MTL0|buffer|resid" "$(ls -t logs/server_$1_*.log | head -1)" | head -10 >> "$LOG"
  cool 300
  python3 -I scripts/spec_bench.py --label "$1" --n 96 > "logs/$1_console.log" 2>&1
  log "bench $1 exit=$? : $(tr '\n' ' ' < logs/$1_console.log)"
  stop_server; check_swap
  [ "$(trips)" -gt "$T0" ] && { log "$1 因熱保護中止"; cool 1800; }
}
rm -f "$ROOT/logs/overnight_done"
pgrep -f thermal_guard.sh >/dev/null || scripts/thermal_guard.sh &
MT0=$(memtrips)
mem_guard & MG=$!
log "pin test start (swap used ${SW0}MB, free $(memfree)%)"
run_cfg pin_res_base 1200 ""
run_cfg pin_res_2 1200 'blk\.[01]\.ffn_.*_exps=MTL0'
run_cfg pin_res_4 1200 'blk\.[0-3]\.ffn_.*_exps=MTL0'
finish "全部完成"
