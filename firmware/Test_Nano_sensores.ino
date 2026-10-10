#include <Wire.h>
#include <Adafruit_BMP085.h>   // Driver correcto: el chip es un BMP180 (confirmado)
#include <DHT.h>
#include <ArduinoJson.h>

// ============================================================
// NODO DE ADQUISICIÓN — Arduino Nano
// Mide y transmite JSON por serie al ESP32 (9600 baud).
// Validación en el origen: un valor imposible se reporta como
// null, nunca como número falso.
// ============================================================

#define DHTPIN 2
#define DHTTYPE DHT22

DHT dht(DHTPIN, DHTTYPE);
Adafruit_BMP085 bmp;

// Cadencia de muestreo. El DHT22 exige >= 2000 ms entre lecturas.
const unsigned long INTERVALO_MUESTREO_MS = 3000;

// Rangos físicos plausibles en la ubicación de la estación.
// No son calibración: descartan lo imposible, no corrigen sesgo.
const float T_MIN = -10.0,  T_MAX = 50.0;    // °C
const float P_MIN = 900.0,  P_MAX = 1100.0;  // hPa a nivel de la estación
const float H_MIN = 5.0,    H_MAX = 100.0;   // %HR (el DHT22 no es fiable < 5 %)

bool bmp_ok = false;

unsigned long ultimaMedicionMs = 0;

// Agrega la clave solo si la lectura existe y es plausible;
// en caso contrario reporta null explícito ("sin dato válido").
void agregarSiValido(JsonDocument& doc, const char* clave,
                     float valor, float minimo, float maximo) {
    if (!isnan(valor) && valor >= minimo && valor <= maximo) {
        doc[clave] = valor;
    } else {
        doc[clave] = nullptr;
    }
}

void setup() {
    Serial.begin(9600);          // Hacia el ESP32
    Wire.begin();
    dht.begin();

    bmp_ok = bmp.begin();        // false si el BMP no responde en el I2C
    if (!bmp_ok) {
        Serial.println("{\"error\":\"BMP180 no detectado en I2C\"}");
    }
}

void loop() {
    unsigned long ahora = millis();

    // Comparación segura frente al desbordamiento de millis()
    if (ahora - ultimaMedicionMs < INTERVALO_MUESTREO_MS) return;
    ultimaMedicionMs = ahora;

    float t_bmp   = bmp_ok ? bmp.readTemperature()       : NAN;
    float presion = bmp_ok ? bmp.readPressure() / 100.0F : NAN;   // Pa → hPa
    float t_dht   = dht.readTemperature();
    float humedad = dht.readHumidity();

    JsonDocument doc;   // ArduinoJson 7: tamaño autogestionado

    agregarSiValido(doc, "t_bmp",   t_bmp,   T_MIN, T_MAX);
    agregarSiValido(doc, "presion", presion, P_MIN, P_MAX);
    agregarSiValido(doc, "t_dht",   t_dht,   T_MIN, T_MAX);
    agregarSiValido(doc, "humedad", humedad, H_MIN, H_MAX);

    // Salud de los sensores: el backend puede alarmar con esto
    doc["bmp_ok"] = bmp_ok;
    doc["dht_ok"] = !isnan(t_dht) && !isnan(humedad);

    serializeJson(doc, Serial);
    Serial.println();            // '\n' delimita cada mensaje
}
