import base64
import concurrent.futures
import datetime as dt
import email.utils
import hashlib
import html
import json
import math
import os
import queue
import re
import shutil
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
APP_VERSION = "0.2.0"
APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "BitcoinMonitor"
ALERTS_FILE = APP_DIR / "alerts.json"
UPDATE_CONFIG_FILE = APP_DIR / "update_config.json"
DEFAULT_UPDATE_MANIFEST_URL = "https://api.github.com/repos/RayakuzaxD/bitcoin-monitor/contents/release/update_manifest.json?ref=main"

ENDPOINTS = {
    "coingecko": (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin&vs_currencies=usd,brl"
        "&include_market_cap=true&include_24hr_vol=true&include_24hr_change=true"
    ),
    "binance_ticker": "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT",
    "candles": "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={interval}&limit=180",
    "weekly_candles": "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1w&limit=500",
    "monthly_candles": "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1M&limit=240",
    "depth": "https://api.binance.com/api/v3/depth?symbol=BTCUSDT&limit=20",
    "fees": "https://mempool.space/api/v1/fees/recommended",
    "mempool": "https://mempool.space/api/mempool",
    "tip_height": "https://mempool.space/api/blocks/tip/height",
    "difficulty": "https://mempool.space/api/v1/difficulty-adjustment",
    "fear_greed": "https://api.alternative.me/fng/?limit=1",
}

NEWS_FEEDS = [
    ("Cointelegraph BR", "https://cointelegraph.com.br/rss/tag/bitcoin"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"),
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
}


def fetch_json(url, timeout=10):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "BitcoinMonitor/1.0 (+https://localhost)",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8-sig")
        return json.loads(payload)


def fetch_text(url, timeout=10):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "BitcoinMonitor/1.0 (+https://localhost)"},
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


def download_file(url, destination, timeout=60):
    request = urllib.request.Request(url, headers={"User-Agent": "BitcoinMonitor/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        with open(destination, "wb") as file:
            shutil.copyfileobj(response, file)


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


def format_percent(value):
    if value is None or not math.isfinite(value):
        return "--"
    sign = "+" if value > 0 else ""
    return f"{sign}{format_number(value, 2)}%"


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


def calculate_indicators(candles):
    closes = [item["close"] for item in candles]
    volumes = [item["volume"] for item in candles]
    if not closes:
        return {}

    ma50 = sma(closes, 50)
    ma100 = sma(closes, 100)
    ma200 = sma(closes, 200)
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

    return {
        "last_close": last,
        "ma50": ma50,
        "ma100": ma100,
        "ma200": ma200,
        "distance_ma200": distance_ma200,
        "bb_upper": upper,
        "bb_basis": basis,
        "bb_lower": lower,
        "rsi14": rsi_value(closes),
        "macd": macd,
        "macd_signal": signal,
        "macd_histogram": histogram,
        "volume": volumes[-1],
        "volume_change": volume_change,
    }


class BitcoinMonitorApp(Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1280x820")
        self.minsize(1020, 680)
        self.configure(bg=COLORS["bg"])

        self.data_queue = queue.Queue()
        self.fetch_lock = threading.Lock()
        self.fetching = False
        self.interval = StringVar(value="1m")
        self.indicator_period = StringVar(value="Semanal")
        self.indicator_layers = {
            "ma50": BooleanVar(value=True),
            "ma100": BooleanVar(value=True),
            "ma200": BooleanVar(value=True),
            "bollinger": BooleanVar(value=True),
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
        self.indicator_candles = {"Semanal": [], "Mensal": []}
        self.depth = {"asks": [], "bids": []}
        self.events = []
        self.news_items = []
        self.news_links = {}
        self.indicator_chart_state = {}
        self.alerts = self.load_alerts()
        self.value_vars = {}
        self.indicator_vars = {}

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
        news_tab = Frame(self.notebook, bg=COLORS["bg"])
        update_tab = Frame(self.notebook, bg=COLORS["bg"])
        self.notebook.add(dashboard_tab, text="Painel")
        self.notebook.add(indicators_tab, text="Indicadores")
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
            values=["Semanal", "Mensal"],
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
        for text, key in [
            ("MM50", "ma50"),
            ("MM100", "ma100"),
            ("MM200", "ma200"),
            ("Bollinger", "bollinger"),
            ("Volume", "volume"),
        ]:
            self.make_check(layers_bar, text, self.indicator_layers[key], self.draw_indicator_chart).pack(
                side=LEFT, padx=(0, 10)
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

        self.indicator_signal_text = self.make_text(side_panel, height=9, font=("Segoe UI", 9))
        self.indicator_signal_text.pack(fill=BOTH, expand=True, pady=(10, 0))

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

    def fetch_worker(self, interval):
        data = {"_kind": "market", "errors": []}
        jobs = {
            "coingecko": (fetch_json, ENDPOINTS["coingecko"]),
            "binance_ticker": (fetch_json, ENDPOINTS["binance_ticker"]),
            "candles": (fetch_json, ENDPOINTS["candles"].format(interval=interval)),
            "weekly_candles": (fetch_json, ENDPOINTS["weekly_candles"]),
            "monthly_candles": (fetch_json, ENDPOINTS["monthly_candles"]),
            "depth": (fetch_json, ENDPOINTS["depth"]),
            "fees": (fetch_json, ENDPOINTS["fees"]),
            "mempool": (fetch_json, ENDPOINTS["mempool"]),
            "tip_height": (fetch_text, ENDPOINTS["tip_height"]),
            "difficulty": (fetch_json, ENDPOINTS["difficulty"]),
            "fear_greed": (fetch_json, ENDPOINTS["fear_greed"]),
        }

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(function, url): name
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
        self.data_queue.put({"_kind": "news", "items": sorted_items[:40], "errors": errors})

    def parse_news_feed(self, source, feed_text):
        root = ET.fromstring(feed_text)
        items = []
        for item in root.findall(".//item"):
            title = self.xml_text(item, "title")
            link = self.xml_text(item, "link") or self.xml_text(item, "guid")
            description = self.clean_html(self.xml_text(item, "description"))
            published = self.parse_date(
                self.xml_text(item, "pubDate")
                or self.xml_text(item, "published")
                or self.xml_text(item, "updated")
                or self.xml_text(item, "date")
            )
            haystack = f"{title} {description}".lower()
            if "bitcoin" not in haystack and "btc" not in haystack:
                continue
            items.append(
                {
                    "source": source,
                    "title": title.strip() or "Sem titulo",
                    "link": link.strip(),
                    "summary": description[:260],
                    "published": published,
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
        self.apply_indicator_candles(payload.get("weekly_candles"), payload.get("monthly_candles"))
        self.apply_depth(payload.get("depth"))
        self.apply_network(payload)
        self.apply_fear_greed(payload.get("fear_greed"))

        if not errors:
            self.set_status("Dados sincronizados", "online")
        elif len(errors) < 5:
            self.set_status("Dados parciais", "neutral")
            self.add_event("Dados", f"{len(errors)} fonte(s) falharam nesta atualizacao.")
        else:
            self.set_status("Fontes indisponiveis", "offline")
            self.add_event("Dados", "Nao foi possivel atualizar as fontes publicas agora.")

        self.value_vars["last_update"].set(time.strftime("%H:%M:%S"))
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
        ticker = payload.get("binance_ticker", {})

        price_usd = self.to_float(coingecko.get("usd")) or self.to_float(ticker.get("lastPrice"))
        price_brl = self.to_float(coingecko.get("brl"))
        change = self.to_float(coingecko.get("usd_24h_change")) or self.to_float(
            ticker.get("priceChangePercent")
        )
        volume = self.to_float(coingecko.get("usd_24h_vol")) or self.to_float(ticker.get("quoteVolume"))
        market_cap = self.to_float(coingecko.get("usd_market_cap"))

        self.metrics.update(
            {
                "price_usd": price_usd,
                "price_brl": price_brl,
                "change_24h": change,
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

    def apply_indicator_candles(self, weekly_rows, monthly_rows):
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
            vmb = self.to_float(mempool.get("vsize")) / 1_000_000
            count = self.to_float(mempool.get("count"))
            self.metrics["mempool_vmb"] = vmb
            self.value_vars["mempool_vmb"].set(f"{format_number(vmb, 1)} vMB")
            self.value_vars["mempool_count"].set(format_number(count, 0))
            self.draw_mempool_bar(vmb)

        if tip_height:
            self.value_vars["block_height"].set(f"{int(tip_height):,}".replace(",", "."))

        if difficulty:
            change = self.to_float(difficulty.get("difficultyChange"))
            self.value_vars["difficulty_change"].set(format_percent(change))

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

        self.write_indicator_signals(self.build_indicator_signals(snapshot, period))
        self.draw_indicator_chart()

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

        show_volume = self.indicator_layers["volume"].get()
        left, right, top = 58, 18, 18
        bottom = 88 if show_volume else 30
        volume_top = height - 62 if show_volume else height - bottom
        plot_h = volume_top - top - 12
        plot_w = width - left - right
        max_price = max(highs + [item for item in bb_upper if item is not None])
        min_price = min(lows + [item for item in bb_lower if item is not None])
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
        if self.indicator_layers["bollinger"].get():
            self.draw_series_line(canvas, bb_upper, left, step, to_y, "#ff9188", "BB sup")
            self.draw_series_line(canvas, bb_lower, left, step, to_y, "#ff9188", "BB inf")

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
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "bb_basis": bb_basis,
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
            ("BB sup", "bb_upper"),
            ("BB inf", "bb_lower"),
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
