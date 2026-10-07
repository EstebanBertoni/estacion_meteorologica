// ============================================================
// ESTACIÓN METEOROLÓGICA IoT
// Cliente WebSocket
// ============================================================

let socket;


// ------------------------------------------------------------
// CONEXIÓN CON FASTAPI
// ------------------------------------------------------------

function conectarWebSocket() {

    const protocolo = window.location.protocol === "https:"
        ? "wss:"
        : "ws:";

    const url = `${protocolo}//${window.location.host}/ws/clima`;

    console.log("[WEBSOCKET] Conectando a:", url);

    socket = new WebSocket(url);


    // --------------------------------------------------------
    // CONEXIÓN ESTABLECIDA
    // --------------------------------------------------------

    socket.onopen = () => {

        console.log("[WEBSOCKET] Conectado correctamente");

        actualizarEstado("ONLINE");
    };


    // --------------------------------------------------------
    // RECEPCIÓN DE DATOS
    // --------------------------------------------------------

    socket.onmessage = (event) => {

        try {

            const datos = JSON.parse(event.data);

            console.log("[DATOS] Recibidos:", datos);

            actualizarDashboard(datos);

        } catch (error) {

            console.error(
                "[WEBSOCKET] Error procesando datos:",
                error
            );
        }
    };


    // --------------------------------------------------------
    // ERROR
    // --------------------------------------------------------

    socket.onerror = (error) => {

        console.error(
            "[WEBSOCKET] Error:",
            error
        );

        actualizarEstado("ERROR");
    };


    // --------------------------------------------------------
    // DESCONEXIÓN
    // --------------------------------------------------------

    socket.onclose = () => {

        console.warn(
            "[WEBSOCKET] Conexión cerrada"
        );

        actualizarEstado("OFFLINE");

        // Intentar reconectar después de 3 segundos
        setTimeout(conectarWebSocket, 3000);
    };
}


// ------------------------------------------------------------
// ACTUALIZAR DASHBOARD
// ------------------------------------------------------------

function actualizarDashboard(datos) {

    actualizarElemento(
        "t_dht",
        datos.t_dht,
        1,
        " °C"
    );

    actualizarElemento(
        "humedad",
        datos.humedad,
        1,
        " %"
    );

    actualizarElemento(
        "t_bmp",
        datos.t_bmp,
        1,
        " °C"
    );

    actualizarElemento(
        "presion",
        datos.presion,
        1,
        " hPa"
    );

    actualizarElemento(
        "altitud",
        datos.altitud,
        1,
        " m"
    );

    actualizarElemento(
        "punto_rocio",
        datos.punto_rocio,
        1,
        " °C"
    );

    actualizarElemento(
        "sensacion_termica",
        datos.sensacion_termica,
        1,
        " °C"
    );

    actualizarElemento(
        "vpd",
        datos.vpd,
        2,
        " kPa"
    );

    actualizarElemento(
        "humedad_absoluta",
        datos.humedad_absoluta,
        2,
        " g/m³"
    );

    actualizarElemento(
        "presion_nivel_mar",
        datos.presion_mar,
        1,
        " hPa"
    );

    actualizarElemento(
        "densidad_aire",
        datos.densidad_aire,
        3,
        " kg/m³"
    );

    actualizarElemento(
        "temperatura_bulbo_humedo",
        datos.bulbo_humedo,
        1,
        " °C"
    );

    actualizarElemento(
        "rssi",
        datos.rssi,
        0,
        " dBm"
    );


    // --------------------------------------------------------
    // TIMESTAMP
    // --------------------------------------------------------

    if (datos.timestamp) {

        const elemento = document.getElementById("timestamp");

        if (elemento) {

            elemento.textContent =
                formatearFecha(datos.timestamp);
        }
    }
}


// ------------------------------------------------------------
// ACTUALIZAR ELEMENTO HTML
// ------------------------------------------------------------

function actualizarElemento(
    id,
    valor,
    decimales = 1,
    unidad = ""
) {

    const elemento = document.getElementById(id);

    if (!elemento) {
        return;
    }

    if (
        valor === null ||
        valor === undefined ||
        Number.isNaN(Number(valor))
    ) {

        elemento.textContent = "--";

        return;
    }

    elemento.textContent =
        `${Number(valor).toFixed(decimales)}${unidad}`;
}


// ------------------------------------------------------------
// ESTADO DEL SISTEMA
// ------------------------------------------------------------

function actualizarEstado(estado) {

    const elemento =
        document.getElementById("estado");

    if (!elemento) {
        return;
    }

    elemento.textContent = estado;
}


// ------------------------------------------------------------
// FORMATEAR FECHA
// ------------------------------------------------------------

function formatearFecha(timestamp) {

    try {

        const fecha = new Date(timestamp);

        return fecha.toLocaleString(
            "es-AR",
            {
                dateStyle: "short",
                timeStyle: "medium"
            }
        );

    } catch (error) {

        return timestamp;
    }
}


// ------------------------------------------------------------
// INICIAR
// ------------------------------------------------------------

document.addEventListener(
    "DOMContentLoaded",
    () => {

        console.log(
            "[SYSTEM] Iniciando dashboard..."
        );

        conectarWebSocket();

    }
);