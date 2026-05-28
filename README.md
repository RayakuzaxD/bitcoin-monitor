# Bitcoin Monitor

Monitor profissional de Bitcoin para Windows, com painel de mercado, rede Bitcoin, macro, ciclo, noticias, alertas, indicadores tecnicos e dados publicos de derivativos.

## Como rodar no Windows

Use o executavel pronto:

```text
dist\BitcoinMonitor.exe
```

Ou rode pelo Python:

```powershell
python bitcoin_monitor_windows.py
```

Tambem existe um atalho simples:

```text
run_windows_app.bat
```

## Recursos atuais

- Painel principal com BTC/USD, BTC/BRL, variacao 24h, 7D e 30D, dominancia BTC, market cap, volume, spread e order book.
- Aba Indicadores com visao diaria, semanal e mensal, grafico interativo e camadas selecionaveis.
- Indicadores tecnicos: MM50, MM100, MM200, EMA21, EMA50, Bollinger, Keltner, Donchian, Ichimoku, RSI14, MACD, ATR14, ADX14, Stoch RSI, MFI, OBV, VWMA20 e volume.
- Aba Derivativos com funding, funding anualizado, basis mark/index, open interest, OI 7D/30D, long/short ratio, taker buy/sell e opcoes Deribit.
- Aba Rede com mempool, fees, blocos projetados, altura do bloco e ajuste de dificuldade.
- Aba Macro/Ciclo com dados oficiais do FRED, Mayer Multiple, Pi Cycle, 200W multiple, halving, subsidy, supply e emissao anual.
- Aba Carteira/Risco com quantidade de BTC, preco medio, P/L, alocacao, DCA, VaR 30D aproximado e persistencia local.
- Aba Relatorio com resumo 7D/30D de mercado, tecnica, derivativos, rede, macro, carteira, noticias e pontos de atencao.
- Aba Noticias com RSS publico, deduplicacao, classificacao por tema e leitura de impacto.
- Alertas locais para preco, variacao, fees, mempool, funding, open interest e long/short.
- Cache local em SQLite para reduzir rate limit e manter dados recentes quando alguma fonte publica falhar.
- Auto-update por manifesto versionado, com validacao SHA-256 antes de instalar.

## Fontes de dados

- Binance Spot API: candles, ticker e livro de ofertas.
- Binance USDS-M Futures API: funding, premium index, open interest, long/short e taker buy/sell.
- Deribit public API: resumo de opcoes BTC.
- CoinGecko API: preco agregado, BTC/BRL, market cap, volume, dominancia e variacoes 1h/24h/7d/30d.
- mempool.space API: fees, mempool, blocos projetados, altura do bloco e ajuste de dificuldade.
- Federal Reserve/FRED: US 10Y, Fed Funds, VIX, dollar amplo, CPI, M2 e balanco do Fed.
- Alternative.me: Fear & Greed Index.
- RSS: Cointelegraph BR, CoinDesk, Bitcoin Magazine, Bitcoin Optech, Decrypt e CryptoSlate.

## Gerar release

No diretorio do projeto:

```powershell
.\build_windows_exe.ps1
```

Esse comando gera:

```text
dist\BitcoinMonitor.exe
release\BitcoinMonitor.exe
release\update_manifest.json
BitcoinMonitor-v0.5.0-release.zip
```

## Auto-update

O app usa esta URL fixa para o manifesto de atualizacao:

```text
https://github.com/RayakuzaxD/bitcoin-monitor/releases/latest/download/update_manifest.json
```

O manifesto tem este formato:

```json
{
  "version": "0.5.0",
  "release_url": "https://github.com/RayakuzaxD/bitcoin-monitor/releases/tag/v0.5.0",
  "download_url": "https://github.com/RayakuzaxD/bitcoin-monitor/releases/download/v0.5.0/BitcoinMonitor.exe",
  "sha256": "...",
  "notes": ["Notas da versao"]
}
```

Tambem e possivel sobrescrever a URL por:

- Variavel de ambiente `BITCOIN_MONITOR_UPDATE_URL`.
- Arquivo `%APPDATA%\BitcoinMonitor\update_config.json`.
- Arquivo `update_config.json` ao lado do executavel.

## Publicacao

O workflow `.github/workflows/windows-release.yml` cria o executavel em Windows, gera manifesto, cria o zip e publica os assets na release do GitHub quando uma tag `v*` e enviada.

Para publicar manualmente a proxima versao:

```powershell
.\build_windows_exe.ps1
gh release create v0.5.0 release\BitcoinMonitor.exe BitcoinMonitor-v0.5.0-release.zip release\update_manifest.json --title v0.5.0 --notes-file release\update_manifest.json
```

## Problemas comuns

Se o Windows mostrar `Failed to load Python DLL`, instale a versao mais recente publicada na release. A partir da `v0.4.1`, o pacote inclui as DLLs de runtime do Visual C++ usadas pelo Python 3.13.

## Arquivos locais

O app grava dados do usuario em:

```text
%APPDATA%\BitcoinMonitor\
```

Principais arquivos:

- `alerts.json`: alertas locais.
- `portfolio.json`: carteira local informada pelo usuario.
- `bitcoin_monitor.db`: cache HTTP, snapshots e noticias recentes.
- `update_config.json`: URL customizada de manifesto, quando existir.
