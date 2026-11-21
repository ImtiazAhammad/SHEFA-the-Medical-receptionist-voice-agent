#!/usr/bin/env bash
# SHEFA on/off for the person at this PC:  shefa.sh start | stop | status
# Nothing runs until `start`. Whether the public link is live is a separate switch on the admin
# page (Overview -> Public link); it keeps its last setting.
set -uo pipefail
ADMIN="http://127.0.0.1:8101/admin.html"
units=(shefa-vllm shefa-collector)

say() { printf '%s\n' "$*"; }
pause_at_end() { [ -t 0 ] && [ "${SHEFA_NO_WAIT:-}" = "" ] && read -r -p "Press Enter to close this window." _; }

case "${1:-status}" in
  start)
    say "Starting SHEFA… (the first minutes are the language model waking up)"
    systemctl --user reset-failed "${units[@]}" 2>/dev/null
    systemctl --user start --no-block "${units[@]}"
    sleep 2
    for i in $(seq 1 120); do   # up to 10 minutes
      if curl -fs -o /dev/null http://127.0.0.1:8101/; then
        say ""; say "✅ SHEFA is running."
        say "   Admin and review: $ADMIN"
        say "   (Is the public link live? See 'Public link' on the admin page.)"
        [ -z "${SHEFA_NO_OPEN:-}" ] && { xdg-open "$ADMIN" >/dev/null 2>&1 & }
        pause_at_end; exit 0
      fi
      if systemctl --user is-failed --quiet shefa-collector; then break; fi
      printf '.'; sleep 5
    done
    say ""; say "❌ SHEFA did not start. Details:"
    systemctl --user --no-pager status shefa-collector | tail -5
    say "Logs: data/collector/logs/serve.log and data/vllm.log"
    pause_at_end; exit 1 ;;
  stop)
    say "Stopping SHEFA…"
    systemctl --user stop "${units[@]}"
    say "✅ SHEFA is off. The link does not open and the graphics card is free."
    pause_at_end ;;
  status)
    for u in "${units[@]}"; do printf '%-16s %s\n' "$u" "$(systemctl --user is-active "$u")"; done ;;
  *) say "usage: shefa.sh start | stop | status"; exit 2 ;;
esac
