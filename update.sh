#!/usr/bin/env bash
set -euo pipefail
STUDIO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$STUDIO_DIR"
python3 scripts/update.py
