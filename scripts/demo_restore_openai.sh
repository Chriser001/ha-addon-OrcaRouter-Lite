#!/usr/bin/env bash
# Reverse demo_kill_openai.sh — un-comments OPENAI_API_KEY and restarts lite.

set -euo pipefail
ENV_FILE="${1:-.env}"

sed -i.bak 's/^# OPENAI_API_KEY=/OPENAI_API_KEY=/' "$ENV_FILE"
docker compose restart api
echo "✓ openai key restored"
