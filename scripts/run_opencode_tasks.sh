#!/bin/sh
# 環境變數：OPENCODE_BIN（opencode 執行檔）、OPENCODE_TASKS（逗號分隔的題目）、OPENCODE_REPEATS（每題次數）、OPENCODE_STOP_AFTER（幾輪工具呼叫後停止，只驗格式）、OPENCODE_TIMEOUT（每題秒數上限）
exec python3 -I "$(dirname "$0")/opencode_tasks.py" --label "$1" --opencode "${OPENCODE_BIN:-opencode}" --tasks "${OPENCODE_TASKS:-}" \
  --repeats "${OPENCODE_REPEATS:-1}" --stop-after-tool-turns "${OPENCODE_STOP_AFTER:-0}" --timeout "${OPENCODE_TIMEOUT:-1800}"
