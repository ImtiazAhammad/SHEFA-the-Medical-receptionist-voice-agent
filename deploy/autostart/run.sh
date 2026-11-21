#!/usr/bin/env bash
# Started by the systemd user services in this folder (see install.sh). Runs one part in the
# foreground so systemd can watch it and restart it; logs go where the manual commands put them.
set -euo pipefail
cd "$(dirname "$0")/../.."
UV="${UV:-$HOME/.local/bin/uv}"
case "${1:-}" in
  vllm)
    mkdir -p data
    exec "$UV" run --no-sync python -c '
import os
from shefa.cli import vllm_command, vllm_environment
from shefa.config.settings import settings
cmd = vllm_command(settings.llm_server.vllm)
os.execvpe(cmd[0], cmd, vllm_environment())
' >> data/vllm.log 2>&1 ;;
  vllm-ready)
    # Wait for the model to answer, so the collector (Whisper) starts after vLLM took its share.
    port=$("$UV" run --no-sync python -c 'from shefa.config.settings import settings; print(settings.llm_server.vllm.port)')
    for _ in $(seq 1 180); do
      curl -fsS "http://127.0.0.1:$port/v1/models" >/dev/null 2>&1 && exit 0
      sleep 5
    done
    echo "vLLM did not answer in 15 minutes; the collector starts anyway (live calls stay off)" >&2 ;;
  collector)
    mkdir -p data/collector/logs
    exec "$UV" run --no-sync shefa collect serve >> data/collector/logs/serve.log 2>&1 ;;
  selftest|selftest-quick)
    # Stopped on purpose (Stop SHEFA) is not a fault: stay quiet. A crashed service is.
    state=$(systemctl --user is-active shefa-vllm 2>/dev/null || true)
    if [ "$state" != "active" ] && ! systemctl --user is-failed --quiet shefa-vllm; then
      exit 0
    fi
    flag=""; [ "$1" = "selftest-quick" ] && flag="--quick"
    mkdir -p data/collector/logs
    exec "$UV" run --no-sync shefa selftest $flag >> data/collector/logs/selftest.log 2>&1 ;;
  *) echo "usage: run.sh vllm|vllm-ready|collector|selftest|selftest-quick" >&2; exit 2 ;;
esac
