# Firmware — Estación Meteorológica IoT

Firmware de los dos nodos de adquisición. Ambos sketches comparten el
protocolo de intercambio: JSON de una línea por serial, delimitado por
`\n`.

## Arquitectura de hardware

```
BMP180 (I2C) ──┐
DHT22 (GPIO 2) ┴→ Arduino Nano ──UART 9600──→ ESP32 ──Wi-Fi/MQTT──→ Broker
```

- El **Nano** es el nodo de adquisición: mide y valida. No tiene red.
- El **ESP32** es la pasarela: enriquece (RSSI, IP, `ts_epoch` por NTP),
  bufferiza en flash interna y publica por MQTT.

## Sketches

| Archivo | Placa | Función |
|---|---|---|
| `Test_Nano_sensores.ino` | Arduino Nano | Lectura BMP180 + DHT22, validación de rangos físicos, reporte de salud (`bmp_ok`, `dht_ok`). Cadencia: 3 s (mínimo del DHT22: 2 s) |
| `Test_MQTT_buffer.ino` | ESP32 | Pasarela serial→MQTT con **buffer local en LittleFS** (log + cursor), NTP, reconexiones no bloqueantes |

## Configuración previa al flasheo

1. Copiar `credentials.h.example` → `credentials.h` y completar credenciales
   Wi-Fi. **`credentials.h` no se sube al repositorio** (está en `.gitignore`).
2. `MQTT_SERVER` en el sketch del ESP32 debe apuntar a la IP del equipo
   donde corre el broker (Mosquitto). Recomendado: **reserva DHCP** en el
   router para que la IP del broker nunca cambie.
3. En Arduino IDE, para el ESP32: Partition Scheme = **"Default 4MB with
   spiffs"** (necesario: ahí vive el buffer LittleFS).
4. Para el Nano: si el flasheo falla con error de sincronización, probar
   la variante de placa **"Arduino Nano (Old Bootloader)"** (común en
   clones).

## Cableado

| Nano | ESP32 | Nota |
|---|---|---|
| TX (pin 1) | RX2 = GPIO 16 | Cruzado: TX de uno → RX del otro |
| RX (pin 0) | TX2 = GPIO 17 | |
| GND | GND | **Obligatorio**: referencia común |

- BMP180: I2C (SDA/SCL a A4/A5 del Nano), alimentación 3.3/5 V según módulo
- DHT22: datos al GPIO 2 del Nano, resistencia pull-up de 10 kΩ entre
  datos y VCC (muchos módulos la traen integrada)

## Buffer del ESP32 (LittleFS)

Log apend-only (`/buffer.log`) + cursor (`/cursor.txt`) con la posición
del próximo mensaje sin confirmar. Flujo:

```
medición → encolar en flash → publish() → si OK: avanzar cursor
                                └→ si falla: el mensaje queda en el buffer
```

- **Capacidad:** ~900 KB ≈ 4.500 mediciones ≈ 3,75 h sin conexión (a 3 s)
- **Política de buffer lleno:** se descarta la medición NUEVA (FIFO — la
  continuidad del histórico tiene prioridad sobre la frescura)
- **Compactación:** al superar 256 KB de tramo confirmado, se reescribe
  el archivo sin el tramo ya enviado
- **Timestamp:** `ts_epoch` en UTC solo si NTP sincronizó (`horaValida()`
  verifica el año); si no, `null` explícito — nunca una hora falsa
- El buffer **sobrevive** reinicios y flasheos (partición LittleFS
  independiente del firmware)

## Dependencias (versiones usadas)

| Librería | Versión | Uso |
|---|---|---|
| ArduinoJson | 7.4.3 | Ambos sketches (API `JsonDocument`) |
| PubSubClient | 2.8 | ESP32 (MQTT) |
| Adafruit BMP085 | 1.x | Nano (driver del BMP180) |
| DHT sensor library | 1.4.x | Nano (DHT22) |

## Verificación post-flasheo

1. Monitor serie del Nano (9600): un JSON por línea cada 3 s con
   `bmp_ok`/`dht_ok`
2. Monitor serie del ESP32 (115200): `[FS] LittleFS OK`, `[MQTT] Conectado`,
   encolados y publicaciones
3. `mosquitto_sub -t "estacion/telemetria" -v`: los JSON con `ts_epoch`
   razonable (~1.79e9)
4. Prueba de resiliencia: detener Mosquitto (`net stop mosquitto`),
   verificar acumulación en el buffer, reactivar y confirmar el reenvío
   con `ts_adquisicion` original en la base de datos
