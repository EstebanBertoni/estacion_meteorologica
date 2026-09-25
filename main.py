import asyncio
import json
import math
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt

# Importar funciones de SQLite (base de datos)
from database import init_db, insertar_medicion, obtener_historial

# --- CONFIGURACIÓN ---
# Si Mosquitto corre en la misma PC que FastAPI, usamos loopback
BROKER_IP = "127.0.0.1"
PORT = 1883
TOPIC = "estacion/meteo"

latest_data = {
    "t_dht": 0.0,
    "humedad": 0.0,
    "t_bmp": 0.0,
    "presion": 0.0,
    "rssi": 0,
    "altitud": 0.0,
    "punto_rocio": 0.0,
    "sensacion_termica": 0.0
}

# --- FÓRMULAS METEOROLÓGICAS ---
def calcular_altitud(presion_hpa, p0_hpa=1032.0):
    if presion_hpa <= 0:
        return 0.0
    return round(44330.0 * (1.0 - (presion_hpa / p0_hpa) ** 0.1903), 1)

def calcular_punto_rocio(temp_c, humedad_pct):
    if temp_c == 0 or humedad_pct == 0:
        return 0.0
    a, b = 17.27, 237.7
    alpha = ((a * temp_c) / (b + temp_c)) + math.log(humedad_pct / 100.0)
    return round((b * alpha) / (a - alpha), 1)

def calcular_sensacion_termica(temp_c, humedad_pct):
    if temp_c < 20 or humedad_pct == 0:
        return round(temp_c, 1)
    hi = 0.5 * (temp_c + 61.0 + ((temp_c - 68.0) * 1.2) + (humedad_pct * 0.094))
    return round(hi, 1)

# --- COLA ASINCRÓNICA Y WEBSOCKET MANAGER ---
mqtt_queue = asyncio.Queue()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WEBSOCKET] Cliente conectado. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"[WEBSOCKET] Cliente desconectado. Quedan: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"[WEBSOCKET ERROR] Error enviando a cliente: {e}")
                self.disconnect(connection)

manager = ConnectionManager()

# --- MQTT CALLBACKS ---
def on_message(client, userdata, msg):
    global latest_data
    try:
        raw_payload = msg.payload.decode('utf-8')
        print(f"\n[MQTT RECIBIDO] Payload: {raw_payload}")
        data = json.loads(raw_payload)

        # Extracción flexible de nombres de claves
        t_dht = float(data.get("t_dht", data.get("temp_dht", 0)))
        humedad = float(data.get("humedad", data.get("hum", 0)))
        t_bmp = float(data.get("t_bmp", data.get("temp_bmp", 0)))
        presion = float(data.get("presion", data.get("press", 0)))
        rssi = int(data.get("rssi", 0))

        latest_data = {
            "t_dht": t_dht,
            "humedad": humedad,
            "t_bmp": t_bmp,
            "presion": presion,
            "rssi": rssi,
            "altitud": calcular_altitud(presion),
            "punto_rocio": calcular_punto_rocio(t_dht, humedad),
            "sensacion_termica": calcular_sensacion_termica(t_dht, humedad)
        }

        # Transmitir a la cola de asyncio si el loop está activo
        if main_loop and main_loop.is_running():
            main_loop.call_soon_threadsafe(mqtt_queue.put_nowait, latest_data)

    except Exception as e:
        print(f"[MQTT ERROR PARSE]: {e}")

def start_mqtt_loop():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message
    
    while True:
        try:
            print(f"[MQTT] Intentando conectar al broker en {BROKER_IP}:{PORT}...")
            client.connect(BROKER_IP, PORT, keepalive=60)
            client.subscribe(TOPIC)
            print(f"[MQTT] Suscripto con éxito al tópico: '{TOPIC}'")
            client.loop_forever()
        except Exception as e:
            print(f"[MQTT ERROR]: No se pudo conectar al broker ({e}). Reintentando en 5s...")
            import time
            time.sleep(5)

async def process_mqtt_queue():
    while True:
        data = await mqtt_queue.get()
        print(f"[WEBSOCKET BROADCAST] Transmitiendo a la web: {data}")
        await manager.broadcast(data)
        mqtt_queue.task_done()

async def guardar_datos_periodicamente():
    await asyncio.sleep(10)
    while True:
        insertar_medicion(latest_data)
        await asyncio.sleep(300)

# --- LIFESPAN Y SERVIDOR ---
main_loop = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop
    main_loop = asyncio.get_running_loop()
    
    init_db()
    
    mqtt_thread = threading.Thread(target=start_mqtt_loop, daemon=True)
    mqtt_thread.start()
    
    asyncio.create_task(process_mqtt_queue())
    asyncio.create_task(guardar_datos_periodicamente())
    
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def read_index():
    return FileResponse("index.html")

@app.get("/api/v1/historial")
async def get_historial(limite: int = 100):
    return obtener_historial(limite)

@app.websocket("/ws/clima")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Enviar el estado más reciente apenas se conecta
        await websocket.send_json(latest_data)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)