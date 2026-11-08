#!/bin/sh
# 第 7 項：Qwen3-Coder-30B-A3B（Q4_K_M，約 18.6GB）的速度和寫程式品質（2026-11-08 晚上）。
# 這個模型放不進 GPU（MTL0 上限約 17.8GiB），所以用和 120b 相同的主設定：專家層 -ot exps=CPU 經 mmap。
# 三組：
#   q30_mmap      ：spec_bench（chatml 格式，生成 96）＋ agent_bench（chatml，三輪各 64）＋ quality_bench（6 題）
#   q30_mmap_ngram：同上設定加 --spec-type ngram-mod，只跑 spec_bench
#   b20_quality   ：gpt-oss-20b 全部放 GPU，只跑 quality_bench，當品質對照
# -c 8192 -b 2048 -ub 2048，與第 3、4、6 項相同。
# 安全規則同第 4、6 項：組間冷卻 20 分鐘且熱壓力 0；載入後冷卻 5 分鐘；thermal_guard 熱壓力 >=1 立即 SIGKILL；
#   本輪跳脫 2 次全部停止；記憶體保護（可用 <12% 或 swap 多 1GB）立即 SIGKILL。
ROOT="/Volumes/LLM SSD/Flashback"
cd "$ROOT" || exit 1
LOG="$ROOT/logs/qwen.log"
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
        pkill -9 -f "llama-server -m"; pkill -9 -f spec_bench.py; pkill -9 -f agent_bench.py; pkill -9 -f quality_bench.py
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
alive() { [ "$(trips)" -eq "$T0" ] && pgrep -f "llama-server -m" >/dev/null; }
run_cfg() {  # $1=label $2=前置冷卻 $3=模型檔 $4=EXPS $5=EXTRA $6=對話格式 $7=要跑的量測（spec,agent,quality）
  [ "$(memtrips)" -gt "$MT0" ] && finish "記憶體保護已觸發，停止"
  cool "$2"
  T0=$(trips); stop_server
  log "start server $1 MODEL=$3 EXPS=$4 EXTRA=[$5] (wired before: $(top -l 1 -n 0 | awk '/PhysMem/ {print $4}'), free $(memfree)%)"
  MODEL="$3" EXPS="$4" EXTRA="$5" CTX=8192 BATCH=2048 scripts/start_server.sh "$1" -1 2048 &
  if ! wait_ready; then stop_server; log "$1 skipped; server log tail: $(tail -5 "$(ls -t logs/server_$1_*.log | head -1)" | tr '\n' ' ')"; return; fi
  log "footprint: $(footprint -p $(pgrep -f 'llama-server -m' | head -1) 2>/dev/null | grep -i 'phys_footprint:' | head -1); wired: $(top -l 1 -n 0 | awk '/PhysMem/ {print $4}'); free $(memfree)%"
  grep -iE "override|buffer size|KV self" "$(ls -t logs/server_$1_*.log | head -1)" | head -10 >> "$LOG"
  case "$7" in *spec*) if alive; then cool 300
    python3 -I scripts/spec_bench.py --label "$1" --fmt "$6" --n 96 > "logs/$1_console.log" 2>&1
    log "spec $1 exit=$? : $(tr '\n' ' ' < logs/$1_console.log)"; fi;; esac
  case "$7" in *agent*) if alive; then cool 300
    python3 -I scripts/agent_bench.py --label "$1_agent" --fmt "$6" --n 64 --pause 60 > "logs/$1_agent_console.log" 2>&1
    log "agent $1 exit=$? : $(tr '\n' ' ' < logs/$1_agent_console.log)"; fi;; esac
  case "$7" in *quality*) if alive; then cool 300
    python3 -I scripts/quality_bench.py --label "$1_quality" --pause 60 > "logs/$1_quality_console.log" 2>&1
    log "quality $1 exit=$? : $(tr '\n' ' ' < logs/$1_quality_console.log)"; fi;; esac
  stop_server; check_swap
  [ "$(trips)" -gt "$T0" ] && { log "$1 因熱保護中止"; cool 1800; }
}
rm -f "$ROOT/logs/overnight_done"
pgrep -f thermal_guard.sh >/dev/null || scripts/thermal_guard.sh &
MT0=$(memtrips)
mem_guard & MG=$!
log "qwen test start (swap used ${SW0}MB, free $(memfree)%)"
run_cfg q30_mmap 1200 Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf CPU "" chatml spec,agent,quality
run_cfg q30_mmap_ngram 1200 Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf CPU "--spec-type ngram-mod" chatml spec
run_cfg b20_quality 1200 gpt-oss-20b-MXFP4.gguf GPU "" harmony quality
finish "全部完成"
