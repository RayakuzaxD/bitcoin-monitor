const ENDPOINTS = {
  coingecko:
    "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd,brl&include_market_cap=true&include_24hr_vol=true&include_24hr_change=true",
  candles: (interval) =>
    `https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=${interval}&limit=240`,
  depth: "https://api.binance.com/api/v3/depth?symbol=BTCUSDT&limit=20",
  fees: "https://mempool.space/api/v1/fees/recommended",
  mempool: "https://mempool.space/api/mempool",
  tipHeight: "https://mempool.space/api/blocks/tip/height",
  difficulty: "https://mempool.space/api/v1/difficulty-adjustment",
  fearGreed: "https://api.alternative.me/fng/?limit=1",
  wsTicker: "wss://stream.binance.com:9443/ws/btcusdt@ticker",
};

const state = {
  interval: "1m",
  chart: null,
  candleSeries: null,
  resizeObserver: null,
  socket: null,
  reconnectTimer: null,
  metrics: {
    priceUsd: null,
    priceBrl: null,
    change24h: null,
    feeFastest: null,
    mempoolVmb: null,
  },
  alerts: loadAlerts(),
  events: [],
};

const els = {
  connectionPill: document.querySelector("#connection-pill"),
  connectionLabel: document.querySelector("#connection-label"),
  refreshButton: document.querySelector("#refresh-button"),
  notificationButton: document.querySelector("#notification-button"),
  btcUsd: document.querySelector("#btc-usd"),
  btcBrl: document.querySelector("#btc-brl"),
  btcChange: document.querySelector("#btc-change"),
  volume24h: document.querySelector("#volume-24h"),
  marketCap: document.querySelector("#market-cap"),
  spread: document.querySelector("#spread"),
  lastUpdated: document.querySelector("#last-updated"),
  dataQuality: document.querySelector("#data-quality"),
  fearGreed: document.querySelector("#fear-greed"),
  fastFee: document.querySelector("#fast-fee"),
  blockHeight: document.querySelector("#block-height"),
  mempoolSize: document.querySelector("#mempool-size"),
  priceChart: document.querySelector("#price-chart"),
  fallbackChart: document.querySelector("#fallback-chart"),
  chartEmpty: document.querySelector("#chart-empty"),
  asks: document.querySelector("#asks"),
  bids: document.querySelector("#bids"),
  midPrice: document.querySelector("#mid-price"),
  bookStatus: document.querySelector("#book-status"),
  economyFee: document.querySelector("#economy-fee"),
  hourFee: document.querySelector("#hour-fee"),
  mempoolCount: document.querySelector("#mempool-count"),
  difficultyChange: document.querySelector("#difficulty-change"),
  mempoolBar: document.querySelector("#mempool-bar"),
  alertForm: document.querySelector("#alert-form"),
  alertMetric: document.querySelector("#alert-metric"),
  alertOperator: document.querySelector("#alert-operator"),
  alertValue: document.querySelector("#alert-value"),
  activeAlerts: document.querySelector("#active-alerts"),
  clearAlerts: document.querySelector("#clear-alerts"),
  eventFeed: document.querySelector("#event-feed"),
};

document.addEventListener("DOMContentLoaded", init);

function init() {
  if (window.lucide) {
    window.lucide.createIcons();
  }

  initChart();
  bindEvents();
  renderAlerts();
  addEvent("Sistema", "Monitor iniciado. Coletando dados públicos.");
  refreshAll();
  connectTicker();

  window.setInterval(refreshAll, 45_000);
}

function bindEvents() {
  els.refreshButton.addEventListener("click", refreshAll);

  document.querySelectorAll("[data-interval]").forEach((button) => {
    button.addEventListener("click", () => {
      state.interval = button.dataset.interval;
      document
        .querySelectorAll("[data-interval]")
        .forEach((item) => item.classList.toggle("active", item === button));
      loadCandles();
    });
  });

  els.notificationButton.addEventListener("click", requestNotifications);

  els.alertForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = Number(els.alertValue.value);

    if (!Number.isFinite(value)) {
      return;
    }

    state.alerts.unshift({
      id: crypto.randomUUID(),
      metric: els.alertMetric.value,
      operator: els.alertOperator.value,
      value,
      createdAt: Date.now(),
      triggeredAt: null,
    });

    els.alertValue.value = "";
    persistAlerts();
    renderAlerts();
    addEvent("Alerta", "Novo alerta local criado.");
  });

  els.clearAlerts.addEventListener("click", () => {
    state.alerts = [];
    persistAlerts();
    renderAlerts();
    addEvent("Alerta", "Alertas locais removidos.");
  });
}

function initChart() {
  if (!window.LightweightCharts) {
    return;
  }

  const chart = window.LightweightCharts.createChart(els.priceChart, {
    autoSize: true,
    layout: {
      background: { color: "#0f0e0b" },
      textColor: "#a99f90",
      fontFamily:
        "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
    },
    grid: {
      vertLines: { color: "rgba(255,255,255,0.045)" },
      horzLines: { color: "rgba(255,255,255,0.045)" },
    },
    crosshair: { mode: window.LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: {
      borderColor: "rgba(255,255,255,0.1)",
    },
    timeScale: {
      borderColor: "rgba(255,255,255,0.1)",
      timeVisible: true,
      secondsVisible: false,
    },
  });

  const candleSeries = chart.addCandlestickSeries({
    upColor: "#35c46b",
    downColor: "#ee5d50",
    borderUpColor: "#35c46b",
    borderDownColor: "#ee5d50",
    wickUpColor: "#35c46b",
    wickDownColor: "#ee5d50",
  });

  state.chart = chart;
  state.candleSeries = candleSeries;
}

async function refreshAll() {
  setQuality("neutral", "Atualizando");

  const jobs = [
    loadMarketSummary(),
    loadCandles(),
    loadOrderBook(),
    loadNetwork(),
    loadFearGreed(),
  ];

  const results = await Promise.allSettled(jobs);
  const failures = results.filter((result) => result.status === "rejected");

  if (failures.length === 0) {
    setQuality("positive", "Dados sincronizados");
  } else if (failures.length < results.length) {
    setQuality("neutral", "Dados parciais");
    addEvent("Dados", `${failures.length} fonte(s) falharam nesta atualização.`);
  } else {
    setQuality("negative", "Fontes indisponíveis");
    addEvent("Dados", "Não foi possível atualizar as fontes públicas agora.");
  }

  updateLastUpdated();
  checkAlerts();
}

async function loadMarketSummary() {
  const data = await fetchJson(ENDPOINTS.coingecko);
  const bitcoin = data.bitcoin;

  state.metrics.priceUsd = bitcoin.usd;
  state.metrics.priceBrl = bitcoin.brl;
  state.metrics.change24h = bitcoin.usd_24h_change;

  els.btcUsd.textContent = formatCurrency(bitcoin.usd, "USD");
  els.btcBrl.textContent = formatCurrency(bitcoin.brl, "BRL");
  els.volume24h.textContent = formatCompactCurrency(bitcoin.usd_24h_vol, "USD");
  els.marketCap.textContent = formatCompactCurrency(bitcoin.usd_market_cap, "USD");
  renderChange(bitcoin.usd_24h_change);
}

async function loadCandles() {
  const rows = await fetchJson(ENDPOINTS.candles(state.interval));
  const candles = rows.map((row) => ({
    time: Math.floor(row[0] / 1000),
    open: Number(row[1]),
    high: Number(row[2]),
    low: Number(row[3]),
    close: Number(row[4]),
  }));

  if (state.candleSeries) {
    els.chartEmpty.style.display = "none";
    els.fallbackChart.style.display = "none";
    state.candleSeries.setData(candles);
    state.chart.timeScale().fitContent();
  } else {
    renderFallbackChart(candles);
  }
}

async function loadOrderBook() {
  const data = await fetchJson(ENDPOINTS.depth);
  const asks = data.asks.slice(0, 8).map(([price, amount]) => [Number(price), Number(amount)]);
  const bids = data.bids.slice(0, 8).map(([price, amount]) => [Number(price), Number(amount)]);
  const bestAsk = asks[0]?.[0];
  const bestBid = bids[0]?.[0];

  if (bestAsk && bestBid) {
    const spread = bestAsk - bestBid;
    const mid = (bestAsk + bestBid) / 2;
    els.spread.textContent = `${formatCurrency(spread, "USD")} (${((spread / mid) * 100).toFixed(4)}%)`;
    els.midPrice.textContent = formatCurrency(mid, "USD");
  }

  renderBookSide(els.asks, asks, "ask");
  renderBookSide(els.bids, bids, "bid");
  els.bookStatus.textContent = `${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
}

async function loadNetwork() {
  const [fees, mempool, tipHeight, difficulty] = await Promise.all([
    fetchJson(ENDPOINTS.fees),
    fetchJson(ENDPOINTS.mempool),
    fetchText(ENDPOINTS.tipHeight),
    fetchJson(ENDPOINTS.difficulty),
  ]);

  const vmb = mempool.vsize / 1_000_000;
  state.metrics.feeFastest = fees.fastestFee;
  state.metrics.mempoolVmb = vmb;

  els.fastFee.textContent = `${fees.fastestFee} sat/vB`;
  els.economyFee.textContent = `${fees.economyFee} sat/vB`;
  els.hourFee.textContent = `${fees.hourFee} sat/vB`;
  els.blockHeight.textContent = Number(tipHeight).toLocaleString("pt-BR");
  els.mempoolSize.textContent = `${vmb.toFixed(1)} vMB`;
  els.mempoolCount.textContent = mempool.count.toLocaleString("pt-BR");
  els.difficultyChange.textContent = formatSignedPercent(difficulty.difficultyChange);
  els.mempoolBar.style.width = `${Math.min(100, Math.round((vmb / 300) * 100))}%`;
}

async function loadFearGreed() {
  const data = await fetchJson(ENDPOINTS.fearGreed);
  const current = data.data?.[0];

  if (!current) {
    return;
  }

  els.fearGreed.textContent = `${current.value} - ${translateFearGreed(current.value_classification)}`;
}

function connectTicker() {
  clearTimeout(state.reconnectTimer);

  try {
    state.socket = new WebSocket(ENDPOINTS.wsTicker);
  } catch (error) {
    setConnection("offline", "WebSocket indisponível");
    return;
  }

  state.socket.addEventListener("open", () => {
    setConnection("online", "Tempo real ativo");
    addEvent("WebSocket", "Ticker BTCUSDT conectado.");
  });

  state.socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    const price = Number(payload.c);
    const change = Number(payload.P);

    state.metrics.priceUsd = price;
    state.metrics.change24h = change;
    els.btcUsd.textContent = formatCurrency(price, "USD");
    renderChange(change);
    checkAlerts();
  });

  state.socket.addEventListener("close", () => {
    setConnection("offline", "Reconectando");
    state.reconnectTimer = window.setTimeout(connectTicker, 3500);
  });

  state.socket.addEventListener("error", () => {
    setConnection("offline", "Erro no tempo real");
  });
}

function renderBookSide(container, rows, side) {
  const maxTotal = rows.reduce((sum, [, amount]) => sum + amount, 0) || 1;
  let runningTotal = 0;

  container.innerHTML = rows
    .map(([price, amount]) => {
      runningTotal += amount;
      const depth = Math.max(6, Math.min(100, (runningTotal / maxTotal) * 100));
      return `
        <div class="book-row" style="--depth: ${depth}%">
          <span class="price">${formatNumber(price, 2)}</span>
          <span>${formatNumber(amount, 4)}</span>
          <span>${formatNumber(runningTotal, 4)}</span>
        </div>
      `;
    })
    .join("");

  container.classList.toggle("asks", side === "ask");
  container.classList.toggle("bids", side === "bid");
}

function renderChange(value) {
  els.btcChange.textContent = formatSignedPercent(value);
  els.btcChange.classList.toggle("positive", value > 0);
  els.btcChange.classList.toggle("negative", value < 0);
  els.btcChange.classList.toggle("neutral", !Number.isFinite(value) || value === 0);
}

function renderFallbackChart(candles) {
  const context = els.fallbackChart.getContext("2d");
  const width = els.fallbackChart.width;
  const height = els.fallbackChart.height;
  const padding = 28;
  const closes = candles.map((item) => item.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = max - min || 1;

  context.clearRect(0, 0, width, height);
  context.strokeStyle = "#35c46b";
  context.lineWidth = 3;
  context.beginPath();

  candles.forEach((item, index) => {
    const x = padding + (index / Math.max(1, candles.length - 1)) * (width - padding * 2);
    const y = height - padding - ((item.close - min) / span) * (height - padding * 2);

    if (index === 0) {
      context.moveTo(x, y);
    } else {
      context.lineTo(x, y);
    }
  });

  context.stroke();
  els.chartEmpty.style.display = "none";
  els.fallbackChart.style.display = "block";
}

function renderAlerts() {
  if (state.alerts.length === 0) {
    els.activeAlerts.innerHTML = '<div class="event-line">Nenhum alerta ativo.</div>';
    return;
  }

  els.activeAlerts.innerHTML = state.alerts
    .map(
      (alert) => `
        <div class="alert-line">
          <span>${metricLabel(alert.metric)} ${operatorLabel(alert.operator)} ${formatAlertValue(alert)}</span>
          <button type="button" title="Remover alerta" aria-label="Remover alerta" data-remove-alert="${alert.id}">
            <i data-lucide="x"></i>
          </button>
        </div>
      `,
    )
    .join("");

  els.activeAlerts.querySelectorAll("[data-remove-alert]").forEach((button) => {
    button.addEventListener("click", () => {
      state.alerts = state.alerts.filter((alert) => alert.id !== button.dataset.removeAlert);
      persistAlerts();
      renderAlerts();
    });
  });

  if (window.lucide) {
    window.lucide.createIcons();
  }
}

function checkAlerts() {
  state.alerts.forEach((alert) => {
    const currentValue = state.metrics[alert.metric];

    if (!Number.isFinite(currentValue)) {
      return;
    }

    const matched =
      alert.operator === "above" ? currentValue >= alert.value : currentValue <= alert.value;
    const canTrigger = !alert.triggeredAt || Date.now() - alert.triggeredAt > 30 * 60 * 1000;

    if (matched && canTrigger) {
      alert.triggeredAt = Date.now();
      const message = `${metricLabel(alert.metric)} ${operatorLabel(alert.operator)} ${formatAlertValue(alert)}. Atual: ${formatMetricValue(alert.metric, currentValue)}.`;
      addEvent("Alerta disparado", message);
      notify("Alerta Bitcoin Monitor", message);
    }
  });

  persistAlerts();
}

function addEvent(title, message) {
  state.events.unshift({ title, message, time: new Date() });
  state.events = state.events.slice(0, 8);
  els.eventFeed.innerHTML = state.events
    .map(
      (event) => `
        <div class="event-line">
          <strong>${event.title}</strong> ${event.message}
          <br />
          <span>${event.time.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
        </div>
      `,
    )
    .join("");
}

async function requestNotifications() {
  if (!("Notification" in window)) {
    addEvent("Notificações", "Este navegador não suporta notificações locais.");
    return;
  }

  const permission = await Notification.requestPermission();
  addEvent(
    "Notificações",
    permission === "granted" ? "Permissão concedida." : "Permissão não concedida.",
  );
}

function notify(title, body) {
  if ("Notification" in window && Notification.permission === "granted") {
    new Notification(title, { body });
  }
}

function setConnection(status, label) {
  els.connectionPill.classList.toggle("online", status === "online");
  els.connectionPill.classList.toggle("offline", status === "offline");
  els.connectionLabel.textContent = label;
}

function setQuality(status, label) {
  els.dataQuality.className = `quality ${status}`;
  els.dataQuality.textContent = label;
}

function updateLastUpdated() {
  els.lastUpdated.textContent = new Date().toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

async function fetchJson(url, timeoutMs = 9000) {
  const response = await fetchWithTimeout(url, timeoutMs);

  if (!response.ok) {
    throw new Error(`Falha HTTP ${response.status} em ${url}`);
  }

  return response.json();
}

async function fetchText(url, timeoutMs = 9000) {
  const response = await fetchWithTimeout(url, timeoutMs);

  if (!response.ok) {
    throw new Error(`Falha HTTP ${response.status} em ${url}`);
  }

  return response.text();
}

async function fetchWithTimeout(url, timeoutMs) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, { signal: controller.signal });
  } finally {
    window.clearTimeout(timeout);
  }
}

function loadAlerts() {
  try {
    return JSON.parse(localStorage.getItem("btc-monitor-alerts") || "[]");
  } catch {
    return [];
  }
}

function persistAlerts() {
  localStorage.setItem("btc-monitor-alerts", JSON.stringify(state.alerts));
}

function metricLabel(metric) {
  return (
    {
      priceUsd: "Preço USD",
      priceBrl: "Preço BRL",
      change24h: "Variação 24h",
      feeFastest: "Fee rápida",
      mempoolVmb: "Mempool",
    }[metric] || metric
  );
}

function operatorLabel(operator) {
  return operator === "above" ? "acima de" : "abaixo de";
}

function formatAlertValue(alert) {
  return formatMetricValue(alert.metric, alert.value);
}

function formatMetricValue(metric, value) {
  if (metric === "priceUsd") {
    return formatCurrency(value, "USD");
  }

  if (metric === "priceBrl") {
    return formatCurrency(value, "BRL");
  }

  if (metric === "change24h") {
    return `${formatNumber(value, 2)}%`;
  }

  if (metric === "feeFastest") {
    return `${formatNumber(value, 0)} sat/vB`;
  }

  if (metric === "mempoolVmb") {
    return `${formatNumber(value, 1)} vMB`;
  }

  return formatNumber(value, 2);
}

function translateFearGreed(value) {
  return (
    {
      "Extreme Fear": "Medo extremo",
      Fear: "Medo",
      Neutral: "Neutro",
      Greed: "Ganância",
      "Extreme Greed": "Ganância extrema",
    }[value] || value
  );
}

function formatCurrency(value, currency) {
  if (!Number.isFinite(value)) {
    return "--";
  }

  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency,
    maximumFractionDigits: currency === "USD" ? 2 : 0,
  }).format(value);
}

function formatCompactCurrency(value, currency) {
  if (!Number.isFinite(value)) {
    return "--";
  }

  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency,
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatNumber(value, digits = 2) {
  if (!Number.isFinite(value)) {
    return "--";
  }

  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function formatSignedPercent(value) {
  if (!Number.isFinite(value)) {
    return "--";
  }

  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value, 2)}%`;
}
