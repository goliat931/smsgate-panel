# Builds dist\SmsPanel.exe (single file, no Python needed on the user's machine).
# Requires uv (https://docs.astral.sh/uv/). Run: powershell -ExecutionPolicy Bypass -File build.ps1
# Keep this file ASCII-only: Windows PowerShell 5.1 misreads UTF-8 without BOM.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
uv sync
uv run pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed - not building." }
uv run pyinstaller --noconfirm --clean --onefile --console --name SmsPanel `
    --add-data "sms_panel/templates;sms_panel/templates" `
    --add-data "sms_panel/static;sms_panel/static" `
    --collect-submodules uvicorn `
    run.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
Copy-Item INSTRUKCJA.md, Tryb-demo.bat dist\ -Force
Write-Host "Done: dist\SmsPanel.exe"
