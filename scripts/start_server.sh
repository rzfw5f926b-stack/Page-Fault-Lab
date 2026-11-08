#!/bin/sh
# 用法：scripts/start_server.sh <label> [threads] [ubatch]
# 主實驗設定：共用層在 GPU，專家層 -ot "exps=CPU" 經 mmap 留在 SSD，上下文 4096，不暖機。
# --no-repack：預防 CPU repack 把專家層複製進一般記憶體。
# GGML_METAL_NO_RESIDENCY=1：與試跑設定一致（試跑時用來排查啟動預讀，保留以維持可比性）。
# 注意：llama.cpp 啟動時會對整個檔案 MADV_WILLNEED 預讀（約 2 分 40 秒），冷啟動要在載入完成後 sudo purge。
ROOT="${FLASHBACK_ROOT:-/Volumes/LLM SSD/Flashback}"
LABEL="$1"; THREADS="${2:--1}"; UB="${3:-512}"
EXTRA="${EXTRA:-}"   # 額外參數（例如推測解碼），不加引號展開
CTX="${CTX:-4096}"; BATCH="${BATCH:-2048}"   # 可用環境變數覆寫上下文與邏輯批次
# 第 4 項：PIN_OT 指定要固定到 GPU 的專家層 -ot 規則（放在 exps=CPU 前面，第一個符合的規則生效）。
# RESIDENCY=1 時不設定 GGML_METAL_NO_RESIDENCY，讓 Metal 用 residency set 把 GPU 緩衝區常駐。
PIN_OT="${PIN_OT:-}"
# 第 6 項：MODEL 指定模型檔（models/ 底下，預設 120b）；EXPS=GPU 時不加 -ot "exps=CPU"，整個模型放 GPU。
MODEL="${MODEL:-gpt-oss-120b-MXFP4.gguf}"
set --
[ -n "$PIN_OT" ] && set -- -ot "$PIN_OT"
[ "${EXPS:-CPU}" = GPU ] || set -- "$@" -ot "exps=CPU"
[ "${RESIDENCY:-0}" = 1 ] || export GGML_METAL_NO_RESIDENCY=1
exec llama-server -m "$ROOT/models/$MODEL" \
  -ngl 999 "$@" --no-repack -c "$CTX" -t "$THREADS" -b "$BATCH" -ub "$UB" --no-warmup \
  --host 127.0.0.1 --port 8080 -np 1 $EXTRA \
  > "$ROOT/logs/server_${LABEL}_$(date +%Y%m%d_%H%M%S).log" 2>&1
