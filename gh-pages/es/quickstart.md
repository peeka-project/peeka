---
layout: default
title: Inicio Rápido
nav_order: 3
---

# Inicio Rápido
{: .no_toc }

Comienza a usar rápidamente las funciones básicas de Peeka en unos simples pasos.
{: .fs-6 .fw-300 }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Primer Ejemplo

### 1. Preparar el programa objetivo

Crea un programa Python simple `demo.py`:

```python
# demo.py
import time
import os

class Calculator:
    def add(self, a, b):
        time.sleep(0.1)  # Simular tiempo de cálculo
        return a + b

    def multiply(self, a, b):
        time.sleep(0.05)
        return a * b

def main():
    calc = Calculator()
    while True:
        result1 = calc.add(1, 2)
        print(f"add(1, 2) = {result1}")

        result2 = calc.multiply(3, 4)
        print(f"multiply(3, 4) = {result2}")

        time.sleep(1)

if __name__ == "__main__":
    print(f"PID del proceso: {os.getpid()}")
    main()
```

### 2. Ejecutar el programa objetivo

```bash
python demo.py
# Salida: PID del proceso: 12345
```

### 3. Adjuntar al proceso

En otra ventana de terminal:

```bash
peeka-cli attach 12345
```

Salida:
```json
{"type":"status","level":"info","message":"Attaching to process 12345"}
{"type":"success","command":"attach","data":{"pid":12345,"socket":"/tmp/peeka_xxx.sock"}}
```

### 4. Observar llamadas a funciones

Observa las llamadas al método `add`:

```bash
peeka-cli watch "demo.Calculator.add" --times 3
```

Salida:
```json
{"type":"event","event":"watch_started","data":{"watch_id":"watch_001","pattern":"demo.Calculator.add"}}
{"type":"observation","watch_id":"watch_001","timestamp":1705586200.123,"func_name":"demo.Calculator.add","args":[1,2],"result":3,"success":true,"duration_ms":100.123,"count":1}
{"type":"observation","watch_id":"watch_001","timestamp":1705586201.123,"func_name":"demo.Calculator.add","args":[1,2],"result":3,"success":true,"duration_ms":100.087,"count":2}
{"type":"observation","watch_id":"watch_001","timestamp":1705586202.123,"func_name":"demo.Calculator.add","args":[1,2],"result":3,"success":true,"duration_ms":100.091,"count":3}
{"type":"event","event":"watch_stopped","data":{"watch_id":"watch_001","reason":"max_count_reached"}}
```

---

## Demostración de Funcionalidades Principales

### Observar Llamadas a Funciones (watch)

#### Observación Básica

```bash
# Observar 5 llamadas
peeka-cli watch "demo.Calculator.add" --times 5

# Observación infinita (presiona Ctrl+C para detener)
peeka-cli watch "demo.Calculator.add"
```

#### Filtrado Condicional

Solo observa llamadas que cumplen condiciones específicas:

```bash
# Solo observa llamadas donde el primer parámetro es mayor que 100
peeka-cli watch "demo.Calculator.multiply" --condition "params[0] > 100"

# Solo observa llamadas que tardan más de 10ms en ejecutarse
peeka-cli watch "demo.Calculator.add" --condition "cost > 10"

# Combinar condiciones
peeka-cli watch "demo.func" --condition "len(params) > 2 and cost > 5"
```

#### Control de Puntos de Observación

```bash
# Observación en la entrada de la función (ver parámetros de entrada)
peeka-cli watch "demo.Calculator.add" --before

# Solo observa cuando tiene éxito
peeka-cli watch "demo.Calculator.add" --success

# Solo observa cuando hay excepción
peeka-cli watch "demo.Calculator.add" --exception
```

### Rastrear Cadena de Llamadas (trace)

Ver la cadena completa de llamadas de una función y el tiempo de consumo de cada llamada:

```bash
peeka-cli trace "demo.Calculator.add" --depth 3 --times 1
```

Salida (estructura de árbol):
```
`---[125.3ms] demo.Calculator.add()
    +---[2.1ms] time.sleep()
    `---[1.2ms] builtins.print()
```

### Rastrear Pila de Llamadas (stack)

Ver quién llamó a la función:

```bash
peeka-cli stack "demo.Calculator.add" --times 1
```

Salida:
```
Thread: MainThread
  File "demo.py", line 15, in main
    result1 = calc.add(1, 2)
  File "demo.py", line 6, in add
    return a + b
```

### Monitoreo de Rendimiento (monitor)

Estadísticas en tiempo real de métricas de rendimiento de funciones:

```bash
peeka-cli monitor "demo.Calculator.add" --interval 5 -c 3
```

Salida:
```json
{"type":"observation","timestamp":1705586200.123,"func_name":"demo.Calculator.add","total":10,"success":10,"fail":0,"avg_rt":100.5,"min_rt":98.2,"max_rt":105.3}
```

---

## Procesamiento de Datos

### Usar jq para procesar la salida

Peeka genera salida en formato JSONL estándar, que se puede integrar fácilmente con herramientas como jq.

#### Extraer datos de observación

```bash
# Solo muestra datos de observación (filtra otros mensajes)
peeka-cli watch "demo.func" | jq 'select(.type == "observation")'

# Solo muestra el valor de retorno de la función
peeka-cli watch "demo.func" | jq 'select(.type == "observation") | .result'

# Muestra parámetros y valor de retorno
peeka-cli watch "demo.func" | jq 'select(.type == "observation") | {args, result}'
```

#### Filtrado y estadísticas

```bash
# Filtrar llamadas lentas (tiempo de ejecución > 10ms)
peeka-cli watch "demo.func" | jq 'select(.type == "observation" and .duration_ms > 10)'

# Estadísticas de tasa de éxito
peeka-cli watch "demo.func" | \
  jq -r 'select(.type == "observation") | if .success then "OK" else "ERROR" end' | \
  uniq -c

# Calcular tiempo de ejecución promedio
peeka-cli watch "demo.func" --times 100 | \
  jq 'select(.type == "observation") | .duration_ms' | \
  awk '{sum+=$1; count++} END {print "avg:", sum/count, "ms"}'
```

#### Guardar en archivo

```bash
# Guardar datos de observación
peeka-cli watch "demo.func" --times 1000 > observations.jsonl

# Análisis posterior
cat observations.jsonl | jq 'select(.type == "observation" and .success == false)'
```

---

## Usar la Interfaz TUI

Peeka proporciona una interfaz TUI interactiva basada en Textual.

### Iniciar TUI

```bash
peeka
```

### Funcionalidades TUI

1. **Selector de procesos** - Descubre y selecciona automáticamente el proceso objetivo
2. **Panel Dashboard** (`1`) - Muestra información del proceso en tiempo real
3. **Vista Watch** (`2`) - Observación interactiva de funciones
4. **Vista Trace** (`3`) - Visualización del árbol de llamadas
5. **Vista Stack** (`4`) - Rastreo de pila de llamadas
6. **Vista Monitor** (`5`) - Monitoreo de rendimiento
7. **Vista Memory** (`6`) - Análisis de memoria
8. **Vista Logger** (`7`) - Gestión de registros
9. **Vista Inspect** (`8`) - Inspección de objetos
10. **Vista Threads** (`9`) - Análisis de hilos
11. **Vista Top** (`0`) - Muestreo de puntos calientes de funciones

### Atajos de Teclado TUI

| Atajo | Función |
|-------|---------|
| `1` | Cambiar a Dashboard |
| `2` | Cambiar a vista Watch |
| `3` | Cambiar a vista Trace |
| `4` | Cambiar a vista Stack |
| `5` | Cambiar a vista Monitor |
| `6` | Cambiar a vista Memory |
| `7` | Cambiar a vista Logger |
| `8` | Cambiar a vista Agent Log |
| `9` | Cambiar a vista Threads |
| `0` | Cambiar a vista Top |
| `?` | Mostrar ayuda |
| `q` | Salir |

Para más detalles sobre el uso de TUI, consulta [Guía de Uso de TUI]({% link es/tui.md %}).

---

## Escenarios Prácticos de Aplicación

### Escenario 1: Diagnosticar interfaz lenta

```bash
# Observar función de procesamiento API, encontrar llamadas lentas
peeka-cli watch "app.api.handle_request" --condition "cost > 1000"

# Rastrear la cadena completa de llamadas de la llamada lenta
peeka-cli trace "app.api.handle_request" --condition "cost > 1000" --depth 5
```

### Escenario 2: Localizar causa de excepción

```bash
# Solo observa situaciones de excepción
peeka-cli watch "app.service.process" --exception

# Ver la pila de llamadas cuando ocurre la excepción
peeka-cli stack "app.service.process" --condition "throwExp != None"
```

### Escenario 3: Monitorear rendimiento de funciones

```bash
# Estadísticas de rendimiento cada 10 segundos
peeka-cli monitor "app.service.critical_func" --interval 10

# Combinar con jq para alertas en tiempo real
peeka-cli monitor "app.service.critical_func" --interval 5 | \
  jq 'select(.type == "observation" and .avg_rt > 100) | "Alerta: promedio RT = \(.avg_rt)ms"'
```

### Escenario 4: Verificar parámetros

```bash
# Verificar llamadas con valores de parámetros específicos
peeka-cli watch "app.service.process" --condition "params[0] == 'debug_value'"

# Ver distribución de parámetros
peeka-cli watch "app.service.process" --times 100 | \
  jq 'select(.type == "observation") | .args[0]' | \
  sort | uniq -c
```

---

## Mejores Prácticas

### 1. Usar filtrado condicional para reducir ruido

En entornos de producción las llamadas a funciones son frecuentes, usa filtrado condicional para observar solo llamadas clave:

```bash
# ✅ Recomendado: solo observa llamadas lentas
peeka-cli watch "func" --condition "cost > 100"

# ❌ No recomendado: observa todas las llamadas (gran volumen de datos)
peeka-cli watch "func"
```

### 2. Limitar el número de observaciones

Evita que la observación prolongada genere demasiados datos:

```bash
# ✅ Recomendado: observa un número fijo de veces
peeka-cli watch "func" --times 10

# ❌ No recomendado: observación infinita
peeka-cli watch "func"  # Puede generar una gran cantidad de datos
```

### 3. Usar formato JSONL para facilitar el análisis

Guarda los datos de observación como JSONL para facilitar el análisis posterior:

```bash
# Recolectar datos
peeka-cli watch "func" --times 1000 > data.jsonl

# Análisis offline
cat data.jsonl | jq 'select(.type == "observation") | {duration_ms, success}' | \
  jq -s 'group_by(.success) | map({success: .[0].success, count: length})'
```

### 4. Diagnóstico por capas

De grueso a fino, localiza problemas paso a paso:

```bash
# 1. Primero usa monitor para entender el rendimiento general
peeka-cli monitor "app.api.*" --interval 10

# 2. Después de encontrar anomalías usa watch para observar detalles
peeka-cli watch "app.api.slow_func" --condition "cost > 100"

# 3. Usa trace para rastrear la cadena completa de llamadas
peeka-cli trace "app.api.slow_func" --depth 5
```

---

## Siguientes Pasos

- [Referencia de Comandos]({% link es/commands/index.md %}) - Conoce el uso detallado de todos los comandos
- [Ejemplos y Tutoriales]({% link es/examples.md %}) - Más escenarios prácticos de aplicación
- [Diseño de Arquitectura]({% link es/architecture.md %}) - Conoce los principios de diseño de Peeka
- [Resolución de Problemas]({% link es/troubleshooting.md %}) - Soluciones cuando encuentras problemas
