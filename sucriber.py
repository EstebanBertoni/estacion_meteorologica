import json
import paho.mqtt.client as mqtt

# Configuración del Broker
BROKER_IP = "127.0.0.1"  # Al ejecutarse en la misma PC que Mosquitto
PORT = 1883
TOPIC = "estacion/telemtria" # Cambia por el tópico exacto que usa el ESP32

# Callback cuando el cliente se conecta al broker
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[MQTT] Conectado exitosamente al broker {BROKER_IP}:{PORT}")
        # Suscribirse al tópico al conectar
        client.subscribe(TOPIC)
        print(f"[MQTT] Suscripto al tópico: '{TOPIC}'\n")
    else:
        print(f"[MQTT] Error de conexión. Código de retorno: {rc}")

# Callback cuando llega un mensaje
def on_message(client, userdata, msg):
    payload_str = msg.payload.decode('utf-8')
    print(f"[Recibido] Tópico '{msg.topic}': {payload_str}")
    
    try:
        # Decodificar la cadena JSON enviada por el ESP32
        data = json.loads(payload_str)
        
        # Extracción de variables
        t_bmp = data.get("t_bmp")
        presion = data.get("presion")
        t_dht = data.get("t_dht")
        humedad = data.get("humedad")
        rssi = data.get("rssi")

        print(f"  ├ Temp BMP: {t_bmp} °C")
        print(f"  ├ Presión: {presion} hPa")
        print(f"  ├ Temp DHT: {t_dht} °C")
        print(f"  ├ Humedad: {humedad} %")
        print(f"  └ RSSI: {rssi} dBm\n")
        
        # Aquí puedes agregar la lógica para guardar en Base de Datos

    except json.JSONDecodeError:
        print("  └ [Error] El mensaje recibido no es un JSON válido.")

# Inicialización del cliente
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

# Conectar e iniciar bucle continuo de lectura
try:
    client.connect(BROKER_IP, PORT, keepalive=60)
    client.loop_forever()  # Mantiene la ejecución bloqueante a la espera de datos
except KeyboardInterrupt:
    print("\n[MQTT] Desconectando suscriptor...")
    client.disconnect()
except Exception as e:
    print(f"[Error] No se pudo conectar al broker: {e}")