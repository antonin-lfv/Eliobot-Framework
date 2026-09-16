#!/usr/bin/env bash
# Lanceur macOS / Linux / Raspberry Pi. Le diagnostic est fait sur l'hôte.
set -e
if ! command -v python3 >/dev/null 2>&1; then
    echo "Installer Python 3.11 ou plus récent, puis relancer ce script."
    exit 1
fi
exec python3 "$(dirname "$0")/setup.py" "$@"
