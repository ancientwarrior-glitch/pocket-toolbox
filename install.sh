#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if ! command -v pkg >/dev/null || [[ -z "${PREFIX:-}" ]]; then
  echo 'Run this installer inside Termux on Android.' >&2
  exit 1
fi
pkg install -y python nano newsboat poppler
python src/install.py "$PWD"
