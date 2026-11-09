#!/bin/sh
# logs/ 會推上公開 repo：把這台機器的家目錄、帳號和主機名稱換掉，再檢查整個 repo 有沒有殘留。
# 可以重複執行。run_mini.sh 結束時會自動跑；commit 前要再跑一次，回傳 1 表示還有殘留，不能推送。
# 名稱都從這台機器讀取，不把任何帳號寫進這個檔案。太常見的名稱（例如 test）不當成帳號，避免改壞紀錄。
ROOT="${FLASHBACK_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
names() {
  for n in "$(id -un)" "$(hostname -s)" "$(hostname)"; do
    case "$n" in ''|root|admin|user|test|guest|localhost) continue;; esac
    [ "${#n}" -ge 4 ] && echo "$n"
  done | sort -u
}
found() {
  { grep -rIlF --exclude-dir=models --exclude-dir=.git --exclude-dir=.hf_home --exclude-dir=.tools --exclude-dir=.venv-mlx -e "$HOME" "$1"
    names | while IFS= read -r n; do
      grep -rIlwF --exclude-dir=models --exclude-dir=.git --exclude-dir=.hf_home --exclude-dir=.tools --exclude-dir=.venv-mlx -e "$n" "$1"
    done; } 2>/dev/null | sort -u
}
N=0
TMP=$(mktemp)
found "$ROOT/logs" > "$TMP"
while IFS= read -r f; do
  SCRUB_HOME="$HOME" SCRUB_NAMES="$(names | tr '\n' ' ')" perl -i -pe '
    BEGIN { $h = $ENV{SCRUB_HOME}; @n = split " ", $ENV{SCRUB_NAMES} }
    s/\Q$h\E/~/g;
    for my $x (@n) { s/(?<!\w)\Q$x\E(?!\w)/<redacted>/g }' "$f"
  N=$((N+1))
done < "$TMP"
found "$ROOT" > "$TMP"
LEFT=$(wc -l < "$TMP" | tr -d ' ')
echo "scrub_logs：清理 $N 個紀錄檔，殘留 $LEFT 個"
if [ "$LEFT" -gt 0 ]; then sed "s#^$ROOT/##" "$TMP"; rm -f "$TMP"; exit 1; fi
rm -f "$TMP"
