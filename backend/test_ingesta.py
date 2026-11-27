"""
test_ingesta.py — Test de integración del pipeline de ingesta.

Verifica la cadena completa CON el backend corriendo:

    MQTT (publish autenticado) -> on_message -> construir_datos
    -> process_mqtt_queue -> insertar_medicion -> SQLite

Uso:
    1. Backend corriendo (uvicorn main:app)
    2. Broker corriendo
    3. python test_ingesta.py

La medición de prueba usa valores inconfundibles (41.5, 77.7, ...)
dentro de los rangos físicos válidos. Al terminar, la fila se
ELIMINA de la DB: es dato sintético, no medición.

Exit code 0 = todos los checks pasaron.
"""

import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

DB_PATH = Path(__file__).resolve().parent / "estacion_meteo.db"
BROKER_IP = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPIC = "estacion/telemetria"

try:
    from credentials import MQTT_USER, MQTT_PASS
except ModuleNotFoundError:
    MQTT_USER = None
    MQTT_PASS = None

# ------------------------------------------------------------
# Valores de prueba: inconfundibles pero físicamente plausibles
# (pasan la validación de rangos del backend a propósito).
# ------------------------------------------------------------

TEST = {
    "t_dht": 41.5,
    "humedad": 77.7,
    "t_bmp": 40.2,
    "presion": 1015.7,
    "rssi": -77,
}

TIMEOUT_S = 10
POLL_S = 0.5

resultados = []


def check(nombre, condicion, detalle=""):
    estado = "OK " if condicion else "FALLO"
    linea = f"  [{estado}] {nombre}"
    if detalle:
        linea += f" -> {detalle}"
    resultados.append(condicion)
    print(linea)
    return condicion


def publicar_test():
    """Publica la medición sintética con timestamp actual."""
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USER and MQTT_PASS:
        cliente.username_pw_set(MQTT_USER, MQTT_PASS)

    cliente.connect(BROKER_IP, MQTT_PORT, keepalive=30)
    cliente.loop_start()

    ts_epoch = int(time.time())
    payload = dict(TEST)
    payload["ts_epoch"] = ts_epoch

    info = cliente.publish(MQTT_TOPIC, json.dumps(payload), qos=0)
    info.wait_for_publish(timeout=5)

    cliente.loop_stop()
    cliente.disconnect()

    esperado = datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat(
        timespec="seconds"
    )
    return esperado


def buscar_fila_test(esperado_ts):
    """
    Busca la fila de prueba por coincidencia TRIPLE: presion + rssi
    + ts_adquisicion. La triple coincidencia hace imposible confundir
    la fila sintética con una medición real que casualmente tuviera
    esos valores (y así la limpieza nunca borra un dato legítimo).
    """
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM mediciones
        WHERE presion = ? AND rssi = ? AND ts_adquisicion = ?
        ORDER BY id DESC LIMIT 1
        """,
        (TEST["presion"], TEST["rssi"], esperado_ts),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def borrar_fila_test(id_fila):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("DELETE FROM mediciones WHERE id = ?", (id_fila,))
    conn.commit()
    conn.close()


def main():
    print("=" * 60)
    print("TEST DE INTEGRACIÓN DEL PIPELINE DE INGESTA")
    print("=" * 60)

    if not DB_PATH.exists():
        print(f"FALLO: no existe la DB en {DB_PATH}")
        return 1

    # --------------------------------------------------------
    # Publicar
    # --------------------------------------------------------
    print("\n[1] Publicando medición sintética al broker...")
    try:
        esperado_ts = publicar_test()
        print(f"    Publicado con ts_epoch -> {esperado_ts}")
    except Exception as error:
        print(f"  [FALLO] No se pudo publicar: {error}")
        print("    Verificar: ¿broker corriendo? ¿credenciales correctas?")
        return 1

    # --------------------------------------------------------
    # Esperar y buscar la fila en la DB
    # --------------------------------------------------------
    print(f"\n[2] Esperando la ingesta (hasta {TIMEOUT_S}s)...")
    fila = None
    inicio = time.time()
    while time.time() - inicio < TIMEOUT_S:
        fila = buscar_fila_test(esperado_ts)
        if fila:
            break
        time.sleep(POLL_S)

    if fila is None:
        print("  [FALLO] La medición no llegó a la DB en el tiempo esperado.")
        print("    Eslabones a revisar: ¿backend corriendo? ¿MQTT conectado?")
        print("    (mirá los logs de uvicorn: [MQTT RECIBIDO] / [DATABASE ERROR])")
        return 1

    print(f"    Fila encontrada: id={fila['id']}")

    # --------------------------------------------------------
    # Checks por eslabón
    # --------------------------------------------------------
    print("\n[3] Verificando cada eslabón del pipeline:")

    check(
        "Valores crudos llegaron intactos (MQTT -> DB)",
        fila["temp_dht"] == TEST["t_dht"]
        and fila["humedad"] == TEST["humedad"]
        and fila["temp_bmp"] == TEST["t_bmp"],
        f"t_dht={fila['temp_dht']} humedad={fila['humedad']} temp_bmp={fila['temp_bmp']}",
    )

    check(
        "RSSI llegó intacto",
        fila["rssi"] == TEST["rssi"],
        f"rssi={fila['rssi']}",
    )

    ts_db = fila["ts_adquisicion"]
    check(
        "ts_adquisicion = hora del ESP32 (el bug del 12/10 está muerto)",
        ts_db == esperado_ts,
        f"esperado={esperado_ts} obtenido={ts_db}",
    )

    fh = fila["fecha_hora"]
    try:
        edad = (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(fh)
        ).total_seconds()
        check(
            "fecha_hora (recepción) es reciente (<10 s)",
            0 <= edad < 10,
            f"edad={edad:.1f}s",
        )
    except Exception as e:
        check("fecha_hora parseable", False, str(e))

    # Nota: presion_mar, vpd, densidad_aire, etc. solo se calculan para
    # latest_data/WebSocket; en la DB se persisten punto_rocio,
    # sensacion_termica y altitud.
    derivadas_ok = (
        fila["punto_rocio"] is not None
        and fila["sensacion_termica"] is not None
        and fila["altitud"] == 90.0
    )
    check(
        "Variables derivadas calculadas (construir_datos)",
        derivadas_ok,
        f"punto_rocio={fila['punto_rocio']} "
        f"sens_term={fila['sensacion_termica']} "
        f"altitud={fila['altitud']}",
    )

    # Punto de rocío re-verificado con Magnus (independiente del backend)
    t, h = TEST["t_dht"], TEST["humedad"]
    import math
    alpha = (17.27 * t) / (237.7 + t) + math.log(h / 100.0)
    td_esperado = round((237.7 * alpha) / (17.27 - alpha), 1)
    check(
        "Punto de rocío coincide con Magnus recalculado",
        abs(fila["punto_rocio"] - td_esperado) < 0.15,
        f"esperado={td_esperado} obtenido={fila['punto_rocio']}",
    )

    # --------------------------------------------------------
    # Limpieza: la fila de prueba sale de la DB
    # --------------------------------------------------------
    print(f"\n[4] Limpieza: eliminando fila de prueba id={fila['id']}...")
    borrar_fila_test(fila["id"])
    print("    Eliminada (dato sintético, no medición).")

    # --------------------------------------------------------
    # Veredicto
    # --------------------------------------------------------
    pasados = sum(resultados)
    total = len(resultados)
    print("\n" + "=" * 60)
    print(f"RESULTADO: {pasados}/{total} checks OK")
    if pasados == total:
        print("PIPELINE DE INGESTA: INTEGRO de punta a punta")
        return 0
    print("PIPELINE CON FALLAS — revisar los checks en FALLO arriba")
    return 1


if __name__ == "__main__":
    sys.exit(main())