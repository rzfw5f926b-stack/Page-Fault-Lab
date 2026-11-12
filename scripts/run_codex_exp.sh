#!/bin/zsh
# 跑 Codex總攬 的派工題目（~/Claude/Codex總攬/exp），Flashback 只負責起 llama-server、記錄資源、記憶體和熱保護。
# 題目、驗收、每次嘗試的紀錄都由 Codex總攬 的 accept_hard.sh／accept.sh + oc_llama.py 處理（唯讀使用，不改它的檔案）。
# 用法：
#   SETS="hard reg" TAG=night OC_TIMEOUT=3600 scripts/run_codex_exp.sh
# 環境變數：
#   SETS        要跑的組：hard（難題組 H1～H6）、reg（回歸組 T1～T5），依序跑，預設 "hard reg"
#   HARD_TASKS  難題組題號，預設全部；REG_TASKS 同理（傳給 accept.sh 的 TASKS）
#   K           每題輪數，預設 3
#   TAG         結果檔名後綴（區分設定），預設空白
#   CTX         llama-server 的 -c，同時傳給 LLAMA_CTX，預設 65536
#   UB          -b/-ub，預設 512（混合架構要 512 前綴快取才有效）
#   QWEN_MODEL  models/ 下的檔名，預設 Qwen3.6-35B-A3B-Q4_K_M.gguf；LLAMA_MODEL 是給 Codex總攬 的標籤
#   CACHE_RAM   傳給 llama-server 的 --cache-ram（MiB，提示詞快取上限；預設不傳，用 llama-server 的預設 8192）
#   RESTART_EACH 設了就在回歸組每題之前重啟 llama-server（測試需求 3-1）；結果檔每題一個（TAG 後加 _r<輪>t<題>）
#   其他（OC_TIMEOUT、OC_STEPS、OC_RETRIES、OC_STALL、LLAMA_OUTPUT…）直接傳給 oc_llama.py
# 保護：可用記憶體 <12%、swap 比開跑時多 SWAP_LIMIT_MB（預設 6144）、或系統記憶體壓力到 critical（kern.memorystatus_vm_pressure_level=4）
#       → 殺掉 llama-server 和題目流程，留下 logs/MEM_TRIP_*。2026-11-11 使用者同意從 1GB 改成 6GB：mini 32GB、內建 SSD，
#       swap 會在可用記憶體 40～50% 時一次跳 1.3～2.7GB（系統寫出壓縮記憶體），1GB 會誤觸發；其他舊腳本維持 1GB。
#       熱壓力 >=1，或連續 3 次（約 15 秒）讀不到熱壓力 → 同樣停止，留下 logs/THERMAL_TRIP_*。觸發後不重跑、不放寬。
#       每題之前確認保護迴圈還活著，不在就停。收到中止訊號時連題目流程（accept、oc_llama、opencode）一起停。
ROOT=${0:A:h:h}; export FLASHBACK_ROOT=$ROOT DISK=${DISK:-disk0}
CX=$HOME/Claude/Codex總攬
SETS=(${=${SETS:-hard reg}}); export K=${K:-3}; [[ -n $TAG ]] && export TAG
CTX=${CTX:-65536}; UB=${UB:-512}
QWEN_MODEL=${QWEN_MODEL:-Qwen3.6-35B-A3B-Q4_K_M.gguf}
export LLAMA_MODEL=${LLAMA_MODEL:-qwen3.6-35b-a3b} LLAMA_CTX=$CTX
LABEL=codex_exp_${LLAMA_MODEL//[.:\/]/_}${TAG:+_$TAG}
LOG=$ROOT/logs/$LABEL.log
SRV='^llama-server -m'
log() { echo "$(date '+%F %T') $*" | tee -a $LOG; }
memfree() { memory_pressure | awk -F': ' '/free percentage/ {gsub("%","",$2); print $2}'; }
swapused() { sysctl -n vm.swapusage | awk '{gsub("M","",$6); print int($6)}'; }
pressure() { sysctl -n kern.memorystatus_vm_pressure_level; }
level() {  # 讀不到或不是數字時回傳 X（呼叫端當成不安全）
  local v=$(notifyutil -g com.apple.system.thermalpressurelevel 2>/dev/null | awk '{print $2}')
  [[ $v == <-> ]] && echo $v || echo X
}
kill_all() {  # 停掉題目流程（accept 腳本、oc_llama、它起的 opencode）和 llama-server
  pkill -f "exp/accept_hard.sh|exp/accept.sh" ; pkill -f "exp/oc_llama.py"
  pkill -f "Codex總攬/exp/runs/(hl|lt)[0-9]"
  pkill -9 -f "$SRV"
}
finish() {
  [[ -n $GD ]] && kill $GD 2>/dev/null
  (( ${2:-1} != 0 )) && kill_all  # 中止或出錯時，題目流程也一起停，不讓它對著已經不在的 server 繼續跑
  pkill -9 -f "$SRV"; i=0; while pgrep -f "$SRV" >/dev/null && (( i < 120 )); do sleep 1; ((i++)); done
  log "end: $1 swap=$(swapused)MB (start ${SW0}MB) free=$(memfree)%"
  R=$(sh $ROOT/scripts/scrub_logs.sh 2>&1) || R="$R（還有殘留，推送前要處理）"; log "$R"
  exit ${2:-1}
}
trap 'finish "收到中止訊號"' INT TERM

# 前置檢查
L0=$(level); [[ $L0 == X ]] && { log "讀不到熱壓力，不開跑"; exit 1; }
(( L0 >= 1 )) && { log "熱壓力 $L0，不開跑"; exit 1; }
pgrep -f "$SRV" >/dev/null && { log "已有 llama-server 在跑，不開跑"; exit 1; }
[[ -f $ROOT/models/$QWEN_MODEL ]] || { log "找不到 models/$QWEN_MODEL"; exit 1; }
[[ -x $CX/exp/oc_llama.py ]] || { log "找不到 Codex總攬 的 exp/oc_llama.py"; exit 1; }
TRIPF=$ROOT/logs/.codex_exp_trip; rm -f $TRIPF
SW0=$(swapused); SWAP_LIMIT_MB=${SWAP_LIMIT_MB:-6144}
log "start $LABEL sets=(${SETS}) K=$K CTX=$CTX UB=$UB model=$QWEN_MODEL TAG=${TAG:-} OC_TIMEOUT=${OC_TIMEOUT:-} OC_STEPS=${OC_STEPS:-} OC_RETRIES=${OC_RETRIES:-} LLAMA_OUTPUT=${LLAMA_OUTPUT:-} RESIDENCY=${RESIDENCY:-0} CACHE_RAM=${CACHE_RAM:-} swap=${SW0}MB swap_limit=+${SWAP_LIMIT_MB}MB free=$(memfree)% opencode=$(opencode --version 2>/dev/null) llama=$(llama-server --version 2>&1 | grep -m1 -i version)"
log "ollama ps: $(ollama ps 2>/dev/null | tail -n +2 | awk '{print $1}' | tr '\n' ' ')"

# 起 llama-server（專家層 exps=CPU 走 mmap）
start_srv() {
  MODEL=$QWEN_MODEL EXPS=CPU CTX=$CTX BATCH=$UB EXTRA="--jinja${CACHE_RAM:+ --cache-ram $CACHE_RAM}" $ROOT/scripts/start_server.sh $LABEL -1 $UB &
  i=0; until [[ $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/health) = 200 ]]; do
    (( i >= 900 )) && finish "server 900 秒沒就緒"
    (( i >= 5 )) && ! pgrep -f "$SRV" >/dev/null && finish "server 載入時掛掉"
    sleep 1; ((i++))
  done
  log "server ready after ${i}s"
  CODE=$(curl -s -m 900 -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' \
    -d '{"messages":[{"role":"user","content":"hi"}],"max_tokens":1}' http://127.0.0.1:8080/v1/chat/completions)
  [[ $CODE = 200 ]] || finish "probe http=$CODE"
  log "probe ok; footprint $(footprint -p $(pgrep -f "$SRV" | head -1) 2>/dev/null | awk '/phys_footprint:/ {print $2$3; exit}')"
}
stop_srv() {  # 正常停 server（不是保護觸發），等它真的結束
  pkill -f "$SRV"; i=0; while pgrep -f "$SRV" >/dev/null && (( i < 60 )); do sleep 1; ((i++)); done
  pgrep -f "$SRV" >/dev/null && { pkill -9 -f "$SRV"; sleep 2; }
}
start_srv

# 資源紀錄與保護
RESOURCE_LOG_OWNER=$$ sh $ROOT/scripts/resource_log.sh &
{
  NA=0
  while :; do
    F=$(memfree); U=$(swapused); L=$(level); PR=$(pressure)
    if (( ${F:-100} < 12 || ${U:-0} - SW0 > SWAP_LIMIT_MB || ${PR:-1} >= 4 )); then
      T=$(date +%H%M%S); echo "free=${F}% swap=${U}MB start=${SW0}MB pressure=$PR" > $ROOT/logs/MEM_TRIP_$T
      log "MEM_TRIP free=${F}% swap=${U}MB (start ${SW0}MB) pressure=$PR"; touch $TRIPF; kill_all; break
    fi
    if [[ $L == X ]]; then ((NA++)); else NA=0; fi
    if (( NA >= 3 )) || { [[ $L != X ]] && (( L >= 1 )); }; then
      T=$(date +%H%M%S); echo "level=$L" > $ROOT/logs/THERMAL_TRIP_$T
      log "THERMAL_TRIP level=$L"; touch $TRIPF; kill_all; break
    fi
    sleep 5
  done
} &
GD=$!

tripped() {
  [[ -f $TRIPF ]] && return 0   # 保護正常觸發後迴圈會自己結束，先看標記檔，才不會誤記成「保護迴圈不在了」
  kill -0 $GD 2>/dev/null || { log "保護迴圈不在了"; return 0; }
  ! pgrep -f "$SRV" >/dev/null
}
cd $CX
for s in $SETS; do
  tripped && finish "server 不在（保護觸發或掛掉），停止"
  case $s in
    hard) log "== hard tasks=(${HARD_TASKS:-1 2 3 4 5 6})"
          exp/accept_hard.sh llama "${HARD_TASKS:-1 2 3 4 5 6}" >> $LOG 2>&1; log "hard rc=$?";;
    reg)  log "== reg tasks=(${REG_TASKS:-default}) restart_each=${RESTART_EACH:-0}"
          if [[ -n $RESTART_EACH ]]; then
            # 3-1：每題之前重啟 server。accept.sh 一次只跑一題一輪（K=1），TAG 加上 _r<輪>t<題> 分開存，事後再合併
            for r in $(seq $K); do for t in ${=${REG_TASKS:-1 2 3 4 5}}; do
              tripped && finish "server 不在（保護觸發或掛掉），停止"
              stop_srv; start_srv
              log "-- r$r t$t"
              K=1 TAG=${TAG}_r${r}t${t} TASKS=$t OC_LLAMA=1 exp/accept.sh >> $LOG 2>&1; log "r$r t$t rc=$?"
            done; done
          else
            TASKS="${REG_TASKS:-1 2 3 4 5}" OC_LLAMA=1 exp/accept.sh >> $LOG 2>&1; log "reg rc=$?"
          fi;;
    *) log "未知的組 $s";;
  esac
done
tripped && finish "跑完時 server 不在（保護觸發或掛掉）"
finish "全部跑完" 0
