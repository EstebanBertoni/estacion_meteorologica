import asyncio
import json
import math
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from funciones.database import (
    init_db,
    insertar_medicion,
    obtener_historial,
)
from funciones.metar import obtener_metar


# ============================================================
# CONFIGURACIÓN
# ============================================================

BROKER_IP = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPIC = "estacion/telemetria"

ALTURA_M = 90.0


# Tiempo de espera para reconectar MQTT
INTERVALO_RECONEXION_MQTT = 5


# ============================================================
# ESTADO GLOBAL DE LA ESTACIÓN
# ============================================================

# Estado inicial: None (no ceros). Un cero parecería una medición
# real de 0 °C; un None el dashboard lo muestra como "--".
latest_data = {
    "t_dht": None,
    "humedad": None,
    "t_bmp": None,
    "presion": None,
    "rssi": None,

    "altitud": None,
    "punto_rocio": None,
    "sensacion_termica": None,

    "humedad_absoluta": None,
    "vpd": None,
    "bulbo_humedo": None,
    "base_nubes": None,
    "presion_mar": None,
    "densidad_aire": None,

    "timestamp": None,
}


# ============================================================
# VARIABLES GLOBALES DE EJECUCIÓN
# ============================================================

main_loop = None

mqtt_queue = asyncio.Queue()


# ============================================================
# FUNCIONES METEOROLÓGICAS
# ============================================================

def calcular_altitud(presion_hpa, p0_hpa=1032.0):
    """
    Calcula una altitud aproximada a partir de la presión atmosférica.

    Args:
        presion_hpa (float): Presión atmosférica medida en hPa.
        p0_hpa (float): Presión de referencia.

    Returns:
        float: Altitud aproximada en metros.
    """

    if presion_hpa <= 0:
        return 0.0

    altitud = 44330.0 * (
        1.0 - (presion_hpa / p0_hpa) ** 0.1903
    )

    return round(altitud, 1)


def calcular_punto_rocio(temp_c, humedad_pct):
    """
    Calcula el punto de rocío mediante la aproximación de Magnus.

    Args:
        temp_c (float): Temperatura en °C.
        humedad_pct (float): Humedad relativa en %.

    Returns:
        float: Punto de rocío en °C.
    """

    if humedad_pct <= 0:
        return 0.0

    a = 17.27
    b = 237.7

    alpha = (
        (a * temp_c) / (b + temp_c)
        + math.log(humedad_pct / 100.0)
    )

    punto_rocio = (b * alpha) / (a - alpha)

    return round(punto_rocio, 1)


def calcular_sensacion_termica(temp_c, humedad_pct):
    """
    Calcula una aproximación de sensación térmica.

    Para temperaturas inferiores a 27 °C se utiliza
    una aproximación de Steadman.

    Para temperaturas superiores se utiliza
    la fórmula de Rothfusz del índice de calor.
    """

    if humedad_pct <= 0:
        return round(temp_c, 1)

    # Conversión a Fahrenheit
    temp_f = temp_c * 9 / 5 + 32

    # Aproximación para temperaturas moderadas
    if temp_c < 27:
        hi_f = (
            0.5
            * (
                temp_f
                + 61.0
                + ((temp_f - 68.0) * 1.2)
                + (humedad_pct * 0.094)
            )
        )

    else:
        h = humedad_pct

        hi_f = (
            -42.379
            + 2.04901523 * temp_f
            + 10.14333127 * h
            - 0.22475541 * temp_f * h
            - 0.00683783 * temp_f ** 2
            - 0.05481717 * h ** 2
            + 0.00122874 * temp_f ** 2 * h
            + 0.00085282 * temp_f * h ** 2
            - 0.00000199 * temp_f ** 2 * h ** 2
        )

    sensacion_c = (hi_f - 32) * 5 / 9

    return round(max(temp_c, sensacion_c), 1)


def presion_vapor_saturacion(temp_c):
    """
    Calcula la presión de vapor de saturación.

    Args:
        temp_c (float): Temperatura en °C.

    Returns:
        float: Presión de vapor de saturación en hPa.
    """

    return 6.112 * math.exp(
        (17.62 * temp_c) / (243.12 + temp_c)
    )


def presion_vapor(temp_c, humedad_pct):
    """
    Calcula la presión parcial de vapor de agua.
    """

    return (
        humedad_pct
        / 100.0
        * presion_vapor_saturacion(temp_c)
    )


def calcular_humedad_absoluta(temp_c, humedad_pct):
    """
    Calcula la humedad absoluta.

    Returns:
        float: g/m³
    """

    vapor = presion_vapor(temp_c, humedad_pct)

    return (
        216.7
        * vapor
        / (temp_c + 273.15)
    )


def calcular_vpd(temp_c, humedad_pct):
    """
    Calcula el déficit de presión de vapor (VPD).

    Returns:
        float: kPa
    """

    saturacion = presion_vapor_saturacion(temp_c)
    vapor = presion_vapor(temp_c, humedad_pct)

    return (saturacion - vapor) / 10


def calcular_presion_nivel_mar(presion_hpa, altura_m, temp_c):
    """
    Estima la presión atmosférica equivalente al nivel del mar.

    Returns:
        float: hPa
    """

    if presion_hpa <= 0:
        return 0.0

    denominador = (
        temp_c
        + 0.0065 * altura_m
        + 273.15
    )

    return (
        presion_hpa
        * (
            1
            - (
                0.0065
                * altura_m
                / denominador
            )
        ) ** -5.257
    )


def calcular_densidad_aire(presion_hpa, temp_c, humedad_pct):
    """
    Calcula la densidad del aire húmedo.

    Returns:
        float: kg/m³
    """

    vapor_hpa = presion_vapor(
        temp_c,
        humedad_pct
    )

    vapor_pa = vapor_hpa * 100
    presion_pa = presion_hpa * 100

    presion_aire_seco = presion_pa - vapor_pa

    temperatura_k = temp_c + 273.15

    densidad_aire_seco = (
        presion_aire_seco
        / (287.058 * temperatura_k)
    )

    densidad_vapor = (
        vapor_pa
        / (461.495 * temperatura_k)
    )

    return densidad_aire_seco + densidad_vapor


def calcular_bulbo_humedo(temp_c, humedad_pct):
    """
    Aproximación de temperatura de bulbo húmedo
    mediante Stull (2011).
    """

    return (
        temp_c
        * math.atan(
            0.151977
            * math.sqrt(humedad_pct + 8.313659)
        )
        + math.atan(temp_c + humedad_pct)
        - math.atan(humedad_pct - 1.676331)
        + 0.00391838
        * humedad_pct ** 1.5
        * math.atan(0.023101 * humedad_pct)
        - 4.686035
    )


# ============================================================
# CONSTRUCCIÓN DE LOS DATOS METEOROLÓGICOS
# ============================================================

def construir_datos(
    t_dht,
    humedad,
    t_bmp,
    presion,
    rssi,
    ts_adquisicion=None,
):
    """
    Construye el objeto final que utilizará
    el backend, WebSocket y base de datos.
    """

    # Solo se calculan derivadas si las variables de entrada existen.
    hay_datos_humedad = t_dht is not None and humedad is not None

    datos = {
        "t_dht": t_dht,
        "humedad": humedad,
        "t_bmp": t_bmp,
        "presion": presion,
        "rssi": rssi,

        # La altitud de la estación es una constante geográfica, no una
        # medición: la altitud derivada de la presión solo refleja el
        # ruido barométrico (±1 hPa equivale a ±8-10 m).
        "altitud": ALTURA_M,

        "punto_rocio": (
            calcular_punto_rocio(t_dht, humedad)
            if hay_datos_humedad
            else None
        ),

        "sensacion_termica": (
            calcular_sensacion_termica(t_dht, humedad)
            if hay_datos_humedad
            else None
        ),

        # Prioridad del timestamp: hora de adquisición del ESP32.
        # Si no llegó (o era inválida), se usa la hora de recepción.
        "timestamp": (
            ts_adquisicion
            if ts_adquisicion is not None
            else int(time.time())
        ),
    }

    # --------------------------------------------------------
    # Variables relacionadas con humedad
    # --------------------------------------------------------

    if humedad is not None and humedad > 0:

        datos["humedad_absoluta"] = round(
            calcular_humedad_absoluta(
                t_dht,
                humedad
            ),
            1,
        )

        datos["vpd"] = round(
            calcular_vpd(
                t_dht,
                humedad
            ),
            2,
        )

        datos["bulbo_humedo"] = round(
            calcular_bulbo_humedo(
                t_dht,
                humedad
            ),
            1,
        )

        datos["base_nubes"] = round(
            max(
                0.0,
                125
                * (
                    t_dht
                    - datos["punto_rocio"]
                ),
            ),
            1,
        )

    else:
        datos["humedad_absoluta"] = None
        datos["vpd"] = None
        datos["bulbo_humedo"] = None
        datos["base_nubes"] = None

    # --------------------------------------------------------
    # Variables relacionadas con presión
    # --------------------------------------------------------

    if presion is not None and presion > 0:

        datos["presion_mar"] = round(
            calcular_presion_nivel_mar(
                presion,
                ALTURA_M,
                t_bmp,
            ),
            1,
        )

        if humedad is not None and humedad > 0:
            datos["densidad_aire"] = round(
                calcular_densidad_aire(
                    presion,
                    t_dht,
                    humedad,
                ),
                3,
            )
        else:
            datos["densidad_aire"] = None

    else:
        datos["presion_mar"] = None
        datos["densidad_aire"] = None

    return datos


# ============================================================
# WEBSOCKET MANAGER
# ============================================================

class ConnectionManager:

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()

        self.active_connections.append(websocket)

        print(
            "[WEBSOCKET] Cliente conectado. "
            f"Total: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):

        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

            print(
                "[WEBSOCKET] Cliente desconectado. "
                f"Quedan: {len(self.active_connections)}"
            )

    async def broadcast(self, message: dict):

        for connection in list(self.active_connections):

            try:
                await connection.send_json(message)

            except Exception as error:

                print(
                    "[WEBSOCKET ERROR] "
                    f"{error}"
                )

                self.disconnect(connection)


manager = ConnectionManager()


# ============================================================
# MQTT
# ============================================================

def a_float_validado(valor, minimo, maximo):
    """
    Convierte a float un valor recibido por MQTT y valida su rango
    físico. Devuelve None si:
    - el valor es None (el ESP32 reportó lectura fallida),
    - no es convertible a número,
    - o está fuera del rango plausible (lectura corrupta).

    Un None se propaga hasta la base de datos como NULL: jamás se
    convierte en 0, porque un 0 sí es un dato (y uno falso).
    """

    if valor is None:
        return None

    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None

    if v < minimo or v > maximo:
        return None

    return v


def on_message(client, userdata, msg):
    """
    Callback ejecutado por Paho MQTT cuando llega
    una nueva medición desde el ESP32.
    """

    global latest_data

    try:

        raw_payload = msg.payload.decode("utf-8")

        print(
            f"\n[MQTT RECIBIDO] {raw_payload}"
        )

        data = json.loads(raw_payload)

        # ----------------------------------------------------
        # Extracción flexible
        # ----------------------------------------------------

        t_dht = a_float_validado(
            data.get("t_dht", data.get("temp_dht")),
            -50.0, 60.0,
        )

        humedad = a_float_validado(
            data.get("humedad", data.get("hum")),
            0.0, 100.0,
        )

        t_bmp = a_float_validado(
            data.get("t_bmp", data.get("temp_bmp")),
            -50.0, 60.0,
        )

        presion = a_float_validado(
            data.get("presion", data.get("press")),
            300.0, 1100.0,
        )

        rssi_bruto = data.get("rssi")
        rssi = int(rssi_bruto) if rssi_bruto is not None else None

        # ----------------------------------------------------
        # Timestamp de adquisición (epoch UTC desde el ESP32).
        # Se acepta solo si es razonablemente reciente
        # (>= nov. 2023) para rechazar relojes desincronizados.
        # ----------------------------------------------------
        ts_epoch = data.get("ts_epoch")
        ts_adquisicion = None

        if isinstance(ts_epoch, (int, float)) and ts_epoch >= 1_700_000_000:
            ts_adquisicion = datetime.fromtimestamp(
                ts_epoch, tz=timezone.utc
            ).isoformat(timespec="seconds")

        # ----------------------------------------------------
        # Construcción de datos derivados
        # ----------------------------------------------------

        nuevos_datos = construir_datos(
            t_dht=t_dht,
            humedad=humedad,
            t_bmp=t_bmp,
            presion=presion,
            rssi=rssi,
            ts_adquisicion=ts_adquisicion,
        )

        # ----------------------------------------------------
        # Actualizar estado global
        # ----------------------------------------------------

        latest_data = nuevos_datos

        print(
            "[DATOS PROCESADOS]"
            f" Temp={t_dht} °C"
            f" Hum={humedad} %"
            f" Presión={presion} hPa"
        )

        # ----------------------------------------------------
        # Enviar a la cola asíncrona
        # ----------------------------------------------------

        if main_loop is not None and main_loop.is_running():

            main_loop.call_soon_threadsafe(
                mqtt_queue.put_nowait,
                nuevos_datos
            )

    except json.JSONDecodeError:
        print(
            "[MQTT ERROR] El payload no contiene "
            "un JSON válido."
        )

    except (TypeError, ValueError) as error:
        print(
            "[MQTT ERROR] Datos numéricos inválidos: "
            f"{error}"
        )

    except Exception as error:
        print(
            f"[MQTT ERROR PARSE] {error}"
        )


def start_mqtt_loop():
    """
    Ejecuta el cliente MQTT en un hilo independiente.
    """

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2
    )

    client.on_message = on_message

    def on_connect(client, userdata, flags, reason_code, properties=None):
        # La suscripción va en el callback de conexión: así se
        # (re)inscribe automáticamente en cada reconexión, en lugar
        # de suscribirse una sola vez antes de estar conectado.
        if reason_code == 0:
            print(f"[MQTT] Suscripto al tópico: '{MQTT_TOPIC}'")
            client.subscribe(MQTT_TOPIC)
        else:
            print(f"[MQTT] Error de conexión: {reason_code}")

    client.on_connect = on_connect

    while True:

        try:

            print(
                "[MQTT] Conectando al broker "
                f"{BROKER_IP}:{MQTT_PORT}..."
            )

            client.connect(
                BROKER_IP,
                MQTT_PORT,
                keepalive=60
            )

            client.loop_forever()

        except Exception as error:

            print(
                "[MQTT ERROR] No se pudo conectar: "
                f"{error}"
            )

            print(
                f"[MQTT] Reintentando en "
                f"{INTERVALO_RECONEXION_MQTT}s..."
            )

            time.sleep(
                INTERVALO_RECONEXION_MQTT
            )


# ============================================================
# PROCESAMIENTO DE LA COLA MQTT
# ============================================================

async def process_mqtt_queue():

    while True:

        data = await mqtt_queue.get()

        # ----------------------------------------------------
        # Almacenamiento: cada medición recibida por MQTT
        # se guarda en la base de datos.
        # ----------------------------------------------------
        try:
            insertar_medicion(data)
        except Exception as error:
            print("[DATABASE ERROR]", error)

        # ----------------------------------------------------
        # Difusión en tiempo real vía WebSocket
        # ----------------------------------------------------
        try:
            await manager.broadcast(data)
        except Exception as error:
            print("[WEBSOCKET ERROR]", error)

        finally:
            mqtt_queue.task_done()


# ============================================================
# NOTA SOBRE EL ALMACENAMIENTO
# ============================================================
# Antes existía una tarea que guardaba latest_data cada 5 minutos,
# lo que descartaba casi todas las mediciones recibidas. Ahora la
# inserción en la base de datos ocurre en process_mqtt_queue, una
# vez por mensaje recibido (~1 medición cada 3 s ≈ 28.800 filas/día;
# SQLite lo maneja sin problema).


# ============================================================
# METAR
# ============================================================

def obtener_datos_metar():
    """
    Obtiene datos METAR de Rafaela.

    Esta función queda separada de la inicialización
    de FastAPI para evitar que una consulta externa
    bloquee el arranque del servidor.
    """

    try:

        datos = obtener_metar("SAFS")

        if not datos:
            print(
                "[METAR] No se encontraron datos."
            )
            return None

        print(
            "\n=== DATOS METAR RAFAELA ==="
        )

        print(
            f"Estación: "
            f"{datos.get('nombre', 'N/D')}"
        )

        print(
            f"ICAO: "
            f"{datos.get('icao', 'N/D')}"
        )

        print(
            f"Dirección del viento: "
            f"{datos.get('viento_dir', 'N/D')}°"
        )

        print(
            f"Velocidad del viento: "
            f"{datos.get('viento_kmh', 'N/D')} km/h"
        )

        rafaga = datos.get("rafagas_kmh")

        if rafaga:
            print(
                f"Ráfagas: {rafaga} km/h"
            )

        return datos

    except Exception as error:

        print(
            f"[METAR ERROR] {error}"
        )

        return None


# ============================================================
# LIFESPAN DE FASTAPI
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    global main_loop

    # Obtener event loop actual
    main_loop = asyncio.get_running_loop()

    print(
        "[SYSTEM] Inicializando base de datos..."
    )

    init_db()

    # --------------------------------------------------------
    # MQTT
    # --------------------------------------------------------

    mqtt_thread = threading.Thread(
        target=start_mqtt_loop,
        daemon=True,
        name="MQTT-Thread",
    )

    mqtt_thread.start()

    # --------------------------------------------------------
    # Tareas asíncronas
    # --------------------------------------------------------

    asyncio.create_task(
        process_mqtt_queue()
    )

    print(
        "[SYSTEM] FastAPI iniciado correctamente."
    )

    yield

    print(
        "[SYSTEM] Cerrando aplicación..."
    )


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="Estación Meteorológica IoT",
    description=(
        "Sistema de adquisición, procesamiento y "
        "visualización de datos meteorológicos."
    ),
    version="1.0.0",
    lifespan=lifespan,
)
app.mount(
    "/static",
    StaticFiles(directory="../frontend"),
    name="static"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# RUTAS HTTP
# ============================================================

@app.get("/")
async def inicio():
    """
    Devuelve el dashboard principal.
    """

    return FileResponse("../frontend/index.html")


@app.get("/api/v1/historial")
async def get_historial(limite: int = 100):
    """
    Devuelve las últimas mediciones almacenadas.
    """

    # Evita valores absurdos o negativos.
    limite = max(1, min(limite, 1000))

    return obtener_historial(limite)


@app.get("/api/v1/actual")
async def get_datos_actuales():
    """
    Devuelve la última medición recibida.
    """

    return latest_data


# ============================================================
# WEBSOCKET
# ============================================================

@app.websocket("/ws/clima")
async def websocket_endpoint(
    websocket: WebSocket
):

    await manager.connect(websocket)

    try:

        # Enviar inmediatamente la última medición.
        await websocket.send_json(
            latest_data
        )

        while True:

            # Mantener abierta la conexión.
            await websocket.receive_text()

    except WebSocketDisconnect:

        manager.disconnect(websocket)

    except Exception as error:

        print(
            f"[WEBSOCKET ERROR] {error}"
        )

        manager.disconnect(websocket)