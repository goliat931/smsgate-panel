#!/usr/bin/env sh
# Buduje dist/SmsPanel (macOS / Linux). Wymaga: uv (https://docs.astral.sh/uv/).
set -e
cd "$(dirname "$0")"
uv sync
uv run pytest -q
uv run pyinstaller --noconfirm --clean --onefile --console --name SmsPanel \
    --add-data "sms_panel/templates:sms_panel/templates" \
    --add-data "sms_panel/static:sms_panel/static" \
    --collect-submodules uvicorn \
    run.py
cp INSTRUKCJA.md dist/
echo "Gotowe: dist/SmsPanel"
