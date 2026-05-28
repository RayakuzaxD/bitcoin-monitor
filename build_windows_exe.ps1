$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$version = "0.5.0"
$tag = "v$version"
$buildDist = Join-Path $PSScriptRoot "dist-build"
$pythonRoot = (& python -c "import sys; print(sys.base_prefix)").Trim()
$runtimeBinaries = @()
foreach ($dll in @("vcruntime140.dll", "vcruntime140_1.dll")) {
  $candidate = Join-Path $pythonRoot $dll
  if (Test-Path $candidate) {
    $runtimeBinaries += @("--add-binary", "$candidate;.")
  }
}

python -m pip install --user --upgrade pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --noupx --name BitcoinMonitor --distpath "$buildDist" @runtimeBinaries bitcoin_monitor_windows.py
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller falhou com codigo $LASTEXITCODE"
}

$exePath = Join-Path $PSScriptRoot "dist\BitcoinMonitor.exe"
$builtExePath = Join-Path $buildDist "BitcoinMonitor.exe"
$releaseDir = Join-Path $PSScriptRoot "release-$tag"
$stableReleaseDir = Join-Path $PSScriptRoot "release"
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
New-Item -ItemType Directory -Force -Path $stableReleaseDir | Out-Null
Copy-Item -Force -Path $builtExePath -Destination (Join-Path $releaseDir "BitcoinMonitor.exe")

$distDir = Join-Path $PSScriptRoot "dist"
New-Item -ItemType Directory -Force -Path $distDir | Out-Null
try {
  Copy-Item -Force -Path $builtExePath -Destination $exePath
} catch {
  Write-Warning "Nao foi possivel atualizar dist\BitcoinMonitor.exe. Feche o app aberto e rode o script novamente se precisar atualizar essa copia."
}

$releaseExePath = Join-Path $releaseDir "BitcoinMonitor.exe"
try {
  Copy-Item -Force -Path $releaseExePath -Destination (Join-Path $stableReleaseDir "BitcoinMonitor.exe")
} catch {
  Write-Warning "Nao foi possivel atualizar release\BitcoinMonitor.exe. A release versionada foi gerada normalmente."
}

$sha = (Get-FileHash -Algorithm SHA256 -Path $releaseExePath).Hash.ToLowerInvariant()
$manifest = [ordered]@{
  version = $version
  release_url = "https://github.com/RayakuzaxD/bitcoin-monitor/releases/tag/$tag"
  download_url = "https://github.com/RayakuzaxD/bitcoin-monitor/releases/download/$tag/BitcoinMonitor.exe"
  sha256 = $sha
  notes = @(
    "Nova aba Carteira/Risco com P/L, alocacao, DCA, risco 30D e persistencia local.",
    "Nova aba Relatorio 7D/30D consolidando mercado, tecnica, derivativos, rede, macro, carteira e noticias.",
    "Relatorio pode ser copiado para acompanhamento semanal.",
    "Mantem a correcao de empacotamento Windows com DLLs de runtime."
  )
}
$manifestJson = $manifest | ConvertTo-Json -Depth 4
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $releaseDir "update_manifest.json"), $manifestJson, $utf8NoBom)
try {
  [System.IO.File]::WriteAllText((Join-Path $stableReleaseDir "update_manifest.json"), $manifestJson, $utf8NoBom)
} catch {
  Write-Warning "Nao foi possivel atualizar release\update_manifest.json."
}

$zipPath = Join-Path $PSScriptRoot "BitcoinMonitor-$tag-release.zip"
if (Test-Path $zipPath) {
  Remove-Item -Force $zipPath
}
Compress-Archive -Path (Join-Path $releaseDir "*") -DestinationPath $zipPath

Write-Host ""
Write-Host "Executavel de release em: $releaseExePath"
Write-Host "Pacote de release em: $releaseDir"
Write-Host "Zip gerado em: $zipPath"
