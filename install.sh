#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if ! command -v pkg >/dev/null || [[ -z "${PREFIX:-}" ]]; then
  echo 'Run this installer inside Termux on Android.' >&2
  exit 1
fi
# Refuse an older-format update before package installation can alter runtimes.
if [[ -e "$HOME/Everyday/.pocket-vault-required" || -e "$HOME/.config/books-menu/.pocket-vault-required" ]]; then
  echo 'Encrypted working records exist. Use an encryption-aware update; this generic installer stopped.' >&2
  exit 1
fi
if command -v python >/dev/null; then
  python - "$PWD/finance" <<'PYGUARD'
from pathlib import Path
import sys
sys.path.insert(0,sys.argv[1])
from pocket_security import require_plain_storage
require_plain_storage(Path.home())
PYGUARD
fi
pkg install -y python nano newsboat poppler age
python src/install.py "$PWD"
