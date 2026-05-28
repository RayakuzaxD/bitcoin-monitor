$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$version = "0.3.0"
$tag = "v$version"
$buildDist = Join-Path $PSScriptRoot "dist-build"

python -m pip install --user --upgrade pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name BitcoinMonitor --distpath "$buildDist" bitcoin_monitor_windows.py
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller falhou com codigo $LASTEXITCODE"
}

$exePath = Join-Path $PSScriptRoot "dist\BitcoinMonitor.exe"
$builtExePath = Join-Path $buildDist "BitcoinMonitor.exe"
$releaseDir = Join-Path $PSScriptRoot "release"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
Copy-Item -Force -Path $builtExePath -Destination (Join-Path $releaseDir "BitcoinMonitor.exe")

$distDir = Join-Path $PSScriptRoot "dist"
New-Item -ItemType Directory -Force -Path $distDir | Out-Null
try {
  Copy-Item -Force -Path $builtExePath -Destination $exePath
} catch {
  Write-Warning "Nao foi possivel atualizar dist\BitcoinMonitor.exe. Feche o app aberto e rode o script novamente se precisar atualizar essa copia."
}

$releaseExePath = Join-Path $releaseDir "BitcoinMonitor.exe"
$sha = (Get-FileHash -Algorithm SHA256 -Path $releaseExePath).Hash.ToLowerInvariant()
$manifest = [ordered]@{
  version = $version
  release_url = "https://github.com/RayakuzaxD/bitcoin-monitor/releases/tag/$tag"
  download_url = "https://github.com/RayakuzaxD/bitcoin-monitor/releases/download/$tag/BitcoinMonitor.exe"
  sha256 = $sha
  notes = @(
    "Cache local em SQLite para reduzir falhas e rate limit.",
    "Novas abas de Rede e Derivativos com mempool blocks, funding, open interest, long/short e opcoes Deribit.",
    "Indicadores avancados no grafico: EMA, Keltner, Donchian, Ichimoku, ATR, ADX, Stoch RSI, MFI, OBV e VWMA.",
    "Noticias com mais fontes, classificacao por tema e impacto."
  )
}
$manifestJson = $manifest | ConvertTo-Json -Depth 4
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $releaseDir "update_manifest.json"), $manifestJson, $utf8NoBom)

$zipPath = Join-Path $PSScriptRoot "BitcoinMonitor-$tag-release.zip"
if (Test-Path $zipPath) {
  Remove-Item -Force $zipPath
}
Compress-Archive -Path (Join-Path $releaseDir "*") -DestinationPath $zipPath

Write-Host ""
Write-Host "Executavel de release em: $releaseExePath"
Write-Host "Pacote de release em: $releaseDir"
Write-Host "Zip gerado em: $zipPath"
