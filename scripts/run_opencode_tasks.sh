#!/bin/sh
# run_mini.sh 第 3 階段呼叫的入口。用法：scripts/run_opencode_tasks.sh <label>
# OPENCODE_TASKS 可指定題目（逗號分隔），預設全部。
exec python3 -I "$(dirname "$0")/opencode_tasks.py" --label "$1" --tasks "${OPENCODE_TASKS:-}"
