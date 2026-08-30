#!/usr/bin/env bash
# Утренний отчёт Беспалько → Telegram. Крон Beget: 30 7 * * * bash /home/p/primeh1e/bespalko/run.sh
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
{
  echo "=== $(date '+%F %T') ==="
  python3 "$DIR/bespalko_report.py" --send --keys "$DIR/api-keys.env"
} >> "$DIR/cron.log" 2>&1
# ротация лога
tail -n 2000 "$DIR/cron.log" > "$DIR/cron.log.tmp" && mv "$DIR/cron.log.tmp" "$DIR/cron.log"
