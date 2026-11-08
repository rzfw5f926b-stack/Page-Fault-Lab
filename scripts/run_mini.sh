#!/bin/sh
# Mac mini（M6、32GB）的測試流程。用法：
#   scripts/run_mini.sh --dry-run   只檢查環境、列出會做什麼，不載入模型、不寫紀錄（任何機器都能跑）
#   scripts/run_mini.sh             正式執行，請放背景；只有 M6、32GB 以上的機器才會真的開始
#
# 順序：
#   第 1 階段  llama.cpp 跑 Qwen3-Coder：先試整個放 GPU（EXPS=GPU），載入失敗才退回 exps=CPU
#   第 2 階段  MLX 跑 Qwen3-Coder，和第 1 階段用同一把尺比較
#   第 3 階段  opencode 跑多檔案題目，Qwen 和 20b 各一輪
#
# 第 2、3 階段依賴的東西缺了就跳過並記錄原因，不會下載或安裝任何東西：
#   第 2 階段：scripts/stream_bench.py、$MLX_PY（裝好 mlx-lm 的 python）、$MLX_MODEL（MLX 模型資料夾）
#   第 3 階段：opencode、tasks/、scripts/run_opencode_tasks.sh
# 這兩支腳本的介面（尚未實作）：
#   python3 -I scripts/stream_bench.py --url http://127.0.0.1:8080 --label <label>
#   scripts/run_opencode_tasks.sh <label>
#
# 安全規則同第 4、6、7 項：組間冷卻 20 分鐘且熱壓力 0；量測前冷卻 5 分鐘；thermal_guard 熱壓力 >=1 立即 SIGKILL；
#   本輪跳脫 2 次全部停止；記憶體保護（可用 <12% 或 swap 多 1GB）立即 SIGKILL。不改任何系統設定。
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export FLASHBACK_ROOT="$ROOT"
export DISK="${DISK:-disk0}"   # resource_log 量測的硬碟；模型放內建 SSD 時是 disk0
cd "$ROOT" || exit 1

QWEN=Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf
B20=gpt-oss-20b-MXFP4.gguf
MLX_PY="${MLX_PY:-$ROOT/.venv-mlx/bin/python}"
MLX_MODEL="${MLX_MODEL:-$ROOT/models/mlx/Qwen3-Coder-30B-A3B-4bit}"
COOLDOWN="${COOLDOWN:-1200}"
BENCH_COOLDOWN="${BENCH_COOLDOWN:-300}"
SRV='llama-server -m|mlx_lm.server'
LOG="$ROOT/logs/mini.log"

level() { notifyutil -g com.apple.system.thermalpressurelevel | awk '{print $2}'; }
chip() { sysctl -n machdep.cpu.brand_string; }
ram_gb() { echo $(( $(sysctl -n hw.memsize) / 1073741824 )); }

# 回傳值 = 第 1 階段無法開始的原因數
preflight() {
  bad=0
  echo "機器：$(chip)，$(ram_gb) GB，熱壓力 $(level)"
  case "$(chip)" in *M6*) ;; *) echo "  ✗ 不是 M6，正式執行會被拒絕"; bad=$((bad+1));; esac
  [ "$(ram_gb)" -ge 32 ] || { echo "  ✗ 記憶體不到 32 GB，正式執行會被拒絕"; bad=$((bad+1)); }
  [ "$(level)" = 0 ] || { echo "  ✗ 熱壓力不是 0"; bad=$((bad+1)); }
  command -v llama-server >/dev/null || { echo "  ✗ 找不到 llama-server"; bad=$((bad+1)); }
  [ -f "$ROOT/models/$QWEN" ] || { echo "  ✗ 缺模型 models/$QWEN"; bad=$((bad+1)); }
  pgrep -f "$SRV" >/dev/null && { echo "  ✗ 已經有推論伺服器在跑"; bad=$((bad+1)); }
  return "$bad"
}
mlx_missing() {
  [ -f "$ROOT/scripts/stream_bench.py" ] || echo "scripts/stream_bench.py"
  { [ -x "$MLX_PY" ] && "$MLX_PY" -c "import mlx_lm" 2>/dev/null; } || echo "mlx-lm（$MLX_PY）"
  [ -d "$MLX_MODEL" ] || echo "MLX 模型（$MLX_MODEL）"
}
opencode_missing() {
  command -v opencode >/dev/null || echo "opencode"
  [ -d "$ROOT/tasks" ] || echo "tasks/"
  [ -x "$ROOT/scripts/run_opencode_tasks.sh" ] || echo "scripts/run_opencode_tasks.sh"
  [ -f "$ROOT/models/$B20" ] || echo "models/$B20"
}
status() {
  M=$("$1" | tr '\n' ' ')
  if [ -z "$M" ]; then echo "$2：就緒"; else echo "$2：未就緒，缺 $M"; fi
}

if [ "$1" = "--dry-run" ]; then
  preflight; n=$?
  if [ "$n" -eq 0 ]; then echo "第 1 階段（llama.cpp Qwen）：就緒"; else echo "第 1 階段（llama.cpp Qwen）：未就緒，$n 個問題"; fi
  status mlx_missing "第 2 階段（MLX Qwen）"
  status opencode_missing "第 3 階段（opencode）"
  echo "冷卻：組間 ${COOLDOWN}s，量測前 ${BENCH_COOLDOWN}s；量測硬碟 $DISK"
  exit 0
fi
preflight || { echo "環境檢查沒過，不開始。"; exit 1; }

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
swapouts() { vm_stat | awk '/Swapouts/ {gsub("\\.","",$2); print $2}'; }
swapused() { sysctl -n vm.swapusage | awk '{gsub("M","",$6); print int($6)}'; }
memfree() { memory_pressure | awk -F': ' '/free percentage/ {gsub("%","",$2); print $2}'; }
trips() { ls "$ROOT"/logs/THERMAL_TRIP_* 2>/dev/null | wc -l | tr -d ' '; }
memtrips() { ls "$ROOT"/logs/MEM_TRIP_* 2>/dev/null | wc -l | tr -d ' '; }
stop_server() {
  pkill -9 -f "$SRV" 2>/dev/null
  i=0; while pgrep -f "$SRV" >/dev/null && [ $i -lt 600 ]; do sleep 1; i=$((i+1)); done
}
finish() { kill "$MG" 2>/dev/null; stop_server; touch "$ROOT/logs/overnight_done"; log "end: $1"; exit 0; }
trap 'finish "收到中止訊號"' INT TERM
S0=$(swapouts); SW0=$(swapused); TRIP0=$(trips)
check_swap() { d=$(( $(swapouts) - S0 )); log "swapouts since start: +$d pages, swap used $(swapused) MB (start $SW0)"; [ "$d" -gt 65536 ] && finish "swap 增加過多，中止"; }
ensure_cool() {
  [ $(( $(trips) - TRIP0 )) -ge 2 ] && finish "熱保護本輪跳脫 2 次，停止"
  i=0; while [ "$(level)" -ge 1 ]; do [ $i -ge 2700 ] && finish "熱壓力 45 分鐘未回到 0"; sleep 30; i=$((i+30)); done
}
cool() { log "cooldown $1 s"; sleep "$1"; ensure_cool; log "cool ok, level=$(level)"; }
mem_guard() {  # 背景：伺服器在跑時檢查記憶體
  while :; do
    if pgrep -f "$SRV" >/dev/null; then
      F=$(memfree); U=$(swapused)
      if [ "${F:-100}" -lt 12 ] || [ $(( ${U:-0} - SW0 )) -gt 1024 ]; then
        T=$(date +%H%M%S); echo "free=${F}% swap=${U}MB" > "$ROOT/logs/MEM_TRIP_$T"
        pkill -9 -f "$SRV"; pkill -9 -f spec_bench.py; pkill -9 -f agent_bench.py; pkill -9 -f quality_bench.py; pkill -9 -f stream_bench.py
        echo "$(date '+%F %T') MEM_TRIP free=${F}% swap=${U}MB (start ${SW0}MB)" >> "$LOG"
      fi
    fi
    sleep 5
  done
}
wait_ready() {  # $1=檢查的路徑
  i=0
  while [ $i -lt 900 ]; do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8080$1")" = 200 ] && { log "server ready after ${i}s"; return 0; }
    # 前 5 秒不判定：start_server.sh 還沒 exec 成 llama-server 時，pgrep 會找不到
    [ $i -lt 5 ] || pgrep -f "$SRV" >/dev/null || { log "server died during load"; return 1; }
    sleep 1; i=$((i+1))
  done
  log "server not ready in 900s"; return 1
}
alive() { [ "$(trips)" -eq "$T0" ] && pgrep -f "$SRV" >/dev/null; }
measure() {  # $1=紀錄用名稱，其餘是要執行的指令；輸出存 logs/<名稱>_console.log
  M_NAME="$1"; shift
  alive || return
  cool "$BENCH_COOLDOWN"
  "$@" > "logs/${M_NAME}_console.log" 2>&1
  M_RC=$?
  log "$M_NAME exit=$M_RC : $(tr '\n' ' ' < "logs/${M_NAME}_console.log")"
}
# $1=label $2=前置冷卻 $3=llama|mlx $4=模型 $5=EXPS $6=EXTRA $7=對話格式 $8=量測項目 $9=上下文長度
# 伺服器載入失敗時回傳 1，其他情況回傳 0
run_cfg() {
  [ "$(memtrips)" -gt "$MT0" ] && finish "記憶體保護已觸發，停止"
  cool "$2"
  T0=$(trips); stop_server
  log "start server $1 backend=$3 MODEL=$4 EXPS=$5 EXTRA=[$6] CTX=$9 (free $(memfree)%)"
  if [ "$3" = llama ]; then
    MODEL="$4" EXPS="$5" EXTRA="$6" CTX="$9" BATCH=2048 scripts/start_server.sh "$1" -1 2048 &
    READY=/health
  else
    "$MLX_PY" -m mlx_lm.server --model "$4" --host 127.0.0.1 --port 8080 > "logs/server_$1_$(date +%Y%m%d_%H%M%S).log" 2>&1 &
    READY=/v1/models
  fi
  if ! wait_ready "$READY"; then
    stop_server
    log "$1 skipped; server log tail: $(tail -5 "$(ls -t logs/server_$1_*.log | head -1)" | tr '\n' ' ')"
    return 1
  fi
  log "footprint: $(footprint -p "$(pgrep -f "$SRV" | head -1)" 2>/dev/null | grep -i 'phys_footprint:' | head -1); wired: $(top -l 1 -n 0 | awk '/PhysMem/ {print $4}'); free $(memfree)%"
  case "$8" in *spec*) measure "$1" python3 -I scripts/spec_bench.py --label "$1" --fmt "$7" --n 96;; esac
  case "$8" in *agent*) measure "$1_agent" python3 -I scripts/agent_bench.py --label "$1_agent" --fmt "$7" --n 64 --pause 60;; esac
  case "$8" in *quality*) measure "$1_quality" python3 -I scripts/quality_bench.py --label "$1_quality" --pause 60;; esac
  case "$8" in *stream*) [ -f scripts/stream_bench.py ] && measure "$1_stream" python3 -I scripts/stream_bench.py --url http://127.0.0.1:8080 --label "$1_stream";; esac
  case "$8" in *opencode*) measure "$1_opencode" scripts/run_opencode_tasks.sh "$1";; esac
  stop_server; check_swap
  [ "$(trips)" -gt "$T0" ] && { log "$1 因熱保護中止"; cool 1800; }
  return 0
}

rm -f "$ROOT/logs/overnight_done"
# 用 if，不用「pgrep || 腳本 &」：後者會多一個名為 run_mini.sh 的子 shell 等待腳本結束，
# 而 resource_log 的迴圈要等 run_mini.sh 消失才停，兩邊會互等。
if ! pgrep -f thermal_guard.sh >/dev/null; then scripts/thermal_guard.sh & fi
MT0=$(memtrips)
mem_guard & MG=$!
if ! pgrep -f resource_log.sh >/dev/null; then scripts/resource_log.sh & fi
log "mini test start: $(chip), $(ram_gb) GB, swap used ${SW0}MB, free $(memfree)%"

log "第 1 階段：llama.cpp Qwen"
run_cfg mini_q_gpu "$COOLDOWN" llama "$QWEN" GPU "" chatml spec,agent,quality,stream 8192 || {
  log "EXPS=GPU 載入失敗，退回 exps=CPU"
  run_cfg mini_q_cpu "$COOLDOWN" llama "$QWEN" CPU "" chatml spec,agent,quality,stream 8192
}

log "第 2 階段：MLX Qwen"
M=$(mlx_missing | tr '\n' ' ')
if [ -z "$M" ]; then
  run_cfg mini_q_mlx "$COOLDOWN" mlx "$MLX_MODEL" - "" chatml quality,stream 8192
else
  log "第 2 階段跳過，缺 $M"
fi

log "第 3 階段：opencode"
M=$(opencode_missing | tr '\n' ' ')
if [ -z "$M" ]; then
  run_cfg mini_oc_qwen "$COOLDOWN" llama "$QWEN" GPU "--jinja" chatml opencode 32768
  run_cfg mini_oc_20b "$COOLDOWN" llama "$B20" GPU "--jinja" harmony opencode 32768
else
  log "第 3 階段跳過，缺 $M"
fi
finish "全部完成"
