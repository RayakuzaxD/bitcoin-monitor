$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

python -m pip install --user --upgrade pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name BitcoinMonitor bitcoin_monitor_windows.py

$exePath = Join-Path $PSScriptRoot "dist\BitcoinMonitor.exe"
$releaseDir = Join-Path $PSScriptRoot "release"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
Copy-Item -Force -Path $exePath -Destination (Join-Path $releaseDir "BitcoinMonitor.exe")

$sha = (Get-FileHash -Algorithm SHA256 -Path $exePath).Hash.ToLowerInvariant()
$manifest = [ordered]@{
  version = "0.2.0"
  release_url = "https://github.com/RayakuzaxD/bitcoin-monitor/releases/tag/v0.2.0"
  download_url = "https://github.com/RayakuzaxD/bitcoin-monitor/releases/download/v0.2.0/BitcoinMonitor.exe"
  sha256 = $sha
  notes = @(
    "Grafico de indicadores com camadas selecionaveis.",
    "Noticias atualizadas por RSS.",
    "Base de auto-update via GitHub Releases."
  )
}
$manifestJson = $manifest | ConvertTo-Json -Depth 4
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $releaseDir "update_manifest.json"), $manifestJson, $utf8NoBom)

Write-Host ""
Write-Host "Executavel gerado em: $exePath"
Write-Host "Pacote de release em: $releaseDir"
