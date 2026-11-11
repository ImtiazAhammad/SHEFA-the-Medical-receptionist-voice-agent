#!/usr/bin/env bash
# Deploys the voice agent to LiveKit Cloud, passing only the secrets it needs from apps/agent/.env.local.
set -euo pipefail

cd "$(dirname "$0")/../apps/agent"
ENV_FILE=".env.local"
SECRET_NAMES=(GOOGLE_API_KEY SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY CLINIC_ID INTERNAL_API_TOKEN VOICE_ENGINE AGENT_NAME
  GEMINI_LIVE_MODEL GEMINI_LIVE_VOICE EXTRACTION_MODEL EXTRACTION_FALLBACK_MODEL MAX_CALL_SECONDS USER_AWAY_TIMEOUT_SECONDS)

SECRETS_FILE="$(mktemp)"
chmod 600 "$SECRETS_FILE"
trap 'rm -f "$SECRETS_FILE"' EXIT

for name in "${SECRET_NAMES[@]}"; do
  line="$(grep -E "^${name}=" "$ENV_FILE" | head -n1 || true)"
  if [[ -n "${line#*=}" ]]; then
    echo "$line" >> "$SECRETS_FILE"
    echo "secret $name"
  fi
done

if [[ -f livekit.toml ]]; then
  lk agent deploy --secrets-file "$SECRETS_FILE" .
else
  lk agent create --secrets-file "$SECRETS_FILE" .
fi
