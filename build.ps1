# Builds a single-file Windows executable for ytm-alice remote.
# Requires Python 3.10+ with pywebview and pyinstaller (pip install pywebview pyinstaller pillow).
[CmdletBinding()]
param(
    [string]$Name = "ytm-alice-remote"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path "icon.ico")) {
    if (Test-Path "icon.png") {
        python -c "from PIL import Image; Image.open('icon.png').save('icon.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
    } else {
        throw "icon.png not found"
    }
}

pyinstaller --noconfirm --onefile --windowed --name $Name --icon "icon.ico" "ytm_alice_remote.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = Join-Path "dist" "$Name.exe"
Write-Host "Built: $exe"
