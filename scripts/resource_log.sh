#!/bin/sh
# 每 10 秒記錄熱壓力與資源占用（不需 sudo）到 logs/resources.csv，只要任何實驗排程還在跑就持續記錄。
# 欄位：時間, 熱壓力(0-4), CPU user/sys/idle %, GPU 使用率 %, GPU 使用中記憶體 MB, 實體記憶體已用,
#       wired MB, 壓縮器 MB, 系統可用記憶體 %, swap 已用 MB, llama-server CPU %, llama-server footprint MB, SSD MB/s
# 註：沒有實際溫度（攝氏）—— 那需要 sudo powermetrics，依規則不使用；熱壓力等級是 macOS 官方的過熱指標。
ROOT="/Volumes/LLM SSD/Flashback"
OUT="$ROOT/logs/resources.csv"
[ -f "$OUT" ] || echo "time,thermal,cpu_user,cpu_sys,cpu_idle,gpu_util,gpu_mem_MB,physmem_used,wired_MB,compressor_MB,mem_free_pct,swap_used_MB,server_cpu,server_footprint_MB,ssd_MBps" > "$OUT"
while pgrep -f "run_ubatch.sh|download_extra.sh|run_spec.sh|run_more.sh" >/dev/null; do
  T=$(date '+%F %T')
  L=$(notifyutil -g com.apple.system.thermalpressurelevel | awk '{print $2}')
  TOP=$(top -l 1 -n 0)
  CPU=$(echo "$TOP" | awk '/CPU usage/ {gsub("%","");print $3","$5","$7}')
  PM=$(echo "$TOP" | awk '/PhysMem/ {print $2}')
  WIRED=$(echo "$TOP" | awk '/PhysMem/ {gsub("[(M]","",$4);print $4}')
  COMP=$(echo "$TOP" | awk '/PhysMem/ {gsub("M","",$6);print $6}')
  G=$(ioreg -r -d 1 -c IOAccelerator 2>/dev/null)
  GU=$(echo "$G" | grep -oE '"Device Utilization %"=[0-9]+' | head -1 | cut -d= -f2)
  GM=$(echo "$G" | grep -oE '"In use system memory"=[0-9]+' | head -1 | cut -d= -f2)
  GM=$(( ${GM:-0} / 1048576 ))
  FREE=$(memory_pressure | awk '/free percentage/ {gsub("%","");print $5}')
  SW=$(sysctl -n vm.swapusage | awk '{gsub("M","",$6);print $6}')
  P=$(pgrep -f "^llama-server -m" | head -1)
  if [ -n "$P" ]; then
    SC=$(ps -o %cpu= -p "$P" | tr -d ' ')
    SF=$(footprint -p "$P" 2>/dev/null | awk '/phys_footprint:/ {print $2$3; exit}')
  else SC=""; SF=""; fi
  D=$(iostat -d -w 1 -c 2 disk4 2>/dev/null | tail -1 | awk '{print $3}')
  echo "$T,$L,$CPU,$GU,$GM,$PM,$WIRED,$COMP,$FREE,$SW,$SC,$SF,$D" >> "$OUT"
  sleep 9
done
