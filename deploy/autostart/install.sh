#!/usr/bin/env bash
# Installs the SHEFA services for this user (vLLM, then the collection site; restarted if they
# crash) and "Start SHEFA" / "Stop SHEFA" icons. Nothing runs until someone presses Start.
#   bash install.sh              # manual: start and stop with the icons (deploy/shefa.sh)
#   bash install.sh --autostart  # also start at power-on (needs `sudo loginctl enable-linger $USER`)
# The public link is Tailscale Funnel, switched on/off on the admin page (Overview -> Public link).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
units="$HOME/.config/systemd/user"
mkdir -p "$units"
cat > "$units/shefa-vllm.service" <<UNIT
[Unit]
Description=SHEFA language model (vLLM)

[Service]
Type=simple
ExecStart=/bin/bash "$here/run.sh" vllm
ExecStartPost=/bin/bash "$here/run.sh" vllm-ready
TimeoutStartSec=1000
Restart=on-failure
SuccessExitStatus=143
RestartSec=30
KillMode=mixed
TimeoutStopSec=60

[Install]
WantedBy=default.target
UNIT
cat > "$units/shefa-collector.service" <<UNIT
[Unit]
Description=SHEFA voice collection site (ports 8100 public, 8101 staff)
Wants=shefa-vllm.service
After=shefa-vllm.service network-online.target

[Service]
Type=simple
ExecStart=/bin/bash "$here/run.sh" collector
Restart=on-failure
SuccessExitStatus=143
RestartSec=10
TimeoutStopSec=30

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
if [ "${1:-}" = "--autostart" ] || [ "${2:-}" = "--autostart" ]; then
  systemctl --user enable shefa-vllm.service shefa-collector.service
  echo "SHEFA starts at power-on. $(loginctl show-user "$USER" -p Linger) (yes = even before login)"
else
  systemctl --user disable shefa-vllm.service shefa-collector.service 2>/dev/null || true
  echo "SHEFA starts only when you press Start SHEFA."
fi

# Self-test (shefa/selftest.py): quick every 15 minutes, a full booking walk-through nightly.
# Installed always, switched on with --selftest (it alerts on Telegram once that is set up).
for kind in quick full; do
  arg=selftest; [ "$kind" = quick ] && arg=selftest-quick
  cat > "$units/shefa-selftest-$kind.service" <<UNIT
[Unit]
Description=SHEFA self-test ($kind)

[Service]
Type=oneshot
ExecStart=/bin/bash "$here/run.sh" $arg
UNIT
done
cat > "$units/shefa-selftest-quick.timer" <<UNIT
[Unit]
Description=SHEFA quick self-test every 15 minutes

[Timer]
OnBootSec=10min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
UNIT
cat > "$units/shefa-selftest-full.timer" <<UNIT
[Unit]
Description=SHEFA full self-test every night

[Timer]
OnCalendar=*-*-* 03:30
Persistent=true

[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
if [ "${1:-}" = "--selftest" ] || [ "${2:-}" = "--selftest" ]; then
  systemctl --user enable --now shefa-selftest-quick.timer shefa-selftest-full.timer
  echo "Self-test on: quick every 15 minutes, full at 03:30 (log: data/collector/logs/selftest.log)"
fi

# The icons: in the app list (search "SHEFA") and on the desktop.
ctl="$(cd "$here/.." && pwd)/shefa.sh"
apps="$HOME/.local/share/applications"
desk="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
mkdir -p "$apps"
for action in start stop; do
  if [ "$action" = start ]; then name="Start SHEFA"; icon=media-playback-start; else name="Stop SHEFA"; icon=media-playback-stop; fi
  file="$apps/shefa-$action.desktop"
  cat > "$file" <<ENTRY
[Desktop Entry]
Type=Application
Name=$name
Comment=SHEFA voice collection: $action
Exec=bash "$ctl" $action
Icon=$icon
Terminal=true
Categories=Utility;
ENTRY
  chmod +x "$file"
  if [ -d "$desk" ]; then
    cp "$file" "$desk/"
    chmod +x "$desk/shefa-$action.desktop"
    gio set "$desk/shefa-$action.desktop" metadata::trusted true 2>/dev/null || true
  fi
done
echo "Icons: search 'SHEFA' in the app list, or use the ones on the desktop."
