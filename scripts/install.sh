#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "AllDebrid Emby STRM Bridge installer"
echo
echo "Optional variables before running:"
echo "  ALLDEBRID_API_KEY=your_api_key"
echo "  ROOT_DIR=/mnt/16G/alldebrid-emby"
echo "  ALLDEBRID_AGENT=alldebrid-emby/1.0"
echo

bash "$PROJECT_DIR/scripts/bootstrap.sh"

echo
echo "Installation complete."
echo "Recommended next step:"
echo "  cd $PROJECT_DIR"
echo "  source .venv/bin/activate"
echo "  python -m app.cli test-auth"
