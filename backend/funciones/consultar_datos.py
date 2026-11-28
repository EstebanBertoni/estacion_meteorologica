"""Agregados diarios y de la última hora para el dashboard.

Los valores se calculan desde la base de datos y se inyectan en
`latest_data` desde una tarea periódica de `main.py`.

Definiciones:
- Mínimos/máximos y viento máximo: día local de la estación (UTC-3),
  sobre las filas de `mediciones` recibidas en ese rango.
- Promedios: última hora rodante (temperatura y humedad del DHT22).
- Lluvia acumulada y probabilidad: desde `referencia_openmeteo`, porque
  son salida del MODELO Open-Meteo, no mediciones del pluviómetro local.

`acum_viento` se conserva como alias de `acum_lluvia` por compatibilidad
con el nombre histórico de la tarjeta del dashboard.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from funciones.database import DB_PATH, rango_dia_local_utc

# Claves que se mantienen vivas en `latest_data` aunque llegue una
# medición MQTT nueva (que reconstruye el dict desde cero).
CLAVES_AGREGADOS = (
    "temp_min",
    "temp_max",
    "hum_min",
    "hum_max",
    "prom_temp",
    "prom_hum",
    "Max_viento",
    "acum_lluvia",
    "acum_viento",
    "prob_lluvia",
)


def _redondear(valor, decimales=2):
    return round(valor, decimales) if valor is not None else None


def consultar_datos() -> dict:
    """Devuelve los agregados actuales listos para el WebSocket."""
    inicio_dia, fin_dia = rango_dia_local_utc()
    ahora_utc = datetime.now(timezone.utc)
    hace_una_hora = (ahora_utc - timedelta(hours=1)).isoformat(timespec="seconds")
    ahora_utc = ahora_utc.isoformat(timespec="seconds")

    conn = sqlite3.connect(DB_PATH, timeout=5)
    try:
        fila_dia = conn.execute(
            """
            SELECT
                MIN(temp_dht),
                MAX(temp_dht),
                MIN(humedad),
                MAX(humedad),
                MAX(viento_velocidad)
            FROM mediciones
            WHERE fecha_hora >= ? AND fecha_hora < ?
            """,
            (inicio_dia, fin_dia),
        ).fetchone()

        fila_hora = conn.execute(
            """
            SELECT AVG(temp_dht), AVG(humedad)
            FROM mediciones
            WHERE fecha_hora >= ? AND fecha_hora <= ?
            """,
            (hace_una_hora, ahora_utc),
        ).fetchone()

        fila_modelo = conn.execute(
            """
            SELECT SUM(lluvia_mm_h), MAX(prob_lluvia)
            FROM referencia_openmeteo
            WHERE fecha_observacion >= ? AND fecha_observacion < ?
            """,
            (inicio_dia, fin_dia),
        ).fetchone()
    finally:
        conn.close()

    temp_min = _redondear(fila_dia[0])
    temp_max = _redondear(fila_dia[1])
    hum_min = _redondear(fila_dia[2])
    hum_max = _redondear(fila_dia[3])
    viento_max = _redondear(fila_dia[4])

    prom_temp = _redondear(fila_hora[0])
    prom_hum = _redondear(fila_hora[1])

    # Suma de mm/h observation a observation del modelo: en la práctica
    # es el acumulado aproximado del día. None si no hay referencias hoy.
    acum_lluvia = _redondear(fila_modelo[0])
    prob_lluvia = _redondear(fila_modelo[1], 0)
    if prob_lluvia is not None:
        prob_lluvia = int(prob_lluvia)

    return {
        "temp_min": temp_min,
        "temp_max": temp_max,
        "hum_min": hum_min,
        "hum_max": hum_max,
        "prom_temp": prom_temp,
        "prom_hum": prom_hum,
        "Max_viento": viento_max,
        "acum_lluvia": acum_lluvia,
        "acum_viento": acum_lluvia,   # alias histórico
        "prob_lluvia": prob_lluvia,
    }
