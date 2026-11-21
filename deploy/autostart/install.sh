#!/usr/bin/env bash
# Installs the SHEFA services for this user: vLLM, then the collection site, started at power-on
# (needs linger: `sudo loginctl enable-linger $USER`, once) and restarted if they crash.
# The public link is Tailscale Funnel (`tailscale funnel --bg 8100`), which tailscaled keeps itself.
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
RestartSec=10
TimeoutStopSec=30

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable shefa-vllm.service shefa-collector.service
echo "Installed. Start now:  systemctl --user start shefa-collector"
echo "Linger (start at power-on, before login): $(loginctl show-user "$USER" -p Linger)"
