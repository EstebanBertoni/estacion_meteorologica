"""
Evaluación y notificación de alertas meteorológicas.

La evaluación es pura (`evaluar_alertas` devuelve mensajes y no tiene
efectos secundarios), así que el backend puede publicar el resultado por
WebSocket sin reproducir sonido en el hilo de MQTT.

Fuentes: temperatura del DHT22 local (o del fallback de Open-Meteo), y
viento/lluvia del modelo Open-Meteo, siempre marcados con su procedencia.
Los valores None se ignoran: nunca se interpretan como 0.
"""

import sys
import threading
import time
from pathlib import Path

# La librería es opcional: sin ella se usa un beep del sistema.
try:
    from playsound3 import playsound

    PLAYSOUND_DISPONIBLE = True
except ImportError:
    PLAYSOUND_DISPONIBLE = False


# --- UMBRALES (fuente única de verdad) --------------------------------

UMBRAL_TEMPERATURA = 38.0   # °C
UMBRAL_VIENTO = 60.0        # km/h
UMBRAL_LLUVIA = 50.0        # mm

# Evita que una condición sostenida dispare la alarma en cada mensaje
# MQTT (llega una medición cada ~3 s).
COOLDOWN_SONIDO_S = 60.0

RUTA_AUDIO = (
    Path(__file__).resolve().parent
    / "sounds"
    / "freesound_community-eas-alarm-81032.mp3"
)

_bloqueo_sonido = threading.Lock()
_ultima_activacion = 0.0


def evaluar_alertas(temperatura=None, viento=None, lluvia=None) -> list[str]:
    """Devuelve los mensajes de alerta correspondientes a los umbrales.

    No imprime ni reproduce sonido: solo evalúa. Los valores None se
    ignoran (sensor sin dato), nunca se interpretan como 0.
    """
    mensajes = []

    if temperatura is not None and temperatura >= UMBRAL_TEMPERATURA:
        mensajes.append(
            f"¡ALERTA! Temperatura extrema: {temperatura}°C"
        )

    if viento is not None and viento >= UMBRAL_VIENTO:
        mensajes.append(
            f"¡ALERTA! Vientos fuertes: {viento} km/h"
        )

    if lluvia is not None and lluvia >= UMBRAL_LLUVIA:
        mensajes.append(
            f"¡ALERTA! Lluvia intensa: {lluvia} mm"
        )

    return mensajes


def activar_sonido(cooldown_s: float = COOLDOWN_SONIDO_S) -> bool:
    """Reproduce la alarma. Devuelve False si estaba en cooldown o falló."""
    global _ultima_activacion

    with _bloqueo_sonido:
        ahora = time.monotonic()
        if ahora - _ultima_activacion < cooldown_s:
            return False
        _ultima_activacion = ahora

    try:
        if PLAYSOUND_DISPONIBLE and RUTA_AUDIO.exists():
            playsound(str(RUTA_AUDIO))
            return True

        if sys.platform == "win32":
            import winsound

            winsound.Beep(2500, 1000)
            return True

        print("\a", end="", flush=True)
        return True

    except Exception as error:
        print(f"[ALERTA] No se pudo reproducir el sonido: {error}")
        return False


def alerta(temperatura=None, viento=None, lluvia=None) -> list[str]:
    """Evalúa, imprime el resultado y suena la alarma si corresponde.

    Se conserva por compatibilidad con el uso standalone del archivo.
    El backend usa `evaluar_alertas` + `activar_sonido` por separado.
    """
    mensajes = evaluar_alertas(
        temperatura=temperatura,
        viento=viento,
        lluvia=lluvia,
    )

    if mensajes:
        print("\n".join(mensajes))
        activar_sonido()
    else:
        print("Condiciones climáticas normales. Sin alertas activas.")

    return mensajes


if __name__ == "__main__":
    print("Probando con clima normal:")
    alerta(temperatura=25, viento=15, lluvia=5)

    print("\nProbando con clima severo:")
    alerta(temperatura=40, viento=75, lluvia=20000)
