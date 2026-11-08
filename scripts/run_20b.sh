#!/bin/sh
# 第 6 項：gpt-oss-20b 在同一顆外接 SSD、同一套量測腳本下的基準（2026-11-08 晚上）。
# 目的：給 120b 的數字一個「模型整個放得進記憶體時」的對照，也和 Ollama 的約 29 tok/s 比較。
# 三組（模型約 12GB，載入後整個在記憶體裡）：
#   b20_gpu      ：全部放 GPU（不加 -ot exps=CPU），上限參考
#   b20_mmap     ：和 120b 主設定相同（專家層 -ot exps=CPU 經 mmap），看 CPU 跑專家的代價
#   b20_gpu_ngram：全部放 GPU + --spec-type ngram-mod，看 n-gram 推測在不受 SSD 限制時的效果
# 每組：spec_bench（prompts/spec_rewrite.txt，生成 96）＋ agent_bench（agent_turn1 三輪，每輪 64，輪間休息 60 秒）；
#       ngram 組只跑 spec_bench。設定 -c 8192 -b 2048 -ub 2048，與第 3、4 項相同。
# 安全規則同第 4 項：組間冷卻 20 分鐘且熱壓力 0；載入後冷卻 5 分鐘；thermal_guard 熱壓力 >=1 立即 SIGKILL；
#   本輪跳脫 2 次全部停止；記憶體保護（可用 <12% 或 swap 多 1GB）立即 SIGKILL。
ROOT="/Volumes/LLM SSD/Flashback"
cd "$ROOT" || exit 1
LOG="$ROOT/logs/b20.log"
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
        pkill -9 -f "llama-server -m"; pkill -9 -f spec_bench.py; pkill -9 -f agent_bench.py
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
run_cfg() {  # $1=label $2=前置冷卻 $3=EXPS（GPU/CPU） $4=EXTRA $5=是否跑 agent_bench（1/0）
  [ "$(memtrips)" -gt "$MT0" ] && finish "記憶體保護已觸發，停止"
  cool "$2"
  T0=$(trips); stop_server
  log "start server $1 MODEL=20b EXPS=$3 EXTRA=[$4] (wired before: $(top -l 1 -n 0 | awk '/PhysMem/ {print $4}'), free $(memfree)%)"
  MODEL=gpt-oss-20b-MXFP4.gguf EXPS="$3" EXTRA="$4" CTX=8192 BATCH=2048 scripts/start_server.sh "$1" -1 2048 &
  if ! wait_ready; then stop_server; log "$1 skipped; server log tail: $(tail -5 "$(ls -t logs/server_$1_*.log | head -1)" | tr '\n' ' ')"; return; fi
  log "footprint: $(footprint -p $(pgrep -f 'llama-server -m' | head -1) 2>/dev/null | grep -i 'phys_footprint:' | head -1); wired: $(top -l 1 -n 0 | awk '/PhysMem/ {print $4}'); free $(memfree)%"
  grep -iE "override|buffer size|KV self" "$(ls -t logs/server_$1_*.log | head -1)" | head -10 >> "$LOG"
  cool 300
  python3 -I scripts/spec_bench.py --label "$1" --n 96 > "logs/$1_console.log" 2>&1
  log "spec $1 exit=$? : $(tr '\n' ' ' < logs/$1_console.log)"
  if [ "$5" = 1 ] && [ "$(trips)" -eq "$T0" ] && pgrep -f "llama-server -m" >/dev/null; then
    cool 300
    python3 -I scripts/agent_bench.py --label "$1_agent" --n 64 --pause 60 > "logs/$1_agent_console.log" 2>&1
    log "agent $1 exit=$? : $(tr '\n' ' ' < logs/$1_agent_console.log)"
  fi
  stop_server; check_swap
  [ "$(trips)" -gt "$T0" ] && { log "$1 因熱保護中止"; cool 1800; }
}
rm -f "$ROOT/logs/overnight_done"
pgrep -f thermal_guard.sh >/dev/null || scripts/thermal_guard.sh &
MT0=$(memtrips)
mem_guard & MG=$!
log "20b test start (swap used ${SW0}MB, free $(memfree)%)"
run_cfg b20_gpu 1200 GPU "" 1
run_cfg b20_mmap 1200 CPU "" 1
run_cfg b20_gpu_ngram 1200 GPU "--spec-type ngram-mod" 0
finish "全部完成"
