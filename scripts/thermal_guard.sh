#!/bin/sh
# 熱保護（使用者要求：不過熱優先於實驗成功）
# 每 10 秒讀 macOS 熱壓力等級（0=正常 1=中等 2=重 3=更重 4=睡眠）。
# 只要 llama-server 或量測正在執行且等級 >=1，就立刻停掉兩者（SIGKILL），並留下 logs/THERMAL_TRIP_* 標記。
# 閒置時只記錄等級、不計跳脫。logs/overnight_done 出現後結束。
ROOT="/Volumes/LLM SSD/Flashback"
while [ ! -f "$ROOT/logs/overnight_done" ]; do
  L=$(notifyutil -g com.apple.system.thermalpressurelevel | awk '{print $2}')
  echo "$(date '+%T') $L" >> "$ROOT/logs/thermal_level.log"
  if [ "${L:-0}" -ge 1 ] && pgrep -f "llama-server -m|agent_bench.py|quality_bench.py|evict.bin" >/dev/null; then
    echo "$(date '+%F %T') THERMAL TRIP level=$L -> stopping bench and server" >> "$ROOT/logs/overnight.log"
    touch "$ROOT/logs/THERMAL_TRIP_$(date '+%H%M%S')"
    pkill -f "agent_bench.py"; pkill -f "quality_bench.py"; pkill -9 -f "llama-server -m"; pkill -f "evict.bin"
    sleep 60
  fi
  sleep 10
done
