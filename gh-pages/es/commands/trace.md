---
layout: default
title: trace
parent: Referencia de Comandos
nav_order: 3
---

# trace - Rastrear cadena de llamadas
{: .no_toc }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

## Introducción

El comando `trace` se usa para rastrear la cadena de llamadas completa y el tiempo de ejecución de funciones Python, mostrando la jerarquía de llamadas de métodos en una estructura de árbol. Esta es una potente herramienta de análisis de rendimiento y diagnóstico que ayuda a los desarrolladores a identificar rápidamente cuellos de botella de rendimiento y comprender las rutas de ejecución del código.

El comando `trace` de Peeka proporciona potentes capacidades de análisis de rendimiento y diagnóstico para aplicaciones Python.

## Uso en TUI

En modo TUI, presiona la tecla **`3`** para cambiar a la **Vista Trace**, que proporciona las siguientes características interactivas:

- **Entrada de Patrón**: Soporta autocompletado de nombres de funciones (obtenido en tiempo real desde el proceso objetivo)
- **Configuración de Parámetros**: Configuración visual de profundidad, número de observaciones, expresiones condicionales, skip-builtin
- **Visualización de Árbol de Llamadas**: Muestra cadenas de llamadas como estructura de árbol interactiva, expandible/colapsable
- **Temporización con Codificación de Colores**:
  - 🟢 Verde: < 10ms (rápido)
  - 🟡 Amarillo: 10-100ms (medio)
  - 🔴 Rojo: >= 100ms (lento)
- **Operaciones Rápidas**:
  - Presiona Enter después de ingresar el patrón para iniciar el rastreo
  - Presiona Enter para expandir/colapsar nodos
  - Presiona `c` para limpiar registros de rastreo
  - Presiona Delete para eliminar el registro seleccionado

**Comandos CLI equivalentes**: Todos los ejemplos a continuación usan comandos CLI para demostración. TUI proporciona la misma funcionalidad con una interfaz gráfica.

## Escenarios de Uso

- **Identificación de cuellos de botella de rendimiento**: Encuentra rápidamente llamadas lentas a través de datos de temporización
- **Análisis de cadena de llamadas**: Comprender las relaciones de llamada internas de funciones y flujos de ejecución
- **Rastreo de rutas de ejecución de código**: Observar rutas de ejecución de código bajo diferentes condiciones
- **Análisis de temporización de sub-funciones**: Analizar la distribución de tiempo entre sub-funciones
- **Diagnóstico de llamadas recursivas**: Rastrear profundidad de llamadas recursivas y distribución de tiempo

## Formato del Comando

```bash
peeka-cli attach <pid>    # Primero adjuntar al proceso objetivo
peeka-cli trace <pattern> [options]
```

### Parámetros

| Parámetro | Descripción | Valor por defecto | Ejemplo |
|-----------|-------------|-------------------|---------|
| `pattern` | Patrón de coincidencia de función | - | `module.Class.method` |
| `-d, --depth` | Profundidad de rastreo (niveles máximos de llamada) | `3` | `-d 5` |
| `-n, --times` | Número de observaciones (-1 para ilimitado) | `-1` | `-n 10` |
| `--condition` | Expresión de condición (soporta variable `cost`) | Ninguno | `--condition "cost > 50"` |
| `--skip-builtin` | Omitir funciones integradas y de la biblioteca estándar | `true` | `--skip-builtin=false` |
| `--min-duration` | Filtro de duración mínima (milisegundos) | `0` | `--min-duration 10` |

**Notas**:
- La profundidad de rastreo no debe exceder 5 niveles; una profundidad excesiva aumenta significativamente el sobrecoste de rendimiento
- `--skip-builtin` está habilitado por defecto para reducir el ruido de salida
- La variable `cost` en expresiones de condición representa la duración total de la llamada (milisegundos)

### Patrón de Coincidencia de Función (pattern)

Soporta los siguientes formatos:

```python
# 1. Función a nivel de módulo
"mymodule.my_function"

# 2. Método de clase
"mymodule.MyClass.my_method"

# 3. Método de clase anidada
"mypackage.mymodule.OuterClass.InnerClass.method"

# 4. Ruta de módulo
"package.subpackage.module.function"
```

**Nota**: Debe usar la ruta completa del módulo (desde la raíz de importación). La versión actual no soporta coincidencia con comodines.

## Uso Básico

### 1. Rastrear Cadena de Llamada de Función

```bash
# Primero adjuntar al proceso objetivo
peeka-cli attach 12345

# Rastrear 5 llamadas
peeka-cli trace "calculator.Calculator.calculate" -n 5
```

**Ejemplo de Salida**:

```json
{
  "type": "observation",
  "watch_id": "trace_abc123",
  "timestamp": 1705586200.123,
  "func_name": "calculator.Calculator.calculate",
  "location": "AtExit",
  "call_tree": [
    {
      "depth": 0,
      "function": "calculator.Calculator.calculate",
      "filename": "/app/calculator.py",
      "lineno": 42,
      "duration_ms": 125.3,
      "children": [
        {
          "depth": 1,
          "function": "calculator.Calculator._validate",
          "filename": "/app/calculator.py",
          "lineno": 18,
          "duration_ms": 2.1
        },
        {
          "depth": 1,
          "function": "calculator.Calculator._compute",
          "filename": "/app/calculator.py",
          "lineno": 25,
          "duration_ms": 98.2,
          "children": [
            {
              "depth": 2,
              "function": "math.sqrt",
              "duration_ms": 95.1
            }
          ]
        },
        {
          "depth": 1,
          "function": "calculator.Logger.info",
          "filename": "/app/logger.py",
          "lineno": 10,
          "duration_ms": 15.7
        }
      ]
    }
  ],
  "total_duration_ms": 125.3,
  "node_count": 5
}
```

**Descripción de Campos**:

| Campo | Descripción | Ejemplo |
|-------|-------------|---------|
| `watch_id` | ID de observación | `"trace_abc123"` |
| `timestamp` | Marca de tiempo | `1705586200.123` |
| `func_name` | Nombre de la función objetivo | `"calculator.calculate"` |
| `location` | Ubicación de observación | `"AtExit"` |
| `call_tree` | Árbol de llamadas (estructura anidada) | `[...]` |
| `total_duration_ms` | Tiempo total de ejecución (milisegundos) | `125.3` |
| `node_count` | Conteo total de nodos de llamada | `5` |

**Campos de Nodo de Árbol de Llamadas**:

| Campo | Descripción | Ejemplo |
|-------|-------------|---------|
| `depth` | Profundidad de llamada (comenzando desde 0) | `0`, `1`, `2` |
| `function` | Nombre completo de la función | `"module.Class.method"` |
| `filename` | Ruta del archivo | `"/app/module.py"` |
| `lineno` | Número de línea | `42` |
| `duration_ms` | Tiempo de ejecución (milisegundos) | `10.5` |
| `children` | Lista de sub-llamadas | `[...]` |

### 2. Salida de Árbol de Texto (TUI)

En modo TUI, el árbol de llamadas se muestra como una estructura de árbol visual:

```
`---[125.3ms] calculator.Calculator.calculate()
    +---[2.1ms] calculator.Calculator._validate()
    +---[98.2ms] calculator.Calculator._compute()
    |   `---[95.1ms] math.sqrt()
    `---[15.7ms] calculator.Logger.info()
```

**Explicación**:
- `---` indica el último nodo hijo
- `+---` indica nodos hijos intermedios
- `|` indica línea de conexión para nodos padre con nodos hermanos subsiguientes
- `[Xms]` muestra el tiempo de ejecución de la función

### 3. Ajustar Profundidad de Rastreo

```bash
# Profundidad de 1: rastrear solo llamadas directas
peeka-cli trace "service.process" -d 1

# Profundidad de 5: rastrear 5 niveles de llamadas
peeka-cli trace "service.process" -d 5
```

**Ejemplo de Comparación de Profundidad**:

```python
# Cadena de llamada original
process() → validate() → check_type() → isinstance()
  ├── query_db() → execute() → connect()
  └── format_result() → json.dumps()

# depth=1
process() → validate()
          → query_db()
          → format_result()

# depth=2
process() → validate() → check_type()
          → query_db() → execute()
          → format_result() → json.dumps()

# depth=3 (predeterminado)
process() → validate() → check_type() → isinstance()
          → query_db() → execute() → connect()
          → format_result() → json.dumps()
```

### 4. Filtrado Condicional

```bash
# Solo rastrear llamadas que exceden 50ms
peeka-cli trace "api.handler" --condition "cost > 50"

# Combinar condiciones de parámetros y temporización
peeka-cli trace "service.query" --condition "cost > 100 and params[0] > 1000"
```

### 5. Omitir Funciones Integradas

```bash
# Comportamiento predeterminado: omitir funciones integradas (reducir ruido de salida)
peeka-cli trace "mymodule.func"

# Mostrar todas las llamadas (incluyendo funciones integradas)
peeka-cli trace "mymodule.func" --skip-builtin=false
```

**Ejemplos de Funciones Integradas**:
- Funciones integradas de Python: `len()`, `str()`, `isinstance()`, `print()`
- Funciones de biblioteca estándar: `json.dumps()`, `os.path.join()`, `datetime.now()`

## Tecnología de Implementación

El comando `trace` de Peeka selecciona automáticamente la implementación óptima según la versión de Python:

### Principios de Implementación

El comando `trace` de Peeka selecciona automáticamente la implementación óptima según la versión de Python:

| Versión de Python | Implementación | Sobrecoste de Rendimiento | Notas |
|----------------|----------------|----------------------|-------|
| 3.12+ | sys.monitoring | < 5% | API oficial de PEP 669, rendimiento óptimo |
| 3.9-3.11 | sys.settrace | < 20% | Buena compatibilidad, habilitado automáticamente |

**Implementación sys.monitoring (Python 3.12+)**:

- Basado en la API oficial de monitoreo de [PEP 669](https://peps.python.org/pep-0669/)
- Usa eventos `PY_START` y `PY_RETURN` para capturar llamadas
- Sobrecoste de rendimiento < 5%, recomendado para entornos de producción
- Asigna automáticamente tool_id, sin conflictos con múltiples observaciones

**Implementación sys.settrace (Python 3.9-3.11)**:

- Usa el mecanismo incorporado `sys.settrace()` de Python
- Habilitado solo durante la ejecución de la función objetivo (rastreo local)
- Sobrecoste de rendimiento < 20%, completamente utilizable en la mayoría de escenarios

**Mecanismo de Filtrado skip-builtin**:

- Verifica `code.co_filename.startswith('<')` para filtrar funciones integradas (ej., `<built-in>`)
- Verifica rutas de la biblioteca estándar de Python para filtrar funciones de la biblioteca estándar
- Habilitado por defecto, reduce los nodos de salida en más de un 50%

## Impacto en el Rendimiento

### Sobrecoste de Rendimiento

| Escenario | Sobrecoste | Notas |
|----------|----------|-------|
| **Funciones simples** | < 5% | Python 3.12+ |
| **Funciones simples** | < 20% | Python 3.9-3.11 |
| **Árbol de llamada complejo (profundidad 5)** | 10-30% | Depende de la versión de Python |
| **Llamadas de alta frecuencia (>1000 QPS)** | 20-50% | Recomienda limitar el número de observaciones |

**Explicación**:
- Python 3.12+ usa `sys.monitoring`, reduciendo significativamente el sobrecoste
- Rastreados más profundos incurren en mayor sobrecoste
- Se recomienda usar filtrado condicional y límites de conteo en producción

### Recomendaciones de Optimización de Rendimiento

1. **Limitar profundidad de rastreo**
   ```bash
   # Rastrear solo 3 niveles de llamadas
   peeka-cli trace "func" -d 3
   ```

2. **Omitir funciones integradas**
   ```bash
   # Habilitado por defecto, reduce los nodos en más de un 50%
   peeka-cli trace "func" --skip-builtin
   ```

3. **Usar filtrado condicional**
   ```bash
   # Solo rastrear llamadas lentas
   peeka-cli trace "func" --condition "cost > 100"
   ```

4. **Limitar número de observaciones**
   ```bash
   # Solo observar 10 veces
   peeka-cli trace "func" -n 10
   ```

5. **Filtrado de duración mínima**
   ```bash
   # Registrar solo sub-llamadas > 10ms
   peeka-cli trace "func" --min-duration 10
   ```

## Ejemplos de Uso

### 1. Identificar Cuellos de Botella de Rendimiento

```bash
# Rastrear endpoints lentos, encontrar sub-llamadas con mayor duración
peeka-cli trace "api.handler.process_request" --condition "cost > 100"
```

**Salida**:
```
`---[1250ms] api.handler.process_request()
    +---[10ms] api.validator.check_params()
    +---[1200ms] database.query.execute()  ← ¡Cuello de botella aquí!
    |   +---[50ms] database.connection.connect()
    |   `---[1150ms] database.cursor.fetch_all()
    `---[20ms] api.formatter.to_json()
```

**Conclusión**: La consulta de base de datos consume el 96% del tiempo, necesita optimización SQL o adición de índice.

### 2. Analizar Llamadas Recursivas

```bash
# Rastrear profundidad de ejecución y temporización de función recursiva
peeka-cli trace "algorithm.factorial" -d 10
```

**Salida**:
```
`---[5.2ms] algorithm.factorial(n=5)
    `---[4.1ms] algorithm.factorial(n=4)
        `---[3.0ms] algorithm.factorial(n=3)
            `---[2.0ms] algorithm.factorial(n=2)
                `---[1.0ms] algorithm.factorial(n=1)
                    `---[0.1ms] algorithm.factorial(n=0)
```

### 3. Comprender Ruta de Ejecución de Código

```bash
# Rastrear rutas de ejecución de ramas condicionales
peeka-cli trace "service.business_logic" -n 1
```

**Escenario A (flujo normal)**:
```
`---[50ms] service.business_logic()
    +---[5ms] service.validate_input()
    +---[30ms] service.process_data()
    `---[10ms] service.save_result()
```

**Escenario B (flujo de excepción)**:
```
`---[20ms] service.business_logic()
    +---[5ms] service.validate_input()
    +---[10ms] service.handle_invalid_input()
    `---[3ms] service.log_error()
```

### 4. Comparar Rendimiento Antes/Después de Optimización

```bash
# Antes de optimización
peeka-cli trace "converter.parse_json" -n 10 > before.jsonl

# Después de optimización
peeka-cli trace "converter.parse_json" -n 10 > after.jsonl

# Analizar cambios de temporización
jq '.total_duration_ms' before.jsonl | awk '{sum+=$1; count++} END {print "Before:", sum/count, "ms"}'
jq '.total_duration_ms' after.jsonl | awk '{sum+=$1; count++} END {print "After:", sum/count, "ms"}'
```

### 5. Integrar en CI/CD

```bash
# Prueba de regresión de rendimiento
#!/bin/bash
THRESHOLD=100  # Duración máxima permitida 100ms

peeka-cli attach $PID
RESULT=$(peeka-cli trace "critical.function" -n 50 | \
  jq -s 'map(select(.type == "observation")) | map(.total_duration_ms) | add / length')

if (( $(echo "$RESULT > $THRESHOLD" | bc -l) )); then
  echo "Regresión de rendimiento detectada: ${RESULT}ms > ${THRESHOLD}ms"
  exit 1
fi
```

## Procesamiento y Análisis de Datos

### Procesar JSON con jq

```bash
# 1. Extraer árbol de llamadas
peeka-cli trace "func" | jq '.call_tree'

# 2. Calcular duración promedio
peeka-cli trace "func" -n 100 | jq '.total_duration_ms' | \
  awk '{sum+=$1; count++} END {print "avg:", sum/count, "ms"}'

# 3. Encontrar la sub-llamada más lenta
peeka-cli trace "func" | jq '.call_tree | .. | objects | select(.duration_ms != null) | {function, duration_ms}' | \
  jq -s 'sort_by(.duration_ms) | reverse | .[0]'

# 4. Contar frecuencia de llamadas
peeka-cli trace "func" -n 100 | jq '.call_tree | .. | objects | select(.function != null) | .function' | \
  sort | uniq -c | sort -rn

# 5. Generar datos para flame graph
peeka-cli trace "func" -n 1000 | jq -r '.call_tree | .. | objects | select(.function != null) | "\(.function) \(.duration_ms)"' > flamegraph.txt
```

### Análisis de Datos con Python

```python
import json
import sys
from collections import defaultdict

# Contar duración total y ocurrencias de sub-llamadas
stats = defaultdict(lambda: {"count": 0, "total_ms": 0})

for line in sys.stdin:
    data = json.loads(line)
    if data["type"] == "observation":
        def traverse(node):
            if "function" in node:
                stats[node["function"]]["count"] += 1
                stats[node["function"]]["total_ms"] += node.get("duration_ms", 0)

            for child in node.get("children", []):
                traverse(child)

        for root in data["call_tree"]:
            traverse(root)

# Ordenar por duración total
sorted_stats = sorted(stats.items(), key=lambda x: x[1]["total_ms"], reverse=True)

print("Top 10 Funciones que Consumen Tiempo:")
print(f"{'Función':<60} {'Conteo':>10} {'Total (ms)':>15} {'Promedio (ms)':>12}")
print("-" * 100)

for func, stat in sorted_stats[:10]:
    avg_ms = stat["total_ms"] / stat["count"]
    print(f"{func:<60} {stat['count']:>10} {stat['total_ms']:>15.2f} {avg_ms:>12.2f}")
```

**Ejecutar**:
```bash
peeka-cli trace "module.func" -n 100 | python analyze_trace.py
```

**Salida**:
```
Top 10 Funciones que Consumen Tiempo:
Función                                                      Conteo     Total (ms)      Promedio (ms)
----------------------------------------------------------------------------------------------------
database.query.execute                                          100       12500.00       125.00
api.handler.process_request                                     100       15000.00       150.00
json.dumps                                                      500        1000.00         2.00
...
```

## Problemas Comunes

### 1. Profundidad de Rastreo Insuficiente

**Problema**: El árbol de llamadas solo muestra 3 niveles, pero hay más niveles en realidad

**Solución**:

```bash
# Aumentar límite de profundidad
peeka-cli trace "module.func" -d 10

# Nota: Profundidad excesiva aumenta el sobrecoste de rendimiento
```

### 2. Demasiados Datos de Salida

**Problema**: Contiene muchas llamadas a funciones integradas, salida difícil de leer

**Solución**:

```bash
# Omitir funciones integradas (habilitado por defecto)
peeka-cli trace "module.func" --skip-builtin

# Registrar solo llamadas > 10ms
peeka-cli trace "module.func" --min-duration 10

# Usar filtrado condicional
peeka-cli trace "module.func" --condition "cost > 50"
```

### 3. Sobrecoste de Rendimiento Excesivo

**Problema**: La respuesta de la aplicación se ralentiza después de habilitar el rastreo

**Solución**:

```bash
# 1. Reducir profundidad de rastreo
peeka-cli trace "module.func" -d 2

# 2. Limitar número de observaciones
peeka-cli trace "module.func" -n 10

# 3. Usar filtrado condicional, rastrear solo llamadas lentas
peeka-cli trace "module.func" --condition "cost > 100"

# 4. Considerar actualizar a Python 3.12+ para mejor rendimiento
```

### 4. Sin Datos Observados

**Posibles Causas**:
- Función no llamada
- Error de ortografía en nombre de función
- Expresión de condición demasiado estricta
- Límite de número de observaciones alcanzado (parámetro -n)

**Pasos de Solución de Problemas**:

```bash
# 1. Confirmar que el nombre de la función es correcto
python3 -c "import mymodule; print(mymodule.MyClass.my_method)"

# 2. Eliminar expresión de condición, observar una vez primero
peeka-cli trace "mymodule.func" -n 1

# 3. Verificar si el proceso existe
ps aux | grep <pid>
```

## Consejos Avanzados

### 1. Generar Flame Graph

```bash
# Recolectar datos de rastreo
peeka-cli trace "module.func" -n 1000 > trace.jsonl

# Convertir a formato flame graph
jq -r '.call_tree | .. | objects | select(.function != null) | "\(.function);\(.duration_ms)"' trace.jsonl \
  > folded.txt

# Generar flame graph (requiere instalación de flamegraph.pl)
flamegraph.pl folded.txt > flamegraph.svg
```

### 2. Comparar Rendimiento entre Versiones

```bash
# Versión A
git checkout v1.0
peeka-cli trace "module.func" -n 100 > trace_v1.jsonl

# Versión B
git checkout v2.0
peeka-cli trace "module.func" -n 100 > trace_v2.jsonl

# Comparar duración promedio
echo "v1.0: $(jq -s 'map(.total_duration_ms) | add / length' trace_v1.jsonl) ms"
echo "v2.0: $(jq -s 'map(.total_duration_ms) | add / length' trace_v2.jsonl) ms"
```

### 3. Monitoreo Automatizado de Rendimiento

```python
#!/usr/bin/env python3
"""Script de monitoreo de regresión de rendimiento"""
import json
import subprocess
import time

THRESHOLD = 100  # Duración máxima permitida (ms)
CHECK_INTERVAL = 3600  # Intervalo de verificación (segundos)

def check_performance(pid, pattern):
    cmd = ["peeka-cli", "trace", pattern, "-n", "50"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)

    durations = []
    for line in proc.stdout:
        data = json.loads(line)
        if data["type"] == "observation":
            durations.append(data["total_duration_ms"])

    avg_duration = sum(durations) / len(durations) if durations else 0

    if avg_duration > THRESHOLD:
        send_alert(f"Regresión de rendimiento: {avg_duration:.2f}ms > {THRESHOLD}ms")

    return avg_duration

def send_alert(message):
    # Enviar alerta (email, Slack, DingTalk, etc.)
    print(f"ALERTA: {message}")

if __name__ == "__main__":
    pid = int(sys.argv[1])
    pattern = sys.argv[2]

    while True:
        duration = check_performance(pid, pattern)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Duración promedio: {duration:.2f}ms")
        time.sleep(CHECK_INTERVAL)
```

### 4. Integrar con Prometheus

```python
from prometheus_client import Histogram, start_http_server
import json
import subprocess

# Definir métricas
trace_duration = Histogram('trace_duration_ms', 'Duración de rastreo de función', ['function'])

# Iniciar servidor Prometheus
start_http_server(8000)

# Recolectar datos de rastreo
proc = subprocess.Popen(
    ["peeka-cli", "trace", "module.func"],
    stdout=subprocess.PIPE,
    text=True
)

for line in proc.stdout:
    data = json.loads(line)
    if data["type"] == "observation":
        # Procesar árbol de llamadas recursivamente
        def record_metrics(node):
            if "function" in node and "duration_ms" in node:
                trace_duration.labels(function=node["function"]).observe(node["duration_ms"])
            for child in node.get("children", []):
                record_metrics(child)

        for root in data["call_tree"]:
            record_metrics(root)
```

## Referencias

- [PEP 669: Low Impact Monitoring for CPython](https://peps.python.org/pep-0669/)
- [Diseño de Arquitectura de Peeka](../architecture.md)

## Registro de Cambios

| Versión | Fecha | Actualizaciones |
|---------|------|---------|
| 0.2.0 | 2026-02 | Agregada documentación del comando trace |
| 0.1.0 | 2025-01 | Versión inicial |
