#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m muldeaiserv doctor
printf '\nSetup complete. Start: .venv/bin/python -m muldeaiserv serve\n'
