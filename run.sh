#!/bin/sh
# HA add-on entrypoint for OrcaRouter Lite.
#
# Supervisor mounts the add-on configuration as /data/options.json. Translate
# its fields into upper-case env vars (pydantic-settings reads them
# case-insensitively), force the persistent SQLite path, then exec the real
# command. Without options.json (plain docker-compose) this is a pure exec
# pass-through — behaviour unchanged.
set -e

if [ -f /data/options.json ]; then
    eval "$(python3 - <<'PY'
import json

with open("/data/options.json") as f:
    opts = json.load(f)

# Persistent data lives in the Supervisor-mapped addon_config dir. An
# explicit database_url in options overrides this default.
env = {"DATABASE_URL": "sqlite+aiosqlite:////addon_config/orca.db"}
env.update({k: v for k, v in opts.items()})

out = []
for key, value in env.items():
    if value is None:
        continue
    if isinstance(value, bool):
        out.append(f"export {key.upper()}={str(value).lower()}")
    elif str(value) != "":
        escaped = (
            str(value)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("$", "\\$")
            .replace("`", "\\`")
        )
        out.append(f'export {key.upper()}="{escaped}"')
print("\n".join(out))
PY
)"
    mkdir -p /addon_config
fi

exec "$@"
