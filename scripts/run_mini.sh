#!/bin/sh
# Mac mini（M6、32GB）的測試流程。用法：
#   scripts/run_mini.sh --dry-run          只檢查環境、列出會做什麼，不載入模型、不寫紀錄（任何機器都能跑）
#   scripts/run_mini.sh                    正式執行，請放背景；只有 M6、32GB 以上的機器才會真的開始
#   scripts/run_mini.sh --air-check        在 Air 上用 20b 驗證工具：stream_bench 對帳、opencode 試跑一題
#   scripts/run_mini.sh --air-qwen-tools   在 Air 上驗證 Qwen 的工具呼叫格式：opencode 跑兩輪工具呼叫就停，不判對錯
#
# 順序：
#   第 0 階段  Ollama 對照：Ollama 的 gpt-oss:latest、llama-server 跑專案的 20b、llama-server 跑 Ollama 的 blob
#   第 1 階段  llama.cpp 跑 Qwen3-Coder：先試整個放 GPU（EXPS=GPU），載入失敗才退回 exps=CPU
#   第 2 階段  MLX 跑 Qwen3-Coder，和第 1 階段用同一把尺比較
#   第 3 階段  opencode 跑多檔案題目，每題 3 次：Qwen、Qwen 加 ngram-mod、20b
#   第 4 階段  先量硬碟隨機讀取（randread.py），再跑 120b 的 -ub 8192 agent_bench，有無 ngram-mod 各一組，記錄生成時每個 token 讀多少 MB
#
# 依賴的東西缺了就跳過並記錄原因，不會下載或安裝任何東西。有跳過、載入失敗或量測失敗時，結尾不會寫「全部完成」。
#   第 0 階段：ollama 服務、$OLLAMA_MODEL、scripts/ollama_bench.py、models/$B20
#   第 2 階段：scripts/stream_bench.py、$MLX_PY（裝好 mlx-lm 的 python）、$MLX_MODEL（MLX 模型資料夾）
#   第 3 階段：opencode（PATH 上或 .tools/opencode/）、tasks/、scripts/run_opencode_tasks.sh
#   第 4 階段：models/$B120
#
# 這台 mini 是共用的：Ollama 平常在跑，也有派工任務和另一個帳號。不要 ollama rm，不要改 OLLAMA_MODELS（Codex總攬 在用）。
#   開始前 ollama ps 必須是空的，也不能有其他重負載；每組開始前會再確認一次，最多等 30 分鐘，等不到就跳過該組。
#   ALLOW_BUSY=1 可以忽略一般重負載（CPU >=100% 或記憶體 >=4GB 的程序），但不會忽略 Ollama 已載入的模型。
#
# 安全規則同第 4、6、7 項：組間冷卻 20 分鐘且熱壓力 0；量測前冷卻 5 分鐘；thermal_guard 熱壓力 >=1 立即 SIGKILL；
#   本輪跳脫 2 次全部停止；記憶體保護（可用 <12% 或 swap 多 1GB）立即 SIGKILL。不改任何系統設定。
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export FLASHBACK_ROOT="$ROOT"
MODE=mini
case "$1" in --air-check) MODE=air;; --air-qwen-tools) MODE=air_qwen;; esac
if [ "$MODE" = mini ]; then export DISK="${DISK:-disk0}"; else export DISK="${DISK:-disk4}"; fi   # resource_log 量測的硬碟；mini 的內建 SSD 是 disk0
cd "$ROOT" || exit 1
# opencode 裝在專案內時用它，設定和資料也留在專案內
if [ -d "$ROOT/.tools/opencode/node_modules/.bin" ]; then
  PATH="$ROOT/.tools/opencode/node_modules/.bin:$PATH"
  export XDG_CONFIG_HOME="$ROOT/.tools/xdg/config" XDG_DATA_HOME="$ROOT/.tools/xdg/data" \
    XDG_CACHE_HOME="$ROOT/.tools/xdg/cache" XDG_STATE_HOME="$ROOT/.tools/xdg/state"
fi

QWEN=Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf
B20=gpt-oss-20b-MXFP4.gguf
B120=gpt-oss-120b-MXFP4.gguf
MLX_PY="${MLX_PY:-$ROOT/.venv-mlx/bin/python}"
MLX_MODEL="${MLX_MODEL:-$ROOT/models/mlx/Qwen3-Coder-30B-A3B-4bit}"
OLLAMA_MODEL="${OLLAMA_MODEL:-gpt-oss:latest}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
COOLDOWN="${COOLDOWN:-1200}"
BENCH_COOLDOWN="${BENCH_COOLDOWN:-300}"
SRV='llama-server -m|mlx_lm.server'
GUARD_PAT="$SRV|ollama_bench.py"
LOG="$ROOT/logs/mini.log"
RUN_BATCH=2048; RUN_UB=2048   # 第 4 階段改成 8192
OLLAMA_USED=0; PROBLEMS=""

level() { notifyutil -g com.apple.system.thermalpressurelevel | awk '{print $2}'; }
chip() { sysctl -n machdep.cpu.brand_string; }
ram_gb() { echo $(( $(sysctl -n hw.memsize) / 1073741824 )); }

# 每行一個正在影響量測的負載，沒有就不輸出。紀錄要公開，所以不印帳號和完整路徑。
ollama_loaded() { command -v ollama >/dev/null && ollama ps 2>/dev/null | tail -n +2 | awk 'NF {print $1}'; }
other_load() {
  ollama_loaded | sed 's/^/Ollama 已載入 /'
  pgrep -f 'ollama runner' | sed 's/^/Ollama 的執行程序 pid /'   # 這段文字不能含 pgrep 的樣式，否則 sed 會比對到自己
  [ "${ALLOW_BUSY:-0}" = 1 ] && return
  ps -Ao pid=,pcpu=,rss=,comm= | awk '$2>=100 || $3>=4194304 {
    c=substr($0, index($0,$4)); sub(/.*\//,"",c); printf "重負載 pid %s cpu %s%% rss %dMB %s\n",$1,$2,$3/1024,c }'
}

# 回傳值 = 第一個量測階段無法開始的原因數
preflight() {
  bad=0
  echo "機器：$(chip)，$(ram_gb) GB，熱壓力 $(level)"
  case "$MODE" in
    mini)
      case "$(chip)" in *M6*) ;; *) echo "  ✗ 不是 M6，正式執行會被拒絕"; bad=$((bad+1));; esac
      [ "$(ram_gb)" -ge 32 ] || { echo "  ✗ 記憶體不到 32 GB，正式執行會被拒絕"; bad=$((bad+1)); }
      [ -f "$ROOT/models/$QWEN" ] || { echo "  ✗ 缺模型 models/$QWEN"; bad=$((bad+1)); };;
    air) [ -f "$ROOT/models/$B20" ] || { echo "  ✗ 缺模型 models/$B20"; bad=$((bad+1)); };;
    air_qwen) [ -f "$ROOT/models/$QWEN" ] || { echo "  ✗ 缺模型 models/$QWEN"; bad=$((bad+1)); };;
  esac
  [ "$(level)" = 0 ] || { echo "  ✗ 熱壓力不是 0"; bad=$((bad+1)); }
  command -v llama-server >/dev/null || { echo "  ✗ 找不到 llama-server"; bad=$((bad+1)); }
  pgrep -f "$SRV" >/dev/null && { echo "  ✗ 已經有推論伺服器在跑"; bad=$((bad+1)); }
  B=$(other_load)
  if [ -n "$B" ]; then echo "$B" | sed 's/^/  ✗ /'; bad=$((bad+1)); fi
  return "$bad"
}
ollama_missing() {
  [ -f "$ROOT/scripts/ollama_bench.py" ] || echo "scripts/ollama_bench.py"
  [ -f "$ROOT/models/$B20" ] || echo "models/$B20"
  if ! command -v ollama >/dev/null; then echo "ollama"; return; fi
  ollama ps >/dev/null 2>&1 || { echo "Ollama 服務"; return; }
  ollama show "$OLLAMA_MODEL" >/dev/null 2>&1 || echo "Ollama 模型 $OLLAMA_MODEL"
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
q120_missing() { [ -f "$ROOT/models/$B120" ] || echo "models/$B120"; }
status() {
  M=$("$1" | tr '\n' ' ')
  if [ -z "$M" ]; then echo "$2：就緒"; else echo "$2：未就緒，缺 $M"; fi
}

if [ "$1" = "--dry-run" ]; then
  preflight; n=$?
  status ollama_missing "第 0 階段（Ollama 對照）"
  if [ "$n" -eq 0 ]; then echo "第 1 階段（llama.cpp Qwen）：就緒"; else echo "第 1 階段（llama.cpp Qwen）：未就緒，$n 個問題"; fi
  status mlx_missing "第 2 階段（MLX Qwen）"
  status opencode_missing "第 3 階段（opencode）"
  status q120_missing "第 4 階段（120b）"
  echo "冷卻：組間 ${COOLDOWN}s，量測前 ${BENCH_COOLDOWN}s；量測硬碟 $DISK"
  exit 0
fi
preflight || { echo "環境檢查沒過，不開始。"; exit 1; }

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
problem() { PROBLEMS="${PROBLEMS}${PROBLEMS:+；}$1"; log "問題：$1"; }
swapouts() { vm_stat | awk '/Swapouts/ {gsub("\\.","",$2); print $2}'; }
swapused() { sysctl -n vm.swapusage | awk '{gsub("M","",$6); print int($6)}'; }
memfree() { memory_pressure | awk -F': ' '/free percentage/ {gsub("%","",$2); print $2}'; }
trips() { ls "$ROOT"/logs/THERMAL_TRIP_* 2>/dev/null | wc -l | tr -d ' '; }
memtrips() { ls "$ROOT"/logs/MEM_TRIP_* 2>/dev/null | wc -l | tr -d ' '; }
stop_server() {
  pkill -9 -f "$SRV" 2>/dev/null
  i=0; while pgrep -f "$SRV" >/dev/null && [ $i -lt 600 ]; do sleep 1; i=$((i+1)); done
}
# 只卸載自己載入的模型，不動 Ollama 服務本身
ollama_unload() { curl -s -m 60 "$OLLAMA_URL/api/generate" -d "{\"model\":\"$OLLAMA_MODEL\",\"keep_alive\":0}" >/dev/null; }
finish() {
  kill "$MG" 2>/dev/null; stop_server
  [ "$OLLAMA_USED" = 1 ] && ollama_unload
  touch "$ROOT/logs/overnight_done"; log "end: $1"; exit 0
}
trap 'finish "收到中止訊號"' INT TERM
S0=$(swapouts); SW0=$(swapused); TRIP0=$(trips)
check_swap() { d=$(( $(swapouts) - S0 )); log "swapouts since start: +$d pages, swap used $(swapused) MB (start $SW0)"; [ "$d" -gt 65536 ] && finish "swap 增加過多，中止"; }
ensure_cool() {
  [ $(( $(trips) - TRIP0 )) -ge 2 ] && finish "熱保護本輪跳脫 2 次，停止"
  i=0; while [ "$(level)" -ge 1 ]; do [ $i -ge 2700 ] && finish "熱壓力 45 分鐘未回到 0"; sleep 30; i=$((i+30)); done
}
cool() { log "cooldown $1 s"; sleep "$1"; ensure_cool; log "cool ok, level=$(level)"; }
wait_quiet() {  # 等其他負載結束，最多 30 分鐘。回傳 1 表示等不到
  i=0
  while :; do
    B=$(other_load | tr '\n' ';')
    [ -z "$B" ] && return 0
    [ $i -eq 0 ] && log "等其他負載結束：$B"
    [ $i -ge 1800 ] && { log "其他負載 30 分鐘未結束：$B"; return 1; }
    sleep 60; i=$((i+60))
  done
}
mem_guard() {  # 背景：伺服器或 Ollama 量測在跑時檢查記憶體
  while :; do
    if pgrep -f "$GUARD_PAT" >/dev/null; then
      F=$(memfree); U=$(swapused)
      if [ "${F:-100}" -lt 12 ] || [ $(( ${U:-0} - SW0 )) -gt 1024 ]; then
        T=$(date +%H%M%S); echo "free=${F}% swap=${U}MB" > "$ROOT/logs/MEM_TRIP_$T"
        pkill -9 -f "$SRV"; pkill -9 -f spec_bench.py; pkill -9 -f agent_bench.py; pkill -9 -f quality_bench.py; pkill -9 -f stream_bench.py; pkill -f opencode_tasks.py
        if pgrep -f ollama_bench.py >/dev/null; then pkill -9 -f ollama_bench.py; ollama_unload; fi
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
  alive || { problem "$M_NAME 沒有量測：伺服器已停止或熱保護跳脫"; return; }
  cool "$BENCH_COOLDOWN"
  "$@" > "logs/${M_NAME}_console.log" 2>&1
  M_RC=$?
  log "$M_NAME exit=$M_RC : $(tr '\n' ' ' < "logs/${M_NAME}_console.log")"
  [ "$M_RC" -eq 0 ] || problem "$M_NAME 量測失敗（exit=$M_RC）"
}
# $1=label $2=前置冷卻 $3=llama|mlx $4=模型 $5=EXPS $6=EXTRA $7=對話格式 $8=量測項目 $9=上下文長度
# 回傳 0：伺服器有起來；1：載入失敗；2：被其他負載擋住，沒有嘗試
run_cfg() {
  [ "$(memtrips)" -gt "$MT0" ] && finish "記憶體保護已觸發，停止"
  cool "$2"
  T0=$(trips); stop_server
  wait_quiet || { problem "$1 跳過：其他負載未結束"; return 2; }
  log "start server $1 backend=$3 MODEL=$(basename "$4") EXPS=$5 EXTRA=[$6] CTX=$9 BATCH=$RUN_BATCH UB=$RUN_UB (free $(memfree)%)"
  if [ "$3" = llama ]; then
    MODEL="$4" EXPS="$5" EXTRA="$6" CTX="$9" BATCH="$RUN_BATCH" scripts/start_server.sh "$1" -1 "$RUN_UB" &
    READY=/health
  else
    "$MLX_PY" -m mlx_lm server --model "$4" > "logs/server_$1_$(date +%Y%m%d_%H%M%S).log" 2>&1 &   # 預設 localhost:8080
    READY=/v1/models
  fi
  if ! wait_ready "$READY"; then
    stop_server
    log "$1 skipped; server log tail: $(tail -5 "$(ls -t logs/server_$1_*.log | head -1)" | tr '\n' ' ' | sed "s#$HOME#~#g")"
    return 1
  fi
  log "footprint: $(footprint -p "$(pgrep -f "$SRV" | head -1)" 2>/dev/null | grep -i 'phys_footprint:' | head -1); wired: $(top -l 1 -n 0 | awk '/PhysMem/ {print $4}'); free $(memfree)%"
  case "$8" in *spec*) measure "$1" python3 -I scripts/spec_bench.py --label "$1" --fmt "$7" --n 96;; esac
  case "$8" in *agent*) measure "$1_agent" python3 -I scripts/agent_bench.py --label "$1_agent" --fmt "$7" --n 64 --pause 60;; esac
  case "$8" in *ub120*) measure "$1_agent" python3 -I scripts/agent_bench.py --label "$1_agent" --fmt "$7" --t1 agent_long.txt --turns t1_long,t2_followup --n 64 --pause 300;; esac
  case "$8" in *quality*) measure "$1_quality" python3 -I scripts/quality_bench.py --label "$1_quality" --pause 60;; esac
  case "$8" in *stream*) [ -f scripts/stream_bench.py ] && measure "$1_stream" python3 -I scripts/stream_bench.py --url http://127.0.0.1:8080 --label "$1_stream";; esac
  case "$8" in *opencode*) measure "$1_opencode" scripts/run_opencode_tasks.sh "$1";; esac
  stop_server; check_swap
  [ "$(trips)" -gt "$T0" ] && { problem "$1 因熱保護中止"; cool 1800; }
  return 0
}
# 同 run_cfg，但載入失敗也算問題
must() { run_cfg "$@"; [ $? -eq 1 ] && problem "$1 載入失敗"; }
run_ollama() {  # $1=label $2=前置冷卻
  [ "$(memtrips)" -gt "$MT0" ] && finish "記憶體保護已觸發，停止"
  cool "$2"
  T0=$(trips); stop_server
  wait_quiet || { problem "$1 跳過：其他負載未結束"; return; }
  log "start $1 MODEL=$OLLAMA_MODEL num_ctx=8192 (free $(memfree)%)"
  OLLAMA_USED=1
  python3 -I scripts/ollama_bench.py --url "$OLLAMA_URL" --model "$OLLAMA_MODEL" --label "$1" --n 96 --num-ctx 8192 \
    --settle "$BENCH_COOLDOWN" --pause "${OLLAMA_PAUSE:-60}" > "logs/$1_console.log" 2>&1
  RC=$?
  ollama_unload   # 腳本被 SIGKILL 時來不及自己卸載
  log "$1 exit=$RC : $(tr '\n' ' ' < "logs/$1_console.log")"
  log "$1 結束後 ollama ps：[$(ollama_loaded | tr '\n' ' ')]"
  [ "$RC" -eq 0 ] || problem "$1 量測失敗（exit=$RC）"
  check_swap
  [ "$(trips)" -gt "$T0" ] && { problem "$1 因熱保護中止"; cool 1800; }
}
run_randread() {  # 量這台機器放模型的硬碟，用來把 120b 的 tok/s 提升拆成硬碟和快取各佔多少
  [ "$(memtrips)" -gt "$MT0" ] && finish "記憶體保護已觸發，停止"
  cool "$BENCH_COOLDOWN"
  stop_server
  wait_quiet || { problem "randread 跳過：其他負載未結束"; return; }
  log "start randread"
  python3 -I scripts/randread.py > "logs/mini_randread_console.log" 2>&1
  RC=$?
  log "randread exit=$RC : $(tr '\n' ' ' < "logs/mini_randread_console.log")"
  [ "$RC" -eq 0 ] || problem "randread 量測失敗（exit=$RC）"
  grep -q '熱壓力 >=1' "logs/mini_randread_console.log" && problem "randread 因熱壓力提早停止"
}
# 跑 Qwen 的 opencode 組。Q_EXPS 是目前已知可行的放法：GPU、CPU，或 none（兩種都載入失敗）
run_qwen_oc() {  # $1=label $2=EXTRA
  [ "$Q_EXPS" = none ] && { problem "$1 跳過：Qwen 兩種放法都載入失敗"; return; }
  if [ "$Q_EXPS" = GPU ]; then
    run_cfg "$1" "$COOLDOWN" llama "$QWEN" GPU "$2" chatml opencode 32768
    RC=$?
    [ "$RC" -eq 1 ] || return
    log "$1 EXPS=GPU 載入失敗（ctx 32768），退回 exps=CPU"
    Q_EXPS=CPU
  fi
  run_cfg "$1_cpu" "$COOLDOWN" llama "$QWEN" CPU "$2" chatml opencode 32768
  RC=$?
  [ "$RC" -eq 1 ] && { problem "$1 EXPS=CPU 也載入失敗"; Q_EXPS=none; }
}

rm -f "$ROOT/logs/overnight_done"
# 用 if，不用「pgrep || 腳本 &」：後者會多一個名為 run_mini.sh 的子 shell 等待腳本結束，
# 而 resource_log 的迴圈要等 run_mini.sh 消失才停，兩邊會互等。
if ! pgrep -f thermal_guard.sh >/dev/null; then scripts/thermal_guard.sh & fi
MT0=$(memtrips)
mem_guard & MG=$!
if ! pgrep -f resource_log.sh >/dev/null; then scripts/resource_log.sh & fi
log "mini test start: $(chip), $(ram_gb) GB, swap used ${SW0}MB, free $(memfree)%"

if [ "$MODE" = air ]; then
  must air_20b_stream "$COOLDOWN" llama "$B20" GPU "" harmony stream 8192
  M=$(opencode_missing | tr '\n' ' ')
  if [ -z "$M" ]; then
    export OPENCODE_TASKS=invoice_rounding
    must air_oc_20b "$COOLDOWN" llama "$B20" GPU "--jinja" harmony opencode 32768
  else
    problem "opencode 試跑跳過，缺 $M"
  fi
  finish "Air 驗證結束${PROBLEMS:+，有問題：$PROBLEMS}"
fi

if [ "$MODE" = air_qwen ]; then
  # Air 的 GPU 放不下整個 Qwen，用 exps=CPU；提示詞約 1 萬 token，所以 ctx 16384 就夠，記憶體比 32768 省
  M=$(opencode_missing | tr '\n' ' ')
  if [ -z "$M" ]; then
    export OPENCODE_TASKS=invoice_rounding OPENCODE_STOP_AFTER=2 OPENCODE_TIMEOUT=2400
    must air_oc_qwen_fmt "$COOLDOWN" llama "$QWEN" CPU "--jinja" chatml opencode 16384
  else
    problem "Qwen 工具呼叫驗證跳過，缺 $M"
  fi
  finish "Air Qwen 工具呼叫驗證結束${PROBLEMS:+，有問題：$PROBLEMS}"
fi

log "第 0 階段：Ollama 對照"
M=$(ollama_missing | tr '\n' ' ')
if [ -z "$M" ]; then
  run_ollama mini_20b_ollama "$COOLDOWN"
  must mini_20b_gguf "$COOLDOWN" llama "$B20" GPU "" harmony stream 8192
  # llama-server 直接載入 Ollama 的 blob，才分得清差距來自引擎還是模型檔。只讀取，不改 Ollama 的任何東西
  BLOB=$(ollama show --modelfile "$OLLAMA_MODEL" 2>/dev/null | sed -n 's/^FROM \(\/.*\)$/\1/p' | head -1)   # 路徑可能有空格，不能用 awk 切欄
  if [ -z "$BLOB" ] || [ ! -r "$BLOB" ]; then
    problem "mini_20b_blob 跳過：找不到或沒有權限讀取 Ollama 的 blob（${BLOB##*/}）"
  else
    log "Ollama blob：${BLOB##*/}，$(stat -f %z "$BLOB") bytes"
    run_cfg mini_20b_blob "$COOLDOWN" llama "$BLOB" GPU "" harmony stream 8192
    RC=$?
    SL=$(ls -t logs/server_mini_20b_blob_*.log 2>/dev/null | head -1)
    [ -n "$SL" ] && sed -i '' "s#$HOME#~#g" "$SL"   # 伺服器日誌會印模型路徑，裡面有帳號名稱，而 logs/ 要公開
    if [ "$RC" -eq 1 ]; then
      log "Ollama blob 載入失敗，原因：$(grep -iE 'error|unknown|failed' "$SL" | tail -3 | tr '\n' ' ')。這樣 Ollama 對 llama-server 的差距分不開引擎和模型檔。"
    fi
  fi
else
  problem "第 0 階段跳過，缺 $M"
fi

log "第 1 階段：llama.cpp Qwen"
Q_EXPS=GPU
run_cfg mini_q_gpu "$COOLDOWN" llama "$QWEN" GPU "" chatml spec,agent,quality,stream 8192
if [ $? -eq 1 ]; then
  log "EXPS=GPU 載入失敗，退回 exps=CPU"
  Q_EXPS=CPU
  run_cfg mini_q_cpu "$COOLDOWN" llama "$QWEN" CPU "" chatml spec,agent,quality,stream 8192
  [ $? -eq 1 ] && { problem "Qwen 兩種放法都載入失敗"; Q_EXPS=none; }
fi

log "第 2 階段：MLX Qwen"
M=$(mlx_missing | tr '\n' ' ')
if [ -z "$M" ]; then
  must mini_q_mlx "$COOLDOWN" mlx "$MLX_MODEL" - "" chatml quality,stream 8192
else
  problem "第 2 階段跳過，缺 $M"
fi

log "第 3 階段：opencode"
M=$(opencode_missing | tr '\n' ' ')
if [ -z "$M" ]; then
  export OPENCODE_REPEATS="${OPENCODE_REPEATS:-3}"
  unset OPENCODE_TASKS
  run_qwen_oc mini_oc_qwen "--jinja"
  run_qwen_oc mini_oc_qwen_ngram "--jinja --spec-type ngram-mod"
  must mini_oc_20b "$COOLDOWN" llama "$B20" GPU "--jinja" harmony opencode 32768
else
  problem "第 3 階段跳過，缺 $M"
fi

log "第 4 階段：120b"
M=$(q120_missing | tr '\n' ' ')
if [ -z "$M" ]; then
  run_randread
  RUN_BATCH=8192; RUN_UB=8192   # 和 Air 第 2 項相同：-c 16384 -b 8192 -ub 8192，提示詞 agent_long.txt
  must mini_120b_ub8192 "$COOLDOWN" llama "$B120" CPU "" harmony ub120 16384
  must mini_120b_ub8192_ngram "$COOLDOWN" llama "$B120" CPU "--spec-type ngram-mod" harmony ub120 16384
  RUN_BATCH=2048; RUN_UB=2048
else
  problem "第 4 階段跳過，缺 $M"
fi

if [ -z "$PROBLEMS" ]; then finish "全部完成"; else finish "流程結束，但有問題：$PROBLEMS"; fi
