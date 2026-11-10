#!/bin/sh
# Mac mini（M6、32GB）的測試流程。用法：
#   scripts/run_mini.sh --dry-run          只檢查環境、列出會做什麼，不載入模型、不寫紀錄（任何機器都能跑）
#   scripts/run_mini.sh                    正式執行，請放背景；只有 M6、32GB 以上的機器才會真的開始
#   scripts/run_mini.sh --air-check        在 Air 上用 20b 驗證工具：stream_bench 對帳、opencode 試跑一題
#   scripts/run_mini.sh --air-qwen-tools   在 Air 上驗證 Qwen 的工具呼叫格式：opencode 跑兩輪工具呼叫就停，不判對錯
#   MLX_MODEL=<資料夾> scripts/run_mini.sh --air-mlx   在 Air 上用小模型走一遍 MLX 流程，只驗流程，速度沒有參考價值
#   PHASES="1 3v 4" scripts/run_mini.sh    只跑列出的階段（空白分隔，預設 "0 1 2 3 4"）。3v = 第 1 階段後用 opencode 讓 Qwen 跑 1 題，確認設定可用，不算可靠度
#   QWEN_MODEL、QWEN_TAG                   換 Qwen 模型檔（models/ 下的檔名）和紀錄名稱後綴（第 1、3v、3 階段）
#   QWEN_EXPS=CPU                       Qwen 直接用 exps=CPU（預設先試整個放 GPU）
#   VERIFY_EXTRA、VERIFY_LABEL             3v 的伺服器參數和紀錄名稱（預設 "--jinja"、mini_oc_qwen${QTAG}_verify）
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
#   第 3 階段：opencode（OPENCODE_BIN、.tools/opencode/ 或 PATH 上）、tasks/、scripts/run_opencode_tasks.sh
#   第 4 階段：models/$B120
# 第 3 階段開始前先用 20b 跑一題當煙霧測試：write_config 只在 opencode 1.19.5 驗證過，其他版本不通過就跳過整個階段。
# 開始前要求 python3 >= 3.11（判題用，系統的 3.9 只要有 python3.14 等就會自動換掉）、llama.cpp build >= 12110 且支援 ngram-mod。
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
case "$1" in --air-check) MODE=air;; --air-qwen-tools) MODE=air_qwen;; --air-mlx) MODE=air_mlx;; esac
if [ "$MODE" = mini ]; then export DISK="${DISK:-disk0}"; else export DISK="${DISK:-disk4}"; fi   # resource_log 量測的硬碟；mini 的內建 SSD 是 disk0
cd "$ROOT" || exit 1
# opencode 的設定和資料一律留在專案內，不碰這個帳號的 ~/.config、~/.local（mini 上派工也在用）
export XDG_CONFIG_HOME="$ROOT/.tools/xdg/config" XDG_DATA_HOME="$ROOT/.tools/xdg/data" \
  XDG_CACHE_HOME="$ROOT/.tools/xdg/cache" XDG_STATE_HOME="$ROOT/.tools/xdg/state"
# mlx-lm 的 /v1/models 會掃 Hugging Face 快取，資料夾不存在就丟例外
mkdir -p "$XDG_CACHE_HOME/huggingface/hub"
# 優先順序：OPENCODE_BIN、專案內的 .tools、PATH 上的 opencode
if [ -z "$OPENCODE_BIN" ] && [ -x "$ROOT/.tools/opencode/node_modules/.bin/opencode" ]; then
  OPENCODE_BIN="$ROOT/.tools/opencode/node_modules/.bin/opencode"
fi
export OPENCODE_BIN="${OPENCODE_BIN:-opencode}"
OPENCODE_VERIFIED=1.19.5
opencode_version() { "$OPENCODE_BIN" --version 2>/dev/null | head -1; }

# 判題和模型寫的程式都用 python3。系統的 3.9 會讓 int | None、match 這類語法失敗，通過率就變成環境問題
py_ok() { "$1" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; }
if ! py_ok python3; then
  for c in python3.14 python3.13 python3.12 python3.11; do
    P=$(command -v "$c") || continue
    py_ok "$P" || continue
    mkdir -p "$ROOT/.tools/pybin"; ln -sf "$P" "$ROOT/.tools/pybin/python3"
    PATH="$ROOT/.tools/pybin:$PATH"; break
  done
fi
LLAMA_MIN_BUILD=12110   # Air 測試用的版本
llama_build() { llama-server --version 2>&1 | sed -n 's/.*build \([0-9][0-9]*\).*/\1/p' | head -1; }

QWEN="${QWEN_MODEL:-Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf}"
QTAG="${QWEN_TAG:-}"   # 換模型時加在第 1 階段紀錄名稱上，例如 _36 → mini_q_36_cpu
B20=gpt-oss-20b-MXFP4.gguf
B120=gpt-oss-120b-MXFP4.gguf
MLX_PY="${MLX_PY:-$ROOT/.venv-mlx/bin/python}"
MLX_MODEL="${MLX_MODEL:-$ROOT/models/mlx/Qwen3-Coder-30B-A3B-4bit}"
MLX_VER=0.32.2
OLLAMA_MODEL="${OLLAMA_MODEL:-gpt-oss:latest}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
COOLDOWN="${COOLDOWN:-1200}"
BENCH_COOLDOWN="${BENCH_COOLDOWN:-300}"
SRV='llama-server -m|mlx_lm.server'
GUARD_PAT="$SRV|ollama_bench.py"
LOG="$ROOT/logs/mini.log"
RUN_BATCH=2048; RUN_UB=2048   # 第 4 階段改成 8192
OLLAMA_USED=0; PROBLEMS=""
PHASES="${PHASES:-0 1 2 3 4}"
phase_on() { case " $PHASES " in *" $1 "*) return 0;; esac; return 1; }

# 讀不到等級（空字串或非數字）時當成 1：看不到熱壓力就當作不安全，不當成正常
level() { L=$(notifyutil -g com.apple.system.thermalpressurelevel 2>/dev/null | awk '{print $2}'); case "$L" in ''|*[!0-9]*) echo 1;; *) echo "$L";; esac; }
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
    air_mlx) M=$(mlx_missing | tr '\n' ' '); [ -z "$M" ] || { echo "  ✗ 缺 $M"; bad=$((bad+1)); };;
  esac
  [ "$(level)" = 0 ] || { echo "  ✗ 熱壓力不是 0"; bad=$((bad+1)); }
  echo "python3：$(python3 --version 2>&1)"
  py_ok python3 || { echo "  ✗ python3 要 3.11 以上（可以 brew install python@3.14）"; bad=$((bad+1)); }
  if command -v llama-server >/dev/null; then
    LB=$(llama_build); echo "llama.cpp build：${LB:-未知}"
    if [ "${ALLOW_LLAMA_BUILD:-0}" != 1 ] && { [ -z "$LB" ] || [ "$LB" -lt "$LLAMA_MIN_BUILD" ]; }; then
      echo "  ✗ llama.cpp 比 Air 測試用的 build $LLAMA_MIN_BUILD 舊，先 brew update 再升級（ALLOW_LLAMA_BUILD=1 可略過）"; bad=$((bad+1))
    fi
    llama-server --help 2>&1 | grep -q 'ngram-mod' || { echo "  ✗ llama-server 不支援 --spec-type ngram-mod"; bad=$((bad+1)); }
  else
    echo "  ✗ 找不到 llama-server"; bad=$((bad+1))
  fi
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
  V=""
  [ -x "$MLX_PY" ] && V=$("$MLX_PY" -c 'import sys, mlx_lm; assert sys.version_info >= (3, 11); print(mlx_lm.__version__)' 2>/dev/null)
  [ "$V" = "$MLX_VER" ] || echo "mlx-lm $MLX_VER（$MLX_PY 目前是 ${V:-無法載入，或 Python 低於 3.11}）"
  [ -d "$MLX_MODEL" ] || echo "MLX 模型（$MLX_MODEL）"
}
opencode_missing() {
  command -v "$OPENCODE_BIN" >/dev/null || echo "opencode"
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
  echo "  opencode 版本：$(opencode_version)（設定格式在 $OPENCODE_VERIFIED 驗證過，開跑時會先做煙霧測試）"
  status q120_missing "第 4 階段（120b）"
  echo "冷卻：組間 ${COOLDOWN}s，量測前 ${BENCH_COOLDOWN}s；量測硬碟 $DISK"
  echo "這次會跑的階段：$PHASES"
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
finish() {  # $1=結束原因 $2=ok 表示流程正常走完；沒有 ok 或 PROBLEMS 不是空的就回傳 1
  kill "$MG" 2>/dev/null; stop_server
  [ "$OLLAMA_USED" = 1 ] && ollama_unload
  log "end: $1"
  R=$(sh "$ROOT/scripts/scrub_logs.sh" 2>&1) || R="$R（還有殘留，推送前要處理）"
  log "$R"
  touch "$ROOT/logs/overnight_done"
  [ "${2:-}" = ok ] && [ -z "$PROBLEMS" ] && exit 0
  exit 1
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
# 伺服器就緒不代表能推論：--no-warmup 時 Metal 記憶體不足可能到第一次推論才出錯，MLX 的模型也是在背景才載入，
# /v1/models 回 200 時可能還沒載完。實際要 1 個 token，失敗就算載入失敗；這也讓後面量到的首 token 時間不含載入。
probe_server() {
  P0=$(date +%s)
  CODE=$(curl -s -m 900 -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' \
    -d '{"messages":[{"role":"user","content":"hi"}],"max_tokens":1,"temperature":0}' http://127.0.0.1:8080/v1/chat/completions)
  log "probe 1 token: http=$CODE, $(( $(date +%s) - P0 ))s"
  [ "$CODE" = 200 ] && pgrep -f "$SRV" >/dev/null
}
# 別人中途載入模型時標記該組。resource_log.sh 每次取樣都會寫 ollama_ps.log
OP="$ROOT/logs/ollama_ps.log"
op_mark() { OP0=0; [ -f "$OP" ] && OP0=$(wc -l < "$OP" | tr -d ' '); }
op_check() {  # $1=label $2=自己載入的模型（可省略）
  [ -f "$OP" ] || return
  S=$(tail -n +$((OP0+1)) "$OP" | cut -d, -f2- | grep -vxF "${2:-}" | sort -u | tr '\n' ' ')
  [ -n "$S" ] && problem "$1 量測期間 Ollama 載入了 $S，這組數據可能受影響"
}
alive() { [ "$(trips)" -eq "$T0" ] && pgrep -f "$SRV" >/dev/null; }
# 每組設定寫一份 logs/<label>_meta_<時間>.json：模型檔、參數、llama.cpp 版本、opencode 版本。
# 同一組的 jsonl 都用 <label> 開頭（例如 <label>_agent_*.jsonl），靠名稱對回這份；換模型時 QWEN_TAG 讓名稱不撞
write_meta() {  # 參數同 run_cfg
  MF="logs/$1_meta_$(date +%Y%m%d_%H%M%S).json"
  LBV=$(llama-server --version 2>&1 | grep -m1 -i 'version' | tr -d '"\\')
  OCV=""; case "$8" in *opencode*) OCV=$(opencode_version | tr -d '"\\');; esac
  printf '{"label":"%s","backend":"%s","model_file":"%s","model_bytes":%s,"exps":"%s","extra":"%s","fmt":"%s","items":"%s","ctx":"%s","batch":"%s","ubatch":"%s","llama_version":"%s","opencode_version":"%s","started":"%s"}\n' \
    "$1" "$3" "$(basename "$4")" "$(stat -f %z "$4" 2>/dev/null || echo null)" "$5" "$6" "$7" "$8" "$9" "$RUN_BATCH" "$RUN_UB" "$LBV" "$OCV" "$(date '+%F %T')" > "$MF"
}
measure() {  # $1=紀錄用名稱，其餘是要執行的指令；輸出存 logs/<名稱>_console.log
  M_NAME="$1"; shift
  alive || { problem "$M_NAME 沒有量測：伺服器已停止或熱保護跳脫"; return; }
  cool "$BENCH_COOLDOWN"
  guard_ok || finish "熱保護沒有在運作（thermal_level.log 超過 30 秒沒更新），停止"
  "$@" > "logs/${M_NAME}_console.log" 2>&1
  M_RC=$?
  log "$M_NAME exit=$M_RC : $(tr '\n' ' ' < "logs/${M_NAME}_console.log")"
  [ "$M_RC" -eq 0 ] || problem "$M_NAME 量測失敗（exit=$M_RC）"
}
# $1=label $2=前置冷卻 $3=llama|mlx $4=模型 $5=EXPS $6=EXTRA $7=對話格式 $8=量測項目 $9=上下文長度
# 回傳 0：伺服器有起來；1：載入失敗（可能放不下）；2：沒有真的嘗試（其他負載、熱保護）；3：參數或模型檔不支援，換放法也沒用
NOT_MEMORY='invalid argument|error while handling argument|unknown argument|unknown model architecture|unknown value for|ModuleNotFoundError'
run_cfg() {
  [ "$(memtrips)" -gt "$MT0" ] && finish "記憶體保護已觸發，停止"
  cool "$2"
  T0=$(trips); stop_server
  wait_quiet || { problem "$1 跳過：其他負載未結束"; return 2; }
  op_mark
  guard_ok || finish "熱保護沒有在運作（thermal_level.log 超過 30 秒沒更新），停止"
  NR=""; [ "$3" = llama ] && [ "${RESIDENCY:-0}" != 1 ] && NR=" GGML_METAL_NO_RESIDENCY=1"   # start_server.sh 的預設，不是 llama.cpp 的預設
  log "start server $1 backend=$3 MODEL=$(basename "$4") EXPS=$5 EXTRA=[$6] CTX=$9 BATCH=$RUN_BATCH UB=$RUN_UB$NR (free $(memfree)%)"
  if [ "$3" = llama ]; then
    MODEL="$4" EXPS="$5" EXTRA="$6" CTX="$9" BATCH="$RUN_BATCH" scripts/start_server.sh "$1" -1 "$RUN_UB" &
    READY=/health
  else
    "$MLX_PY" -m mlx_lm server --model "$4" > "logs/server_$1_$(date +%Y%m%d_%H%M%S).log" 2>&1 &   # 預設 localhost:8080
    READY=/v1/models
  fi
  FAIL=""
  if ! wait_ready "$READY"; then FAIL=啟動; elif ! probe_server; then FAIL="1 token 探測"; fi
  if [ -n "$FAIL" ]; then
    SL=$(ls -t logs/server_$1_*.log | head -1)
    stop_server
    log "$1 skipped（$FAIL失敗）; server log tail: $(tail -5 "$SL" | tr '\n' ' ')"
    if [ "$(trips)" -gt "$T0" ]; then problem "$1 載入時熱保護跳脫"; cool 1800; return 2; fi
    grep -qE "$NOT_MEMORY" "$SL" && return 3
    return 1
  fi
  write_meta "$@"
  log "footprint: $(footprint -p "$(pgrep -f "$SRV" | head -1)" 2>/dev/null | grep -i 'phys_footprint:' | head -1); wired: $(top -l 1 -n 0 | awk '/PhysMem/ {print $4}'); free $(memfree)%"
  case "$8" in *spec*) measure "$1" python3 -I scripts/spec_bench.py --label "$1" --fmt "$7" --n 96;; esac
  case "$8" in *agent*) measure "$1_agent" python3 -I scripts/agent_bench.py --label "$1_agent" --fmt "$7" --n 64 --pause 60;; esac
  case "$8" in *ub120*) measure "$1_agent" python3 -I scripts/agent_bench.py --label "$1_agent" --fmt "$7" --t1 agent_long.txt --turns t1_long,t2_followup --n 64 --pause 300;; esac
  case "$8" in *quality*) measure "$1_quality" python3 -I scripts/quality_bench.py --label "$1_quality" --pause 60;; esac
  case "$8" in *stream*) [ -f scripts/stream_bench.py ] && measure "$1_stream" python3 -I scripts/stream_bench.py --url http://127.0.0.1:8080 --label "$1_stream";; esac
  case "$8" in *opencode*) measure "$1_opencode" scripts/run_opencode_tasks.sh "$1";; esac
  stop_server; check_swap
  op_check "$1"
  [ "$(trips)" -gt "$T0" ] && { problem "$1 因熱保護中止"; cool 1800; }
  return 0
}
# 同 run_cfg，但載入失敗也算問題
must() {
  run_cfg "$@"; MR=$?
  [ "$MR" -eq 1 ] && problem "$1 載入失敗"
  [ "$MR" -eq 3 ] && problem "$1 載入失敗：參數或模型檔不支援，不是記憶體問題"
  return "$MR"
}
run_ollama() {  # $1=label $2=前置冷卻
  [ "$(memtrips)" -gt "$MT0" ] && finish "記憶體保護已觸發，停止"
  cool "$2"
  T0=$(trips); stop_server
  wait_quiet || { problem "$1 跳過：其他負載未結束"; return; }
  op_mark
  guard_ok || finish "熱保護沒有在運作（thermal_level.log 超過 30 秒沒更新），停止"
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
  op_check "$1" "$OLLAMA_MODEL"
  [ "$(trips)" -gt "$T0" ] && { problem "$1 因熱保護中止"; cool 1800; }
}
run_randread() {  # 量這台機器放模型的硬碟，用來把 120b 的 tok/s 提升拆成硬碟和快取各佔多少
  [ "$(memtrips)" -gt "$MT0" ] && finish "記憶體保護已觸發，停止"
  cool "$BENCH_COOLDOWN"
  stop_server
  wait_quiet || { problem "randread 跳過：其他負載未結束"; return; }
  guard_ok || finish "熱保護沒有在運作（thermal_level.log 超過 30 秒沒更新），停止"
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
    [ "$RC" -eq 3 ] && { problem "$1 載入失敗：參數或模型檔不支援，不退回 CPU"; return; }
    [ "$RC" -eq 1 ] || return
    log "$1 EXPS=GPU 載入失敗（ctx 32768），退回 exps=CPU"
    Q_EXPS=CPU
  fi
  run_cfg "$1_cpu" "$COOLDOWN" llama "$QWEN" CPU "$2" chatml opencode 32768
  RC=$?
  [ "$RC" -eq 3 ] && problem "$1 載入失敗：參數或模型檔不支援"
  [ "$RC" -eq 1 ] && { problem "$1 EXPS=CPU 也載入失敗"; Q_EXPS=none; }
}

rm -f "$ROOT/logs/overnight_done"
# 用 if，不用「pgrep || 腳本 &」：後者會多一個名為 run_mini.sh 的子 shell 等待腳本結束，
# 而 resource_log 的迴圈要等 run_mini.sh 消失才停，兩邊會互等。
# 熱保護用 PID 和 thermal_level.log 的更新時間確認有在跑，不用 pgrep 比對名稱（可能比對到別的程序而沒啟動）。
# thermal_level.log 30 秒內有更新就表示已經有一份在跑（例如上一輪留下的），不再多開一份
guard_fresh() { f="$ROOT/logs/thermal_level.log"; [ -f "$f" ] && [ $(( $(date +%s) - $(stat -f %m "$f") )) -lt 30 ]; }
TG=""
start_guard() { scripts/thermal_guard.sh >/dev/null 2>&1 & TG=$!; }
guard_ok() {  # 量測和載入前呼叫；確認不了就重啟一次，還是不行回傳 1
  guard_fresh && return 0
  if [ -n "$TG" ] && kill -0 "$TG" 2>/dev/null; then sleep 12; guard_fresh && return 0; fi
  log "熱保護沒有更新 thermal_level.log，重新啟動"
  start_guard; sleep 15; guard_fresh
}
guard_fresh || start_guard
sleep 3; guard_fresh || { sleep 12; guard_fresh; } || finish "熱保護啟動後沒有更新 thermal_level.log，不開始"
MT0=$(memtrips)
mem_guard & MG=$!
# 背景程序不繼承 stdout/stderr，否則外層的輸出管線要等它們結束才會關閉
if ! pgrep -f resource_log.sh >/dev/null; then RESOURCE_LOG_OWNER=$$ scripts/resource_log.sh >/dev/null 2>&1 & fi
log "mini test start: $(chip), $(ram_gb) GB, swap used ${SW0}MB, free $(memfree)%, PHASES=[$PHASES]"

if [ "$MODE" = air ]; then
  must air_20b_stream "$COOLDOWN" llama "$B20" GPU "" harmony stream 8192
  M=$(opencode_missing | tr '\n' ' ')
  if [ -z "$M" ]; then
    export OPENCODE_TASKS=invoice_rounding
    must air_oc_20b "$COOLDOWN" llama "$B20" GPU "--jinja" harmony opencode 32768
  else
    problem "opencode 試跑跳過，缺 $M"
  fi
  finish "Air 驗證結束${PROBLEMS:+，有問題：$PROBLEMS}" ok
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
  finish "Air Qwen 工具呼叫驗證結束${PROBLEMS:+，有問題：$PROBLEMS}" ok
fi

if [ "$MODE" = air_mlx ]; then
  must air_mlx "$COOLDOWN" mlx "$MLX_MODEL" - "" chatml quality,stream 8192
  finish "Air MLX 流程驗證結束${PROBLEMS:+，有問題：$PROBLEMS}" ok
fi

log "第 0 階段：Ollama 對照"
M=$(ollama_missing | tr '\n' ' ')
if ! phase_on 0; then
  log "第 0 階段不在 PHASES，略過"
elif [ -z "$M" ]; then
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
    if [ "$RC" -eq 1 ] || [ "$RC" -eq 3 ]; then
      log "Ollama blob 載入失敗，原因：$(grep -iE 'error|unknown|failed' "$SL" | tail -3 | tr '\n' ' ')。這樣 Ollama 對 llama-server 的差距分不開引擎和模型檔。"
    fi
  fi
else
  problem "第 0 階段跳過，缺 $M"
fi

log "第 1 階段：llama.cpp Qwen"
Q_EXPS="${QWEN_EXPS:-GPU}"   # QWEN_EXPS=CPU：專家層走 mmap，不佔 wired 記憶體，用時間換記憶體
RC=0
if phase_on 1 && [ "$Q_EXPS" = CPU ]; then
  run_cfg "mini_q${QTAG}_cpu" "$COOLDOWN" llama "$QWEN" CPU "" chatml spec,agent,quality,stream 8192
  case $? in 1|3) problem "Qwen exps=CPU 載入失敗"; Q_EXPS=none;; esac
elif phase_on 1; then
  run_cfg "mini_q${QTAG}_gpu" "$COOLDOWN" llama "$QWEN" GPU "" chatml spec,agent,quality,stream 8192
  RC=$?
else
  log "第 1 階段不在 PHASES，略過"
fi
if [ "$RC" -eq 1 ]; then
  log "EXPS=GPU 載入失敗，退回 exps=CPU"
  Q_EXPS=CPU
  run_cfg "mini_q${QTAG}_cpu" "$COOLDOWN" llama "$QWEN" CPU "" chatml spec,agent,quality,stream 8192
  case $? in 1|3) problem "Qwen 兩種放法都載入失敗"; Q_EXPS=none;; esac
elif [ "$RC" -eq 3 ]; then
  problem "mini_q_gpu 載入失敗：參數或模型檔不支援，不退回 CPU"; Q_EXPS=none
fi

log "第 2 階段：MLX Qwen"
M=$(mlx_missing | tr '\n' ' ')
if ! phase_on 2; then
  log "第 2 階段不在 PHASES，略過"
elif [ -z "$M" ]; then
  must mini_q_mlx "$COOLDOWN" mlx "$MLX_MODEL" - "" chatml quality,stream 8192
else
  problem "第 2 階段跳過，缺 $M"
fi

if phase_on 3v; then
  log "opencode 設定驗證：Qwen 跑 1 題，只確認設定可用，不算可靠度"
  M=$(opencode_missing | tr '\n' ' ')
  if [ -z "$M" ]; then
    log "opencode 版本：$(opencode_version)"
    OPENCODE_REPEATS=1 OPENCODE_TASKS=invoice_rounding; export OPENCODE_REPEATS OPENCODE_TASKS
    run_qwen_oc "${VERIFY_LABEL:-mini_oc_qwen${QTAG}_verify}" "${VERIFY_EXTRA:---jinja}"
    unset OPENCODE_REPEATS OPENCODE_TASKS
  else
    problem "opencode 設定驗證跳過，缺 $M"
  fi
fi

log "第 3 階段：opencode"
M=$(opencode_missing | tr '\n' ' ')
if ! phase_on 3; then
  log "第 3 階段不在 PHASES，略過"
elif [ -z "$M" ]; then
  OC_V=$(opencode_version); log "opencode 版本：${OC_V:-未知}（write_config 在 $OPENCODE_VERIFIED 驗證過）"
  # 設定格式、事件格式和專案設定的尋找方式都可能隨版本改變，先用最快的 20b 跑一題確認。模型沒解出題目不算失敗，工具沒跑起來才算
  REPEATS_WANTED="${OPENCODE_REPEATS:-3}"
  export OPENCODE_REPEATS=1 OPENCODE_TASKS=invoice_rounding
  M_RC=""
  must mini_oc_smoke "$COOLDOWN" llama "$B20" GPU "--jinja" harmony opencode 32768
  RC=$?
  export OPENCODE_REPEATS="$REPEATS_WANTED"
  unset OPENCODE_TASKS
  if [ "$RC" -ne 0 ] || [ "$M_RC" != 0 ]; then
    problem "第 3 階段跳過：opencode ${OC_V:-未知版本} 煙霧測試沒過（見 logs/mini_oc_smoke_opencode_console.log）"
  else
    run_qwen_oc "mini_oc_qwen${QTAG}" "--jinja"
    run_qwen_oc "mini_oc_qwen${QTAG}_ngram" "--jinja --spec-type ngram-mod"
    must mini_oc_20b "$COOLDOWN" llama "$B20" GPU "--jinja" harmony opencode 32768
  fi
else
  problem "第 3 階段跳過，缺 $M"
fi

log "第 4 階段：120b"
M=$(q120_missing | tr '\n' ' ')
if ! phase_on 4; then
  log "第 4 階段不在 PHASES，略過"
elif [ -z "$M" ]; then
  run_randread
  RUN_BATCH=8192; RUN_UB=8192   # 和 Air 第 2 項相同：-c 16384 -b 8192 -ub 8192，提示詞 agent_long.txt
  must mini_120b_ub8192 "$COOLDOWN" llama "$B120" CPU "" harmony ub120 16384
  must mini_120b_ub8192_ngram "$COOLDOWN" llama "$B120" CPU "--spec-type ngram-mod" harmony ub120 16384
  RUN_BATCH=2048; RUN_UB=2048
else
  problem "第 4 階段跳過，缺 $M"
fi

if [ -z "$PROBLEMS" ]; then finish "全部完成" ok; else finish "流程結束，但有問題：$PROBLEMS" ok; fi
