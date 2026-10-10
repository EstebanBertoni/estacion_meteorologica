// ============================================================
// ESTACIÓN METEOROLÓGICA IoT
// Cliente WebSocket — generación nueva (HTML dinámico)
//
// Arquitectura:
//   - El HTML define el esqueleto (header, #dashboard vacío, footer).
//   - Este script construye las tarjetas dinámicamente según las
//     definiciones de TARJETAS, y las actualiza con cada mensaje.
//   - Cada tarjeta muestra: valor, unidad, tendencia (vs. medición
//     anterior) y un mini-gráfico (sparkline) con el historial reciente.
// ============================================================

"use strict";

// ------------------------------------------------------------
// CONFIGURACIÓN
// ------------------------------------------------------------

// Si pasan más de 30 s sin datos (la cadencia normal es ~3 s),
// el estado pasa a DATOS DESACTUALIZADOS aunque el WebSocket siga vivo.
const STALE_MS = 30000;

// Muestras que guarda cada tarjeta para su sparkline.
const HISTORIA_MAX = 40;

// Intervalo de revisión del estado (stale/offline).
const CHECK_ESTADO_MS = 5000;

// ------------------------------------------------------------
// DEFINICIÓN DE TARJETAS
// Las claves deben coincidir con las que envía el backend.
// color: cualquier variable CSS de color definida en style.css.
// ------------------------------------------------------------

const TARJETAS = [
    { clave: "t_dht",              titulo: "Temperatura DHT22",  unidad: " °C",   decimales: 1, color: "var(--up)",     grupo: "Temperatura", ayuda: "Temperatura del sensor DHT22" },
    { clave: "t_bmp",              titulo: "Temperatura BMP180", unidad: " °C",   decimales: 1, color: "var(--up)",     grupo: "Temperatura", ayuda: "Temperatura del barómetro" },
    { clave: "sensacion_termica",  titulo: "Sensación térmica",  unidad: " °C",   decimales: 1, color: "var(--up)",     grupo: "Temperatura", ayuda: "Índice de calor sobre t_dht y humedad" },
    { clave: "bulbo_humedo",       titulo: "Bulbo húmedo",       unidad: " °C",   decimales: 1, color: "var(--up)",     grupo: "Temperatura", ayuda: "Aproximación de Stull (2011)" },
    { clave: "punto_rocio",        titulo: "Punto de rocío",     unidad: " °C",   decimales: 1, color: "var(--up)",     grupo: "Temperatura", ayuda: "Magnus: temperatura de saturación" },

    { clave: "humedad",            titulo: "Humedad relativa",   unidad: " %",    decimales: 1, color: "var(--down)",   grupo: "Humedad", ayuda: "HR del DHT22" },
    { clave: "humedad_absoluta",   titulo: "Humedad absoluta",   unidad: " g/m³", decimales: 2, color: "var(--down)",   grupo: "Humedad", ayuda: "Gramos de vapor por m³ de aire" },
    { clave: "vpd",                titulo: "VPD",                unidad: " kPa",  decimales: 2, color: "var(--down)",   grupo: "Humedad", ayuda: "Déficit de presión de vapor" },

    { clave: "presion",            titulo: "Presión",            unidad: " hPa",  decimales: 2, color: "var(--brand-2)", grupo: "Presión", ayuda: "Presión absoluta medida" },
    { clave: "presion_mar",        titulo: "Presión nivel mar",  unidad: " hPa",  decimales: 1, color: "var(--brand-2)", grupo: "Presión", ayuda: "Presión reducida a 0 m — comparable entre estaciones" },
    { clave: "altitud",            titulo: "Altitud",            unidad: " m",    decimales: 0, color: "var(--brand-2)", grupo: "Presión", ayuda: "Altitud fija de la estación (constante)" },
    { clave: "base_nubes",         titulo: "Base de nubes",      unidad: " m",    decimales: 0, color: "var(--brand-2)", grupo: "Presión", ayuda: "Altura estimada ≈ 125 m por °C de spread" },
    { clave: "densidad_aire",      titulo: "Densidad del aire",  unidad: " kg/m³", decimales: 3, color: "var(--brand-2)", grupo: "Presión", ayuda: "Aire húmedo: seco + vapor" },

    { clave: "rssi",               titulo: "RSSI Wi-Fi",         unidad: " dBm",  decimales: 0, color: "var(--brand-1)", grupo: "Conexión", ayuda: "Intensidad de señal (más cerca de 0 = mejor)" },
];

// Historial por clave para las sparklines.
const historiales = new Map();
TARJETAS.forEach(t => historiales.set(t.clave, []));

// Referencias a los elementos de valor, por clave.
const elementos = new Map();

let socket = null;
let ultimoDatoMs = 0;

// ------------------------------------------------------------
// CONSTRUCCIÓN DEL DASHBOARD
// ------------------------------------------------------------

function construirDashboard() {
    const main = document.getElementById("dashboard");
    if (!main) return;

    // Agrupar tarjetas por su campo "grupo", conservando el orden.
    const grupos = new Map();
    TARJETAS.forEach(t => {
        if (!grupos.has(t.grupo)) grupos.set(t.grupo, []);
        grupos.get(t.grupo).push(t);
    });

    grupos.forEach((tarjetas, nombreGrupo) => {
        const seccion = document.createElement("section");
        seccion.className = "group";
        seccion.style.setProperty("--c", tarjetas[0].color);

        const h2 = document.createElement("h2");
        h2.textContent = nombreGrupo;
        seccion.appendChild(h2);

        const grid = document.createElement("div");
        grid.className = "grid";

        tarjetas.forEach(def => grid.appendChild(crearTarjeta(def)));

        seccion.appendChild(grid);
        main.appendChild(seccion);
    });
}

function crearTarjeta(def) {
    const card = document.createElement("article");
    card.className = "card";
    card.style.setProperty("--c", def.color);

    // Título + tooltip con la explicación de la variable
    const titulo = document.createElement("div");
    titulo.className = "card-title";
    const texto = document.createElement("span");
    texto.textContent = def.titulo;
    const ayuda = document.createElement("span");
    ayuda.title = def.ayuda;
    ayuda.textContent = "ⓘ";
    titulo.append(texto, ayuda);

    // Valor (con clase .val para el shimmer del estado .loading)
    const valor = document.createElement("div");
    valor.className = "card-value";
    const val = document.createElement("span");
    val.className = "val";
    val.textContent = "--";
    const unit = document.createElement("span");
    unit.className = "unit";
    unit.textContent = def.unidad;
    valor.append(val, unit);

    // Tendencia (se llena con cada actualización)
    const trend = document.createElement("span");
    trend.className = "trend";

    // Sparkline: SVG con un polyline que se redibuja por muestra
    const spark = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    spark.setAttribute("class", "spark");
    spark.setAttribute("viewBox", "0 0 100 30");
    spark.setAttribute("preserveAspectRatio", "none");
    const polyline = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    spark.appendChild(polyline);

    card.append(titulo, valor, trend, spark);

    elementos.set(def.clave, { val, unit, trend, polyline, def, anterior: null });
    return card;
}

// ------------------------------------------------------------
// ACTUALIZACIÓN CON DATOS
// ------------------------------------------------------------

function actualizarDashboard(datos) {
    const ahora = Date.now();
    ultimoDatoMs = ahora;

    TARJETAS.forEach(def => {
        const el = elementos.get(def.clave);
        if (!el) return;

        const valor = datos[def.clave];
        actualizarValor(el, valor);
        actualizarTendencia(el, valor);
        actualizarSparkline(el, valor);
    });

    // Quitar el esqueleto de carga al primer dato real
    const main = document.getElementById("dashboard");
    if (main) main.classList.remove("loading");

    // Footer: última medición (timestamp de adquisición o recepción)
    const lastUpdate = document.getElementById("last-update");
    if (lastUpdate && datos.timestamp) {
        lastUpdate.textContent = formatearFecha(datos.timestamp);
    }
}

function actualizarValor(el, valor) {
    if (valor === null || valor === undefined || Number.isNaN(Number(valor))) {
        el.val.textContent = "--";
        return;
    }

    const texto = Number(valor).toFixed(el.def.decimales);
    if (el.val.textContent !== texto) {
        el.val.textContent = texto;
        el.val.classList.remove("flash");
        // Forzar reflow para que la animación se reinicie en cada cambio
        void el.val.offsetWidth;
        el.val.classList.add("flash");
    }
}

function actualizarTendencia(el, valor) {
    if (valor === null || valor === undefined) { el.trend.textContent = ""; return; }

    const actual = Number(valor);
    if (el.anterior === null || Number.isNaN(el.anterior)) {
        el.trend.textContent = "";
    } else if (actual > el.anterior) {
        el.trend.textContent = "▲";
        el.trend.className = "trend up";
    } else if (actual < el.anterior) {
        el.trend.textContent = "▼";
        el.trend.className = "trend down";
    } else {
        el.trend.textContent = "–";
        el.trend.className = "trend";
    }

    el.anterior = actual;
}

function actualizarSparkline(el, valor) {
    if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return;

    const historial = historiales.get(el.def.clave);
    historial.push(Number(valor));
    if (historial.length > HISTORIA_MAX) historial.shift();

    if (historial.length < 2) return;

    const min = Math.min(...historial);
    const max = Math.max(...historial);
    const rango = (max - min) || 1;   // si todos iguales, línea plana

    // Normalizar cada muestra a un punto dentro del viewBox 100x30
    const puntos = historial.map((v, i) => {
        const x = (i / (historial.length - 1)) * 100;
        const y = 28 - ((v - min) / rango) * 26;   // margen 2 px arriba/abajo
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");

    el.polyline.setAttribute("points", puntos);
}

// ------------------------------------------------------------
// ESTADO DE CONEXIÓN
// ONLINE (WebSocket vivo, datos frescos)
// DESACTUALIZADO (WebSocket vivo, sin datos nuevos)
// OFFLINE / ERROR (sin conexión)
// ------------------------------------------------------------

function establecerEstado(estado) {
    const texto = document.getElementById("status-text");
    const dot = document.getElementById("dot");
    if (!texto || !dot) return;

    texto.textContent = estado;

    dot.classList.remove("connected", "stale");
    if (estado === "ONLINE") dot.classList.add("connected");
    if (estado === "DATOS DESACTUALIZADOS") dot.classList.add("stale");
}

function revisarEstado() {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    if (ultimoDatoMs === 0) return;   // aún no llegó nada: no es "stale", es "esperando"

    const transcurrido = Date.now() - ultimoDatoMs;
    if (transcurrido > STALE_MS) {
        establecerEstado("DATOS DESACTUALIZADOS");
    } else {
        establecerEstado("ONLINE");
    }
}

// ------------------------------------------------------------
// CONEXIÓN WEBSOCKET
// ------------------------------------------------------------

function conectarWebSocket() {
    // URL relativa al origen: funciona en localhost y en producción
    // (http→ws, https→wss) sin hardcodear 127.0.0.1.
    const protocolo = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocolo}//${window.location.host}/ws/clima`;

    console.log("[WEBSOCKET] Conectando a:", url);
    socket = new WebSocket(url);

    socket.onopen = () => {
        console.log("[WEBSOCKET] Conectado");
        establecerEstado("ONLINE");
    };

    socket.onmessage = (event) => {
        try {
            const datos = JSON.parse(event.data);
            actualizarDashboard(datos);
            revisarEstado();
        } catch (error) {
            console.error("[WEBSOCKET] Error procesando datos:", error);
        }
    };

    socket.onerror = () => establecerEstado("ERROR");

    socket.onclose = () => {
        console.warn("[WEBSOCKET] Conexión cerrada — reintentando en 3 s");
        establecerEstado("OFFLINE");
        setTimeout(conectarWebSocket, 3000);
    };
}

// ------------------------------------------------------------
// UTILIDADES
// ------------------------------------------------------------

function formatearFecha(valor) {
    const fecha = new Date(valor);
    if (Number.isNaN(fecha.getTime())) return String(valor);

    return fecha.toLocaleString("es-AR", {
        dateStyle: "short",
        timeStyle: "medium",
    });
}

// ------------------------------------------------------------
// INICIO
// ------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    console.log("[SYSTEM] Iniciando dashboard...");
    construirDashboard();
    conectarWebSocket();
    setInterval(revisarEstado, CHECK_ESTADO_MS);
});
