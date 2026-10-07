from datetime import datetime, timezone
from pathlib import Path
import sqlite3

# ------------------------------------------------------------
# Ruta absoluta: la base de datos vive junto al paquete backend.
# Antes se usaba una ruta relativa, lo que generaba DOS bases
# de datos distintas según el directorio desde donde se lanzara
# uvicorn. Con ruta absoluta eso ya no puede pasar.
# ------------------------------------------------------------
DB_PATH = Path(__file__).resolve().parent.parent / "estacion_meteo.db"


def init_db():
    """Crea la tabla de mediciones si no existe y agrega columnas si faltan."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS mediciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_adquisicion TEXT,
            fecha_hora TEXT NOT NULL,
            temp_dht REAL,
            humedad REAL,
            temp_bmp REAL,
            presion REAL,
            altitud REAL,
            punto_rocio REAL,
            sensacion_termica REAL,
            rssi INTEGER,
            viento_velocidad REAL,
            viento_rafaga REAL,
            viento_direccion TEXT,
            fuente_viento TEXT
        )
        """
    )

    # Migración automática para bases preexistentes sin estas columnas
    columnas_nuevas = [
        ("ts_adquisicion", "TEXT"),
        ("viento_velocidad", "REAL"),
        ("viento_rafaga", "REAL"),
        ("viento_direccion", "TEXT"),
        ("fuente_viento", "TEXT"),
    ]

    cursor.execute("PRAGMA table_info(mediciones)")
    columnas_existentes = [col[1] for col in cursor.fetchall()]

    for col_nombre, col_tipo in columnas_nuevas:
        if col_nombre not in columnas_existentes:
            cursor.execute(
                f"ALTER TABLE mediciones ADD COLUMN {col_nombre} {col_tipo}"
            )

    # Índice por tiempo: es la consulta dominante en un histórico
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_mediciones_fecha_hora "
        "ON mediciones (fecha_hora)"
    )

    conn.commit()
    conn.close()


def insertar_medicion(data: dict):
    """
    Inserta una medición recibida por MQTT.

    Distingue dos timestamps (requisito del diseño):
    - ts_adquisicion: hora de la medición según el ESP32 (ISO 8601 UTC).
      Puede ser None si el ESP32 no tenía hora confiable.
    - fecha_hora: momento de recepción en el servidor (ISO 8601 UTC).

    Los valores ausentes (sensor fallido) se guardan como NULL,
    nunca como 0.
    """
    if not data:
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    fecha_hora = datetime.now(timezone.utc).isoformat(timespec="seconds")

    cursor.execute(
        """
        INSERT INTO mediciones (
            ts_adquisicion, fecha_hora, temp_dht, humedad,
            temp_bmp, presion, altitud, punto_rocio, sensacion_termica, rssi,
            viento_velocidad, viento_rafaga, viento_direccion, fuente_viento
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("ts_adquisicion"),
            fecha_hora,
            data.get("t_dht"),
            data.get("humedad"),
            data.get("t_bmp"),
            data.get("presion"),
            data.get("altitud"),
            data.get("punto_rocio"),
            data.get("sensacion_termica"),
            data.get("rssi"),
            data.get("viento_velocidad"),
            data.get("viento_rafaga"),
            data.get("viento_direccion"),
            data.get("fuente_viento"),
        ),
    )

    conn.commit()
    conn.close()


def obtener_historial(limite=100):
    """Devuelve las últimas N mediciones registradas (más recientes primero)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM mediciones ORDER BY id DESC LIMIT ?
        """,
        (limite,),
    )

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
