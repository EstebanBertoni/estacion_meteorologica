import sqlite3
from datetime import datetime

DB_NAME = "estacion_meteo.db"

def init_db():
    """Crea la tabla de mediciones si no existe."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mediciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            temp_dht REAL,
            humedad REAL,
            temp_bmp REAL,
            presion REAL,
            altitud REAL,
            punto_rocio REAL,
            sensacion_termica REAL,
            rssi INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def insertar_medicion(data: dict):
    """Inserta un registro con el timestamp actual."""
    if not data or data.get("t_dht", 0) == 0:
        return  # Evitar guardar datos vacíos o iniciales
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT INTO mediciones (
            fecha_hora, temp_dht, humedad, temp_bmp, 
            presion, altitud, punto_rocio, sensacion_termica, rssi
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        fecha_hora,
        data.get("t_dht"),
        data.get("humedad"),
        data.get("t_bmp"),
        data.get("presion"),
        data.get("altitud"),
        data.get("punto_rocio"),
        data.get("sensacion_termica"),
        data.get("rssi")
    ))
    
    conn.commit()
    conn.close()
    print(f"[BD SQLITE] Registro guardado exitosamente a las {fecha_hora}")

def obtener_historial(limite=100):
    """Devuelve las últimas N mediciones registradas."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Para retornar diccionarios
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM mediciones ORDER BY id DESC LIMIT ?
    ''', (limite,))
    
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]