#!/bin/sh
# 延伸研究的模型下載（使用者 2026-11-08 同意）。等第 2 項（run_ubatch.sh）結束後才開始，避免干擾 I/O 量測。
ROOT="/Volumes/LLM SSD/Flashback"
cd "$ROOT" || exit 1
LOG="$ROOT/logs/download_extra.log"
export HF_HOME="$ROOT/.hf_home"
while pgrep -f run_ubatch.sh >/dev/null; do sleep 60; done
echo "$(date '+%F %T') start downloads" >> "$LOG"
dl() {  # repo file
  echo "$(date '+%F %T') hf download $1 $2" >> "$LOG"
  hf download "$1" "$2" --local-dir "$ROOT/models" >> "$LOG" 2>&1
  echo "$(date '+%F %T') exit=$?" >> "$LOG"
  oid=$(curl -s "https://huggingface.co/api/models/$1/tree/main" | python3 -I -c "
import json,sys
print([f['lfs']['oid'] for f in json.load(sys.stdin) if f['path']=='$2'][0])")
  got=$(shasum -a 256 "$ROOT/models/$2" | awk '{print $1}')
  [ "$oid" = "$got" ] && r=MATCH || r=MISMATCH
  echo "$(date '+%F %T') sha256 $2 $r expected=$oid got=$got" >> "$LOG"
}
dl ggml-org/gpt-oss-120b-GGUF eagle3-gpt-oss-120b-Q8_0.gguf
dl ggml-org/gpt-oss-20b-GGUF gpt-oss-20b-MXFP4.gguf
dl unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf
echo "$(date '+%F %T') all downloads done" >> "$LOG"
df -h "/Volumes/LLM SSD" | tail -1 >> "$LOG"
