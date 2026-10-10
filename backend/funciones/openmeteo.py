import requests
from datetime import datetime, timezone

URL_BASE = "https://api.open-meteo.com/v1/forecast"

# Variables del estado actual que nos interesan (API de Open-Meteo)
VARIABLES_ACTUALES = (
    "temperature_2m,"
    "relative_humidity_2m,"
    "pressure_msl,"
    "surface_pressure,"
    "wind_speed_10m,"
    "wind_direction_10m,"
    "wind_gusts_10m"
)


def obtener_openmeteo(latitud: float, longitud: float, timeout: int = 10) -> dict | None:
    """
    Consulta el estado actual del modelo para las coordenadas de la
    estación y lo devuelve normalizado.

    IMPORTANTE — procedencia del dato: los valores de Open-Meteo son
    SALIDA DE MODELO NUMÉRICO interpolada a la coordenada, NO una
    medición instrumental. Se almacenan en su propia tabla y con el
    campo `fuente` para no mezclarlos jamás con las mediciones reales
    de la estación.

    Nota sobre presiones:
    - pressure_msl: presión reducida al nivel del mar (comparable entre
      estaciones y con el METAR histórico).
    - surface_pressure: presión del modelo a la altitud de la celda.
    Ambas se almacenan; para comparar con nuestra `presion_mar` local,
    usar `presion_msl_hpa`.

    Devuelve None ante error de red o respuesta inesperada.
    """

    params = {
        "latitude": latitud,
        "longitude": longitud,
        "current": VARIABLES_ACTUALES,
        "wind_speed_unit": "kmh",
        # Disciplina UTC: la hora del modelo llega como ISO en UTC y la
        # local la calcula el frontend, igual que con el resto del sistema.
        "timezone": "UTC",
    }

    try:
        response = requests.get(URL_BASE, params=params, timeout=timeout)
        response.raise_for_status()
        datos = response.json()

    except requests.exceptions.RequestException as error:
        print(f"[OPEN-METEO ERROR] {error}")
        return None

    actual = datos.get("current")
    if not actual:
        print("[OPEN-METEO] Respuesta sin bloque 'current'")
        return None

    # Normalizar la hora del modelo a ISO 8601 UTC explícito.
    # Open-Meteo devuelve "2026-10-10T02:15" (con timezone=UTC).
    hora_modelo = actual.get("time")
    fecha_observacion = None
    if hora_modelo:
        try:
            fecha_observacion = (
                datetime.fromisoformat(hora_modelo)
                .replace(tzinfo=timezone.utc)
                .isoformat(timespec="seconds")
            )
        except ValueError:
            fecha_observacion = hora_modelo   # conservar crudo ante formatos nuevos

    return {
        "fecha_observacion": fecha_observacion,
        "fuente": "open-meteo",
        "latitud": latitud,
        "longitud": longitud,
        "temp_c": actual.get("temperature_2m"),
        "humedad": actual.get("relative_humidity_2m"),
        "presion_msl_hpa": actual.get("pressure_msl"),
        "presion_superficie_hpa": actual.get("surface_pressure"),
        "viento_kmh": actual.get("wind_speed_10m"),
        "viento_dir": actual.get("wind_direction_10m"),
        "rafagas_kmh": actual.get("wind_gusts_10m"),
    }
