"use strict";

/* ---------- Configuración ---------- */
const DEBUG = false;
const STALE_MS = 30000;      // ajustalo al intervalo de envío del ESP32
const HISTORY_POINTS = 120;  // puntos guardados para cada gráfico
const TREND_WINDOW = 30;     // mediciones usadas para calcular la tendencia
const LAST_URL = "/api/ultimo"; // opcional: devuelve el último JSON conocido

const protocol = location.protocol === "https:" ? "wss:" : "ws:";
const WS_URL = `${protocol}//${location.host}/ws/clima`;

const GROUPS = {
  temp: { title: "Temperatura", color: "#ea580c" },
  atm:  { title: "Atmósfera",   color: "#0891b2" },
  dev:  { title: "Dispositivo", color: "#7c3aed" }
};

// k: clave del JSON, d: decimales, th: umbral de tendencia
const FIELDS = [
  { k: "t_dht", l: "Temp. DHT22", u: "°C", d: 1, g: "temp", th: 0.3 },
  { k: "t_bmp", l: "Temp. BMP280", u: "°C", d: 1, g: "temp", th: 0.3 },
  { k: "sensacion_termica", l: "Sensación térmica", u: "°C", d: 1, g: "temp", th: 0.3,
    tip: "Estimación que combina temperatura y humedad; sin dato de viento es aproximada." },
  { k: "punto_rocio", l: "Punto de rocío", u: "°C", d: 1, g: "temp", th: 0.3 },
  { k: "humedad", l: "Humedad", u: "%", d: 1, g: "atm", th: 1 },
  { k: "presion", l: "Presión atmosférica", u: "hPa", d: 1, g: "atm", th: 0.5 },
  { k: "altitud", l: "Altitud", u: "m", d: 1, g: "atm", th: 2,
    tip: "Calculada con la presión: varía con el clima aunque el sensor no se mueva." },
  { k: "rssi", l: "Señal Wi-Fi (ESP32)", u: "dBm", d: 0, g: "dev", th: 3, quality: true }
];

/* ---------- Estado ---------- */
const $ = id => document.getElementById(id);
const dot = $("dot"), statusText = $("status-text"), lastUpdate = $("last-update");
const dashboard = $("dashboard");
const history = {};
let ws = null, reconnectTimer = null, attempts = 0, lastMessageAt = 0;
const log = (...a) => DEBUG && console.log(...a);

/* ---------- Construcción de la interfaz ---------- */
function buildDashboard() {
  for (const [gid, g] of Object.entries(GROUPS)) {
    const section = document.createElement("section");
    section.className = "group";
    section.style.setProperty("--c", g.color);
    section.setAttribute("aria-label", g.title);
    const cards = FIELDS.filter(f => f.g === gid).map(f => `
      <article class="card" data-card="${f.k}">
        <div class="card-title">
          <span ${f.tip ? `title="${f.tip}"` : ""}>${f.l}</span>
        </div>
        <div class="card-value">
          <span class="val" data-field="${f.k}">--</span>
          <span class="unit">${f.u}</span>
          <span class="trend" data-trend="${f.k}" aria-hidden="true"></span>
        </div>
        <svg class="spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
          <polyline data-spark="${f.k}" points=""></polyline>
        </svg>
        <div class="range" data-range="${f.k}"></div>
      </article>`).join("");
    section.innerHTML = `<h2>${g.title}</h2><div class="grid">${cards}</div>`;
    dashboard.appendChild(section);
  }
}

/* ---------- Utilidades ---------- */
function formatNumber(value, decimals = 1) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(decimals) : "--";
}

function rssiQuality(v) {
  if (v >= -60) return ["Excelente", "q-excelente"];
  if (v >= -70) return ["Buena", "q-buena"];
  if (v >= -80) return ["Regular", "q-regular"];
  return ["Débil", "q-debil"];
}

// Acepta segundos, milisegundos o texto ISO
function parseTimestamp(ts) {
  if (ts === undefined || ts === null) return new Date();
  const d = typeof ts === "number" ? new Date(ts < 1e12 ? ts * 1000 : ts) : new Date(ts);
  return isNaN(d) ? new Date() : d;
}

/* Mín/máx del día, guardados en el navegador (con tolerancia a fallos) */
const todayKey = () => new Date().toLocaleDateString("es-AR");
let extremes = { day: todayKey(), v: {} };
try {
  const saved = JSON.parse(localStorage.getItem("clima-extremos"));
  if (saved && saved.day === todayKey()) extremes = saved;
} catch (e) { /* sin almacenamiento disponible */ }

function updateExtremes(k, n) {
  if (extremes.day !== todayKey()) extremes = { day: todayKey(), v: {} };
  const e = extremes.v[k] || (extremes.v[k] = { min: n, max: n });
  e.min = Math.min(e.min, n);
  e.max = Math.max(e.max, n);
  try { localStorage.setItem("clima-extremos", JSON.stringify(extremes)); } catch (err) {}
  return e;
}

function drawSpark(k) {
  const h = history[k];
  const el = document.querySelector(`[data-spark="${k}"]`);
  if (!el || h.length < 2) return;
  const min = Math.min(...h), max = Math.max(...h), span = max - min || 1;
  el.setAttribute("points", h.map((v, i) =>
    `${(i / (h.length - 1) * 100).toFixed(1)},${(27 - (v - min) / span * 24).toFixed(1)}`).join(" "));
}

function drawTrend(f) {
  const h = history[f.k];
  const el = document.querySelector(`[data-trend="${f.k}"]`);
  if (!el || h.length < 5) return;
  const diff = h[h.length - 1] - h[Math.max(0, h.length - TREND_WINDOW)];
  const [arrow, cls] = diff > f.th ? ["↑", "up"] : diff < -f.th ? ["↓", "down"] : ["→", ""];
  el.textContent = arrow;
  el.className = "trend " + cls;
}

function flash(card) {
  card.classList.remove("flash");
  void card.offsetWidth; // reinicia la animación
  card.classList.add("flash");
}

/* ---------- Actualización ---------- */
function updateInterface(data) {
  log("[INTERFAZ]", data);
  let any = false;

  for (const f of FIELDS) {
    if (data[f.k] === undefined) continue;
    const n = Number(data[f.k]);
    if (!Number.isFinite(n)) continue;
    any = true;

    const valEl = document.querySelector(`[data-field="${f.k}"]`);
    const text = formatNumber(n, f.d);
    if (valEl.textContent !== text) flash(valEl.closest(".card"));
    valEl.textContent = text;

    const h = history[f.k] || (history[f.k] = []);
    h.push(n);
    if (h.length > HISTORY_POINTS) h.shift();
    drawSpark(f.k);
    drawTrend(f);

    const rangeEl = document.querySelector(`[data-range="${f.k}"]`);
    if (f.quality) {
      const [label, cls] = rssiQuality(n);
      rangeEl.innerHTML = `Calidad: <span class="${cls}">${label}</span>`;
    } else {
      const e = updateExtremes(f.k, n);
      rangeEl.textContent = `Hoy: mín ${formatNumber(e.min, f.d)} / máx ${formatNumber(e.max, f.d)}`;
    }
  }

  if (!any) return;
  dashboard.classList.remove("loading");
  lastMessageAt = Date.now();
  lastUpdate.textContent = parseTimestamp(data.timestamp).toLocaleTimeString("es-AR");
  setStatus();
}

/* ---------- Estado de conexión y datos viejos ---------- */
function setStatus() {
  const open = ws && ws.readyState === WebSocket.OPEN;
  const stale = lastMessageAt && Date.now() - lastMessageAt > STALE_MS;
  dot.classList.toggle("connected", open && !stale);
  dot.classList.toggle("stale", open && !!stale);
  if (open) statusText.textContent = stale ? "Sin datos recientes" : "En vivo";
}
setInterval(setStatus, 1000);

/* ---------- WebSocket ---------- */
function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  log("[WebSocket] Conectando a", WS_URL);
  statusText.textContent = "Conectando...";
  ws = new WebSocket(WS_URL);

  ws.onopen = () => { attempts = 0; setStatus(); };

  ws.onmessage = event => {
    try { updateInterface(JSON.parse(event.data)); }
    catch (error) { console.error("[WebSocket] JSON inválido:", error); }
  };

  ws.onclose = () => {
    dot.classList.remove("connected", "stale");
    statusText.textContent = "Reconectando...";
    scheduleReconnect();
  };

  ws.onerror = error => console.error("[WebSocket] Error:", error);
}

// Backoff exponencial: 3 s, 6 s, 12 s... hasta 30 s
function scheduleReconnect() {
  if (reconnectTimer !== null) return;
  const delay = Math.min(3000 * 2 ** attempts++, 30000);
  reconnectTimer = setTimeout(() => { reconnectTimer = null; connect(); }, delay);
}

// Al volver a la pestaña, reconecta sin esperar
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") return;
  if (!ws || ws.readyState === WebSocket.CLOSED) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
    connect();
  }
});

/* ---------- Inicio ---------- */
buildDashboard();

// Muestra el último dato conocido al instante (si el backend lo ofrece)
fetch(LAST_URL).then(r => r.ok ? r.json() : null).then(d => d && updateInterface(d)).catch(() => {});

connect();