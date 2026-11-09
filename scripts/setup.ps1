# MulDeAIServ Windows bootstrap. Run from repository root.
$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } elseif (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { throw 'Python 3.11+ not found.' }
if ($python -eq 'py') { & py -3 -m venv .venv } else { & python -m venv .venv }
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
$venvPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& $venvPython -m pip install -e '.[dev]'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $venvPython -m muldeaiserv doctor
Write-Host 'Setup complete. Start: .venv\Scripts\python.exe -m muldeaiserv serve' -ForegroundColor Green
