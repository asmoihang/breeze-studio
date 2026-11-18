#!/usr/bin/env bash
set -euo pipefail
STUDIO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$STUDIO_DIR"
export PYTHONIOENCODING=utf-8
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3 is required. Run this script inside the Ubuntu WSL distribution.'
  exit 1
fi
python3 scripts/configure.py "$@"
exec python3 backend/server.py --port "${BREEZE_STUDIO_PORT:-7860}"
