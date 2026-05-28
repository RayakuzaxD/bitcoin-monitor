# Bitcoin Monitor

Monitor completo de Bitcoin para Windows, com painel de mercado, rede Bitcoin, noticias, alertas e indicadores tecnicos.

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
```

## Auto-update

O app ja tem a base de auto-update:

1. Publicar `release\BitcoinMonitor.exe` em um GitHub Release.
2. Publicar `release\update_manifest.json` em uma URL publica.
3. Configurar a URL do manifesto no app.

O manifesto tem este formato:

```json
{
  "version": "0.2.0",
  "release_url": "https://github.com/RayakuzaxD/bitcoin-monitor/releases/tag/v0.2.0",
  "download_url": "https://raw.githubusercontent.com/RayakuzaxD/bitcoin-monitor/refs/heads/main/release/BitcoinMonitor.exe",
  "sha256": "...",
  "notes": ["Notas da versao"]
}
```

Formas de configurar o manifesto:

- Variavel de ambiente `BITCOIN_MONITOR_UPDATE_URL`.
- Arquivo `%APPDATA%\BitcoinMonitor\update_config.json`.
- Arquivo `update_config.json` ao lado do executavel.
- Recompilar com `DEFAULT_UPDATE_MANIFEST_URL` preenchido no codigo.

Modelo:

```text
update_config.template.json
```

## Recursos atuais

- Aba Painel com preco BTC/USD e BTC/BRL, candles, order book, mempool, fees, altura do bloco e alertas.
- Aba Indicadores com visao semanal e mensal.
- Grafico interativo com camadas selecionaveis: MM50, MM100, MM200, Bollinger e Volume.
- Hover no grafico com OHLC, volume e indicadores do candle.
- RSI 14, MACD, volume atual e comparacao com volume medio.
- Aba Noticias com Cointelegraph BR, CoinDesk e Bitcoin Magazine via RSS.
- Aba Atualizacao com checagem de nova versao via manifesto.
- Alertas locais salvos em `%APPDATA%\BitcoinMonitor\alerts.json`.

## Fontes de dados

- Binance Spot API: candles e livro de ofertas.
- CoinGecko API: preco agregado, BTC/BRL, volume e market cap.
- mempool.space API: fees, mempool, bloco atual e ajuste de dificuldade.
- Alternative.me: Fear & Greed Index.
- RSS: Cointelegraph BR, CoinDesk e Bitcoin Magazine.

## Proximos passos

1. Publicar o repositorio no GitHub.
2. Criar o primeiro GitHub Release `v0.2.0`.
3. Subir `BitcoinMonitor.exe` como asset da release.
4. Ajustar `update_manifest.json` com URLs reais.
5. Publicar o manifesto em uma URL fixa.
6. Recompilar o app com `DEFAULT_UPDATE_MANIFEST_URL` real ou distribuir `update_config.json`.
