import base64
import concurrent.futures
import csv
import datetime as dt
import email.utils
import hashlib
import html
import io
import json
import math
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
import winsound
import xml.etree.ElementTree as ET
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, BooleanVar, Canvas, Checkbutton, Frame, Label, StringVar, Tk, Toplevel
from tkinter import messagebox, ttk


APP_NAME = "Bitcoin Monitor"
APP_VERSION = "0.5.0"
APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "BitcoinMonitor"
ALERTS_FILE = APP_DIR / "alerts.json"
PORTFOLIO_FILE = APP_DIR / "portfolio.json"
DB_FILE = APP_DIR / "bitcoin_monitor.db"
UPDATE_CONFIG_FILE = APP_DIR / "update_config.json"
DEFAULT_UPDATE_MANIFEST_URL = "https://github.com/RayakuzaxD/bitcoin-monitor/releases/latest/download/update_manifest.json"

ENDPOINTS = {
    "coingecko": (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin&vs_currencies=usd,brl"
        "&include_market_cap=true&include_24hr_vol=true&include_24hr_change=true"
    ),
    "coingecko_markets": (
        "https://api.coingecko.com/api/v3/coins/markets"
        "?vs_currency=usd&ids=bitcoin"
        "&price_change_percentage=1h,24h,7d,30d,1y"
        "&sparkline=false"
    ),
    "coingecko_global": "https://api.coingecko.com/api/v3/global",
    "binance_ticker": "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT",
    "candles": "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={interval}&limit=180",
    "daily_candles": "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=1000",
    "weekly_candles": "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1w&limit=500",
    "monthly_candles": "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1M&limit=240",
    "depth": "https://api.binance.com/api/v3/depth?symbol=BTCUSDT&limit=20",
    "fees": "https://mempool.space/api/v1/fees/recommended",
    "mempool_blocks": "https://mempool.space/api/v1/fees/mempool-blocks",
    "mempool": "https://mempool.space/api/mempool",
    "tip_height": "https://mempool.space/api/blocks/tip/height",
    "difficulty": "https://mempool.space/api/v1/difficulty-adjustment",
    "fear_greed": "https://api.alternative.me/fng/?limit=1",
    "futures_open_interest": "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT",
    "futures_funding": "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=8",
    "futures_premium": "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT",
    "futures_open_interest_hist": (
        "https://fapi.binance.com/futures/data/openInterestHist"
        "?symbol=BTCUSDT&period=1d&limit=30"
    ),
    "futures_long_short": (
        "https://fapi.binance.com/futures/data/topLongShortPositionRatio"
        "?symbol=BTCUSDT&period=1d&limit=30"
    ),
    "futures_taker_ratio": (
        "https://fapi.binance.com/futures/data/takerlongshortRatio"
        "?symbol=BTCUSDT&period=1d&limit=30"
    ),
    "deribit_options": (
        "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
        "?currency=BTC&kind=option"
    ),
}

FRED_SERIES = {
    "fred_10y": ("US 10Y", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"),
    "fred_fed_funds": ("Fed Funds", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF"),
    "fred_vix": ("VIX", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS"),
    "fred_dollar": ("Dollar amplo", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS"),
    "fred_cpi": ("CPI", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"),
    "fred_m2": ("M2", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=M2SL"),
    "fred_fed_balance": ("Balanco Fed", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=WALCL"),
}

HALVING_INTERVAL = 210_000
INITIAL_SUBSIDY = 50.0

NEWS_FEEDS = [
    ("Cointelegraph BR", "https://cointelegraph.com.br/rss/tag/bitcoin"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"),
    ("Bitcoin Optech", "https://bitcoinops.org/feed.xml"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("CryptoSlate", "https://cryptoslate.com/feed/"),
]

CACHE_TTLS = {
    "coingecko": 35,
    "coingecko_markets": 90,
    "coingecko_global": 300,
    "binance_ticker": 15,
    "candles": 30,
    "daily_candles": 3_600,
    "weekly_candles": 10_800,
    "monthly_candles": 21_600,
    "depth": 15,
    "fees": 30,
    "mempool_blocks": 30,
    "mempool": 30,
    "tip_height": 20,
    "difficulty": 600,
    "fear_greed": 3_600,
    "futures_open_interest": 45,
    "futures_funding": 300,
    "futures_premium": 45,
    "futures_open_interest_hist": 600,
    "futures_long_short": 600,
    "futures_taker_ratio": 600,
    "deribit_options": 300,
    "fred_10y": 21_600,
    "fred_fed_funds": 21_600,
    "fred_vix": 21_600,
    "fred_dollar": 21_600,
    "fred_cpi": 43_200,
    "fred_m2": 43_200,
    "fred_fed_balance": 43_200,
}

NEWS_CATEGORIES = [
    ("ETF/Institucional", ["etf", "blackrock", "fidelity", "strategy", "treasury", "tesouraria"]),
    ("Regulacao", ["sec", "cvm", "regulation", "regulacao", "regulador", "lei", "law", "ban", "tax"]),
    ("Macro", ["fed", "fomc", "cpi", "inflation", "inflacao", "dxy", "rates", "juros"]),
    ("Mineracao", ["miner", "mining", "mineracao", "hashrate", "difficulty", "halving"]),
    ("Rede/On-chain", ["mempool", "lightning", "taproot", "ordinals", "inscriptions", "wallet", "node"]),
    ("Derivativos", ["funding", "futures", "options", "open interest", "liquidation", "derivatives"]),
]

COLORS = {
    "bg": "#100f0c",
    "panel": "#191713",
    "panel_2": "#211e18",
    "line": "#373124",
    "line_soft": "#2a261e",
    "text": "#f4efe4",
    "muted": "#a99f90",
    "dim": "#746b5d",
    "orange": "#f7931a",
    "green": "#35c46b",
    "red": "#ee5d50",
    "cyan": "#3ccfcf",
}

INTERVALS = {
    "1m": "1 minuto",
    "5m": "5 minutos",
    "15m": "15 minutos",
    "1h": "1 hora",
    "1d": "1 dia",
}

METRICS = {
    "Preco USD": "price_usd",
    "Preco BRL": "price_brl",
    "Variacao 24h %": "change_24h",
    "Fee rapida sat/vB": "fee_fastest",
    "Mempool vMB": "mempool_vmb",
    "Funding %": "funding_rate_pct",
    "Open interest USD": "open_interest_usd",
    "Long/Short ratio": "long_short_ratio",
}


def fetch_json(url, timeout=10):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"BitcoinMonitor/{APP_VERSION} (+https://github.com/RayakuzaxD/bitcoin-monitor)",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8-sig")
        return json.loads(payload)


def fetch_text(url, timeout=10):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"BitcoinMonitor/{APP_VERSION} (+https://github.com/RayakuzaxD/bitcoin-monitor)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8-sig").strip()


def fetch_update_manifest(url, timeout=15):
    data = fetch_json(url, timeout)
    if isinstance(data, dict) and data.get("encoding") == "base64" and data.get("content"):
        packed = "".join(str(data["content"]).split())
        text = base64.b64decode(packed).decode("utf-8-sig")
        return json.loads(text)
    return data


def fetch_fred_series(url, timeout=20):
    text = fetch_text(url, timeout)
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        if not row:
            continue
        date_value = row.get("observation_date") or row.get("DATE") or row.get("date")
        value = None
        for key, raw in row.items():
            if key and key.lower() not in ("observation_date", "date"):
                value = raw
                break
        numeric = parse_float(value)
        if date_value and numeric is not None:
            rows.append({"date": date_value, "value": numeric})
    return rows


def download_file(url, destination, timeout=60):
    request = urllib.request.Request(url, headers={"User-Agent": f"BitcoinMonitor/{APP_VERSION}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        with open(destination, "wb") as file:
            shutil.copyfileobj(response, file)


def parse_float(value):
    try:
        if value is None or value == ".":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class LocalStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.ensure_schema()

    def connect(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path, timeout=8)

    def ensure_schema(self):
        with self.lock:
            with self.connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS http_cache (
                        cache_key TEXT PRIMARY KEY,
                        fetched_at REAL NOT NULL,
                        payload TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS market_snapshots (
                        created_at REAL NOT NULL,
                        metrics_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS news_items (
                        link TEXT PRIMARY KEY,
                        source TEXT,
                        title TEXT,
                        summary TEXT,
                        category TEXT,
                        impact TEXT,
                        published TEXT,
                        saved_at REAL NOT NULL
                    )
                    """
                )

    def get_cache(self, cache_key, max_age=None):
        with self.lock:
            with self.connect() as connection:
                row = connection.execute(
                    "SELECT fetched_at, payload FROM http_cache WHERE cache_key = ?",
                    (cache_key,),
                ).fetchone()
        if not row:
            return None
        fetched_at, payload = row
        if max_age is not None and time.time() - fetched_at > max_age:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None

    def set_cache(self, cache_key, payload):
        with self.lock:
            with self.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO http_cache(cache_key, fetched_at, payload)
                    VALUES (?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        fetched_at = excluded.fetched_at,
                        payload = excluded.payload
                    """,
                    (cache_key, time.time(), json.dumps(payload)),
                )

    def save_market_snapshot(self, metrics):
        packed = json.dumps(metrics, sort_keys=True)
        with self.lock:
            with self.connect() as connection:
                connection.execute(
                    "INSERT INTO market_snapshots(created_at, metrics_json) VALUES (?, ?)",
                    (time.time(), packed),
                )
                connection.execute(
                    """
                    DELETE FROM market_snapshots
                    WHERE rowid NOT IN (
                        SELECT rowid FROM market_snapshots ORDER BY created_at DESC LIMIT 2500
                    )
                    """
                )

    def save_news(self, items):
        with self.lock:
            with self.connect() as connection:
                for item in items:
                    published = item.get("published")
                    if isinstance(published, dt.datetime):
                        published = published.isoformat()
                    connection.execute(
                        """
                        INSERT INTO news_items(
                            link, source, title, summary, category, impact, published, saved_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(link) DO UPDATE SET
                            source = excluded.source,
                            title = excluded.title,
                            summary = excluded.summary,
                            category = excluded.category,
                            impact = excluded.impact,
                            published = excluded.published,
                            saved_at = excluded.saved_at
                        """,
                        (
                            item.get("link") or item.get("title"),
                            item.get("source"),
                            item.get("title"),
                            item.get("summary"),
                            item.get("category"),
                            item.get("impact"),
                            published,
                            time.time(),
                        ),
                    )

    def load_news(self, limit=40):
        with self.lock:
            with self.connect() as connection:
                rows = connection.execute(
                    """
                    SELECT source, title, summary, category, impact, published, link
                    FROM news_items
                    ORDER BY COALESCE(published, '') DESC, saved_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        items = []
        for source, title, summary, category, impact, published, link in rows:
            items.append(
                {
                    "source": source or "Cache",
                    "title": title or "Sem titulo",
                    "summary": summary or "",
                    "category": category or "Mercado",
                    "impact": impact or "normal",
                    "published": BitcoinMonitorApp.parse_date(published) if published else None,
                    "link": link or "",
                    "cached": True,
                }
            )
        return items


def format_currency(value, currency="USD", decimals=2):
    if value is None or not math.isfinite(value):
        return "--"
    prefix = "US$" if currency == "USD" else "R$"
    return f"{prefix} {value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def format_compact_currency(value, currency="USD"):
    if value is None or not math.isfinite(value):
        return "--"
    prefix = "US$" if currency == "USD" else "R$"
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"{prefix} {value / 1_000_000_000_000:.2f} tri".replace(".", ",")
    if abs_value >= 1_000_000_000:
        return f"{prefix} {value / 1_000_000_000:.2f} bi".replace(".", ",")
    if abs_value >= 1_000_000:
        return f"{prefix} {value / 1_000_000:.2f} mi".replace(".", ",")
    return format_currency(value, currency)


def format_number(value, decimals=2):
    if value is None or not math.isfinite(value):
        return "--"
    return f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def format_compact_number(value, decimals=2):
    if value is None or not math.isfinite(value):
        return "--"
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.{decimals}f} bi".replace(".", ",")
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.{decimals}f} mi".replace(".", ",")
    if abs_value >= 1_000:
        return f"{value / 1_000:.{decimals}f} mil".replace(".", ",")
    return format_number(value, decimals)


def format_percent(value):
    if value is None or not math.isfinite(value):
        return "--"
    sign = "+" if value > 0 else ""
    return f"{sign}{format_number(value, 2)}%"


def format_btc(value):
    if value is None or not math.isfinite(value):
        return "--"
    return f"{format_number(value, 2)} BTC"


def format_btc_precise(value):
    if value is None or not math.isfinite(value):
        return "--"
    return f"{format_number(value, 8)} BTC"


def format_signed_currency(value, currency="USD"):
    if value is None or not math.isfinite(value):
        return "--"
    sign = "+" if value > 0 else ""
    return f"{sign}{format_currency(value, currency)}"


def format_timestamp_ms(value):
    try:
        if not value:
            return "--"
        return dt.datetime.fromtimestamp(float(value) / 1000).strftime("%d/%m %H:%M")
    except Exception:
        return "--"


def format_duration_ms(value):
    try:
        seconds = max(0, int(float(value) / 1000))
    except Exception:
        return "--"
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours >= 24:
        days = hours // 24
        return f"{days}d {hours % 24}h"
    return f"{hours}h {minutes}m"


def metric_value_label(metric, value):
    if metric == "price_usd":
        return format_currency(value, "USD")
    if metric == "price_brl":
        return format_currency(value, "BRL", 0)
    if metric == "change_24h":
        return format_percent(value)
    if metric == "fee_fastest":
        return f"{format_number(value, 0)} sat/vB"
    if metric == "mempool_vmb":
        return f"{format_number(value, 1)} vMB"
    if metric == "funding_rate_pct":
        return format_percent(value)
    if metric == "open_interest_usd":
        return format_compact_currency(value, "USD")
    if metric == "long_short_ratio":
        return format_number(value, 2)
    return format_number(value, 2)


def parse_version(version):
    parts = re.findall(r"\d+", str(version or "0"))
    numbers = [int(part) for part in parts[:3]]
    while len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers)


def is_newer_version(candidate, current):
    return parse_version(candidate) > parse_version(current)


def translate_fear_greed(value):
    return {
        "Extreme Fear": "Medo extremo",
        "Fear": "Medo",
        "Neutral": "Neutro",
        "Greed": "Ganancia",
        "Extreme Greed": "Ganancia extrema",
    }.get(value, value)


def sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def rolling_sma(values, period):
    output = []
    running = 0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        output.append(running / period if index >= period - 1 else None)
    return output


def rolling_std(values, period):
    output = []
    for index in range(len(values)):
        if index < period - 1:
            output.append(None)
            continue
        window = values[index - period + 1 : index + 1]
        mean = sum(window) / period
        variance = sum((item - mean) ** 2 for item in window) / period
        output.append(math.sqrt(variance))
    return output


def ema_series(values, period):
    if not values:
        return []
    multiplier = 2 / (period + 1)
    output = []
    ema = None
    for index, value in enumerate(values):
        if index < period - 1:
            output.append(None)
            continue
        if ema is None:
            ema = sum(values[index - period + 1 : index + 1]) / period
        else:
            ema = value * multiplier + ema * (1 - multiplier)
        output.append(ema)
    return output


def rsi_value(values, period=14):
    if len(values) <= period:
        return None
    gains = []
    losses = []
    for index in range(len(values) - period, len(values)):
        change = values[index] - values[index - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd_value(values):
    if len(values) < 35:
        return None, None, None
    ema12 = ema_series(values, 12)
    ema26 = ema_series(values, 26)
    macd_line = [
        fast - slow if fast is not None and slow is not None else None
        for fast, slow in zip(ema12, ema26)
    ]
    valid_macd = [item for item in macd_line if item is not None]
    signal_series = ema_series(valid_macd, 9)
    if not valid_macd or not signal_series or signal_series[-1] is None:
        return macd_line[-1], None, None
    macd_latest = valid_macd[-1]
    signal_latest = signal_series[-1]
    return macd_latest, signal_latest, macd_latest - signal_latest


def last_valid(values):
    for value in reversed(values):
        if value is not None:
            return value
    return None


def rolling_vwma(closes, volumes, period):
    output = []
    for index in range(len(closes)):
        if index < period - 1:
            output.append(None)
            continue
        price_volume = 0
        volume_total = 0
        for offset in range(index - period + 1, index + 1):
            price_volume += closes[offset] * volumes[offset]
            volume_total += volumes[offset]
        output.append(price_volume / volume_total if volume_total else None)
    return output


def true_range_series(candles):
    output = []
    for index, candle in enumerate(candles):
        if index == 0:
            output.append(candle["high"] - candle["low"])
            continue
        previous_close = candles[index - 1]["close"]
        output.append(
            max(
                candle["high"] - candle["low"],
                abs(candle["high"] - previous_close),
                abs(candle["low"] - previous_close),
            )
        )
    return output


def atr_series(candles, period=14):
    ranges = true_range_series(candles)
    if not ranges:
        return []
    output = []
    atr = None
    for index, value in enumerate(ranges):
        if index < period - 1:
            output.append(None)
            continue
        if atr is None:
            atr = sum(ranges[index - period + 1 : index + 1]) / period
        else:
            atr = ((atr * (period - 1)) + value) / period
        output.append(atr)
    return output


def rsi_series(values, period=14):
    if len(values) <= period:
        return [None] * len(values)
    output = [None] * len(values)
    gains = []
    losses = []
    for index in range(1, period + 1):
        change = values[index] - values[index - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    output[period] = 100 if avg_loss == 0 else 100 - (100 / (1 + (avg_gain / avg_loss)))
    for index in range(period + 1, len(values)):
        change = values[index] - values[index - 1]
        gain = max(change, 0)
        loss = abs(min(change, 0))
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        output[index] = 100 if avg_loss == 0 else 100 - (100 / (1 + (avg_gain / avg_loss)))
    return output


def stoch_rsi_value(values, rsi_period=14, stoch_period=14):
    series = [item for item in rsi_series(values, rsi_period) if item is not None]
    if len(series) < stoch_period:
        return None
    window = series[-stoch_period:]
    low = min(window)
    high = max(window)
    if high == low:
        return 50
    return ((series[-1] - low) / (high - low)) * 100


def adx_value(candles, period=14):
    if len(candles) < period * 2 + 1:
        return None
    trs = []
    plus_dm = []
    minus_dm = []
    for index in range(1, len(candles)):
        current = candles[index]
        previous = candles[index - 1]
        up_move = current["high"] - previous["high"]
        down_move = previous["low"] - current["low"]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)
        trs.append(
            max(
                current["high"] - current["low"],
                abs(current["high"] - previous["close"]),
                abs(current["low"] - previous["close"]),
            )
        )
    atr = sum(trs[:period])
    plus = sum(plus_dm[:period])
    minus = sum(minus_dm[:period])
    dx_values = []
    for index in range(period, len(trs)):
        atr = atr - (atr / period) + trs[index]
        plus = plus - (plus / period) + plus_dm[index]
        minus = minus - (minus / period) + minus_dm[index]
        if atr == 0:
            continue
        plus_di = 100 * (plus / atr)
        minus_di = 100 * (minus / atr)
        total = plus_di + minus_di
        if total:
            dx_values.append(100 * abs(plus_di - minus_di) / total)
    if len(dx_values) < period:
        return None
    return sum(dx_values[-period:]) / period


def obv_series(candles):
    output = []
    total = 0
    for index, candle in enumerate(candles):
        if index == 0:
            output.append(total)
            continue
        if candle["close"] > candles[index - 1]["close"]:
            total += candle["volume"]
        elif candle["close"] < candles[index - 1]["close"]:
            total -= candle["volume"]
        output.append(total)
    return output


def mfi_value(candles, period=14):
    if len(candles) <= period:
        return None
    positive = 0
    negative = 0
    for index in range(len(candles) - period, len(candles)):
        current = candles[index]
        previous = candles[index - 1]
        current_typical = (current["high"] + current["low"] + current["close"]) / 3
        previous_typical = (previous["high"] + previous["low"] + previous["close"]) / 3
        money_flow = current_typical * current["volume"]
        if current_typical > previous_typical:
            positive += money_flow
        elif current_typical < previous_typical:
            negative += money_flow
    if negative == 0:
        return 100
    ratio = positive / negative
    return 100 - (100 / (1 + ratio))


def donchian_series(candles, period=20):
    upper = []
    lower = []
    for index in range(len(candles)):
        if index < period - 1:
            upper.append(None)
            lower.append(None)
            continue
        window = candles[index - period + 1 : index + 1]
        upper.append(max(item["high"] for item in window))
        lower.append(min(item["low"] for item in window))
    return upper, lower


def keltner_series(candles, period=20, multiplier=2):
    closes = [item["close"] for item in candles]
    basis = ema_series(closes, period)
    atr = atr_series(candles, period)
    upper = [
        mid + multiplier * range_value if mid is not None and range_value is not None else None
        for mid, range_value in zip(basis, atr)
    ]
    lower = [
        mid - multiplier * range_value if mid is not None and range_value is not None else None
        for mid, range_value in zip(basis, atr)
    ]
    return basis, upper, lower


def ichimoku_series(candles):
    tenkan = []
    kijun = []
    span_b = []
    for index in range(len(candles)):
        if index >= 8:
            window = candles[index - 8 : index + 1]
            tenkan.append((max(item["high"] for item in window) + min(item["low"] for item in window)) / 2)
        else:
            tenkan.append(None)
        if index >= 25:
            window = candles[index - 25 : index + 1]
            kijun.append((max(item["high"] for item in window) + min(item["low"] for item in window)) / 2)
        else:
            kijun.append(None)
        if index >= 51:
            window = candles[index - 51 : index + 1]
            span_b.append((max(item["high"] for item in window) + min(item["low"] for item in window)) / 2)
        else:
            span_b.append(None)
    span_a = [
        (fast + slow) / 2 if fast is not None and slow is not None else None
        for fast, slow in zip(tenkan, kijun)
    ]
    return tenkan, kijun, span_a, span_b


def percent_distance(value, base):
    if value is None or base in (None, 0):
        return None
    return ((value / base) - 1) * 100


def calculate_supply(height):
    if height is None:
        return {}
    try:
        blocks_mined = int(height) + 1
    except (TypeError, ValueError):
        return {}
    remaining = max(blocks_mined, 0)
    supply = 0.0
    epoch = 0
    while remaining > 0 and epoch < 34:
        blocks = min(remaining, HALVING_INTERVAL)
        subsidy = INITIAL_SUBSIDY / (2 ** epoch)
        supply += blocks * subsidy
        remaining -= blocks
        epoch += 1
    current_epoch = max(0, int(height) // HALVING_INTERVAL)
    current_subsidy = INITIAL_SUBSIDY / (2 ** current_epoch) if current_epoch < 34 else 0
    next_halving = (current_epoch + 1) * HALVING_INTERVAL
    remaining_blocks = max(next_halving - int(height), 0)
    days_remaining = remaining_blocks * 10 / 1440
    annual_issuance = current_subsidy * 144 * 365
    issuance_rate = (annual_issuance / supply) * 100 if supply else None
    return {
        "epoch": current_epoch,
        "supply": supply,
        "subsidy": current_subsidy,
        "next_halving": next_halving,
        "halving_blocks": remaining_blocks,
        "halving_days": days_remaining,
        "annual_issuance": annual_issuance,
        "issuance_rate": issuance_rate,
    }


def latest_fred_value(rows):
    for row in reversed(rows or []):
        value = parse_float(row.get("value"))
        if value is not None:
            return row.get("date"), value
    return None, None


def fred_value_before(rows, days):
    if not rows:
        return None
    latest_date_text, _latest = latest_fred_value(rows)
    if not latest_date_text:
        return None
    try:
        target = dt.datetime.strptime(latest_date_text, "%Y-%m-%d").date() - dt.timedelta(days=days)
    except ValueError:
        return None
    selected = None
    for row in rows:
        try:
            row_date = dt.datetime.strptime(row.get("date", ""), "%Y-%m-%d").date()
        except ValueError:
            continue
        value = parse_float(row.get("value"))
        if value is not None and row_date <= target:
            selected = value
    return selected


def fred_change(rows, days, absolute=False):
    _date, latest = latest_fred_value(rows)
    previous = fred_value_before(rows, days)
    if latest is None or previous in (None, 0):
        return None
    if absolute:
        return latest - previous
    return ((latest / previous) - 1) * 100


def calculate_cycle_metrics(daily_candles, weekly_candles):
    if not daily_candles:
        return {}
    closes = [item["close"] for item in daily_candles]
    if not closes:
        return {}
    last = closes[-1]
    ma200d = sma(closes, 200)
    ma111d = sma(closes, 111)
    ma350d = sma(closes, 350)
    ma365d = sma(closes, 365)
    mayer = last / ma200d if ma200d else None
    pi_top = ma350d * 2 if ma350d else None
    pi_distance = percent_distance(ma111d, pi_top) if ma111d and pi_top else None
    one_year_return = percent_distance(last, closes[-366]) if len(closes) >= 366 else None
    returns = []
    for index in range(max(1, len(closes) - 30), len(closes)):
        previous = closes[index - 1]
        if previous:
            returns.append(math.log(closes[index] / previous))
    volatility = None
    if len(returns) > 1:
        mean = sum(returns) / len(returns)
        variance = sum((item - mean) ** 2 for item in returns) / (len(returns) - 1)
        volatility = math.sqrt(variance) * math.sqrt(365) * 100
    weekly_closes = [item["close"] for item in weekly_candles or []]
    ma200w = sma(weekly_closes, 200)
    return {
        "last_close": last,
        "ma200d": ma200d,
        "ma365d": ma365d,
        "mayer_multiple": mayer,
        "pi_111d": ma111d,
        "pi_350d_2x": pi_top,
        "pi_distance": pi_distance,
        "one_year_return": one_year_return,
        "volatility_30d": volatility,
        "ma200w": ma200w,
        "ma200w_multiple": last / ma200w if ma200w else None,
    }


def calculate_indicators(candles):
    closes = [item["close"] for item in candles]
    volumes = [item["volume"] for item in candles]
    if not closes:
        return {}

    ma50 = sma(closes, 50)
    ma100 = sma(closes, 100)
    ma200 = sma(closes, 200)
    ema21 = last_valid(ema_series(closes, 21))
    ema50 = last_valid(ema_series(closes, 50))
    vwma20 = last_valid(rolling_vwma(closes, volumes, 20))
    basis = sma(closes, 20)
    std = None
    if len(closes) >= 20:
        window = closes[-20:]
        mean = sum(window) / 20
        std = math.sqrt(sum((item - mean) ** 2 for item in window) / 20)
    upper = basis + 2 * std if basis is not None and std is not None else None
    lower = basis - 2 * std if basis is not None and std is not None else None
    macd, signal, histogram = macd_value(closes)
    volume_avg = sma(volumes, 20)
    volume_change = ((volumes[-1] / volume_avg) - 1) * 100 if volume_avg else None
    last = closes[-1]
    distance_ma200 = ((last / ma200) - 1) * 100 if ma200 else None
    atr14 = last_valid(atr_series(candles, 14))
    atr_percent = (atr14 / last) * 100 if atr14 and last else None
    donchian_upper, donchian_lower = donchian_series(candles, 20)
    keltner_basis, keltner_upper, keltner_lower = keltner_series(candles, 20)
    tenkan, kijun, span_a, span_b = ichimoku_series(candles)
    obv_values = obv_series(candles)
    previous_obv = obv_values[-6] if len(obv_values) > 6 else None
    obv_change = percent_distance(obv_values[-1], previous_obv) if previous_obv else None
    donchian_high = last_valid(donchian_upper)
    donchian_low = last_valid(donchian_lower)
    trend_score = 0
    for reference in [ma50, ma100, ma200, ema21, ema50, last_valid(kijun)]:
        if reference is not None:
            trend_score += 1 if last >= reference else -1
    if histogram is not None:
        trend_score += 1 if histogram >= 0 else -1

    return {
        "last_close": last,
        "ma50": ma50,
        "ma100": ma100,
        "ma200": ma200,
        "ema21": ema21,
        "ema50": ema50,
        "vwma20": vwma20,
        "distance_ma200": distance_ma200,
        "bb_upper": upper,
        "bb_basis": basis,
        "bb_lower": lower,
        "rsi14": rsi_value(closes),
        "stoch_rsi14": stoch_rsi_value(closes),
        "mfi14": mfi_value(candles),
        "atr14": atr14,
        "atr_percent": atr_percent,
        "adx14": adx_value(candles),
        "macd": macd,
        "macd_signal": signal,
        "macd_histogram": histogram,
        "volume": volumes[-1],
        "volume_change": volume_change,
        "obv": obv_values[-1] if obv_values else None,
        "obv_change": obv_change,
        "donchian_upper": donchian_high,
        "donchian_lower": donchian_low,
        "keltner_upper": last_valid(keltner_upper),
        "keltner_basis": last_valid(keltner_basis),
        "keltner_lower": last_valid(keltner_lower),
        "ichimoku_tenkan": last_valid(tenkan),
        "ichimoku_kijun": last_valid(kijun),
        "ichimoku_span_a": last_valid(span_a),
        "ichimoku_span_b": last_valid(span_b),
        "trend_score": trend_score,
    }


def classify_news(title, summary):
    haystack = f"{title} {summary}".lower()
    for category, keywords in NEWS_CATEGORIES:
        if any(keyword in haystack for keyword in keywords):
            return category
    return "Mercado"


def news_impact(title, summary):
    haystack = f"{title} {summary}".lower()
    score = 0
    high_keywords = [
        "etf",
        "sec",
        "fed",
        "cpi",
        "hack",
        "ban",
        "liquidation",
        "liquidacao",
        "crash",
        "record",
        "all-time high",
        "ath",
    ]
    medium_keywords = [
        "funding",
        "open interest",
        "miner",
        "difficulty",
        "mempool",
        "lightning",
        "regulation",
        "regulacao",
    ]
    score += sum(2 for keyword in high_keywords if keyword in haystack)
    score += sum(1 for keyword in medium_keywords if keyword in haystack)
    if score >= 3:
        return "alto"
    if score >= 1:
        return "medio"
    return "normal"


class BitcoinMonitorApp(Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1280x820")
        self.minsize(1020, 680)
        self.configure(bg=COLORS["bg"])

        self.store = LocalStore(DB_FILE)
        self.data_queue = queue.Queue()
        self.fetch_lock = threading.Lock()
        self.fetching = False
        self.interval = StringVar(value="1m")
        self.indicator_period = StringVar(value="Semanal")
        self.indicator_layers = {
            "ma50": BooleanVar(value=True),
            "ma100": BooleanVar(value=True),
            "ma200": BooleanVar(value=True),
            "ema21": BooleanVar(value=False),
            "ema50": BooleanVar(value=False),
            "bollinger": BooleanVar(value=True),
            "keltner": BooleanVar(value=False),
            "donchian": BooleanVar(value=False),
            "ichimoku": BooleanVar(value=False),
            "volume": BooleanVar(value=True),
        }
        self.update_status_var = StringVar(value=f"Versao atual: {APP_VERSION}")
        self.update_manifest_url = self.load_update_manifest_url()
        self.latest_update = None
        self.alert_metric = StringVar(value="Preco USD")
        self.alert_operator = StringVar(value="acima de")
        self.alert_value = StringVar(value="")

        self.metrics = {}
        self.candles = []
        self.indicator_candles = {"Diario": [], "Semanal": [], "Mensal": []}
        self.depth = {"asks": [], "bids": []}
        self.events = []
        self.news_items = []
        self.news_links = {}
        self.indicator_chart_state = {}
        self.derivatives_chart_state = {}
        self.alerts = self.load_alerts()
        self.portfolio = self.load_portfolio()
        self.value_vars = {}
        self.indicator_vars = {}
        self.derivative_vars = {}
        self.onchain_vars = {}
        self.macro_vars = {}
        self.cycle_vars = {}
        self.portfolio_inputs = {}
        self.portfolio_vars = {}
        self.portfolio_state = {}
        self.report_period = StringVar(value="30D")
        self.macro_chart_state = {}

        self.setup_styles()
        self.build_ui()
        self.render_alerts()
        self.add_event("Sistema", "Aplicativo iniciado. Coletando dados publicos.")

        self.after(100, self.refresh_now)
        self.after(900, self.refresh_news_now)
        self.after(350, self.process_queue)
        self.after(45_000, self.periodic_refresh)
        self.after(600_000, self.periodic_news_refresh)

    def setup_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Dark.TCombobox",
            fieldbackground=COLORS["panel_2"],
            background=COLORS["panel_2"],
            foreground=COLORS["text"],
            arrowcolor=COLORS["orange"],
            bordercolor=COLORS["line"],
            lightcolor=COLORS["line"],
            darkcolor=COLORS["line"],
        )
        style.configure(
            "Dark.TNotebook",
            background=COLORS["bg"],
            borderwidth=0,
            tabmargins=(0, 4, 0, 0),
        )
        style.configure(
            "Dark.TNotebook.Tab",
            background=COLORS["panel_2"],
            foreground=COLORS["muted"],
            borderwidth=1,
            padding=(16, 9),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Dark.TNotebook.Tab",
            background=[("selected", COLORS["orange"])],
            foreground=[("selected", "#180f04")],
        )

    def build_ui(self):
        root = Frame(self, bg=COLORS["bg"])
        root.pack(fill=BOTH, expand=True, padx=18, pady=16)

        topbar = Frame(root, bg=COLORS["bg"])
        topbar.pack(fill=X, pady=(0, 14))

        mark = Label(
            topbar,
            text="B",
            bg=COLORS["orange"],
            fg="#1b1205",
            font=("Segoe UI", 22, "bold"),
            width=2,
            height=1,
        )
        mark.pack(side=LEFT, padx=(0, 12))

        title_box = Frame(topbar, bg=COLORS["bg"])
        title_box.pack(side=LEFT, fill=X, expand=True)
        Label(
            title_box,
            text="Monitor em tempo real",
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        Label(
            title_box,
            text=APP_NAME,
            bg=COLORS["bg"],
            fg=COLORS["text"],
            font=("Segoe UI", 22, "bold"),
        ).pack(anchor="w")

        self.status_var = StringVar(value="Conectando")
        self.status_label = Label(
            topbar,
            textvariable=self.status_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            padx=14,
            pady=9,
            font=("Segoe UI", 10, "bold"),
        )
        self.status_label.pack(side=RIGHT, padx=(8, 0))

        self.refresh_button = self.make_button(topbar, "Atualizar", self.refresh_now)
        self.refresh_button.pack(side=RIGHT)

        self.notebook = ttk.Notebook(root, style="Dark.TNotebook")
        self.notebook.pack(fill=BOTH, expand=True)

        dashboard_tab = Frame(self.notebook, bg=COLORS["bg"])
        indicators_tab = Frame(self.notebook, bg=COLORS["bg"])
        derivatives_tab = Frame(self.notebook, bg=COLORS["bg"])
        onchain_tab = Frame(self.notebook, bg=COLORS["bg"])
        macro_tab = Frame(self.notebook, bg=COLORS["bg"])
        portfolio_tab = Frame(self.notebook, bg=COLORS["bg"])
        report_tab = Frame(self.notebook, bg=COLORS["bg"])
        news_tab = Frame(self.notebook, bg=COLORS["bg"])
        update_tab = Frame(self.notebook, bg=COLORS["bg"])
        self.notebook.add(dashboard_tab, text="Painel")
        self.notebook.add(indicators_tab, text="Indicadores")
        self.notebook.add(derivatives_tab, text="Derivativos")
        self.notebook.add(onchain_tab, text="Rede")
        self.notebook.add(macro_tab, text="Macro/Ciclo")
        self.notebook.add(portfolio_tab, text="Carteira")
        self.notebook.add(report_tab, text="Relatorio")
        self.notebook.add(news_tab, text="Noticias")
        self.notebook.add(update_tab, text="Atualizacao")

        summary = Frame(dashboard_tab, bg=COLORS["bg"])
        summary.pack(fill=X)
        summary.grid_columnconfigure(0, weight=2)
        summary.grid_columnconfigure(1, weight=1)

        price_panel = self.panel(summary)
        price_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        signal_panel = self.panel(summary)
        signal_panel.grid(row=0, column=1, sticky="nsew")

        self.price_usd_var = StringVar(value="US$ --")
        self.price_brl_var = StringVar(value="R$ --")
        self.change_var = StringVar(value="--")
        Label(
            price_panel,
            text="BTC / USD",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        Label(
            price_panel,
            textvariable=self.price_usd_var,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 44, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        price_meta = Frame(price_panel, bg=COLORS["panel"])
        price_meta.pack(fill=X)
        self.change_label = Label(
            price_meta,
            textvariable=self.change_var,
            bg=COLORS["panel_2"],
            fg=COLORS["muted"],
            padx=10,
            pady=5,
            font=("Segoe UI", 10, "bold"),
        )
        self.change_label.pack(side=LEFT)
        Label(
            price_meta,
            textvariable=self.price_brl_var,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(side=LEFT, padx=14)

        cards = Frame(price_panel, bg=COLORS["panel"])
        cards.pack(fill=X, pady=(18, 0))
        for idx, (title, key) in enumerate(
            [
                ("Volume 24h", "volume_24h"),
                ("Market cap", "market_cap"),
                ("Dominancia BTC", "btc_dominance"),
                ("Spread", "spread"),
                ("Ultima atualizacao", "last_update"),
            ]
        ):
            cards.grid_columnconfigure(idx, weight=1)
            self.value_vars[key] = StringVar(value="--")
            self.metric_card(cards, title, self.value_vars[key]).grid(
                row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 8, 0)
            )

        Label(
            signal_panel,
            text="Sinais rapidos",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        signal_grid = Frame(signal_panel, bg=COLORS["panel"])
        signal_grid.pack(fill=BOTH, expand=True, pady=(12, 0))
        for idx, (title, key) in enumerate(
            [
                ("Fear & Greed", "fear_greed"),
                ("Variacao 7D", "change_7d"),
                ("Variacao 30D", "change_30d"),
                ("Fee rapida", "fee_fastest"),
                ("Altura do bloco", "block_height"),
                ("Mempool", "mempool_vmb"),
            ]
        ):
            signal_grid.grid_columnconfigure(idx % 2, weight=1)
            signal_grid.grid_rowconfigure(idx // 2, weight=1)
            self.value_vars[key] = StringVar(value="--")
            self.metric_card(signal_grid, title, self.value_vars[key]).grid(
                row=idx // 2,
                column=idx % 2,
                sticky="nsew",
                padx=(0 if idx % 2 == 0 else 8, 0),
                pady=(0 if idx < 2 else 8, 0),
            )

        chart_panel = self.panel(dashboard_tab)
        chart_panel.pack(fill=BOTH, expand=True, pady=14)
        chart_header = Frame(chart_panel, bg=COLORS["panel"])
        chart_header.pack(fill=X)
        title_frame = Frame(chart_header, bg=COLORS["panel"])
        title_frame.pack(side=LEFT)
        Label(
            title_frame,
            text="BTCUSDT",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        Label(
            title_frame,
            text="Candles de mercado",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")

        interval_box = ttk.Combobox(
            chart_header,
            values=list(INTERVALS.keys()),
            textvariable=self.interval,
            state="readonly",
            width=8,
            style="Dark.TCombobox",
        )
        interval_box.pack(side=RIGHT, padx=(8, 0))
        interval_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_now())

        self.chart_canvas = Canvas(
            chart_panel,
            height=310,
            bg="#0f0e0b",
            bd=0,
            highlightthickness=1,
            highlightbackground=COLORS["line_soft"],
        )
        self.chart_canvas.pack(fill=BOTH, expand=True, pady=(14, 0))
        self.chart_canvas.bind("<Configure>", lambda _event: self.draw_chart())

        lower = Frame(dashboard_tab, bg=COLORS["bg"])
        lower.pack(fill=BOTH)
        for idx in range(4):
            lower.grid_columnconfigure(idx, weight=1)

        self.build_orderbook(lower).grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.build_network(lower).grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        self.build_alerts(lower).grid(row=0, column=2, sticky="nsew", padx=(0, 10))
        self.build_events(lower).grid(row=0, column=3, sticky="nsew")
        self.build_indicators_tab(indicators_tab)
        self.build_derivatives_tab(derivatives_tab)
        self.build_onchain_tab(onchain_tab)
        self.build_macro_tab(macro_tab)
        self.build_portfolio_tab(portfolio_tab)
        self.build_report_tab(report_tab)
        self.build_news_tab(news_tab)
        self.build_update_tab(update_tab)

    def panel(self, parent):
        frame = Frame(
            parent,
            bg=COLORS["panel"],
            highlightthickness=1,
            highlightbackground=COLORS["line"],
            padx=16,
            pady=14,
        )
        return frame

    def metric_card(self, parent, title, variable):
        card = Frame(
            parent,
            bg=COLORS["panel_2"],
            highlightthickness=1,
            highlightbackground=COLORS["line_soft"],
            padx=10,
            pady=10,
        )
        Label(
            card,
            text=title,
            bg=COLORS["panel_2"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        Label(
            card,
            textvariable=variable,
            bg=COLORS["panel_2"],
            fg=COLORS["text"],
            font=("Segoe UI", 12, "bold"),
            wraplength=180,
            justify=LEFT,
        ).pack(anchor="w", pady=(7, 0))
        return card

    def make_button(self, parent, text, command, primary=False):
        return LabelButton(
            parent,
            text=text,
            command=command,
            bg=COLORS["orange"] if primary else COLORS["panel"],
            fg="#180f04" if primary else COLORS["text"],
            active_bg="#ffad42" if primary else COLORS["panel_2"],
            border=COLORS["line"],
        )

    def make_check(self, parent, text, variable, command):
        check = Checkbutton(
            parent,
            text=text,
            variable=variable,
            command=command,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            activebackground=COLORS["panel"],
            activeforeground=COLORS["orange"],
            selectcolor=COLORS["panel_2"],
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        return check

    def build_orderbook(self, parent):
        panel = self.panel(parent)
        Label(
            panel,
            text="Livro de ofertas",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        self.orderbook_text = self.make_text(panel, height=16, font=("Consolas", 9))
        self.orderbook_text.tag_config("ask", foreground="#ff9188")
        self.orderbook_text.tag_config("bid", foreground="#7af09c")
        self.orderbook_text.tag_config("muted", foreground=COLORS["muted"])
        self.orderbook_text.pack(fill=BOTH, expand=True, pady=(12, 0))
        return panel

    def build_network(self, parent):
        panel = self.panel(parent)
        Label(
            panel,
            text="Rede Bitcoin",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        grid = Frame(panel, bg=COLORS["panel"])
        grid.pack(fill=BOTH, expand=True, pady=(12, 0))
        for idx, (title, key) in enumerate(
            [
                ("Fee economica", "fee_economy"),
                ("Fee 1h", "fee_hour"),
                ("Transacoes", "mempool_count"),
                ("Dificuldade", "difficulty_change"),
            ]
        ):
            grid.grid_columnconfigure(idx % 2, weight=1)
            self.value_vars[key] = StringVar(value="--")
            self.metric_card(grid, title, self.value_vars[key]).grid(
                row=idx // 2,
                column=idx % 2,
                sticky="nsew",
                padx=(0 if idx % 2 == 0 else 8, 0),
                pady=(0 if idx < 2 else 8, 0),
            )
        self.mempool_bar = Canvas(panel, height=14, bg=COLORS["panel_2"], bd=0, highlightthickness=0)
        self.mempool_bar.pack(fill=X, pady=(14, 0))
        return panel

    def build_alerts(self, parent):
        panel = self.panel(parent)
        header = Frame(panel, bg=COLORS["panel"])
        header.pack(fill=X)
        Label(
            header,
            text="Alertas",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(side=LEFT)
        self.make_button(header, "Limpar", self.clear_alerts).pack(side=RIGHT)

        form = Frame(panel, bg=COLORS["panel"])
        form.pack(fill=X, pady=(12, 8))
        ttk.Combobox(
            form,
            values=list(METRICS.keys()),
            textvariable=self.alert_metric,
            state="readonly",
            style="Dark.TCombobox",
        ).pack(fill=X, pady=(0, 7))
        ttk.Combobox(
            form,
            values=["acima de", "abaixo de"],
            textvariable=self.alert_operator,
            state="readonly",
            style="Dark.TCombobox",
        ).pack(fill=X, pady=(0, 7))
        value_row = Frame(form, bg=COLORS["panel"])
        value_row.pack(fill=X)
        entry = ttk.Entry(value_row, textvariable=self.alert_value)
        entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        self.make_button(value_row, "+", self.add_alert, primary=True).pack(side=RIGHT)

        self.alerts_frame = Frame(panel, bg=COLORS["panel"])
        self.alerts_frame.pack(fill=BOTH, expand=True, pady=(6, 0))
        return panel

    def build_events(self, parent):
        panel = self.panel(parent)
        Label(
            panel,
            text="Timeline",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        self.events_text = self.make_text(panel, height=16, font=("Segoe UI", 9))
        self.events_text.pack(fill=BOTH, expand=True, pady=(12, 0))
        return panel

    def build_indicators_tab(self, parent):
        parent.grid_columnconfigure(0, weight=2)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        header = self.panel(parent)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(8, 12))
        title_frame = Frame(header, bg=COLORS["panel"])
        title_frame.pack(side=LEFT, fill=X, expand=True)
        Label(
            title_frame,
            text="Analise tecnica",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        Label(
            title_frame,
            text="Medias, Bollinger, RSI, MACD e volume",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        period_box = ttk.Combobox(
            header,
            values=["Diario", "Semanal", "Mensal"],
            textvariable=self.indicator_period,
            state="readonly",
            width=12,
            style="Dark.TCombobox",
        )
        period_box.pack(side=RIGHT, padx=(10, 0))
        period_box.bind("<<ComboboxSelected>>", lambda _event: self.render_indicators())

        chart_panel = self.panel(parent)
        chart_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        Label(
            chart_panel,
            text="Preco, medias moveis e bandas",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        layers_bar = Frame(chart_panel, bg=COLORS["panel"])
        layers_bar.pack(fill=X, pady=(10, 0))
        Label(
            layers_bar,
            text="Camadas:",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        ).pack(side=LEFT, padx=(0, 8))
        layers_grid = Frame(layers_bar, bg=COLORS["panel"])
        layers_grid.pack(side=LEFT, fill=X, expand=True)
        for idx, (text, key) in enumerate([
            ("MM50", "ma50"),
            ("MM100", "ma100"),
            ("MM200", "ma200"),
            ("EMA21", "ema21"),
            ("EMA50", "ema50"),
            ("Bollinger", "bollinger"),
            ("Keltner", "keltner"),
            ("Donchian", "donchian"),
            ("Ichimoku", "ichimoku"),
            ("Volume", "volume"),
        ]):
            self.make_check(layers_grid, text, self.indicator_layers[key], self.draw_indicator_chart).grid(
                row=idx // 5,
                column=idx % 5,
                sticky="w",
                padx=(0, 10),
                pady=(0, 3),
            )
        self.indicator_canvas = Canvas(
            chart_panel,
            height=420,
            bg="#0f0e0b",
            bd=0,
            highlightthickness=1,
            highlightbackground=COLORS["line_soft"],
        )
        self.indicator_canvas.pack(fill=BOTH, expand=True, pady=(12, 0))
        self.indicator_canvas.bind("<Configure>", lambda _event: self.draw_indicator_chart())
        self.indicator_canvas.bind("<Motion>", self.show_indicator_hover)
        self.indicator_canvas.bind("<Leave>", self.clear_indicator_hover)
        self.indicator_hover_var = StringVar(value="Passe o mouse no grafico para ver OHLC, volume e indicadores do candle.")
        Label(
            chart_panel,
            textvariable=self.indicator_hover_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(8, 0))

        side_panel = self.panel(parent)
        side_panel.grid(row=1, column=1, sticky="nsew")
        Label(
            side_panel,
            text="Leitura dos indicadores",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")

        indicators_grid = Frame(side_panel, bg=COLORS["panel"])
        indicators_grid.pack(fill=X, pady=(12, 8))
        indicator_specs = [
            ("Fechamento", "last_close"),
            ("MM 50", "ma50"),
            ("MM 100", "ma100"),
            ("MM 200", "ma200"),
            ("Dist. MM200", "distance_ma200"),
            ("Bollinger sup.", "bb_upper"),
            ("Bollinger base", "bb_basis"),
            ("Bollinger inf.", "bb_lower"),
            ("RSI 14", "rsi14"),
            ("MACD", "macd"),
            ("Volume", "volume"),
            ("Vol. vs media", "volume_change"),
        ]
        for idx, (title, key) in enumerate(indicator_specs):
            indicators_grid.grid_columnconfigure(idx % 2, weight=1)
            self.indicator_vars[key] = StringVar(value="--")
            self.metric_card(indicators_grid, title, self.indicator_vars[key]).grid(
                row=idx // 2,
                column=idx % 2,
                sticky="nsew",
                padx=(0 if idx % 2 == 0 else 8, 0),
                pady=(0 if idx < 2 else 8, 0),
            )

        self.indicator_extra_text = self.make_text(side_panel, height=7, font=("Consolas", 9))
        self.indicator_extra_text.pack(fill=X, pady=(10, 0))

        self.indicator_signal_text = self.make_text(side_panel, height=8, font=("Segoe UI", 9))
        self.indicator_signal_text.pack(fill=BOTH, expand=True, pady=(10, 0))

    def build_derivatives_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        header = self.panel(parent)
        header.grid(row=0, column=0, sticky="ew", pady=(8, 12))
        title_frame = Frame(header, bg=COLORS["panel"])
        title_frame.pack(side=LEFT, fill=X, expand=True)
        Label(
            title_frame,
            text="Futuros, funding e opcoes",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        Label(
            title_frame,
            text="Sentimento profissional de derivativos",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")

        metrics_panel = self.panel(parent)
        metrics_panel.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        metrics_grid = Frame(metrics_panel, bg=COLORS["panel"])
        metrics_grid.pack(fill=X)
        derivative_specs = [
            ("Funding atual", "funding_rate"),
            ("Funding anualizado", "funding_annualized"),
            ("Proximo funding", "next_funding"),
            ("Basis mark/index", "basis"),
            ("Open interest", "open_interest_btc"),
            ("OI nocional", "open_interest_usd"),
            ("OI 7D", "open_interest_7d"),
            ("Long/Short top", "long_short"),
            ("Taker buy/sell", "taker_ratio"),
            ("Opcoes OI", "options_oi"),
            ("Put/Call OI", "put_call_ratio"),
            ("IV media", "options_iv"),
        ]
        for idx, (title, key) in enumerate(derivative_specs):
            metrics_grid.grid_columnconfigure(idx % 4, weight=1)
            self.derivative_vars[key] = StringVar(value="--")
            self.metric_card(metrics_grid, title, self.derivative_vars[key]).grid(
                row=idx // 4,
                column=idx % 4,
                sticky="nsew",
                padx=(0 if idx % 4 == 0 else 8, 0),
                pady=(0 if idx < 4 else 8, 0),
            )

        lower = Frame(parent, bg=COLORS["bg"])
        lower.grid(row=2, column=0, sticky="nsew")
        lower.grid_columnconfigure(0, weight=2)
        lower.grid_columnconfigure(1, weight=1)
        lower.grid_rowconfigure(0, weight=1)

        chart_panel = self.panel(lower)
        chart_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        Label(
            chart_panel,
            text="Open interest e posicionamento 30D",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        self.derivatives_canvas = Canvas(
            chart_panel,
            height=360,
            bg="#0f0e0b",
            bd=0,
            highlightthickness=1,
            highlightbackground=COLORS["line_soft"],
        )
        self.derivatives_canvas.pack(fill=BOTH, expand=True, pady=(12, 0))
        self.derivatives_canvas.bind("<Configure>", lambda _event: self.draw_derivatives_chart())

        signal_panel = self.panel(lower)
        signal_panel.grid(row=0, column=1, sticky="nsew")
        Label(
            signal_panel,
            text="Leitura",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        self.derivative_signal_text = self.make_text(signal_panel, height=18, font=("Segoe UI", 9))
        self.derivative_signal_text.pack(fill=BOTH, expand=True, pady=(12, 0))

    def build_onchain_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        header = self.panel(parent)
        header.grid(row=0, column=0, sticky="ew", pady=(8, 12))
        title_frame = Frame(header, bg=COLORS["panel"])
        title_frame.pack(side=LEFT, fill=X, expand=True)
        Label(
            title_frame,
            text="Mempool, fees e seguranca da rede",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        Label(
            title_frame,
            text="Estado operacional do Bitcoin",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")

        metrics_panel = self.panel(parent)
        metrics_panel.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        grid = Frame(metrics_panel, bg=COLORS["panel"])
        grid.pack(fill=X)
        onchain_specs = [
            ("Altura do bloco", "height"),
            ("Mempool", "mempool_vmb"),
            ("Transacoes", "mempool_count"),
            ("Fee rapida", "fee_fastest"),
            ("Fee 1h", "fee_hour"),
            ("Fee economica", "fee_economy"),
            ("Ajuste dificuldade", "difficulty_change"),
            ("Retarget em", "retarget_eta"),
            ("Blocos restantes", "remaining_blocks"),
            ("Bloco projetado 1", "projected_block_1"),
            ("Bloco projetado 2", "projected_block_2"),
            ("Bloco projetado 3", "projected_block_3"),
        ]
        for idx, (title, key) in enumerate(onchain_specs):
            grid.grid_columnconfigure(idx % 4, weight=1)
            self.onchain_vars[key] = StringVar(value="--")
            self.metric_card(grid, title, self.onchain_vars[key]).grid(
                row=idx // 4,
                column=idx % 4,
                sticky="nsew",
                padx=(0 if idx % 4 == 0 else 8, 0),
                pady=(0 if idx < 4 else 8, 0),
            )

        detail_panel = self.panel(parent)
        detail_panel.grid(row=2, column=0, sticky="nsew")
        Label(
            detail_panel,
            text="Blocos projetados e diagnostico",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        self.onchain_text = self.make_text(detail_panel, height=22, font=("Consolas", 10))
        self.onchain_text.pack(fill=BOTH, expand=True, pady=(12, 0))

    def build_macro_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        header = self.panel(parent)
        header.grid(row=0, column=0, sticky="ew", pady=(8, 12))
        title_frame = Frame(header, bg=COLORS["panel"])
        title_frame.pack(side=LEFT, fill=X, expand=True)
        Label(
            title_frame,
            text="FRED oficial, liquidez e ciclo Bitcoin",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        Label(
            title_frame,
            text="Macro/Ciclo",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")

        metrics_panel = self.panel(parent)
        metrics_panel.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        grid = Frame(metrics_panel, bg=COLORS["panel"])
        grid.pack(fill=X)
        macro_specs = [
            ("US 10Y", "us10y"),
            ("Fed funds", "fed_funds"),
            ("VIX", "vix"),
            ("Dollar amplo", "dollar"),
            ("CPI YoY", "cpi_yoy"),
            ("M2 YoY", "m2_yoy"),
            ("Balanco Fed 90D", "fed_balance_90d"),
            ("Mayer Multiple", "mayer"),
            ("Pi Cycle dist.", "pi_distance"),
            ("200W multiple", "ma200w_multiple"),
            ("Halving", "halving_eta"),
            ("Emissao anual", "issuance_rate"),
        ]
        for idx, (title, key) in enumerate(macro_specs):
            grid.grid_columnconfigure(idx % 4, weight=1)
            variable = StringVar(value="--")
            self.macro_vars[key] = variable
            self.metric_card(grid, title, variable).grid(
                row=idx // 4,
                column=idx % 4,
                sticky="nsew",
                padx=(0 if idx % 4 == 0 else 8, 0),
                pady=(0 if idx < 4 else 8, 0),
            )

        lower = Frame(parent, bg=COLORS["bg"])
        lower.grid(row=2, column=0, sticky="nsew")
        lower.grid_columnconfigure(0, weight=2)
        lower.grid_columnconfigure(1, weight=1)
        lower.grid_rowconfigure(0, weight=1)

        chart_panel = self.panel(lower)
        chart_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        Label(
            chart_panel,
            text="Macro normalizado e ciclo BTC",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        self.macro_canvas = Canvas(
            chart_panel,
            height=360,
            bg="#0f0e0b",
            bd=0,
            highlightthickness=1,
            highlightbackground=COLORS["line_soft"],
        )
        self.macro_canvas.pack(fill=BOTH, expand=True, pady=(12, 0))
        self.macro_canvas.bind("<Configure>", lambda _event: self.draw_macro_chart())

        signal_panel = self.panel(lower)
        signal_panel.grid(row=0, column=1, sticky="nsew")
        Label(
            signal_panel,
            text="Leitura macro",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        self.macro_text = self.make_text(signal_panel, height=18, font=("Segoe UI", 9))
        self.macro_text.pack(fill=BOTH, expand=True, pady=(12, 0))

    def build_portfolio_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        header = self.panel(parent)
        header.grid(row=0, column=0, sticky="ew", pady=(8, 12))
        title_frame = Frame(header, bg=COLORS["panel"])
        title_frame.pack(side=LEFT, fill=X, expand=True)
        Label(
            title_frame,
            text="Controle local, risco e alocacao",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        Label(
            title_frame,
            text="Carteira/Risco",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        self.make_button(header, "Salvar carteira", self.save_portfolio_from_inputs, primary=True).pack(side=RIGHT)

        form_panel = self.panel(parent)
        form_panel.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        form = Frame(form_panel, bg=COLORS["panel"])
        form.pack(fill=X)
        input_specs = [
            ("BTC em carteira", "btc_amount"),
            ("Preco medio USD", "avg_cost_usd"),
            ("Caixa USD", "cash_usd"),
            ("Patrimonio total USD", "total_equity_usd"),
            ("Alocacao alvo %", "target_allocation"),
            ("DCA mensal USD", "dca_monthly_usd"),
        ]
        for idx, (label, key) in enumerate(input_specs):
            form.grid_columnconfigure(idx % 3, weight=1)
            cell = Frame(form, bg=COLORS["panel"])
            cell.grid(row=idx // 3, column=idx % 3, sticky="ew", padx=(0 if idx % 3 == 0 else 10, 0), pady=(0 if idx < 3 else 8, 0))
            Label(
                cell,
                text=label,
                bg=COLORS["panel"],
                fg=COLORS["muted"],
                font=("Segoe UI", 9, "bold"),
            ).pack(anchor="w")
            value = self.portfolio.get(key)
            variable = StringVar(value="" if value in (None, "") else str(value))
            self.portfolio_inputs[key] = variable
            ttk.Entry(cell, textvariable=variable).pack(fill=X, pady=(5, 0))

        buttons = Frame(form_panel, bg=COLORS["panel"])
        buttons.pack(fill=X, pady=(10, 0))
        self.make_button(buttons, "Atualizar leitura", self.apply_portfolio).pack(side=LEFT)
        self.make_button(buttons, "Limpar carteira", self.clear_portfolio).pack(side=LEFT, padx=(8, 0))

        lower = Frame(parent, bg=COLORS["bg"])
        lower.grid(row=2, column=0, sticky="nsew")
        lower.grid_columnconfigure(0, weight=2)
        lower.grid_columnconfigure(1, weight=1)
        lower.grid_rowconfigure(0, weight=1)

        metrics_panel = self.panel(lower)
        metrics_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        Label(
            metrics_panel,
            text="Metricas da carteira",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        grid = Frame(metrics_panel, bg=COLORS["panel"])
        grid.pack(fill=BOTH, expand=True, pady=(12, 0))
        portfolio_specs = [
            ("Valor BTC USD", "btc_value_usd"),
            ("Valor BTC BRL", "btc_value_brl"),
            ("Custo base", "cost_basis"),
            ("P/L", "pnl"),
            ("P/L %", "pnl_percent"),
            ("Alocacao", "allocation"),
            ("BTC para alvo", "target_delta_btc"),
            ("DCA mensal", "dca_monthly_btc"),
            ("Risco 30D 95%", "var_30d"),
            ("Queda -20%", "drop_20"),
            ("Drawdown ATH", "ath_drawdown"),
            ("Break-even", "breakeven"),
        ]
        for idx, (title, key) in enumerate(portfolio_specs):
            grid.grid_columnconfigure(idx % 3, weight=1)
            self.portfolio_vars[key] = StringVar(value="--")
            self.metric_card(grid, title, self.portfolio_vars[key]).grid(
                row=idx // 3,
                column=idx % 3,
                sticky="nsew",
                padx=(0 if idx % 3 == 0 else 8, 0),
                pady=(0 if idx < 3 else 8, 0),
            )

        risk_panel = self.panel(lower)
        risk_panel.grid(row=0, column=1, sticky="nsew")
        Label(
            risk_panel,
            text="Leitura de risco",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        self.portfolio_text = self.make_text(risk_panel, height=18, font=("Segoe UI", 9))
        self.portfolio_text.pack(fill=BOTH, expand=True, pady=(12, 0))
        self.apply_portfolio()

    def build_report_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        header = self.panel(parent)
        header.grid(row=0, column=0, sticky="ew", pady=(8, 12))
        title_frame = Frame(header, bg=COLORS["panel"])
        title_frame.pack(side=LEFT, fill=X, expand=True)
        Label(
            title_frame,
            text="Resumo consolidado para acompanhamento",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        Label(
            title_frame,
            text="Relatorio 7D/30D",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        period_box = ttk.Combobox(
            header,
            values=["7D", "30D"],
            textvariable=self.report_period,
            state="readonly",
            width=8,
            style="Dark.TCombobox",
        )
        period_box.pack(side=RIGHT, padx=(8, 0))
        period_box.bind("<<ComboboxSelected>>", lambda _event: self.render_report())
        self.make_button(header, "Copiar", self.copy_report).pack(side=RIGHT, padx=(8, 0))
        self.make_button(header, "Gerar relatorio", self.render_report, primary=True).pack(side=RIGHT)

        panel = self.panel(parent)
        panel.grid(row=1, column=0, sticky="nsew")
        self.report_text = self.make_text(panel, height=30, font=("Consolas", 10))
        self.report_text.pack(fill=BOTH, expand=True)
        self.render_report()

    def build_news_tab(self, parent):
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        header = self.panel(parent)
        header.grid(row=0, column=0, sticky="ew", pady=(8, 12))
        title_frame = Frame(header, bg=COLORS["panel"])
        title_frame.pack(side=LEFT, fill=X, expand=True)
        Label(
            title_frame,
            text="Noticias atualizadas",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        Label(
            title_frame,
            text="Bitcoin em fontes RSS publicas",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        self.news_status_var = StringVar(value="Aguardando noticias")
        Label(
            header,
            textvariable=self.news_status_var,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10, "bold"),
        ).pack(side=RIGHT, padx=(10, 0))
        self.news_refresh_button = self.make_button(header, "Atualizar noticias", self.refresh_news_now)
        self.news_refresh_button.pack(side=RIGHT)

        news_panel = self.panel(parent)
        news_panel.grid(row=1, column=0, sticky="nsew")
        self.news_text = self.make_text(news_panel, height=26, font=("Segoe UI", 10))
        self.news_text.tag_config("source", foreground=COLORS["cyan"], font=("Segoe UI", 9, "bold"))
        self.news_text.tag_config("date", foreground=COLORS["dim"], font=("Segoe UI", 9))
        self.news_text.tag_config("headline", foreground=COLORS["text"], font=("Segoe UI", 12, "bold"))
        self.news_text.tag_config("summary", foreground=COLORS["muted"], font=("Segoe UI", 9))
        self.news_text.tag_config("category", foreground="#ffd166", font=("Segoe UI", 9, "bold"))
        self.news_text.tag_config("impact", foreground=COLORS["red"], font=("Segoe UI", 9, "bold"))
        self.news_text.tag_config("link", foreground=COLORS["orange"], underline=True)
        self.news_text.pack(fill=BOTH, expand=True)

    def build_update_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        header = self.panel(parent)
        header.grid(row=0, column=0, sticky="ew", pady=(8, 12))
        title_frame = Frame(header, bg=COLORS["panel"])
        title_frame.pack(side=LEFT, fill=X, expand=True)
        Label(
            title_frame,
            text="Publicacao e auto-update",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        Label(
            title_frame,
            text=f"{APP_NAME} {APP_VERSION}",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        self.make_button(header, "Verificar atualizacao", self.check_update_now, primary=True).pack(
            side=RIGHT
        )

        panel = self.panel(parent)
        panel.grid(row=1, column=0, sticky="nsew")
        Label(
            panel,
            textvariable=self.update_status_var,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")

        manifest_label = self.update_manifest_url or "Nao configurado ainda"
        Label(
            panel,
            text=f"Manifesto: {manifest_label}",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
            wraplength=980,
            justify=LEFT,
        ).pack(anchor="w", pady=(8, 12))

        self.update_notes_text = self.make_text(panel, height=18, font=("Segoe UI", 10))
        self.update_notes_text.pack(fill=BOTH, expand=True)
        self.write_update_notes(
            [
                "Para ativar auto-update, publique update_manifest.json e BitcoinMonitor.exe em GitHub Releases.",
                "Depois configure a URL do manifesto em update_config.json ou recompile com DEFAULT_UPDATE_MANIFEST_URL.",
                "Quando houver versao nova, o app baixa o exe e substitui apos confirmar.",
            ]
        )

    def make_text(self, parent, height=10, font=("Segoe UI", 10)):
        text = tk_text = __import__("tkinter").Text(
            parent,
            height=height,
            bg="#11100d",
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            wrap="word",
            font=font,
            padx=8,
            pady=8,
        )
        tk_text.configure(state="disabled")
        return text

    def refresh_now(self):
        if self.fetching:
            return
        self.fetching = True
        self.set_status("Atualizando", "neutral")
        self.refresh_button.set_enabled(False)
        thread = threading.Thread(target=self.fetch_worker, args=(self.interval.get(),), daemon=True)
        thread.start()

    def periodic_refresh(self):
        self.refresh_now()
        self.after(45_000, self.periodic_refresh)

    def periodic_news_refresh(self):
        self.refresh_news_now()
        self.after(600_000, self.periodic_news_refresh)

    def refresh_news_now(self):
        if getattr(self, "fetching_news", False):
            return
        self.fetching_news = True
        if hasattr(self, "news_refresh_button"):
            self.news_refresh_button.set_enabled(False)
        if hasattr(self, "news_status_var"):
            self.news_status_var.set("Atualizando...")
        thread = threading.Thread(target=self.fetch_news_worker, daemon=True)
        thread.start()

    def fetch_with_cache(self, cache_key, function, url, timeout=10, ttl=60):
        cached = self.store.get_cache(cache_key, ttl)
        if cached is not None:
            return cached
        try:
            payload = function(url, timeout)
            self.store.set_cache(cache_key, payload)
            return payload
        except Exception:
            stale = self.store.get_cache(cache_key, None)
            if stale is not None:
                return stale
            raise

    def fetch_worker(self, interval):
        data = {"_kind": "market", "errors": []}
        jobs = {
            "coingecko": (fetch_json, ENDPOINTS["coingecko"]),
            "coingecko_markets": (fetch_json, ENDPOINTS["coingecko_markets"]),
            "coingecko_global": (fetch_json, ENDPOINTS["coingecko_global"]),
            "binance_ticker": (fetch_json, ENDPOINTS["binance_ticker"]),
            "candles": (fetch_json, ENDPOINTS["candles"].format(interval=interval)),
            "daily_candles": (fetch_json, ENDPOINTS["daily_candles"]),
            "weekly_candles": (fetch_json, ENDPOINTS["weekly_candles"]),
            "monthly_candles": (fetch_json, ENDPOINTS["monthly_candles"]),
            "depth": (fetch_json, ENDPOINTS["depth"]),
            "fees": (fetch_json, ENDPOINTS["fees"]),
            "mempool_blocks": (fetch_json, ENDPOINTS["mempool_blocks"]),
            "mempool": (fetch_json, ENDPOINTS["mempool"]),
            "tip_height": (fetch_text, ENDPOINTS["tip_height"]),
            "difficulty": (fetch_json, ENDPOINTS["difficulty"]),
            "fear_greed": (fetch_json, ENDPOINTS["fear_greed"]),
            "futures_open_interest": (fetch_json, ENDPOINTS["futures_open_interest"]),
            "futures_funding": (fetch_json, ENDPOINTS["futures_funding"]),
            "futures_premium": (fetch_json, ENDPOINTS["futures_premium"]),
            "futures_open_interest_hist": (fetch_json, ENDPOINTS["futures_open_interest_hist"]),
            "futures_long_short": (fetch_json, ENDPOINTS["futures_long_short"]),
            "futures_taker_ratio": (fetch_json, ENDPOINTS["futures_taker_ratio"]),
            "deribit_options": (fetch_json, ENDPOINTS["deribit_options"]),
        }
        for name, (_label, url) in FRED_SERIES.items():
            jobs[name] = (fetch_fred_series, url)

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            futures = {
                executor.submit(
                    self.fetch_with_cache,
                    f"{name}:{interval}" if name == "candles" else name,
                    function,
                    url,
                    12,
                    CACHE_TTLS.get(name, 60),
                ): name
                for name, (function, url) in jobs.items()
            }
            for future in concurrent.futures.as_completed(futures):
                name = futures[future]
                try:
                    data[name] = future.result()
                except Exception as exc:
                    data["errors"].append(f"{name}: {exc}")

        self.data_queue.put(data)

    def fetch_news_worker(self):
        items = []
        errors = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(fetch_text, url, 12): source
                for source, url in NEWS_FEEDS
            }
            for future in concurrent.futures.as_completed(futures):
                source = futures[future]
                try:
                    feed_text = future.result()
                    items.extend(self.parse_news_feed(source, feed_text))
                except Exception as exc:
                    errors.append(f"{source}: {exc}")

        deduped = {}
        for item in items:
            key = item["link"] or item["title"]
            if key not in deduped:
                deduped[key] = item
        sorted_items = sorted(
            deduped.values(),
            key=lambda item: item.get("published") or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
            reverse=True,
        )
        if sorted_items:
            self.store.save_news(sorted_items[:80])
        elif errors:
            sorted_items = self.store.load_news(40)
        self.data_queue.put({"_kind": "news", "items": sorted_items[:40], "errors": errors})

    def parse_news_feed(self, source, feed_text):
        root = ET.fromstring(feed_text)
        items = []
        candidates = root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for item in candidates:
            title = self.xml_text(item, "title")
            link = self.xml_link(item)
            description = self.clean_html(
                self.xml_text(item, "description")
                or self.xml_text(item, "summary")
                or self.xml_text(item, "content")
            )
            published = self.parse_date(
                self.xml_text(item, "pubDate")
                or self.xml_text(item, "published")
                or self.xml_text(item, "updated")
                or self.xml_text(item, "date")
            )
            haystack = f"{title} {description}".lower()
            if "bitcoin" not in haystack and "btc" not in haystack:
                continue
            category = classify_news(title, description)
            items.append(
                {
                    "source": source,
                    "title": title.strip() or "Sem titulo",
                    "link": link.strip(),
                    "summary": description[:260],
                    "published": published,
                    "category": category,
                    "impact": news_impact(title, description),
                }
            )
        return items

    def process_queue(self):
        try:
            while True:
                payload = self.data_queue.get_nowait()
                if payload.get("_kind") == "news":
                    self.apply_news(payload)
                elif payload.get("_kind") == "update":
                    self.apply_update_check(payload)
                else:
                    self.apply_data(payload)
        except queue.Empty:
            pass
        self.after(350, self.process_queue)

    def apply_data(self, payload):
        self.fetching = False
        self.refresh_button.set_enabled(True)
        errors = payload.get("errors", [])

        self.apply_market(payload)
        self.apply_candles(payload.get("candles"))
        self.apply_indicator_candles(
            payload.get("daily_candles"),
            payload.get("weekly_candles"),
            payload.get("monthly_candles"),
        )
        self.apply_depth(payload.get("depth"))
        self.apply_network(payload)
        self.apply_onchain(payload)
        self.apply_derivatives(payload)
        self.apply_macro_cycle(payload)
        self.apply_fear_greed(payload.get("fear_greed"))
        self.apply_portfolio()
        self.render_report()

        if not errors:
            self.set_status("Dados sincronizados", "online")
        elif len(errors) < 5:
            self.set_status("Dados parciais", "neutral")
            self.add_event("Dados", f"{len(errors)} fonte(s) falharam nesta atualizacao.")
        else:
            self.set_status("Fontes indisponiveis", "offline")
            self.add_event("Dados", "Nao foi possivel atualizar as fontes publicas agora.")

        self.value_vars["last_update"].set(time.strftime("%H:%M:%S"))
        self.store.save_market_snapshot(self.metrics)
        self.check_alerts()

    def apply_news(self, payload):
        self.fetching_news = False
        if hasattr(self, "news_refresh_button"):
            self.news_refresh_button.set_enabled(True)
        items = payload.get("items", [])
        errors = payload.get("errors", [])
        if items:
            self.news_items = items
            self.render_news()
            self.render_report()
        if hasattr(self, "news_status_var"):
            if errors and items:
                self.news_status_var.set(f"{len(items)} noticias, algumas fontes falharam")
            elif errors:
                self.news_status_var.set("Fontes de noticia indisponiveis")
            else:
                self.news_status_var.set(f"{len(items)} noticias atualizadas")
        if errors:
            self.add_event("Noticias", f"{len(errors)} fonte(s) de noticias falharam.")

    def render_news(self):
        if not hasattr(self, "news_text"):
            return
        self.news_links = {}
        self.news_text.configure(state="normal")
        self.news_text.delete("1.0", END)

        if not self.news_items:
            self.news_text.insert(END, "Nenhuma noticia de Bitcoin encontrada agora.\n", "summary")
            self.news_text.configure(state="disabled")
            return

        for index, item in enumerate(self.news_items, start=1):
            date_label = self.format_news_date(item.get("published"))
            self.news_text.insert(END, f"{item['source']}  ", "source")
            self.news_text.insert(END, f"{date_label}\n", "date")
            self.news_text.insert(END, f"{item['title']}\n", "headline")
            meta = f"{item.get('category', 'Mercado')} | impacto {item.get('impact', 'normal')}"
            if item.get("cached"):
                meta += " | cache local"
            self.news_text.insert(END, f"{meta}\n", "impact" if item.get("impact") == "alto" else "category")
            if item.get("summary"):
                self.news_text.insert(END, f"{item['summary']}\n", "summary")
            tag = f"news_link_{index}"
            self.news_links[tag] = item.get("link")
            self.news_text.insert(END, "Abrir noticia\n\n", ("link", tag))
            self.news_text.tag_bind(tag, "<Button-1>", lambda _event, link=item.get("link"): self.open_link(link))
            self.news_text.tag_bind(tag, "<Enter>", lambda _event: self.news_text.configure(cursor="hand2"))
            self.news_text.tag_bind(tag, "<Leave>", lambda _event: self.news_text.configure(cursor=""))
        self.news_text.configure(state="disabled")

    def check_update_now(self):
        if getattr(self, "checking_update", False):
            return
        manifest_url = self.update_manifest_url
        if not manifest_url:
            self.update_status_var.set("Auto-update ainda nao configurado.")
            self.write_update_notes(
                [
                    "Falta configurar a URL publica do update_manifest.json.",
                    "Quando publicarmos no GitHub Releases, essa URL entra no update_config.json ou no codigo.",
                ]
            )
            return
        self.checking_update = True
        self.update_status_var.set("Verificando atualizacao...")
        threading.Thread(target=self.update_worker, args=(manifest_url,), daemon=True).start()

    def update_worker(self, manifest_url):
        try:
            manifest = fetch_update_manifest(manifest_url, 15)
            self.data_queue.put({"_kind": "update", "manifest": manifest, "error": None})
        except Exception as exc:
            self.data_queue.put({"_kind": "update", "manifest": None, "error": str(exc)})

    def apply_update_check(self, payload):
        self.checking_update = False
        error = payload.get("error")
        if error:
            self.update_status_var.set("Nao foi possivel verificar atualizacao.")
            self.write_update_notes([error])
            return

        install_path = payload.get("install_path")
        if install_path:
            self.update_status_var.set("Download concluido.")
            self.write_update_notes(["Nova versao baixada.", "O app sera reiniciado para concluir a atualizacao."])
            if messagebox.askyesno(APP_NAME, "Reiniciar agora para instalar a atualizacao?"):
                self.install_downloaded_update(install_path)
            return

        manifest = payload.get("manifest") or {}
        self.latest_update = manifest
        latest = manifest.get("version")
        notes = manifest.get("notes") or []
        if isinstance(notes, str):
            notes = [notes]

        if latest and is_newer_version(latest, APP_VERSION):
            self.update_status_var.set(f"Nova versao disponivel: {latest}")
            lines = [f"Versao atual: {APP_VERSION}", f"Versao nova: {latest}", ""]
            lines.extend(notes or ["Sem notas de release."])
            self.write_update_notes(lines)
            if messagebox.askyesno(APP_NAME, f"Baixar e instalar a versao {latest} agora?"):
                self.download_and_install_update(manifest)
        else:
            self.update_status_var.set(f"Voce ja esta na versao mais recente: {APP_VERSION}")
            self.write_update_notes(notes or ["Nenhuma atualizacao disponivel agora."])

    def download_and_install_update(self, manifest):
        download_url = manifest.get("download_url")
        if not download_url:
            release_url = manifest.get("release_url")
            if release_url:
                webbrowser.open(release_url)
            messagebox.showwarning(APP_NAME, "O manifesto nao tem download_url.")
            return
        self.update_status_var.set("Baixando nova versao...")
        threading.Thread(target=self.download_update_worker, args=(manifest,), daemon=True).start()

    def download_update_worker(self, manifest):
        try:
            download_url = manifest["download_url"]
            temp_dir = Path(tempfile.mkdtemp(prefix="BitcoinMonitorUpdate_"))
            new_exe = temp_dir / "BitcoinMonitor.exe"
            download_file(download_url, new_exe, 90)
            expected_hash = (manifest.get("sha256") or "").strip().lower()
            if expected_hash:
                actual_hash = hashlib.sha256(new_exe.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    raise ValueError("Hash SHA-256 do download nao confere com o manifesto.")
            self.data_queue.put({"_kind": "update", "install_path": str(new_exe), "error": None})
        except Exception as exc:
            self.data_queue.put({"_kind": "update", "install_path": None, "error": str(exc)})

    def install_downloaded_update(self, new_exe):
        if not getattr(sys, "frozen", False):
            messagebox.showinfo(
                APP_NAME,
                "Update baixado. Auto-substituicao so funciona no executavel empacotado.",
            )
            return

        current_exe = Path(sys.executable)
        updater = Path(tempfile.gettempdir()) / "bitcoin_monitor_apply_update.bat"
        script = f"""@echo off
timeout /t 2 /nobreak > nul
copy /y "{new_exe}" "{current_exe}" > nul
start "" "{current_exe}"
del "{new_exe}" > nul 2> nul
del "%~f0" > nul 2> nul
"""
        updater.write_text(script, encoding="utf-8")
        subprocess.Popen(["cmd", "/c", str(updater)], shell=False)
        self.destroy()

    def write_update_notes(self, lines):
        if not hasattr(self, "update_notes_text"):
            return
        self.update_notes_text.configure(state="normal")
        self.update_notes_text.delete("1.0", END)
        for line in lines:
            self.update_notes_text.insert(END, f"{line}\n")
        self.update_notes_text.configure(state="disabled")

    def apply_market(self, payload):
        coingecko = payload.get("coingecko", {}).get("bitcoin", {})
        market_rows = payload.get("coingecko_markets") or []
        market = market_rows[0] if market_rows else {}
        global_data = (payload.get("coingecko_global") or {}).get("data") or {}
        ticker = payload.get("binance_ticker", {})

        price_usd = self.to_float(coingecko.get("usd")) or self.to_float(ticker.get("lastPrice"))
        price_brl = self.to_float(coingecko.get("brl"))
        change = self.to_float(coingecko.get("usd_24h_change")) or self.to_float(
            ticker.get("priceChangePercent")
        )
        volume = self.to_float(coingecko.get("usd_24h_vol")) or self.to_float(ticker.get("quoteVolume"))
        market_cap = self.to_float(coingecko.get("usd_market_cap"))
        change_1h = self.to_float(market.get("price_change_percentage_1h_in_currency"))
        change_7d = self.to_float(market.get("price_change_percentage_7d_in_currency"))
        change_30d = self.to_float(market.get("price_change_percentage_30d_in_currency"))
        ath_change = self.to_float(market.get("ath_change_percentage"))
        dominance = self.to_float((global_data.get("market_cap_percentage") or {}).get("btc"))

        self.metrics.update(
            {
                "price_usd": price_usd,
                "price_brl": price_brl,
                "change_24h": change,
                "change_1h": change_1h,
                "change_7d": change_7d,
                "change_30d": change_30d,
                "ath_change": ath_change,
                "btc_dominance": dominance,
            }
        )

        self.price_usd_var.set(format_currency(price_usd, "USD"))
        self.price_brl_var.set(format_currency(price_brl, "BRL", 0))
        self.change_var.set(format_percent(change))
        self.change_label.configure(
            fg="#7af09c" if change and change > 0 else "#ff9188" if change and change < 0 else COLORS["muted"]
        )
        self.value_vars["volume_24h"].set(format_compact_currency(volume, "USD"))
        self.value_vars["market_cap"].set(format_compact_currency(market_cap, "USD"))
        self.value_vars["btc_dominance"].set(f"{format_number(dominance, 1)}%")
        self.value_vars["change_7d"].set(format_percent(change_7d))
        self.value_vars["change_30d"].set(format_percent(change_30d))

    def apply_candles(self, rows):
        if not rows:
            return
        self.candles = [
            {
                "time": row[0],
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
            for row in rows
        ]
        self.draw_chart()

    def apply_indicator_candles(self, daily_rows, weekly_rows, monthly_rows):
        if daily_rows:
            self.indicator_candles["Diario"] = self.parse_candle_rows(daily_rows)
        if weekly_rows:
            self.indicator_candles["Semanal"] = self.parse_candle_rows(weekly_rows)
        if monthly_rows:
            self.indicator_candles["Mensal"] = self.parse_candle_rows(monthly_rows)
        self.render_indicators()

    def apply_depth(self, depth):
        if not depth:
            return
        asks = [(float(price), float(amount)) for price, amount in depth.get("asks", [])[:8]]
        bids = [(float(price), float(amount)) for price, amount in depth.get("bids", [])[:8]]
        self.depth = {"asks": asks, "bids": bids}

        if asks and bids:
            best_ask = asks[0][0]
            best_bid = bids[0][0]
            spread = best_ask - best_bid
            mid = (best_ask + best_bid) / 2
            self.value_vars["spread"].set(
                f"{format_currency(spread, 'USD')} ({(spread / mid) * 100:.4f}%)"
            )
        self.render_orderbook()

    def apply_network(self, payload):
        fees = payload.get("fees")
        mempool = payload.get("mempool")
        tip_height = payload.get("tip_height")
        difficulty = payload.get("difficulty")

        if fees:
            fastest = self.to_float(fees.get("fastestFee"))
            economy = self.to_float(fees.get("economyFee"))
            hour = self.to_float(fees.get("hourFee"))
            self.metrics["fee_fastest"] = fastest
            self.value_vars["fee_fastest"].set(f"{format_number(fastest, 0)} sat/vB")
            self.value_vars["fee_economy"].set(f"{format_number(economy, 0)} sat/vB")
            self.value_vars["fee_hour"].set(f"{format_number(hour, 0)} sat/vB")

        if mempool:
            vsize = self.to_float(mempool.get("vsize"))
            vmb = vsize / 1_000_000 if vsize is not None else None
            count = self.to_float(mempool.get("count"))
            self.metrics["mempool_vmb"] = vmb
            self.value_vars["mempool_vmb"].set(f"{format_number(vmb, 1)} vMB")
            self.value_vars["mempool_count"].set(format_number(count, 0))
            if vmb is not None:
                self.draw_mempool_bar(vmb)

        if tip_height:
            self.value_vars["block_height"].set(f"{int(tip_height):,}".replace(",", "."))
            self.metrics["block_height"] = self.to_float(tip_height)

        if difficulty:
            change = self.to_float(difficulty.get("difficultyChange"))
            self.metrics["difficulty_change"] = change
            self.value_vars["difficulty_change"].set(format_percent(change))

    def apply_onchain(self, payload):
        if not self.onchain_vars:
            return

        fees = payload.get("fees") or {}
        mempool = payload.get("mempool") or {}
        difficulty = payload.get("difficulty") or {}
        blocks = payload.get("mempool_blocks") or []
        tip_height = payload.get("tip_height")

        fastest = self.to_float(fees.get("fastestFee"))
        hour = self.to_float(fees.get("hourFee"))
        economy = self.to_float(fees.get("economyFee"))
        vmb = self.to_float(mempool.get("vsize"))
        count = self.to_float(mempool.get("count"))
        vmb = vmb / 1_000_000 if vmb is not None else None
        change = self.to_float(difficulty.get("difficultyChange"))

        if tip_height:
            self.onchain_vars["height"].set(f"{int(tip_height):,}".replace(",", "."))
        self.onchain_vars["mempool_vmb"].set(f"{format_number(vmb, 1)} vMB")
        self.onchain_vars["mempool_count"].set(format_number(count, 0))
        self.onchain_vars["fee_fastest"].set(f"{format_number(fastest, 0)} sat/vB")
        self.onchain_vars["fee_hour"].set(f"{format_number(hour, 0)} sat/vB")
        self.onchain_vars["fee_economy"].set(f"{format_number(economy, 0)} sat/vB")
        self.onchain_vars["difficulty_change"].set(format_percent(change))
        self.onchain_vars["retarget_eta"].set(format_duration_ms(difficulty.get("remainingTime")))
        self.onchain_vars["remaining_blocks"].set(format_number(self.to_float(difficulty.get("remainingBlocks")), 0))

        for index in range(3):
            key = f"projected_block_{index + 1}"
            if index < len(blocks):
                block = blocks[index]
                median = self.to_float(block.get("medianFee"))
                txs = self.to_float(block.get("nTx"))
                self.onchain_vars[key].set(f"{format_number(median, 1)} sat/vB | {format_number(txs, 0)} tx")
            else:
                self.onchain_vars[key].set("--")

        lines = [
            "Bloco  Mediana sat/vB  Tx        Fees BTC    Faixa sat/vB",
            "-----  -------------  --------  ----------  ----------------",
        ]
        for index, block in enumerate(blocks[:8], start=1):
            median = self.to_float(block.get("medianFee"))
            txs = self.to_float(block.get("nTx"))
            total_fees = self.to_float(block.get("totalFees"))
            fee_btc = total_fees / 100_000_000 if total_fees is not None else None
            fee_range = block.get("feeRange") or []
            low = self.to_float(fee_range[0]) if fee_range else None
            high = self.to_float(fee_range[-1]) if fee_range else None
            lines.append(
                f"{index:>5}  {format_number(median, 2):>13}  "
                f"{format_number(txs, 0):>8}  {format_number(fee_btc, 4):>10}  "
                f"{format_number(low, 1)} - {format_number(high, 1)}"
            )
        lines.append("")
        lines.append(f"Retarget estimado: {format_timestamp_ms(difficulty.get('estimatedRetargetDate'))}")
        lines.append(f"Progresso do periodo: {format_percent(self.to_float(difficulty.get('progressPercent')))}")
        lines.append(f"Tempo medio ajustado: {format_duration_ms(self.to_float(difficulty.get('adjustedTimeAvg')))}")
        self.write_text_widget(self.onchain_text, lines)

    def apply_derivatives(self, payload):
        if not self.derivative_vars:
            return

        premium = payload.get("futures_premium") or {}
        open_interest = payload.get("futures_open_interest") or {}
        funding_rows = payload.get("futures_funding") or []
        oi_hist = payload.get("futures_open_interest_hist") or []
        long_short_rows = payload.get("futures_long_short") or []
        taker_rows = payload.get("futures_taker_ratio") or []
        options = (payload.get("deribit_options") or {}).get("result") or []

        latest_funding = funding_rows[-1] if funding_rows else {}
        funding_rate = self.to_float(premium.get("lastFundingRate"))
        if funding_rate is None:
            funding_rate = self.to_float(latest_funding.get("fundingRate"))
        funding_pct = funding_rate * 100 if funding_rate is not None else None
        annualized = funding_rate * 3 * 365 * 100 if funding_rate is not None else None
        mark = self.to_float(premium.get("markPrice"))
        index_price = self.to_float(premium.get("indexPrice"))
        basis_pct = percent_distance(mark, index_price) if mark and index_price else None
        oi_btc = self.to_float(open_interest.get("openInterest"))
        oi_usd = oi_btc * mark if oi_btc is not None and mark else None

        oi_values = [self.to_float(row.get("sumOpenInterestValue")) for row in oi_hist]
        oi_values = [item for item in oi_values if item is not None]
        oi_7d = percent_distance(oi_values[-1], oi_values[-8]) if len(oi_values) >= 8 else None
        oi_30d = percent_distance(oi_values[-1], oi_values[0]) if len(oi_values) >= 2 else None

        long_short = self.to_float(long_short_rows[-1].get("longShortRatio")) if long_short_rows else None
        taker = self.to_float(taker_rows[-1].get("buySellRatio")) if taker_rows else None

        call_oi = 0
        put_oi = 0
        iv_weighted = 0
        iv_weight = 0
        strike_oi = {}
        for option in options:
            name = option.get("instrument_name") or ""
            oi = self.to_float(option.get("open_interest")) or 0
            iv = self.to_float(option.get("mark_iv"))
            parts = name.split("-")
            strike = parts[2] if len(parts) >= 4 else ""
            if name.endswith("-C"):
                call_oi += oi
            elif name.endswith("-P"):
                put_oi += oi
            if strike:
                strike_oi[strike] = strike_oi.get(strike, 0) + oi
            if iv is not None and oi:
                iv_weighted += iv * oi
                iv_weight += oi
        options_oi = call_oi + put_oi
        put_call = put_oi / call_oi if call_oi else None
        average_iv = iv_weighted / iv_weight if iv_weight else None
        largest_strike = max(strike_oi.items(), key=lambda item: item[1])[0] if strike_oi else "--"

        self.metrics.update(
            {
                "funding_rate_pct": funding_pct,
                "open_interest_usd": oi_usd,
                "open_interest_7d": oi_7d,
                "open_interest_30d": oi_30d,
                "long_short_ratio": long_short,
                "taker_ratio": taker,
                "put_call_ratio": put_call,
                "options_iv": average_iv,
            }
        )

        self.derivative_vars["funding_rate"].set(format_percent(funding_pct))
        self.derivative_vars["funding_annualized"].set(format_percent(annualized))
        self.derivative_vars["next_funding"].set(format_timestamp_ms(premium.get("nextFundingTime")))
        self.derivative_vars["basis"].set(format_percent(basis_pct))
        self.derivative_vars["open_interest_btc"].set(format_btc(oi_btc))
        self.derivative_vars["open_interest_usd"].set(format_compact_currency(oi_usd, "USD"))
        self.derivative_vars["open_interest_7d"].set(f"{format_percent(oi_7d)} / 30D {format_percent(oi_30d)}")
        self.derivative_vars["long_short"].set(format_number(long_short, 2))
        self.derivative_vars["taker_ratio"].set(format_number(taker, 2))
        self.derivative_vars["options_oi"].set(format_btc(options_oi))
        self.derivative_vars["put_call_ratio"].set(format_number(put_call, 2))
        self.derivative_vars["options_iv"].set(format_percent(average_iv))

        lines = self.build_derivative_signals(
            funding_pct,
            annualized,
            basis_pct,
            oi_7d,
            oi_30d,
            long_short,
            taker,
            put_call,
            average_iv,
            largest_strike,
        )
        self.write_text_widget(self.derivative_signal_text, lines, prefix="- ")
        self.derivatives_chart_state = {
            "oi_hist": oi_hist,
            "long_short": long_short_rows,
            "taker": taker_rows,
        }
        self.draw_derivatives_chart()

    def build_derivative_signals(
        self,
        funding_pct,
        annualized,
        basis_pct,
        oi_7d,
        oi_30d,
        long_short,
        taker,
        put_call,
        average_iv,
        largest_strike,
    ):
        lines = ["Dados publicos: Binance USDS-M Futures e Deribit options."]
        if funding_pct is not None:
            if funding_pct > 0.05:
                lines.append("Funding elevado: longs pagando caro para manter exposicao.")
            elif funding_pct < -0.01:
                lines.append("Funding negativo: shorts pagando, possivel estresse baixista.")
            else:
                lines.append("Funding perto do neutro.")
        if annualized is not None:
            lines.append(f"Funding anualizado aproximado: {format_percent(annualized)}.")
        if basis_pct is not None:
            if abs(basis_pct) > 0.15:
                lines.append(f"Basis mark/index relevante: {format_percent(basis_pct)}.")
            else:
                lines.append("Mark price proximo do indice spot.")
        if oi_7d is not None:
            direction = "subiu" if oi_7d >= 0 else "caiu"
            lines.append(f"Open interest {direction} {format_percent(abs(oi_7d))} em 7 dias.")
        if oi_30d is not None:
            direction = "expansao" if oi_30d >= 0 else "contracao"
            lines.append(f"OI 30D em {direction}: {format_percent(oi_30d)}.")
        if long_short is not None:
            if long_short > 1.25:
                lines.append("Top traders inclinados para long.")
            elif long_short < 0.85:
                lines.append("Top traders inclinados para short.")
            else:
                lines.append("Long/short dos top traders equilibrado.")
        if taker is not None:
            if taker > 1.08:
                lines.append("Fluxo taker comprador acima do vendedor.")
            elif taker < 0.92:
                lines.append("Fluxo taker vendedor acima do comprador.")
            else:
                lines.append("Fluxo taker perto do equilibrio.")
        if put_call is not None:
            if put_call > 1.1:
                lines.append("Opcoes com put/call alto: hedge ou vies defensivo mais forte.")
            elif put_call < 0.7:
                lines.append("Opcoes com maior concentracao relativa em calls.")
            else:
                lines.append("Put/call de opcoes em zona intermediaria.")
        if average_iv is not None:
            lines.append(f"IV media ponderada de opcoes: {format_percent(average_iv)}.")
        if largest_strike and largest_strike != "--":
            lines.append(f"Maior concentracao bruta de OI por strike: {largest_strike}.")
        return lines

    def draw_derivatives_chart(self):
        canvas = getattr(self, "derivatives_canvas", None)
        if not canvas:
            return
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 20 or height <= 20:
            return
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill="#0f0e0b", outline="")

        state = self.derivatives_chart_state
        oi_rows = state.get("oi_hist") or []
        long_rows = state.get("long_short") or []
        if not oi_rows:
            canvas.create_text(
                width / 2,
                height / 2,
                text="Aguardando derivativos...",
                fill=COLORS["muted"],
                font=("Segoe UI", 12, "bold"),
            )
            return

        oi_values = [self.to_float(row.get("sumOpenInterestValue")) for row in oi_rows]
        oi_values = [value for value in oi_values if value is not None]
        ratios = [self.to_float(row.get("longShortRatio")) for row in long_rows]
        ratios = [value for value in ratios if value is not None]
        if not oi_values:
            return

        left, right, top, bottom = 72, 48, 22, 42
        plot_w = width - left - right
        plot_h = height - top - bottom
        min_oi = min(oi_values)
        max_oi = max(oi_values)
        span_oi = max(max_oi - min_oi, 1)
        step = plot_w / max(len(oi_values) - 1, 1)

        for idx in range(5):
            y = top + (plot_h / 4) * idx
            canvas.create_line(left, y, width - right, y, fill="#27231b")
            value = max_oi - (span_oi / 4) * idx
            canvas.create_text(
                8,
                y,
                text=format_compact_currency(value, "USD"),
                fill=COLORS["dim"],
                anchor="w",
                font=("Segoe UI", 8),
            )

        points = []
        for idx, value in enumerate(oi_values):
            x = left + idx * step
            y = top + (max_oi - value) / span_oi * plot_h
            points.extend([x, y])
        if len(points) >= 4:
            canvas.create_line(points, fill=COLORS["orange"], width=2)
            canvas.create_text(points[-2], points[-1] - 12, text="OI USD", fill=COLORS["orange"], font=("Segoe UI", 8))

        if ratios:
            min_ratio = min(min(ratios), 0.75)
            max_ratio = max(max(ratios), 1.35)
            span_ratio = max(max_ratio - min_ratio, 0.1)
            ratio_step = plot_w / max(len(ratios) - 1, 1)
            ratio_points = []
            for idx, value in enumerate(ratios):
                x = left + idx * ratio_step
                y = top + (max_ratio - value) / span_ratio * plot_h
                ratio_points.extend([x, y])
            if len(ratio_points) >= 4:
                canvas.create_line(ratio_points, fill=COLORS["cyan"], width=2)
                canvas.create_text(
                    width - right,
                    top + 8,
                    text="Long/Short",
                    fill=COLORS["cyan"],
                    anchor="e",
                    font=("Segoe UI", 8),
                )
            neutral_y = top + (max_ratio - 1) / span_ratio * plot_h
            canvas.create_line(left, neutral_y, width - right, neutral_y, fill="#3b372d", dash=(4, 4))

        canvas.create_text(left, height - 18, text="30 dias", fill=COLORS["muted"], anchor="w")

    def apply_macro_cycle(self, payload):
        if not self.macro_vars:
            return

        fred = {name: payload.get(name) or [] for name in FRED_SERIES}
        cycle = calculate_cycle_metrics(
            self.indicator_candles.get("Diario", []),
            self.indicator_candles.get("Semanal", []),
        )
        supply = calculate_supply(payload.get("tip_height"))

        _date_10y, us10y = latest_fred_value(fred["fred_10y"])
        _date_fed, fed_funds = latest_fred_value(fred["fred_fed_funds"])
        _date_vix, vix = latest_fred_value(fred["fred_vix"])
        _date_dollar, dollar = latest_fred_value(fred["fred_dollar"])
        cpi_yoy = fred_change(fred["fred_cpi"], 365)
        m2_yoy = fred_change(fred["fred_m2"], 365)
        fed_balance_90d = fred_change(fred["fred_fed_balance"], 90)
        dollar_30d = fred_change(fred["fred_dollar"], 30)
        us10y_30d = fred_change(fred["fred_10y"], 30, absolute=True)
        vix_30d = fred_change(fred["fred_vix"], 30)

        self.metrics.update(
            {
                "us10y": us10y,
                "us10y_30d": us10y_30d,
                "fed_funds": fed_funds,
                "vix": vix,
                "vix_30d": vix_30d,
                "dollar": dollar,
                "dollar_30d": dollar_30d,
                "cpi_yoy": cpi_yoy,
                "m2_yoy": m2_yoy,
                "fed_balance_90d": fed_balance_90d,
                "mayer_multiple": cycle.get("mayer_multiple"),
                "pi_distance": cycle.get("pi_distance"),
                "ma200w_multiple": cycle.get("ma200w_multiple"),
                "volatility_30d": cycle.get("volatility_30d"),
                "one_year_return": cycle.get("one_year_return"),
                "halving_days": supply.get("halving_days") if supply else None,
                "issuance_rate": supply.get("issuance_rate") if supply else None,
            }
        )

        self.macro_vars["us10y"].set(f"{format_number(us10y, 2)}% | 30D {format_number(us10y_30d, 2)} p.p.")
        self.macro_vars["fed_funds"].set(f"{format_number(fed_funds, 2)}%")
        self.macro_vars["vix"].set(f"{format_number(vix, 2)} | 30D {format_percent(vix_30d)}")
        self.macro_vars["dollar"].set(f"{format_number(dollar, 2)} | 30D {format_percent(dollar_30d)}")
        self.macro_vars["cpi_yoy"].set(format_percent(cpi_yoy))
        self.macro_vars["m2_yoy"].set(format_percent(m2_yoy))
        self.macro_vars["fed_balance_90d"].set(format_percent(fed_balance_90d))
        self.macro_vars["mayer"].set(format_number(cycle.get("mayer_multiple"), 2))
        self.macro_vars["pi_distance"].set(format_percent(cycle.get("pi_distance")))
        self.macro_vars["ma200w_multiple"].set(format_number(cycle.get("ma200w_multiple"), 2))
        if supply:
            self.macro_vars["halving_eta"].set(
                f"{format_number(supply.get('halving_days'), 0)} dias | bloco {format_number(supply.get('next_halving'), 0)}"
            )
            self.macro_vars["issuance_rate"].set(
                f"{format_percent(supply.get('issuance_rate'))} | {format_btc(supply.get('annual_issuance'))}/ano"
            )
        else:
            self.macro_vars["halving_eta"].set("--")
            self.macro_vars["issuance_rate"].set("--")

        lines = self.build_macro_signals(
            us10y,
            us10y_30d,
            vix,
            vix_30d,
            dollar_30d,
            cpi_yoy,
            m2_yoy,
            fed_balance_90d,
            cycle,
            supply,
        )
        self.write_text_widget(self.macro_text, lines, prefix="- ")
        self.macro_chart_state = {
            "fred": fred,
            "cycle": cycle,
        }
        self.draw_macro_chart()

    def build_macro_signals(
        self,
        us10y,
        us10y_30d,
        vix,
        vix_30d,
        dollar_30d,
        cpi_yoy,
        m2_yoy,
        fed_balance_90d,
        cycle,
        supply,
    ):
        lines = ["Fontes macro oficiais do Federal Reserve/FRED."]
        if us10y is not None and us10y_30d is not None:
            if us10y_30d > 0.25:
                lines.append("Juro de 10 anos subiu forte em 30D; vento macro mais duro para risco.")
            elif us10y_30d < -0.25:
                lines.append("Juro de 10 anos caiu em 30D; alivio macro para ativos de risco.")
            else:
                lines.append("Juro de 10 anos sem choque relevante em 30D.")
        if vix is not None:
            if vix >= 25:
                lines.append("VIX elevado: mercado global em modo defensivo.")
            elif vix <= 15:
                lines.append("VIX baixo: apetite por risco mais confortavel.")
        if vix_30d is not None and vix_30d > 20:
            lines.append("VIX acelerou em 30D; risco de volatilidade de curto prazo.")
        if dollar_30d is not None:
            if dollar_30d > 2:
                lines.append("Dollar amplo em alta de 30D; costuma pressionar liquidez global.")
            elif dollar_30d < -2:
                lines.append("Dollar amplo em queda de 30D; costuma aliviar liquidez global.")
        if cpi_yoy is not None:
            lines.append(f"CPI YoY em {format_percent(cpi_yoy)}.")
        if m2_yoy is not None:
            if m2_yoy > 4:
                lines.append("M2 YoY em expansao relevante: liquidez monetaria melhora.")
            elif m2_yoy < 0:
                lines.append("M2 YoY negativo: liquidez monetaria restritiva.")
        if fed_balance_90d is not None:
            if fed_balance_90d > 1:
                lines.append("Balanco do Fed expandiu em 90D.")
            elif fed_balance_90d < -1:
                lines.append("Balanco do Fed contraiu em 90D.")

        mayer = cycle.get("mayer_multiple")
        if mayer is not None:
            if mayer >= 2.4:
                lines.append("Mayer Multiple muito alto: zona historicamente aquecida.")
            elif mayer <= 0.8:
                lines.append("Mayer Multiple baixo: preco abaixo da media de 200D.")
            else:
                lines.append("Mayer Multiple em faixa intermediaria.")
        pi_distance = cycle.get("pi_distance")
        if pi_distance is not None:
            if pi_distance > -5:
                lines.append("Pi Cycle perto do gatilho de topo historico.")
            elif pi_distance < -35:
                lines.append("Pi Cycle distante do gatilho de topo.")
        one_year = cycle.get("one_year_return")
        if one_year is not None:
            lines.append(f"Retorno BTC 1Y: {format_percent(one_year)}.")
        volatility = cycle.get("volatility_30d")
        if volatility is not None:
            lines.append(f"Volatilidade anualizada 30D: {format_percent(volatility)}.")
        if supply:
            lines.append(
                f"Subsidio atual {format_btc(supply.get('subsidy'))} por bloco; "
                f"emissao anual {format_percent(supply.get('issuance_rate'))}."
            )
            lines.append(
                f"Proximo halving em cerca de {format_number(supply.get('halving_days'), 0)} dias."
            )
        return lines

    def draw_macro_chart(self):
        canvas = getattr(self, "macro_canvas", None)
        if not canvas:
            return
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 20 or height <= 20:
            return
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill="#0f0e0b", outline="")

        state = self.macro_chart_state
        fred = state.get("fred") or {}
        series_specs = [
            ("Dollar", fred.get("fred_dollar") or [], COLORS["orange"]),
            ("US10Y", fred.get("fred_10y") or [], COLORS["cyan"]),
            ("VIX", fred.get("fred_vix") or [], "#ff9188"),
        ]
        left, right, top, bottom = 54, 18, 22, 34
        plot_w = width - left - right
        plot_h = height - top - bottom
        for idx in range(5):
            y = top + (plot_h / 4) * idx
            canvas.create_line(left, y, width - right, y, fill="#27231b")
            canvas.create_text(8, y, text=f"{100 - idx * 25}", fill=COLORS["dim"], anchor="w", font=("Segoe UI", 8))

        drew = False
        for label, rows, color in series_specs:
            values = [parse_float(row.get("value")) for row in rows[-180:]]
            values = [value for value in values if value is not None]
            if len(values) < 2:
                continue
            low = min(values)
            high = max(values)
            span = max(high - low, 0.0001)
            step = plot_w / max(len(values) - 1, 1)
            points = []
            for idx, value in enumerate(values):
                normalized = (value - low) / span
                x = left + idx * step
                y = top + (1 - normalized) * plot_h
                points.extend([x, y])
            canvas.create_line(points, fill=color, width=2)
            canvas.create_text(points[-2] + 4, points[-1], text=label, fill=color, anchor="w", font=("Segoe UI", 8))
            drew = True

        cycle = state.get("cycle") or {}
        mayer = cycle.get("mayer_multiple")
        pi_distance = cycle.get("pi_distance")
        footer = []
        if mayer is not None:
            footer.append(f"Mayer {format_number(mayer, 2)}")
        if pi_distance is not None:
            footer.append(f"Pi {format_percent(pi_distance)}")
        if footer:
            canvas.create_text(left, height - 16, text=" | ".join(footer), fill=COLORS["muted"], anchor="w")
        if not drew:
            canvas.create_text(
                width / 2,
                height / 2,
                text="Aguardando dados macro...",
                fill=COLORS["muted"],
                font=("Segoe UI", 12, "bold"),
            )

    def apply_portfolio(self):
        if not self.portfolio_vars:
            return

        price_usd = self.metrics.get("price_usd")
        price_brl = self.metrics.get("price_brl")
        amount = self.portfolio_number("btc_amount") or 0
        avg_cost = self.portfolio_number("avg_cost_usd")
        cash_usd = self.portfolio_number("cash_usd") or 0
        total_equity_input = self.portfolio_number("total_equity_usd")
        target_allocation = self.portfolio_number("target_allocation")
        dca_monthly = self.portfolio_number("dca_monthly_usd")

        if not price_usd or amount <= 0:
            for variable in self.portfolio_vars.values():
                variable.set("--")
            self.portfolio_state = {}
            lines = [
                "Informe a quantidade de BTC para ativar a leitura de carteira.",
                "Os dados ficam salvos localmente em portfolio.json.",
            ]
            self.write_text_widget(getattr(self, "portfolio_text", None), lines, prefix="- ")
            return

        market_value = amount * price_usd
        market_value_brl = amount * price_brl if price_brl else None
        cost_basis = amount * avg_cost if avg_cost else None
        pnl = market_value - cost_basis if cost_basis is not None else None
        pnl_percent = (pnl / cost_basis) * 100 if pnl is not None and cost_basis else None
        total_equity = total_equity_input or (market_value + cash_usd)
        allocation = (market_value / total_equity) * 100 if total_equity else None
        target_value = total_equity * target_allocation / 100 if total_equity and target_allocation is not None else None
        target_delta_usd = target_value - market_value if target_value is not None else None
        target_delta_btc = target_delta_usd / price_usd if target_delta_usd is not None and price_usd else None
        dca_monthly_btc = dca_monthly / price_usd if dca_monthly and price_usd else None
        volatility = self.metrics.get("volatility_30d")
        var_30d = None
        if volatility is not None:
            var_30d = market_value * (volatility / 100) * math.sqrt(30 / 365) * 1.65
        drop_20 = market_value * 0.2
        ath_drawdown = self.metrics.get("ath_change")

        self.portfolio_vars["btc_value_usd"].set(format_currency(market_value, "USD"))
        self.portfolio_vars["btc_value_brl"].set(format_currency(market_value_brl, "BRL", 0))
        self.portfolio_vars["cost_basis"].set(format_currency(cost_basis, "USD"))
        self.portfolio_vars["pnl"].set(format_signed_currency(pnl, "USD"))
        self.portfolio_vars["pnl_percent"].set(format_percent(pnl_percent))
        self.portfolio_vars["allocation"].set(format_percent(allocation))
        self.portfolio_vars["target_delta_btc"].set(format_btc_precise(target_delta_btc))
        self.portfolio_vars["dca_monthly_btc"].set(format_btc_precise(dca_monthly_btc))
        self.portfolio_vars["var_30d"].set(format_currency(var_30d, "USD"))
        self.portfolio_vars["drop_20"].set(format_currency(drop_20, "USD"))
        self.portfolio_vars["ath_drawdown"].set(format_percent(ath_drawdown))
        self.portfolio_vars["breakeven"].set(format_currency(avg_cost, "USD"))

        self.portfolio_state = {
            "amount": amount,
            "price_usd": price_usd,
            "market_value": market_value,
            "market_value_brl": market_value_brl,
            "cost_basis": cost_basis,
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "cash_usd": cash_usd,
            "total_equity": total_equity,
            "allocation": allocation,
            "target_allocation": target_allocation,
            "target_delta_usd": target_delta_usd,
            "target_delta_btc": target_delta_btc,
            "dca_monthly_btc": dca_monthly_btc,
            "var_30d": var_30d,
            "drop_20": drop_20,
        }
        self.write_text_widget(self.portfolio_text, self.build_portfolio_lines(), prefix="- ")

    def build_portfolio_lines(self):
        state = self.portfolio_state
        if not state:
            return ["Aguardando dados de carteira."]
        lines = ["Dados de carteira ficam apenas neste computador."]
        pnl = state.get("pnl")
        pnl_percent = state.get("pnl_percent")
        if pnl is not None:
            status = "positivo" if pnl >= 0 else "negativo"
            lines.append(f"P/L {status}: {format_signed_currency(pnl, 'USD')} ({format_percent(pnl_percent)}).")
        allocation = state.get("allocation")
        target = state.get("target_allocation")
        if allocation is not None and target is not None:
            diff = allocation - target
            if abs(diff) <= 2:
                lines.append("Alocacao perto do alvo informado.")
            elif diff > 0:
                lines.append(f"Alocacao acima do alvo em {format_number(diff, 1)} p.p.")
            else:
                lines.append(f"Alocacao abaixo do alvo em {format_number(abs(diff), 1)} p.p.")
        if state.get("var_30d") is not None:
            lines.append(f"VaR 30D 95% aproximado: {format_currency(state['var_30d'], 'USD')}.")
        if state.get("drop_20") is not None:
            lines.append(f"Uma queda de 20% reduziria cerca de {format_currency(state['drop_20'], 'USD')}.")
        if state.get("dca_monthly_btc") is not None:
            lines.append(f"DCA mensal informado compra cerca de {format_btc_precise(state['dca_monthly_btc'])}.")
        funding = self.metrics.get("funding_rate_pct")
        if funding is not None and funding > 0.05:
            lines.append("Funding alto: risco de alavancagem comprada no mercado.")
        vix = self.metrics.get("vix")
        if vix is not None and vix >= 25:
            lines.append("VIX elevado: risco macro global acima do normal.")
        mayer = self.metrics.get("mayer_multiple")
        if mayer is not None:
            if mayer >= 2.4:
                lines.append("Mayer Multiple historicamente aquecido.")
            elif mayer <= 0.8:
                lines.append("Mayer Multiple em zona historicamente fria.")
        return lines

    def render_report(self):
        if not hasattr(self, "report_text"):
            return
        lines = self.build_report_lines(self.report_period.get())
        self.write_text_widget(self.report_text, lines)

    def build_report_lines(self, period):
        change = self.metrics.get("change_7d" if period == "7D" else "change_30d")
        daily_snapshot = calculate_indicators(self.indicator_candles.get("Diario", []))
        weekly_snapshot = calculate_indicators(self.indicator_candles.get("Semanal", []))
        lines = [
            f"Bitcoin Monitor - Relatorio {period}",
            f"Gerado em {dt.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            "",
            "MERCADO",
            f"- Preco BTC/USD: {format_currency(self.metrics.get('price_usd'), 'USD')}",
            f"- Preco BTC/BRL: {format_currency(self.metrics.get('price_brl'), 'BRL', 0)}",
            f"- Variacao {period}: {format_percent(change)}",
            f"- Variacao 24h: {format_percent(self.metrics.get('change_24h'))}",
            f"- Dominancia BTC: {format_number(self.metrics.get('btc_dominance'), 1)}%",
            "",
            "TECNICA",
            f"- Diario: RSI14 {format_number(daily_snapshot.get('rsi14'), 1)} | ADX14 {format_number(daily_snapshot.get('adx14'), 1)} | ATR {format_percent(daily_snapshot.get('atr_percent'))}",
            f"- Diario: MM200 {format_currency(daily_snapshot.get('ma200'), 'USD')} | Dist. MM200 {format_percent(daily_snapshot.get('distance_ma200'))}",
            f"- Semanal: MM200 {format_currency(weekly_snapshot.get('ma200'), 'USD')} | Dist. MM200 {format_percent(weekly_snapshot.get('distance_ma200'))}",
            f"- Mayer Multiple: {format_number(self.metrics.get('mayer_multiple'), 2)} | 200W multiple {format_number(self.metrics.get('ma200w_multiple'), 2)}",
            "",
            "DERIVATIVOS",
            f"- Funding: {format_percent(self.metrics.get('funding_rate_pct'))}",
            f"- Open interest: {format_compact_currency(self.metrics.get('open_interest_usd'), 'USD')} | 7D {format_percent(self.metrics.get('open_interest_7d'))}",
            f"- Long/Short top traders: {format_number(self.metrics.get('long_short_ratio'), 2)} | Taker buy/sell {format_number(self.metrics.get('taker_ratio'), 2)}",
            f"- Put/Call options: {format_number(self.metrics.get('put_call_ratio'), 2)} | IV media {format_percent(self.metrics.get('options_iv'))}",
            "",
            "REDE",
            f"- Fee rapida: {format_number(self.metrics.get('fee_fastest'), 0)} sat/vB",
            f"- Mempool: {format_number(self.metrics.get('mempool_vmb'), 1)} vMB",
            f"- Dificuldade: {format_percent(self.metrics.get('difficulty_change'))}",
            f"- Halving estimado: {format_number(self.metrics.get('halving_days'), 0)} dias | emissao anual {format_percent(self.metrics.get('issuance_rate'))}",
            "",
            "MACRO",
            f"- US 10Y: {format_number(self.metrics.get('us10y'), 2)}% | 30D {format_number(self.metrics.get('us10y_30d'), 2)} p.p.",
            f"- VIX: {format_number(self.metrics.get('vix'), 2)} | 30D {format_percent(self.metrics.get('vix_30d'))}",
            f"- Dollar amplo 30D: {format_percent(self.metrics.get('dollar_30d'))}",
            f"- CPI YoY: {format_percent(self.metrics.get('cpi_yoy'))} | M2 YoY {format_percent(self.metrics.get('m2_yoy'))}",
            "",
            "CARTEIRA",
        ]
        if self.portfolio_state:
            lines.extend(
                [
                    f"- Valor BTC: {format_currency(self.portfolio_state.get('market_value'), 'USD')}",
                    f"- P/L: {format_signed_currency(self.portfolio_state.get('pnl'), 'USD')} ({format_percent(self.portfolio_state.get('pnl_percent'))})",
                    f"- Alocacao: {format_percent(self.portfolio_state.get('allocation'))}",
                    f"- Risco 30D 95% aprox.: {format_currency(self.portfolio_state.get('var_30d'), 'USD')}",
                ]
            )
        else:
            lines.append("- Carteira nao configurada.")
        lines.extend(["", "NOTICIAS RECENTES"])
        for item in self.news_items[:5]:
            lines.append(
                f"- [{item.get('category', 'Mercado')}/{item.get('impact', 'normal')}] "
                f"{item.get('source')}: {item.get('title')}"
            )
        if not self.news_items:
            lines.append("- Aguardando noticias.")
        lines.extend(["", "PONTOS DE ATENCAO"])
        flags = self.build_report_flags(daily_snapshot)
        lines.extend([f"- {flag}" for flag in flags] or ["- Nenhum ponto critico detectado pelos filtros atuais."])
        return lines

    def build_report_flags(self, daily_snapshot):
        flags = []
        if self.metrics.get("funding_rate_pct") is not None and self.metrics["funding_rate_pct"] > 0.05:
            flags.append("Funding elevado pode indicar excesso de alavancagem comprada.")
        if self.metrics.get("open_interest_7d") is not None and self.metrics["open_interest_7d"] > 10:
            flags.append("Open interest subiu forte em 7D; movimentos podem ficar mais violentos.")
        if self.metrics.get("vix") is not None and self.metrics["vix"] >= 25:
            flags.append("VIX acima de 25 sinaliza estresse macro.")
        if self.metrics.get("us10y_30d") is not None and self.metrics["us10y_30d"] > 0.25:
            flags.append("Juro de 10 anos subiu mais de 0,25 p.p. em 30D.")
        if daily_snapshot.get("distance_ma200") is not None and daily_snapshot["distance_ma200"] < 0:
            flags.append("Preco diario abaixo da MM200.")
        if daily_snapshot.get("rsi14") is not None and daily_snapshot["rsi14"] >= 70:
            flags.append("RSI diario em sobrecompra.")
        if daily_snapshot.get("rsi14") is not None and daily_snapshot["rsi14"] <= 30:
            flags.append("RSI diario em sobrevenda.")
        return flags

    def copy_report(self):
        if not hasattr(self, "report_text"):
            return
        content = self.report_text.get("1.0", END).strip()
        self.clipboard_clear()
        self.clipboard_append(content)
        self.add_event("Relatorio", "Relatorio copiado para a area de transferencia.")

    def apply_fear_greed(self, payload):
        if not payload:
            return
        current = (payload.get("data") or [{}])[0]
        value = current.get("value")
        label = translate_fear_greed(current.get("value_classification"))
        if value:
            self.value_vars["fear_greed"].set(f"{value} - {label}")

    def render_orderbook(self):
        self.orderbook_text.configure(state="normal")
        self.orderbook_text.delete("1.0", END)
        self.orderbook_text.insert(END, "ASKS        QTD.        TOTAL\n", "muted")
        for price, amount, total in self.with_totals(self.depth["asks"]):
            self.orderbook_text.insert(
                END,
                f"{price:>10.2f}  {amount:>9.4f}  {total:>9.4f}\n",
                "ask",
            )
        self.orderbook_text.insert(END, "\nBIDS        QTD.        TOTAL\n", "muted")
        for price, amount, total in self.with_totals(self.depth["bids"]):
            self.orderbook_text.insert(
                END,
                f"{price:>10.2f}  {amount:>9.4f}  {total:>9.4f}\n",
                "bid",
            )
        self.orderbook_text.configure(state="disabled")

    def draw_chart(self):
        canvas = self.chart_canvas
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 20 or height <= 20:
            return

        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill="#0f0e0b", outline="")

        if not self.candles:
            canvas.create_text(
                width / 2,
                height / 2,
                text="Carregando candles...",
                fill=COLORS["muted"],
                font=("Segoe UI", 12, "bold"),
            )
            return

        candles = self.candles[-140:]
        highs = [item["high"] for item in candles]
        lows = [item["low"] for item in candles]
        max_price = max(highs)
        min_price = min(lows)
        span = max(max_price - min_price, 1)
        left, right, top, bottom = 52, 18, 18, 34
        plot_w = width - left - right
        plot_h = height - top - bottom

        for idx in range(5):
            y = top + (plot_h / 4) * idx
            canvas.create_line(left, y, width - right, y, fill="#27231b")
            price = max_price - (span / 4) * idx
            canvas.create_text(
                8,
                y,
                text=f"{price:,.0f}".replace(",", "."),
                fill=COLORS["dim"],
                anchor="w",
                font=("Segoe UI", 8),
            )

        step = plot_w / max(len(candles), 1)
        body_w = max(3, min(9, step * 0.62))

        def to_y(price):
            return top + (max_price - price) / span * plot_h

        for idx, candle in enumerate(candles):
            x = left + idx * step + step / 2
            color = COLORS["green"] if candle["close"] >= candle["open"] else COLORS["red"]
            y_high = to_y(candle["high"])
            y_low = to_y(candle["low"])
            y_open = to_y(candle["open"])
            y_close = to_y(candle["close"])
            canvas.create_line(x, y_high, x, y_low, fill=color, width=1)
            top_body = min(y_open, y_close)
            bottom_body = max(y_open, y_close)
            if abs(bottom_body - top_body) < 1:
                bottom_body = top_body + 1
            canvas.create_rectangle(
                x - body_w / 2,
                top_body,
                x + body_w / 2,
                bottom_body,
                fill=color,
                outline=color,
            )

        last = candles[-1]["close"]
        y_last = to_y(last)
        canvas.create_line(left, y_last, width - right, y_last, fill=COLORS["orange"], dash=(4, 4))
        canvas.create_text(
            width - right - 4,
            y_last - 10,
            text=format_currency(last, "USD"),
            fill=COLORS["orange"],
            anchor="e",
            font=("Segoe UI", 9, "bold"),
        )

    def draw_mempool_bar(self, vmb):
        self.mempool_bar.delete("all")
        width = max(self.mempool_bar.winfo_width(), 1)
        height = max(self.mempool_bar.winfo_height(), 1)
        fill_width = min(width, int(width * min(vmb / 300, 1)))
        color = COLORS["green"] if vmb < 80 else COLORS["orange"] if vmb < 180 else COLORS["red"]
        self.mempool_bar.create_rectangle(0, 0, width, height, fill=COLORS["panel_2"], outline="")
        self.mempool_bar.create_rectangle(0, 0, fill_width, height, fill=color, outline="")

    def render_indicators(self):
        period = self.indicator_period.get()
        candles = self.indicator_candles.get(period, [])
        snapshot = calculate_indicators(candles)

        if not snapshot:
            for variable in self.indicator_vars.values():
                variable.set("--")
            if hasattr(self, "indicator_extra_text"):
                self.write_text_widget(self.indicator_extra_text, ["Aguardando indicadores avancados."])
            self.write_indicator_signals(["Aguardando candles semanais e mensais."])
            self.draw_indicator_chart()
            return

        self.indicator_vars["last_close"].set(format_currency(snapshot.get("last_close"), "USD"))
        self.indicator_vars["ma50"].set(format_currency(snapshot.get("ma50"), "USD"))
        self.indicator_vars["ma100"].set(format_currency(snapshot.get("ma100"), "USD"))
        self.indicator_vars["ma200"].set(format_currency(snapshot.get("ma200"), "USD"))
        self.indicator_vars["distance_ma200"].set(format_percent(snapshot.get("distance_ma200")))
        self.indicator_vars["bb_upper"].set(format_currency(snapshot.get("bb_upper"), "USD"))
        self.indicator_vars["bb_basis"].set(format_currency(snapshot.get("bb_basis"), "USD"))
        self.indicator_vars["bb_lower"].set(format_currency(snapshot.get("bb_lower"), "USD"))
        self.indicator_vars["rsi14"].set(format_number(snapshot.get("rsi14"), 1))
        self.indicator_vars["macd"].set(
            f"{format_number(snapshot.get('macd'), 2)} / {format_number(snapshot.get('macd_signal'), 2)}"
        )
        self.indicator_vars["volume"].set(format_number(snapshot.get("volume"), 0))
        self.indicator_vars["volume_change"].set(format_percent(snapshot.get("volume_change")))

        self.write_indicator_extras(snapshot)
        self.write_indicator_signals(self.build_indicator_signals(snapshot, period))
        self.draw_indicator_chart()

    def write_indicator_extras(self, snapshot):
        lines = [
            f"EMA21       {format_currency(snapshot.get('ema21'), 'USD')}",
            f"EMA50       {format_currency(snapshot.get('ema50'), 'USD')}",
            f"VWMA20      {format_currency(snapshot.get('vwma20'), 'USD')}",
            f"ATR14       {format_currency(snapshot.get('atr14'), 'USD')} ({format_percent(snapshot.get('atr_percent'))})",
            f"ADX14       {format_number(snapshot.get('adx14'), 1)}",
            f"Stoch RSI   {format_number(snapshot.get('stoch_rsi14'), 1)}",
            f"MFI14       {format_number(snapshot.get('mfi14'), 1)}",
            f"OBV         {format_compact_number(snapshot.get('obv'), 2)}",
            f"Donchian    {format_currency(snapshot.get('donchian_lower'), 'USD')} - {format_currency(snapshot.get('donchian_upper'), 'USD')}",
            f"Keltner     {format_currency(snapshot.get('keltner_lower'), 'USD')} - {format_currency(snapshot.get('keltner_upper'), 'USD')}",
            f"Ichimoku    Tenkan {format_currency(snapshot.get('ichimoku_tenkan'), 'USD')} | Kijun {format_currency(snapshot.get('ichimoku_kijun'), 'USD')}",
        ]
        self.write_text_widget(self.indicator_extra_text, lines)

    def build_indicator_signals(self, snapshot, period):
        close = snapshot.get("last_close")
        lines = [f"Periodo analisado: {period.lower()}."]
        if close and snapshot.get("ma50"):
            side = "acima" if close >= snapshot["ma50"] else "abaixo"
            lines.append(f"Preco esta {side} da media movel de 50 periodos.")
        if close and snapshot.get("ma100"):
            side = "acima" if close >= snapshot["ma100"] else "abaixo"
            lines.append(f"Preco esta {side} da media movel de 100 periodos.")
        if close and snapshot.get("ma200"):
            side = "acima" if close >= snapshot["ma200"] else "abaixo"
            lines.append(f"Preco esta {side} da media movel de 200 periodos.")
        else:
            lines.append("Media de 200 periodos ainda sem historico suficiente neste intervalo.")

        rsi = snapshot.get("rsi14")
        if rsi is not None:
            if rsi >= 70:
                lines.append("RSI 14 em zona de sobrecompra.")
            elif rsi <= 30:
                lines.append("RSI 14 em zona de sobrevenda.")
            else:
                lines.append("RSI 14 em faixa neutra.")

        close = snapshot.get("last_close")
        upper = snapshot.get("bb_upper")
        lower = snapshot.get("bb_lower")
        basis = snapshot.get("bb_basis")
        if close and upper and lower and basis:
            if close > upper:
                lines.append("Preco acima da banda superior de Bollinger.")
            elif close < lower:
                lines.append("Preco abaixo da banda inferior de Bollinger.")
            elif close > basis:
                lines.append("Preco entre a media e a banda superior de Bollinger.")
            else:
                lines.append("Preco entre a banda inferior e a media de Bollinger.")

        histogram = snapshot.get("macd_histogram")
        if histogram is not None:
            direction = "positivo" if histogram >= 0 else "negativo"
            lines.append(f"Histograma MACD {direction}.")

        adx = snapshot.get("adx14")
        if adx is not None:
            if adx >= 25:
                lines.append("ADX 14 indica tendencia com forca acima da media.")
            elif adx < 18:
                lines.append("ADX 14 sugere mercado mais lateral.")

        stoch_rsi = snapshot.get("stoch_rsi14")
        if stoch_rsi is not None:
            if stoch_rsi >= 80:
                lines.append("Stoch RSI em regiao quente; cuidado com entradas atrasadas.")
            elif stoch_rsi <= 20:
                lines.append("Stoch RSI frio; possivel exaustao de venda no curto prazo do periodo.")

        mfi = snapshot.get("mfi14")
        if mfi is not None:
            if mfi >= 80:
                lines.append("MFI 14 mostra pressao de compra/volume elevada.")
            elif mfi <= 20:
                lines.append("MFI 14 mostra pressao de venda/volume elevada.")

        atr_percent = snapshot.get("atr_percent")
        if atr_percent is not None:
            if atr_percent >= 8:
                lines.append("ATR percentual alto: volatilidade estrutural elevada.")
            elif atr_percent <= 3:
                lines.append("ATR percentual baixo: volatilidade comprimida.")

        donchian_upper = snapshot.get("donchian_upper")
        donchian_lower = snapshot.get("donchian_lower")
        if close and donchian_upper and donchian_lower:
            if close >= donchian_upper * 0.995:
                lines.append("Preco proximo da maxima Donchian 20: zona de rompimento.")
            elif close <= donchian_lower * 1.005:
                lines.append("Preco proximo da minima Donchian 20: zona de suporte/risco.")

        keltner_upper = snapshot.get("keltner_upper")
        keltner_lower = snapshot.get("keltner_lower")
        if close and keltner_upper and keltner_lower:
            if close > keltner_upper:
                lines.append("Preco acima do canal de Keltner.")
            elif close < keltner_lower:
                lines.append("Preco abaixo do canal de Keltner.")

        trend_score = snapshot.get("trend_score")
        if trend_score is not None:
            if trend_score >= 4:
                lines.append("Score de tendencia majoritariamente altista.")
            elif trend_score <= -4:
                lines.append("Score de tendencia majoritariamente baixista.")
            else:
                lines.append("Score de tendencia misto.")

        volume_change = snapshot.get("volume_change")
        if volume_change is not None:
            if volume_change > 30:
                lines.append("Volume bem acima da media de 20 periodos.")
            elif volume_change < -30:
                lines.append("Volume bem abaixo da media de 20 periodos.")
            else:
                lines.append("Volume perto da media recente.")
        return lines

    def write_indicator_signals(self, lines):
        self.indicator_signal_text.configure(state="normal")
        self.indicator_signal_text.delete("1.0", END)
        for line in lines:
            self.indicator_signal_text.insert(END, f"- {line}\n")
        self.indicator_signal_text.configure(state="disabled")

    def write_text_widget(self, widget, lines, prefix=""):
        if not widget:
            return
        widget.configure(state="normal")
        widget.delete("1.0", END)
        for line in lines:
            widget.insert(END, f"{prefix}{line}\n")
        widget.configure(state="disabled")

    def draw_indicator_chart(self):
        canvas = getattr(self, "indicator_canvas", None)
        if not canvas:
            return
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 20 or height <= 20:
            return

        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill="#0f0e0b", outline="")
        candles = self.indicator_candles.get(self.indicator_period.get(), [])[-260:]
        if not candles:
            canvas.create_text(
                width / 2,
                height / 2,
                text="Aguardando historico...",
                fill=COLORS["muted"],
                font=("Segoe UI", 12, "bold"),
            )
            return

        closes = [item["close"] for item in candles]
        highs = [item["high"] for item in candles]
        lows = [item["low"] for item in candles]
        volumes = [item["volume"] for item in candles]
        ma50 = rolling_sma(closes, 50)
        ma100 = rolling_sma(closes, 100)
        ma200 = rolling_sma(closes, 200)
        ema21 = ema_series(closes, 21)
        ema50 = ema_series(closes, 50)
        bb_basis = rolling_sma(closes, 20)
        bb_std = rolling_std(closes, 20)
        bb_upper = [
            basis + 2 * std if basis is not None and std is not None else None
            for basis, std in zip(bb_basis, bb_std)
        ]
        bb_lower = [
            basis - 2 * std if basis is not None and std is not None else None
            for basis, std in zip(bb_basis, bb_std)
        ]
        keltner_basis, keltner_upper, keltner_lower = keltner_series(candles, 20)
        donchian_upper, donchian_lower = donchian_series(candles, 20)
        tenkan, kijun, span_a, span_b = ichimoku_series(candles)

        show_volume = self.indicator_layers["volume"].get()
        left, right, top = 58, 18, 18
        bottom = 88 if show_volume else 30
        volume_top = height - 62 if show_volume else height - bottom
        plot_h = volume_top - top - 12
        plot_w = width - left - right
        price_refs = highs + lows
        if self.indicator_layers["bollinger"].get():
            price_refs.extend(item for item in bb_upper + bb_lower if item is not None)
        if self.indicator_layers["keltner"].get():
            price_refs.extend(item for item in keltner_upper + keltner_lower if item is not None)
        if self.indicator_layers["donchian"].get():
            price_refs.extend(item for item in donchian_upper + donchian_lower if item is not None)
        if self.indicator_layers["ichimoku"].get():
            price_refs.extend(item for item in tenkan + kijun + span_a + span_b if item is not None)
        max_price = max(price_refs)
        min_price = min(price_refs)
        span = max(max_price - min_price, 1)

        def to_y(price):
            return top + (max_price - price) / span * plot_h

        for idx in range(5):
            y = top + (plot_h / 4) * idx
            canvas.create_line(left, y, width - right, y, fill="#27231b")
            price = max_price - (span / 4) * idx
            canvas.create_text(
                8,
                y,
                text=f"{price:,.0f}".replace(",", "."),
                fill=COLORS["dim"],
                anchor="w",
                font=("Segoe UI", 8),
            )

        step = plot_w / max(len(candles), 1)
        candle_w = max(2, min(7, step * 0.58))
        for idx, candle in enumerate(candles):
            x = left + idx * step + step / 2
            color = COLORS["green"] if candle["close"] >= candle["open"] else COLORS["red"]
            y_high = to_y(candle["high"])
            y_low = to_y(candle["low"])
            y_open = to_y(candle["open"])
            y_close = to_y(candle["close"])
            canvas.create_line(x, y_high, x, y_low, fill=color, width=1)
            canvas.create_rectangle(
                x - candle_w / 2,
                min(y_open, y_close),
                x + candle_w / 2,
                max(y_open, y_close) + 1,
                fill=color,
                outline=color,
            )

        if self.indicator_layers["ma50"].get():
            self.draw_series_line(canvas, ma50, left, step, to_y, "#ffd166", "MM50")
        if self.indicator_layers["ma100"].get():
            self.draw_series_line(canvas, ma100, left, step, to_y, COLORS["cyan"], "MM100")
        if self.indicator_layers["ma200"].get():
            self.draw_series_line(canvas, ma200, left, step, to_y, "#c084fc", "MM200")
        if self.indicator_layers["ema21"].get():
            self.draw_series_line(canvas, ema21, left, step, to_y, "#4ade80", "EMA21")
        if self.indicator_layers["ema50"].get():
            self.draw_series_line(canvas, ema50, left, step, to_y, "#60a5fa", "EMA50")
        if self.indicator_layers["bollinger"].get():
            self.draw_series_line(canvas, bb_upper, left, step, to_y, "#ff9188", "BB sup")
            self.draw_series_line(canvas, bb_lower, left, step, to_y, "#ff9188", "BB inf")
        if self.indicator_layers["keltner"].get():
            self.draw_series_line(canvas, keltner_upper, left, step, to_y, "#fbbf24", "Kelt sup")
            self.draw_series_line(canvas, keltner_lower, left, step, to_y, "#fbbf24", "Kelt inf")
        if self.indicator_layers["donchian"].get():
            self.draw_series_line(canvas, donchian_upper, left, step, to_y, "#a3e635", "Don sup")
            self.draw_series_line(canvas, donchian_lower, left, step, to_y, "#a3e635", "Don inf")
        if self.indicator_layers["ichimoku"].get():
            self.draw_series_line(canvas, tenkan, left, step, to_y, "#fb7185", "Tenkan")
            self.draw_series_line(canvas, kijun, left, step, to_y, "#818cf8", "Kijun")
            self.draw_series_line(canvas, span_a, left, step, to_y, "#34d399", "Span A")
            self.draw_series_line(canvas, span_b, left, step, to_y, "#f87171", "Span B")

        if show_volume:
            max_volume = max(volumes) or 1
            volume_h = 42
            for idx, volume in enumerate(volumes):
                x = left + idx * step + step / 2
                bar_h = (volume / max_volume) * volume_h
                canvas.create_rectangle(
                    x - candle_w / 2,
                    height - bottom + volume_h - bar_h,
                    x + candle_w / 2,
                    height - bottom + volume_h,
                    fill="#5c5446",
                    outline="",
                )
            canvas.create_text(left, height - 18, text="Volume", fill=COLORS["muted"], anchor="w")

        self.indicator_chart_state = {
            "candles": candles,
            "left": left,
            "right": right,
            "top": top,
            "plot_w": plot_w,
            "plot_h": plot_h,
            "step": step,
            "ma50": ma50,
            "ma100": ma100,
            "ma200": ma200,
            "ema21": ema21,
            "ema50": ema50,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "bb_basis": bb_basis,
            "keltner_upper": keltner_upper,
            "keltner_lower": keltner_lower,
            "donchian_upper": donchian_upper,
            "donchian_lower": donchian_lower,
            "tenkan": tenkan,
            "kijun": kijun,
        }

    def draw_series_line(self, canvas, values, left, step, to_y, color, label):
        points = []
        for idx, value in enumerate(values):
            if value is None:
                if len(points) > 1:
                    canvas.create_line(points, fill=color, width=2)
                points = []
                continue
            points.extend([left + idx * step + step / 2, to_y(value)])
        if len(points) > 1:
            canvas.create_line(points, fill=color, width=2)
            canvas.create_text(points[-2] + 3, points[-1], text=label, fill=color, anchor="w", font=("Segoe UI", 8))

    def show_indicator_hover(self, event):
        chart_state = self.indicator_chart_state
        candles = chart_state.get("candles") or []
        if not candles:
            return
        left = chart_state.get("left", 0)
        step = chart_state.get("step", 1)
        index = int((event.x - left) / max(step, 1))
        if index < 0 or index >= len(candles):
            return

        candle = candles[index]
        date_label = dt.datetime.fromtimestamp(candle["time"] / 1000).strftime("%d/%m/%Y")
        parts = [
            date_label,
            f"O {format_currency(candle['open'], 'USD')}",
            f"H {format_currency(candle['high'], 'USD')}",
            f"L {format_currency(candle['low'], 'USD')}",
            f"C {format_currency(candle['close'], 'USD')}",
            f"Vol {format_number(candle['volume'], 0)}",
        ]
        for label, key in [
            ("MM50", "ma50"),
            ("MM100", "ma100"),
            ("MM200", "ma200"),
            ("EMA21", "ema21"),
            ("EMA50", "ema50"),
            ("BB sup", "bb_upper"),
            ("BB inf", "bb_lower"),
            ("Kelt sup", "keltner_upper"),
            ("Kelt inf", "keltner_lower"),
            ("Don sup", "donchian_upper"),
            ("Don inf", "donchian_lower"),
            ("Tenkan", "tenkan"),
            ("Kijun", "kijun"),
        ]:
            values = chart_state.get(key) or []
            if index < len(values) and values[index] is not None:
                parts.append(f"{label} {format_currency(values[index], 'USD')}")
        self.indicator_hover_var.set(" | ".join(parts))

    def clear_indicator_hover(self, _event):
        self.indicator_hover_var.set("Passe o mouse no grafico para ver OHLC, volume e indicadores do candle.")

    def add_alert(self):
        value = self.to_float(self.alert_value.get().replace(",", "."))
        if value is None:
            messagebox.showwarning(APP_NAME, "Informe um valor numerico para o alerta.")
            return

        alert = {
            "id": str(time.time_ns()),
            "label": self.alert_metric.get(),
            "metric": METRICS[self.alert_metric.get()],
            "operator": "above" if self.alert_operator.get() == "acima de" else "below",
            "value": value,
            "created_at": time.time(),
            "triggered_at": None,
        }
        self.alerts.insert(0, alert)
        self.alert_value.set("")
        self.save_alerts()
        self.render_alerts()
        self.add_event("Alerta", "Novo alerta local criado.")

    def clear_alerts(self):
        self.alerts = []
        self.save_alerts()
        self.render_alerts()
        self.add_event("Alerta", "Alertas locais removidos.")

    def remove_alert(self, alert_id):
        self.alerts = [alert for alert in self.alerts if alert["id"] != alert_id]
        self.save_alerts()
        self.render_alerts()

    def render_alerts(self):
        for child in self.alerts_frame.winfo_children():
            child.destroy()

        if not self.alerts:
            Label(
                self.alerts_frame,
                text="Nenhum alerta ativo.",
                bg=COLORS["panel"],
                fg=COLORS["muted"],
                font=("Segoe UI", 9),
            ).pack(anchor="w", pady=6)
            return

        for alert in self.alerts:
            row = Frame(self.alerts_frame, bg=COLORS["panel_2"], padx=8, pady=6)
            row.pack(fill=X, pady=(0, 7))
            op = "acima de" if alert["operator"] == "above" else "abaixo de"
            Label(
                row,
                text=f"{alert['label']} {op} {metric_value_label(alert['metric'], alert['value'])}",
                bg=COLORS["panel_2"],
                fg=COLORS["text"],
                font=("Segoe UI", 9),
                wraplength=220,
                justify=LEFT,
            ).pack(side=LEFT, fill=X, expand=True)
            self.make_button(row, "x", lambda alert_id=alert["id"]: self.remove_alert(alert_id)).pack(
                side=RIGHT
            )

    def check_alerts(self):
        changed = False
        now = time.time()
        for alert in self.alerts:
            current = self.metrics.get(alert["metric"])
            if current is None or not math.isfinite(current):
                continue
            matched = current >= alert["value"] if alert["operator"] == "above" else current <= alert["value"]
            can_trigger = not alert.get("triggered_at") or now - alert["triggered_at"] > 30 * 60
            if matched and can_trigger:
                alert["triggered_at"] = now
                changed = True
                op = "acima de" if alert["operator"] == "above" else "abaixo de"
                message = (
                    f"{alert['label']} {op} {metric_value_label(alert['metric'], alert['value'])}. "
                    f"Atual: {metric_value_label(alert['metric'], current)}."
                )
                self.add_event("Alerta disparado", message)
                self.show_toast("Alerta Bitcoin Monitor", message)
        if changed:
            self.save_alerts()

    def show_toast(self, title, message):
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

        toast = Toplevel(self)
        toast.title(title)
        toast.configure(bg=COLORS["panel"])
        toast.attributes("-topmost", True)
        toast.resizable(False, False)
        Label(
            toast,
            text=title,
            bg=COLORS["panel"],
            fg=COLORS["orange"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=14, pady=(12, 2))
        Label(
            toast,
            text=message,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI", 9),
            wraplength=320,
            justify=LEFT,
        ).pack(anchor="w", padx=14, pady=(0, 12))
        toast.update_idletasks()
        x = self.winfo_x() + self.winfo_width() - toast.winfo_width() - 28
        y = self.winfo_y() + self.winfo_height() - toast.winfo_height() - 48
        toast.geometry(f"+{max(x, 20)}+{max(y, 20)}")
        toast.after(6500, toast.destroy)

    def add_event(self, title, message):
        self.events.insert(0, (time.strftime("%H:%M:%S"), title, message))
        self.events = self.events[:10]
        self.render_events()

    def render_events(self):
        self.events_text.configure(state="normal")
        self.events_text.delete("1.0", END)
        for when, title, message in self.events:
            self.events_text.insert(END, f"{when}  {title}\n", "title")
            self.events_text.insert(END, f"{message}\n\n")
        self.events_text.tag_config("title", foreground=COLORS["orange"], font=("Segoe UI", 9, "bold"))
        self.events_text.configure(state="disabled")

    def set_status(self, text, status):
        self.status_var.set(text)
        color = {
            "online": COLORS["green"],
            "offline": COLORS["red"],
            "neutral": COLORS["muted"],
        }.get(status, COLORS["muted"])
        self.status_label.configure(fg=color)

    def load_update_manifest_url(self):
        env_url = os.environ.get("BITCOIN_MONITOR_UPDATE_URL", "").strip()
        if env_url:
            return env_url

        candidates = [UPDATE_CONFIG_FILE]
        try:
            app_base = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
            candidates.append(app_base / "update_config.json")
        except Exception:
            pass

        for candidate in candidates:
            try:
                if candidate.exists():
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                    url = data.get("manifest_url", "").strip()
                    if url:
                        return url
            except Exception:
                continue
        return DEFAULT_UPDATE_MANIFEST_URL

    def load_alerts(self):
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            if ALERTS_FILE.exists():
                return json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
        return []

    def load_portfolio(self):
        defaults = {
            "btc_amount": "",
            "avg_cost_usd": "",
            "cash_usd": "",
            "total_equity_usd": "",
            "target_allocation": "",
            "dca_monthly_usd": "",
        }
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            if PORTFOLIO_FILE.exists():
                data = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    defaults.update(data)
        except Exception:
            pass
        return defaults

    def save_portfolio_from_inputs(self):
        data = {}
        for key, variable in self.portfolio_inputs.items():
            value = self.portfolio_number(key)
            data[key] = "" if value is None else value
            variable.set("" if value is None else str(value))
        self.portfolio = data
        self.save_portfolio()
        self.apply_portfolio()
        self.render_report()
        self.add_event("Carteira", "Carteira salva localmente.")

    def clear_portfolio(self):
        for variable in self.portfolio_inputs.values():
            variable.set("")
        self.portfolio = self.load_portfolio()
        for key in self.portfolio:
            self.portfolio[key] = ""
        self.save_portfolio()
        self.apply_portfolio()
        self.render_report()
        self.add_event("Carteira", "Carteira local limpa.")

    def save_portfolio(self):
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            PORTFOLIO_FILE.write_text(json.dumps(self.portfolio, indent=2), encoding="utf-8")
        except Exception as exc:
            self.add_event("Arquivo", f"Nao foi possivel salvar carteira: {exc}")

    def portfolio_number(self, key):
        variable = self.portfolio_inputs.get(key)
        raw = variable.get() if variable else self.portfolio.get(key)
        if isinstance(raw, str):
            raw = raw.strip().replace(".", "").replace(",", ".") if "," in raw else raw.strip()
        return self.to_float(raw)

    def save_alerts(self):
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            ALERTS_FILE.write_text(json.dumps(self.alerts, indent=2), encoding="utf-8")
        except Exception as exc:
            self.add_event("Arquivo", f"Nao foi possivel salvar alertas: {exc}")

    @staticmethod
    def with_totals(rows):
        total = 0
        output = []
        for price, amount in rows:
            total += amount
            output.append((price, amount, total))
        return output

    @staticmethod
    def parse_candle_rows(rows):
        return [
            {
                "time": row[0],
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
            for row in rows
        ]

    @staticmethod
    def xml_text(element, name):
        direct = element.findtext(name)
        if direct:
            return direct
        for child in list(element):
            local_name = child.tag.split("}")[-1]
            if local_name == name and child.text:
                return child.text
        return ""

    @staticmethod
    def xml_link(element):
        direct = element.findtext("link")
        if direct:
            return direct
        for child in list(element):
            local_name = child.tag.split("}")[-1]
            if local_name == "link":
                href = child.attrib.get("href")
                if href:
                    return href
                if child.text:
                    return child.text
            if local_name == "guid" and child.text:
                return child.text
        return ""

    @staticmethod
    def clean_html(value):
        text = re.sub(r"<[^>]+>", " ", value or "")
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def parse_date(value):
        if not value:
            return None
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed
        except Exception:
            pass
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = dt.datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed
        except Exception:
            return None

    @staticmethod
    def format_news_date(value):
        if not value:
            return "sem data"
        local_value = value.astimezone()
        return local_value.strftime("%d/%m/%Y %H:%M")

    @staticmethod
    def open_link(link):
        if link:
            webbrowser.open(link)

    @staticmethod
    def to_float(value):
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None


class LabelButton(Label):
    def __init__(self, parent, text, command, bg, fg, active_bg, border):
        super().__init__(
            parent,
            text=text,
            bg=bg,
            fg=fg,
            padx=13,
            pady=8,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=border,
        )
        self.command = command
        self.normal_bg = bg
        self.active_bg = active_bg
        self.enabled = True
        self.bind("<Button-1>", self.on_click)
        self.bind("<Enter>", lambda _event: self.configure(bg=self.active_bg) if self.enabled else None)
        self.bind("<Leave>", lambda _event: self.configure(bg=self.normal_bg) if self.enabled else None)

    def on_click(self, _event):
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.configure(fg=COLORS["text"] if enabled else COLORS["dim"])


if __name__ == "__main__":
    app = BitcoinMonitorApp()
    app.mainloop()
