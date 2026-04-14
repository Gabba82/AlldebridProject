#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/mnt/16G/alldebrid-emby}"
ALLDEBRID_API_KEY="${ALLDEBRID_API_KEY:-}"
ALLDEBRID_AGENT="${ALLDEBRID_AGENT:-alldebrid-emby/1.0}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p "$ROOT_DIR"/{app,config,data,data/inbox,data/cache,data/state,data/logs,library,library/Peliculas,library/Series,scripts,tests,docker}

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
  echo "Created $PROJECT_DIR/.env from template"
fi

if [[ ! -f "$PROJECT_DIR/config/config.yaml" ]]; then
  cp "$PROJECT_DIR/config/config.example.yaml" "$PROJECT_DIR/config/config.yaml"
  echo "Created $PROJECT_DIR/config/config.yaml from template"
fi

python3 - "$PROJECT_DIR/.env" "$ROOT_DIR" "$ALLDEBRID_API_KEY" "$ALLDEBRID_AGENT" <<'PY'
from pathlib import Path
import sys

env_path = Path(sys.argv[1])
root_dir = sys.argv[2]
api_key = sys.argv[3]
agent = sys.argv[4]

updates = {
    "ROOT_PATH": root_dir,
    "LIBRARY_MOVIES_PATH": f"{root_dir}/library/Peliculas",
    "LIBRARY_SERIES_PATH": f"{root_dir}/library/Series",
    "ALLDEBRID_AGENT": agent,
}
if api_key:
    updates["ALLDEBRID_API_KEY"] = api_key

lines = env_path.read_text(encoding="utf-8").splitlines()
output = []
seen = set()
for line in lines:
    if "=" not in line or line.lstrip().startswith("#"):
        output.append(line)
        continue
    key, _ = line.split("=", 1)
    key = key.strip()
    if key in updates:
        output.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        output.append(line)

for key, value in updates.items():
    if key not in seen:
        output.append(f"{key}={value}")

env_path.write_text("\n".join(output) + "\n", encoding="utf-8")
PY

python3 -m venv "$PROJECT_DIR/.venv"
source "$PROJECT_DIR/.venv/bin/activate"
pip install --upgrade pip
pip install -r "$PROJECT_DIR/requirements.txt"
python -m app.cli init

echo "Bootstrap complete."
echo "ROOT_PATH configured as: $ROOT_DIR"
if [[ -n "$ALLDEBRID_API_KEY" ]]; then
  echo "API key written to .env"
else
  echo "Remember to edit .env and set ALLDEBRID_API_KEY"
fi
echo "Next command:"
echo "  source .venv/bin/activate && python -m app.cli test-auth"
