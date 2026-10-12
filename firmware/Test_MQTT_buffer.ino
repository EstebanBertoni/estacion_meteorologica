#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <time.h>
#include "credentials.h"

// ============================================================
// ESTACIÓN METEOROLÓGICA — ESP32 con BUFFER LOCAL
//
// Principio de resiliencia:
//   medición → ALMACENAR en flash → transmitir → confirmar
//   → avanzar cursor.
//
// El mensaje NUNCA se borra antes de que publish() confirme.
// Si el broker o el Wi-Fi caen, las mediciones quedan en el
// buffer y se reenvían (en orden, con su ts_epoch original)
// cuando todo vuelve.
// ============================================================

// Configuración de red y MQTT
// La IP del broker es configuración de entorno: vive en credentials.h
// (MQTT_SERVER_ADDR). Las migraciones de red no tocan el sketch.
const char* MQTT_SERVER = MQTT_SERVER_ADDR;
const int   MQTT_PORT   = 1883;
const char* MQTT_TOPIC  = "estacion/telemetria";

// NTP (epoch UTC: la hora local la calcula el backend)
const char* NTP_SERVER_1 = "pool.ntp.org";
const char* NTP_SERVER_2 = "time.nist.gov";

// ------------------------------------------------------------
// BUFFER (LittleFS): log apend-only + cursor
//   /buffer.log  : los JSON encolados, uno por línea
//   /cursor.txt  : offset del próximo mensaje SIN confirmar
//   /buffer.tmp  : temporal para la compactación
// ------------------------------------------------------------

const char* RUTA_BUFFER = "/buffer.log";
const char* RUTA_CURSOR = "/cursor.txt";
const char* RUTA_TEMP   = "/buffer.tmp";

// Política de tamaño: LittleFS tiene ~1.5 MB en el esquema por
// defecto. Con ~200 bytes por medición, 900 KB ≈ 4.500 mediciones
// ≈ 3.75 h de autonomía sin conexión a cadencia de 3 s.
const size_t BUFFER_MAX_BYTES      = 900 * 1024;
// Se compacta (se borra el tramo ya enviado) a partir de este consumo.
const size_t COMPACTAR_UMBRAL      = 256 * 1024;
// Máximo de publicaciones por vuelta de loop (evita monopolizarlo).
const uint8_t MAX_POR_LOOP         = 5;

WiFiClient espClient;
PubSubClient mqttClient(espClient);

unsigned long ultimoIntentoWiFi = 0;
unsigned long ultimoIntentoMQTT = 0;

// ------------------------------------------------------------
// HORA (NTP)
// ------------------------------------------------------------

void iniciarRelojNTP() {
    configTime(0, 0, NTP_SERVER_1, NTP_SERVER_2);
}

// No stampar con hora falsa: verificar el año antes de usar time().
bool horaValida() {
    time_t ahora = time(nullptr);
    struct tm info;
    gmtime_r(&ahora, &info);
    return (info.tm_year + 1900) >= 2024;
}

// ------------------------------------------------------------
// BUFFER: cursor, encolado, publicación, compactación
// ------------------------------------------------------------

uint32_t leerCursor() {
    File f = LittleFS.open(RUTA_CURSOR, "r");
    if (!f) return 0;
    uint32_t cursor = (uint32_t) f.parseInt();
    f.close();
    return cursor;
}

void guardarCursor(uint32_t offset) {
    File f = LittleFS.open(RUTA_CURSOR, "w");
    if (!f) {
        Serial.println("[BUFFER] ERROR: no se pudo guardar el cursor");
        return;
    }
    f.print(offset);
    f.close();
}

// Agrega una medición al final del log. Si el buffer está lleno,
// se descarta la medición NUEVA (política FIFO: el histórico vale
// más que lo último — para una serie temporal la continuidad manda).
bool encolar(const String& json) {
    File f = LittleFS.open(RUTA_BUFFER, "r");
    size_t tamano = f ? f.size() : 0;
    if (f) f.close();

    if (tamano >= BUFFER_MAX_BYTES) {
        Serial.println("[BUFFER] LLENO — medición descartada");
        return false;
    }

    f = LittleFS.open(RUTA_BUFFER, "a");
    if (!f) {
        Serial.println("[BUFFER] ERROR: no se pudo abrir para escribir");
        return false;
    }
    f.print(json);
    f.print('\n');
    f.close();
    return true;
}

// Publica el próximo mensaje sin confirmar. Solo avanza el cursor
// si publish() devolvió true. Devuelve false si no hay más (vacío)
// o si la publicación falló (el mensaje queda para el próximo intento).
bool publicarSiguienteDelBuffer() {
    uint32_t cursor = leerCursor();

    File f = LittleFS.open(RUTA_BUFFER, "r");
    if (!f) return false;

    if (cursor >= f.size()) {
        f.close();
        return false;   // buffer al día
    }

    f.seek(cursor);
    String linea = f.readStringUntil('\n');
    uint32_t nuevoCursor = f.position();   // justo después del '\n'
    f.close();

    linea.trim();
    if (linea.length() == 0) {
        guardarCursor(nuevoCursor);
        return true;
    }

    // Longitud explícita: evita truncamientos por bytes nulos.
    if (mqttClient.publish(MQTT_TOPIC, linea.c_str(), linea.length())) {
        guardarCursor(nuevoCursor);
        return true;
    }

    Serial.println("[MQTT] publish() falló — el mensaje queda en el buffer");
    return false;
}

// Reescribe el archivo dejando solo lo pendiente y resetea el cursor.
// Se ejecuta solo cuando no hay nada por publicar, para no interferir.
void compactarBuffer() {
    uint32_t cursor = leerCursor();

    File origen = LittleFS.open(RUTA_BUFFER, "r");
    if (!origen) return;

    if (cursor >= origen.size()) {
        // Nada pendiente: vaciar el log directamente.
        origen.close();
        LittleFS.remove(RUTA_BUFFER);
        guardarCursor(0);
        Serial.println("[BUFFER] Compactado (vacío)");
        return;
    }

    origen.seek(cursor);
    File destino = LittleFS.open(RUTA_TEMP, "w");
    if (!destino) {
        origen.close();
        return;
    }

    // Copia por bloques (mucho más rápido que byte a byte)
    uint8_t bloque[512];
    while (origen.available()) {
        size_t leidos = origen.read(bloque, sizeof(bloque));
        destino.write(bloque, leidos);
    }
    origen.close();
    destino.close();

    LittleFS.remove(RUTA_BUFFER);
    LittleFS.rename(RUTA_TEMP, RUTA_BUFFER);
    guardarCursor(0);

    Serial.println("[BUFFER] Compactado: tramo confirmado eliminado");
}

// ------------------------------------------------------------
// WI-FI Y MQTT (reconexión NO bloqueante)
// ------------------------------------------------------------

void conectarWiFiInicial() {
    delay(10);
    Serial.println();
    Serial.print("Conectando a Wi-Fi: ");
    Serial.println(WIFI_SSID);

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }

    Serial.println("\n¡Wi-Fi Conectado!");
    Serial.print("IP asignada al ESP32: ");
    Serial.println(WiFi.localIP());
}

void setup() {
    Serial.begin(115200);

    // RX2 = GPIO 16, TX2 = GPIO 17 (Arduino Nano a 9600 baud)
    Serial2.begin(9600, SERIAL_8N1, 16, 17);

    conectarWiFiInicial();
    iniciarRelojNTP();

    // begin(true): formatea la partición si el montaje falla.
    // Ojo: eso borra el buffer — es el caso de flash corrupta.
    if (!LittleFS.begin(true)) {
        Serial.println("[FS] ERROR CRÍTICO: no hay buffer disponible");
    } else {
        Serial.printf("[FS] LittleFS OK. Total: %u KB, usado: %u KB\n",
                      LittleFS.totalBytes() / 1024,
                      LittleFS.usedBytes() / 1024);
    }

    mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
    mqttClient.setBufferSize(512);
}

void loop() {
    unsigned long ahora = millis();

    // --------------------------------------------------------
    // Reconexiones NO bloqueantes: el loop sigue corriendo y
    // el buffer acumula mientras tanto. Este es el cambio clave
    // respecto a las versiones anteriores.
    // --------------------------------------------------------

    if (WiFi.status() != WL_CONNECTED && ahora - ultimoIntentoWiFi > 5000) {
        ultimoIntentoWiFi = ahora;
        Serial.println("[WIFI] Reconectando...");
        WiFi.disconnect();
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    }

    if (!mqttClient.connected() && ahora - ultimoIntentoMQTT > 5000) {
        ultimoIntentoMQTT = ahora;
        String clientId = "ESP32_Estacion_";
        clientId += String((uint32_t)ESP.getEfuseMac(), HEX);

        if (mqttClient.connect(clientId.c_str())) {
            Serial.println("[MQTT] Conectado");
        } else {
            Serial.print("[MQTT] Fallo, rc=");
            Serial.println(mqttClient.state());
        }
    }

    mqttClient.loop();

    // --------------------------------------------------------
    // 1. Recibir del Nano, enriquecer y ENCOLAR (siempre se
    //    almacena primero; publicar es un paso aparte)
    // --------------------------------------------------------

    if (Serial2.available() > 0) {
        String payload = Serial2.readStringUntil('\n');
        payload.trim();

        if (payload.length() > 0) {
            JsonDocument doc;
            DeserializationError error = deserializeJson(doc, payload);

            if (!error) {
                doc["rssi"]     = WiFi.RSSI();
                doc["ip_esp32"] = WiFi.localIP().toString();
                doc["red_ssid"] = WiFi.SSID();

                if (horaValida()) {
                    doc["ts_epoch"] = (long long)time(nullptr);
                } else {
                    doc["ts_epoch"] = nullptr;
                }

                String json;
                serializeJson(doc, json);

                if (encolar(json)) {
                    Serial.print("[BUFFER] Encolado (");
                    Serial.print(lecturaCursorPendiente());
                    Serial.print(" pendientes): ");
                    Serial.println(json);
                }
            } else {
                Serial.print("Error al parsear JSON del Nano: ");
                Serial.println(error.c_str());
            }
        }
    }

    // --------------------------------------------------------
    // 2. Publicar desde el buffer (orden FIFO, hasta 5 por loop)
    //    Solo si hay conexión. Los fallos no avanzan el cursor.
    // --------------------------------------------------------

    if (mqttClient.connected()) {
        for (uint8_t i = 0; i < MAX_POR_LOOP; i++) {
            if (!publicarSiguienteDelBuffer()) break;
        }

        // 3. Compactación: solo cuando el buffer está al día
        if (leerCursor() >= COMPACTAR_UMBRAL) {
            compactarBuffer();
        }
    }
}

// Cantidad de bytes pendientes de confirmación (para el log)
uint32_t lecturaCursorPendiente() {
    uint32_t cursor = leerCursor();
    File f = LittleFS.open(RUTA_BUFFER, "r");
    if (!f) return 0;
    uint32_t pendiente = (f.size() > cursor) ? (f.size() - cursor) : 0;
    f.close();
    return pendiente;
}
