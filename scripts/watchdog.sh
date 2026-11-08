#!/bin/sh
# 看門狗：llama-server RSS 超過 $1 MB 或 swapouts 增加超過 $2 頁(16KB) 就強制結束
MAXRSS_MB=${1:-6000}; MAXSWAP=${2:-10000}
S0=$(vm_stat | awk '/Swapouts/ {gsub("\\.","",$2); print $2}')
while pgrep -f "llama-server -m" >/dev/null; do
  RSS=$(ps -Ao rss,command | awk '/llama-server -m/ && !/awk/ {print int($1/1024)}' | head -1)
  S=$(vm_stat | awk '/Swapouts/ {gsub("\\.","",$2); print $2}')
  if [ "${RSS:-0}" -gt "$MAXRSS_MB" ] || [ $((S - S0)) -gt "$MAXSWAP" ]; then
    echo "$(date '+%T') WATCHDOG KILL rss=${RSS}MB swapouts+=$((S - S0))"; pkill -9 -f "llama-server -m"; exit 1
  fi
  sleep 1
done
echo "$(date '+%T') server gone, watchdog exit"
