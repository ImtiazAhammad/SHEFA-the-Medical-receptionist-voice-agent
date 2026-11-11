#!/usr/bin/env bash
# Copies the web app's env values from apps/web/.env.local into Vercel (production) and deploys.
set -euo pipefail

cd "$(dirname "$0")/../apps/web"
ENV_FILE=".env.local"
VARIABLES=(NEXT_PUBLIC_SUPABASE_URL NEXT_PUBLIC_SUPABASE_ANON_KEY LIVEKIT_AGENT_NAME INTERNAL_API_TOKEN LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET AGENT_API_URL)

for name in "${VARIABLES[@]}"; do
  value="$(grep -E "^${name}=" "$ENV_FILE" | head -n1 | cut -d= -f2- || true)"
  if [[ -z "$value" || "$value" == http://localhost* ]]; then
    echo "skip  $name (not set for production)"
    continue
  fi
  vercel env rm "$name" production --yes >/dev/null 2>&1 || true
  printf '%s' "$value" | vercel env add "$name" production >/dev/null
  echo "set   $name"
done

vercel deploy --prod --yes
