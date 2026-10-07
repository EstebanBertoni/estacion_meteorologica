import re
import requests
from playwright.sync_api import sync_playwright


def obtener_viento_siga(estacion_id="A872862"):
    """Intenta extraer la lectura de viento desde la interfaz web del SIGA INTA."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        try:
            print("[+] [SIGA-INTA] Conectando a la estación A872862...")
            page.goto("https://siga.inta.gob.ar/#/data", wait_until="networkidle")

            # Esperar renderizado del DOM de Angular
            page.wait_for_timeout(3000)

            filas = page.query_selector_all("table tr")
            headers = []
            data_rows = []

            for fila in filas:
                celdas_th = [
                    th.inner_text().strip()
                    for th in fila.query_selector_all("th")
                ]
                celdas_td = [
                    td.inner_text().strip()
                    for td in fila.query_selector_all("td")
                ]

                if celdas_th and not headers:
                    headers = celdas_th
                if celdas_td:
                    data_rows.append(celdas_td)

            browser.close()

            if not data_rows or not headers:
                return None

            ultima_lectura = data_rows[0]
            mapeo = {h: v for h, v in zip(headers, ultima_lectura)}

            v_media = extraer_numero(mapeo.get("V2md(km/h)"))
            v_max = extraer_numero(mapeo.get("Vmx(km/h)"))
            direccion = mapeo.get("Dir2(PC)")

            # Validar si los campos de viento contienen información válida
            if v_media is None and (
                not direccion or direccion in ["-", "", "N/D", "null"]
            ):
                print(
                    "[!] [SIGA-INTA] Sensores de viento inactivos o sin datos registrados."
                )
                return None

            return {
                "fuente": "SIGA-INTA (EEA Rafaela)",
                "velocidad_kmh": v_media,
                "rafaga_kmh": v_max,
                "direccion": direccion,
            }

        except Exception as e:
            print(f"[-] [SIGA-INTA] Error durante el scraping: {e}")
            browser.close()
            return None


def obtener_viento_openmeteo(lat=-31.189, lon=-61.472):
    """Consulta la API de Open-Meteo para las coordenadas exactas de EEA Rafaela."""
    print(
        "[+] [Open-Meteo] Ejecutando consulta de respaldo (Fallback) para Rafaela..."
    )
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ["wind_speed_10m", "wind_direction_10m", "wind_gusts_10m"],
        "wind_speed_unit": "kmh",
        "timezone": "America/Argentina/Cordoba",
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json().get("current", {})

        grados = data.get("wind_direction_10m")

        return {
            "fuente": "Open-Meteo (API Fallback)",
            "velocidad_kmh": data.get("wind_speed_10m"),
            "rafaga_kmh": data.get("wind_gusts_10m"),
            "direccion": (
                f"{grados}° ({grados_a_cardinal(grados)})"
                if grados is not None
                else None
            ),
        }
    except requests.RequestException as e:
        print(f"[-] [Open-Meteo] Error al consultar la API: {e}")
        return None


def grados_a_cardinal(grados):
    """Convierte azimut en grados a punto cardinal de la rosa de los vientos."""
    try:
        puntos = [
            "N",
            "NNE",
            "NE",
            "ENE",
            "E",
            "ESE",
            "SE",
            "SSE",
            "S",
            "SSO",
            "SO",
            "OSO",
            "O",
            "ONO",
            "NO",
            "NNO",
        ]
        idx = int((float(grados) + 11.25) / 22.5) % 16
        return puntos[idx]
    except (ValueError, TypeError):
        return ""


def extraer_numero(texto):
    if not texto:
        return None
    match = re.search(r"[-+]?\d+(?:[\.,]\d+)?", texto)
    if match:
        return float(match.group().replace(",", "."))
    return None


def obtener_telemetria_viento():
    # 1. Intento primario: SIGA INTA
    datos = obtener_viento_siga("A872862")

    # 2. Respaldo: Open-Meteo si el primario no retornó viento válido
    if not datos:
        datos = obtener_viento_openmeteo()

    return datos


if __name__ == "__main__":
    viento = obtener_telemetria_viento()

    if viento:
        print("\n==========================================")
        print(f" FUENTE DE DATOS: {viento['fuente']}")
        print("==========================================")
        print(f" Velocidad Viento: {viento['velocidad_kmh']} km/h")
        print(f" Ráfagas / Máx:   {viento['rafaga_kmh']} km/h")
        print(f" Dirección:       {viento['direccion']}")
        print("==========================================")
    else:
        print("[-] Fallaron todas las fuentes de telemetría de viento.")