import requests

def obtener_metar(icao_code: str = "SAAR", timeout: int = 10) -> dict | None:
    """
    Obtiene y procesa datos METAR desde AviationWeather API.
    
    :param icao_code: Código OACI/ICAO del aeródromo (ej. 'SAAR', 'SABE').
    :param timeout: Tiempo límite para la petición HTTP en segundos.
    :return: Diccionario con los datos procesados o None si ocurre un error.
    """
    url = f"https://aviationweather.gov/api/data/metar?ids={icao_code.upper()}&format=json"
    
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        datos = response.json()
        
        if not datos:
            return None
        
        metar = datos[0]
        viento_kt = metar.get('wspd', 0)
        rafagas_kt = metar.get('wgst')
        
        return {
            "icao": metar.get('icaoId', icao_code.upper()),
            "nombre": metar.get('name', 'Desconocido'),
            "observacion": metar.get('rawOb'),
            "temp_c": metar.get('temp'),
            "viento_dir": metar.get('wdir'),
            "viento_kt": viento_kt,
            "viento_kmh": round(viento_kt * 1.852, 1),
            "rafagas_kmh": round(rafagas_kt * 1.852, 1) if rafagas_kt is not None else None,
        }
        
    except requests.exceptions.RequestException as err:
        print(f"[ERROR METAR] No se pudo obtener información para {icao_code}: {err}")
        return None