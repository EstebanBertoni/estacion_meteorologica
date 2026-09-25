# 🌦️ Estación Meteorológica IoT de Bajo Costo con Predicción Microclimática mediante IA

> Sistema de monitoreo ambiental basado en ESP32, almacenamiento de series temporales y aprendizaje automático para el análisis y la predicción de condiciones meteorológicas a corto plazo.

## 📌 Descripción

Este proyecto consiste en el desarrollo de una **estación meteorológica IoT de bajo costo**, capaz de adquirir, almacenar, transmitir y analizar variables ambientales en tiempo real.

El sistema combina **electrónica, sistemas embebidos, Internet de las Cosas (IoT), procesamiento de datos y Machine Learning** en una arquitectura modular diseñada para ser escalable y adaptable a distintos entornos.

La estación utiliza un **ESP32** como nodo de adquisición, conectado a sensores ambientales para obtener variables como:

* 🌡️ Temperatura
* 💧 Humedad relativa
* 🌡️ Presión atmosférica
* 📏 Altitud estimada a partir de presión
* 💠 Punto de rocío
* 💧 Humedad absoluta
* 📉 Tendencia de presión atmosférica

Los datos son posteriormente procesados mediante un backend desarrollado en **Python**, almacenados como series temporales y utilizados para generar variables derivadas que alimentan un modelo de aprendizaje automático.

El objetivo final es desarrollar un sistema capaz de **identificar patrones microclimáticos y estimar la probabilidad de determinados eventos meteorológicos a corto plazo**, con un horizonte de predicción de aproximadamente 1 a 3 horas.

---

## 🎯 Objetivos

### Objetivo general

Desarrollar un sistema IoT de bajo costo para la **observación y análisis de variables meteorológicas locales**, incorporando técnicas de Machine Learning para la predicción de condiciones microclimáticas a corto plazo.

### Objetivos específicos

* Diseñar un nodo de adquisición basado en ESP32.
* Obtener mediciones ambientales mediante sensores de bajo costo.
* Implementar mecanismos de validación y detección de lecturas anómalas.
* Permitir el funcionamiento ante interrupciones temporales de conectividad.
* Implementar almacenamiento temporal local de datos.
* Transmitir las mediciones hacia un servidor mediante protocolos adecuados para IoT.
* Diseñar una API para la recepción y consulta de datos.
* Almacenar las mediciones en una estructura optimizada para series temporales.
* Implementar un pipeline de procesamiento y limpieza de datos.
* Generar variables meteorológicas derivadas mediante Feature Engineering.
* Entrenar y evaluar modelos de Machine Learning.
* Desarrollar una interfaz web para monitoreo y visualización.
* Evaluar el desempeño del sistema mediante datos reales.

---

## 🏗️ Arquitectura

La arquitectura propuesta sigue un modelo de adquisición en el borde (*Edge Computing*), procesamiento centralizado y visualización web.

```text
┌─────────────────────────────┐
│       SENSORES              │
│                             │
│ BME280 / DHT22              │
│ Temp. · Humedad · Presión   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│           ESP32             │
│                             │
│ • Adquisición               │
│ • Validación                │
│ • Timestamp                 │
│ • Buffer local              │
│ • Gestión de conectividad   │
└──────────────┬──────────────┘
               │
          MQTT / HTTP
               │
               ▼
┌─────────────────────────────┐
│       BACKEND PYTHON        │
│                             │
│ FastAPI / Flask             │
│ • API REST                  │
│ • Validación                │
│ • Ingesta                   │
│ • Logging                   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      BASE DE DATOS          │
│                             │
│ SQLite / TimescaleDB        │
│                             │
│ Series temporales           │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│     DATA PIPELINE            │
│                             │
│ Python + Pandas             │
│ • Limpieza                  │
│ • Resampling                │
│ • Feature Engineering       │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│       MACHINE LEARNING      │
│                             │
│ scikit-learn / XGBoost      │
│                             │
│ Predicción 1–3 horas        │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│         DASHBOARD           │
│                             │
│ HTML · CSS · JavaScript     │
│                             │
│ Monitoreo + análisis + IA   │
└─────────────────────────────┘
```

---

## 🔧 Tecnologías

### Hardware

* **ESP32**
* **BME280** y/o **DHT22**
* Tarjeta SD o memoria Flash para almacenamiento temporal
* Fuente de alimentación adecuada para operación continua

### Firmware

* C++
* Arduino Framework
* ESP32
* I²C
* Wi-Fi
* MQTT / HTTP

### Backend

* Python
* FastAPI / Flask
* REST API
* JSON

### Datos

* Pandas
* SQLite
* TimescaleDB
* Series temporales

### Inteligencia Artificial

* Python
* scikit-learn
* XGBoost
* Feature Engineering
* Validación temporal

### Frontend

* HTML5
* CSS3
* JavaScript
* Flexbox
* CSS Grid
* Diseño responsive
* Font Awesome

---

## 📊 Procesamiento de datos

Las mediciones obtenidas directamente de los sensores no constituyen necesariamente las variables utilizadas por el modelo.

El sistema genera variables derivadas para obtener una representación más completa del estado atmosférico.

Entre ellas:

### Punto de rocío

Estimación de la temperatura a la cual el aire alcanza la saturación.

### Humedad absoluta

Cantidad de vapor de agua presente en un volumen determinado de aire.

### Tendencia barométrica

Se analiza la variación de la presión atmosférica durante un período determinado.

Por ejemplo:

```text
ΔP/Δt = P(t) - P(t-3h)
```

Esta variable permite representar cambios recientes en la presión en lugar de utilizar únicamente su valor instantáneo.

---

## 🤖 Machine Learning

Uno de los objetivos principales del proyecto es investigar la posibilidad de utilizar modelos de Machine Learning para identificar patrones asociados a cambios meteorológicos locales.

El pipeline previsto es:

```text
Datos históricos
       │
       ▼
Limpieza
       │
       ▼
Feature Engineering
       │
       ▼
Construcción del dataset
       │
       ▼
Entrenamiento
       │
       ▼
Validación temporal
       │
       ▼
Evaluación
       │
       ▼
Predicción
```

Se contempla utilizar modelos como:

* Regresión logística como baseline.
* Random Forest.
* XGBoost.
* Otros modelos que puedan resultar apropiados durante la experimentación.

El objetivo no es únicamente obtener una métrica elevada, sino evaluar si las predicciones presentan **utilidad real para anticipar cambios meteorológicos locales**.

Por este motivo se consideran métricas como:

* Precision
* Recall
* F1-Score
* PR-AUC
* Matriz de confusión
* Calibración de probabilidades

La validación se realizará respetando el orden temporal de las observaciones para reducir el riesgo de *data leakage*.

---

## 📡 Resiliencia y operación offline

Una estación IoT instalada en un entorno real no puede depender completamente de la disponibilidad de Internet.

Por este motivo, el diseño contempla un mecanismo de almacenamiento temporal:

```text
                 ┌─────────────┐
                 │   Sensores  │
                 └──────┬──────┘
                        │
                        ▼
                     ESP32
                        │
              ┌─────────┴─────────┐
              │                   │
           Wi-Fi OK            Wi-Fi OFF
              │                   │
              ▼                   ▼
          Transmitir          Guardar localmente
              │                   │
              │              ┌────┴────┐
              │              │ Buffer  │
              │              └────┬────┘
              │                   │
              └──────────┬────────┘
                         │
                  Conexión recuperada
                         │
                         ▼
                    Sincronización
```

De esta manera, una interrupción de conectividad no debería implicar automáticamente la pérdida de las mediciones.

---

## 🖥️ Dashboard

La interfaz web está concebida como un **centro de monitoreo microclimático**, en lugar de una aplicación meteorológica convencional.

El dashboard busca presentar tres niveles de información:

### 1. Monitoreo

¿Qué está ocurriendo actualmente?

```text
Temperatura
Humedad
Presión
Punto de rocío
Estado de la estación
```

### 2. Análisis

¿Cómo evolucionaron las variables?

```text
Gráficos históricos
Tendencias
Variaciones
Eventos detectados
```

### 3. Predicción

¿Qué podría ocurrir durante las próximas horas?

```text
Probabilidad estimada
Horizonte temporal
Variables relevantes
Estado del modelo
```

La interfaz también contempla información relacionada con la salud del nodo IoT, como conectividad, sensores y datos pendientes de sincronización.

---

## 🚧 Estado actual

El proyecto se encuentra en desarrollo.

### Implementado

* [x] Prototipo físico básico
* [x] Adquisición de datos mediante sensores
* [x] Lectura mediante ESP32
* [x] Persistencia inicial de mediciones
* [x] Comunicación con backend
* [x] Endpoint para consulta de datos
* [x] Dashboard web básico
* [x] Visualización de temperatura, humedad, presión y altitud

### En desarrollo

* [ ] Arquitectura definitiva de almacenamiento
* [ ] Buffer local y sincronización
* [ ] Sistema de detección de anomalías
* [ ] Pipeline completo de Feature Engineering
* [ ] Dataset histórico
* [ ] Entrenamiento del modelo
* [ ] Validación temporal
* [ ] Predicción meteorológica 1–3 h
* [ ] Sistema de alertas
* [ ] Dashboard avanzado
* [ ] Evaluación frente a datos meteorológicos externos

---

## 🔬 Enfoque experimental

El proyecto no pretende reemplazar una estación meteorológica profesional ni proporcionar pronósticos meteorológicos oficiales.

Su finalidad es **investigar hasta qué punto un sistema de sensores de bajo costo, combinado con procesamiento de datos y Machine Learning, puede capturar y anticipar patrones microclimáticos locales**.

Las limitaciones de precisión de los sensores, la disponibilidad de datos históricos, la representatividad espacial y la naturaleza poco frecuente de determinados eventos meteorológicos serán consideradas durante la evaluación.

---

## 🌱 Aplicaciones potenciales

Una arquitectura de este tipo podría utilizarse como base para diferentes aplicaciones:

* Agricultura de precisión.
* Monitoreo ambiental.
* Investigación microclimática.
* Gestión de riesgos meteorológicos.
* Sistemas de alerta temprana.
* Educación tecnológica.
* Redes distribuidas de estaciones meteorológicas.
* Integración con sistemas de Protección Civil.

El proyecto también busca demostrar cómo tecnologías de bajo costo pueden combinarse con análisis de datos e Inteligencia Artificial para construir sistemas de observación ambiental escalables.

---

## 🎓 Contexto académico

Proyecto desarrollado en el marco de la **Tecnicatura Universitaria en Programación (TUP) de la Universidad Tecnológica Nacional — Facultad Regional Rafaela**.

El proyecto integra conocimientos de:

* Programación.
* Sistemas embebidos.
* Bases de datos.
* Redes.
* Desarrollo web.
* Internet de las Cosas.
* Análisis de datos.
* Inteligencia Artificial.

---

## 👨‍💻 Autor

**Esteban Bertoni**

Tecnicatura Universitaria en Programación
Universidad Tecnológica Nacional — Facultad Regional Rafaela

---

## 📌 Próximos pasos

El desarrollo continuará priorizando la confiabilidad de la adquisición y almacenamiento de datos antes de avanzar hacia modelos predictivos más complejos.

La evolución prevista es:

```text
MEDIR
  ↓
ALMACENAR
  ↓
TRANSMITIR
  ↓
ANALIZAR
  ↓
APRENDER
  ↓
PREDECIR
  ↓
ALERTAR
```

El objetivo final es transformar un prototipo de estación meteorológica en una **plataforma IoT de observación y análisis microclimático reproducible, escalable y basada en datos reales**.
