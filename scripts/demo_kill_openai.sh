#!/usr/bin/env bash
# Pull the OpenAI key + restart lite — the visible "failover trigger" for the demo.
#
# Pairs with scripts/demo.sh. Run this in Terminal B while demo.sh is running
# in Terminal A; the demo's output should flip from `gpt-*` to `claude-*` /
# `gemini-*` / etc within ~5 seconds.

set -euo pipefail

ENV_FILE="${1:-.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "✗ env file not found: $ENV_FILE"
  exit 1
fi

echo "▶ removing OPENAI_API_KEY from $ENV_FILE"
# Comment it out rather than delete, so demo_restore_openai.sh can flip it back.
sed -i.bak 's/^OPENAI_API_KEY=/# OPENAI_API_KEY=/' "$ENV_FILE"

echo "▶ restarting lite container"
docker compose restart api

echo "✓ failover triggered — watch demo.sh output flip"
