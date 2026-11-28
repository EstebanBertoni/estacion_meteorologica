# Inventario de archivos del proyecto

Generado: 2026-11-28. Se listan las rutas absolutas trabajadas, excluyendo el contenido interno de `.git`.

## 1. Repo de código — `C:\Users\esteb\Desktop\estacion_meteo`

**35 archivos en disco · 23 versionados por Git · 12 ignorados/generados**

```
estacion_meteo/
├─ .gitignore                              [git]
├─ README.md                               [git]
├─ .vscode/
│  └─ settings.json                        [local / ignorado]
├─ backend/
│  ├─ credentials.py                       [local / ignorado — secreto]
│  ├─ estacion_meteo.db                    [local / ignorado — base de datos]
│  ├─ main.py                              [git]
│  ├─ main.spec                            [git]
│  ├─ requirements.txt                     [git]
│  ├─ test_ingesta.py                      [git]
│  ├─ logs/
│  │  └─ backend.log                       [local / ignorado]
│  ├─ __pycache__/                         [generado]
│  │  ├─ credentials.cpython-312.pyc
│  │  └─ main.cpython-312.pyc
│  └─ funciones/
│     ├─ __init__.py                       [git]
│     ├─ alerta.py                         [git]
│     ├─ consultar_datos.py                [git] ← agregados diarios pendientes
│     ├─ database.py                       [git]
│     ├─ openmeteo.py                      [git]
│     ├─ sucriber.py                       [git]
│     ├─ test.py                           [git]
│     ├─ sounds/
│     │  └─ freesound_community-eas-alarm-81032.mp3  [git]
│     └─ __pycache__/                      [generado]
│        ├─ __init__.cpython-312.pyc
│        ├─ alerta.cpython-312.pyc
│        ├─ database.cpython-312.pyc
│        ├─ metar.cpython-312.pyc
│        ├─ openmeteo.cpython-312.pyc
│        └─ sucriber.cpython-312.pyc
├─ docs/
│  └─ ARQUITECTURA.md                      [git]
├─ firmware/
│  ├─ README.md                            [git]
│  ├─ credentials.h.example                [git]
│  ├─ Test_MQTT_buffer.ino                 [git]
│  └─ Test_Nano_sensores.ino               [git]
└─ frontend/
   ├─ app.js                               [git]
   ├─ index.html                           [git]
   ├─ style.css                            [git]
   └─ assets/
      └─ cloud-sun.svg                     [git]
```

Los 12 archivos **no versionados** son: `backend/credentials.py`, `backend/estacion_meteo.db`, `backend/logs/backend.log`, `.vscode/settings.json` y los 8 archivos `.pyc` de `__pycache__`.

## 2. Repo de datos — `C:\Users\esteb\Desktop\meteo\estacion_meteorologica_datos`

**3 archivos, los 3 versionados**

```
estacion_meteorologica_datos/
├─ README.md
├─ datos.csv
└─ docs/
   └─ VALIDACION.md
```

## 3. Desarrollo Arduino Nano — `C:\Users\esteb\Desktop\meteo\Test_ArduinoNano_MQTT`

**1 archivo. No es repositorio Git.**

```
Test_ArduinoNano_MQTT/
└─ Test_ArduinoNano_MQTT.ino
```

## 4. Desarrollo ESP32 — `C:\Users\esteb\Desktop\meteo\Test_MQTT`

**2 archivos. No es repositorio Git.**

```
Test_MQTT/
├─ credentials.h        ← secreto local (WiFi/MQTT); no subir al repo
└─ Test_MQTT.ino
```

## Totales

| Ubicación | Archivos | Estado Git |
|---|---:|---|
| `Desktop\estacion_meteo` (código) | 35 | 23 versionados + 12 ignorados/generados |
| `Desktop\meteo\estacion_meteorologica_datos` | 3 | 3 versionados |
| `Desktop\meteo\Test_ArduinoNano_MQTT` | 1 | No es repo |
| `Desktop\meteo\Test_MQTT` | 2 | No es repo |
| **Total** | **41** | — |
