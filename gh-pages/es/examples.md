---
layout: default
title: Ejemplos y Tutoriales
nav_order: 5
---

# Ejemplos y Tutoriales
{: .no_toc }

Aprende a usar Peeka para diagnosticar y resolver problemas a través de escenarios prácticos.
{: .fs-6 .fw-300 }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Escenario 1: Diagnosticar interfaz lenta

### Descripción del Problema

La interfaz API ocasionalmente responde muy lentamente (> 1 segundo), necesitas encontrar la causa de la llamada lenta.

### Pasos de Solución

#### 1. Adjuntar al proceso

```bash
# Encuentra el proceso del servidor API
ps aux | grep "api_server.py"
# Salida: user 12345 ...

# Adjuntar
peeka-cli attach 12345
```

#### 2. Monitorear el rendimiento general

```bash
# Estadísticas cada 10 segundos
peeka-cli monitor "app.api.handle_request" --interval 10
```

Salida:
```json
{"type":"observation","func_name":"app.api.handle_request","total":150,"success":148,"fail":2,"avg_rt":250.5,"min_rt":50.2,"max_rt":1850.3}
```

Se descubre que `max_rt` alcanza los 1850ms, existen llamadas lentas.

#### 3. Observar llamadas lentas

```bash
# Solo observa llamadas con tiempo de ejecución > 1000ms
peeka-cli watch "app.api.handle_request" \
  --condition "cost > 1000" \
  --times 10
```

Salida:
```json
{"type":"observation","watch_id":"watch_001","func_name":"app.api.handle_request","args":[{"user_id": 12345}],"result":{"status": "ok"},"duration_ms":1850.3,"count":1}
```

Se descubre que el parámetro de la llamada lenta es `user_id=12345`.

#### 4. Rastrear cadena de llamadas

```bash
# Rastrear la cadena completa de llamadas, encontrar el enlace que consume tiempo
peeka-cli trace "app.api.handle_request" \
  --condition "cost > 1000" \
  --depth 5 \
  --times 1
```

Salida:
```
`---[1850.3ms] app.api.handle_request()
    +---[5.2ms] app.auth.validate_token()
    +---[1800.1ms] app.db.query_user_data()  ← Lento
    |   +---[1795.5ms] sqlalchemy.query.all()
    |   `---[2.1ms] app.db._parse_results()
    `---[15.7ms] app.response.build()
```

**Conclusión**: La llamada lenta es causada por `app.db.query_user_data()`, la consulta SQL tarda demasiado.

#### 5. Verificar reparación

Después de optimizar la consulta SQL, monitorea nuevamente:

```bash
peeka-cli monitor "app.api.handle_request" --interval 10
```

Salida:
```json
{"type":"observation","total":150,"avg_rt":120.5,"max_rt":450.3}
```

¡El rendimiento mejora significativamente!

---

## Escenario 2: Localizar causa de excepción

### Descripción del Problema

La tarea en segundo plano ocasionalmente lanza `ValueError`, pero los registros están incompletos y no se puede localizar la causa.

### Pasos de Solución

#### 1. Observar excepción

```bash
# Solo observa llamadas que lanzan excepciones
peeka-cli watch "app.tasks.process_data" \
  --exception
```

Salida:
```json
{
  "type":"observation",
  "func_name":"app.tasks.process_data",
  "args":[{"data": [1, 2, null]}],
  "success":false,
  "exception":"ValueError: invalid value",
  "duration_ms":5.2
}
```

Se descubre que el parámetro de excepción contiene `null`.

#### 2. Ver pila de llamadas

```bash
# Capturar la pila de llamadas cuando ocurre la excepción
peeka-cli stack "app.tasks.process_data" \
  --condition "throwExp is not None" \
  --times 1
```

Salida:
```
Thread: WorkerThread-1
  File "scheduler.py", line 45, in run
    self.execute_task(task)
  File "scheduler.py", line 78, in execute_task
    result = task.process_data(data)
  File "tasks.py", line 120, in process_data
    validated = self._validate(data)  ← Aquí se lanza la excepción
```

**Conclusión**: La excepción es causada por datos `null` ingresados por `scheduler.py`.

#### 3. Verificar reparación

Después de agregar validación de entrada, prueba nuevamente:

```bash
peeka-cli watch "app.tasks.process_data" --times 100
```

Después de observar 100 llamadas, no hay excepciones.

---

## Escenario 3: Verificar modificación de código

### Descripción del Problema

Modificaste la lógica de caché, necesitas verificar si el caché realmente funciona.

### Pasos de Solución

#### 1. Observar función de caché

```bash
# Observar situación de aciertos de caché
peeka-cli watch "app.cache.get" --times 20
```

Salida:
```json
{"type":"observation","func_name":"app.cache.get","args":["user_123"],"result":{"name":"Alice"},"from_cache":true}
{"type":"observation","func_name":"app.cache.get","args":["user_456"],"result":null,"from_cache":false}
{"type":"observation","func_name":"app.cache.get","args":["user_123"],"result":{"name":"Alice"},"from_cache":true}
```

#### 2. Estadísticas de tasa de aciertos

```bash
peeka-cli watch "app.cache.get" --times 1000 | \
  jq 'select(.type == "observation") | .from_cache' | \
  awk '{if($1=="true") hit++; total++} END {print "Hit Rate:", (hit/total)*100, "%"}'
```

Salida:
```
Hit Rate: 85.3 %
```

**Conclusión**: La tasa de aciertos de caché es 85%, cumple con las expectativas.

---

## Escenario 4: Monitorear regresión de rendimiento de funciones

### Descripción del Problema

Después de implementar una nueva versión, te preocupa la regresión de rendimiento, necesitas monitoreo en tiempo real.

### Pasos de Solución

#### 1. Establecer línea de base de rendimiento

Antes del despliegue:
```bash
peeka-cli monitor "app.service.critical_func" --interval 5 -c 12 > baseline.jsonl
```

#### 2. Monitoreo después del despliegue

```bash
peeka-cli monitor "app.service.critical_func" --interval 5 -c 12 > after_deploy.jsonl
```

#### 3. Análisis comparativo

```python
# compare.py
import json

def load_stats(file):
    stats = []
    with open(file) as f:
        for line in f:
            msg = json.loads(line)
            if msg.get("type") == "observation":
                stats.append(msg["avg_rt"])
    return sum(stats) / len(stats) if stats else 0

baseline = load_stats("baseline.jsonl")
after = load_stats("after_deploy.jsonl")

print(f"Baseline: {baseline:.2f}ms")
print(f"After Deploy: {after:.2f}ms")
print(f"Change: {((after - baseline) / baseline) * 100:.1f}%")
```

Salida:
```
Baseline: 125.50ms
After Deploy: 130.20ms
Change: +3.7%
```

**Conclusión**: El rendimiento disminuyó ligeramente en un 3.7%, está dentro del rango aceptable.

---

## Escenario 5: Depurar condición de carrera

### Descripción del Problema

Los programas multihilo ocasionalmente tienen datos inconsistentes, se sospecha que es una condición de carrera.

### Pasos de Solución

#### 1. Observar orden de llamadas de funciones clave

```bash
# Observa dos funciones clave
peeka-cli watch "app.data.read" --times 100 > read.jsonl &
peeka-cli watch "app.data.write" --times 100 > write.jsonl &
```

#### 2. Analizar marcas de tiempo

```python
# analyze_race.py
import json
from collections import defaultdict

def load_calls(file):
    calls = []
    with open(file) as f:
        for line in f:
            msg = json.loads(line)
            if msg.get("type") == "observation":
                calls.append((msg["timestamp"], msg["func_name"]))
    return calls

reads = load_calls("read.jsonl")
writes = load_calls("write.json")

# Combinar y ordenar
all_calls = sorted(reads + writes, key=lambda x: x[0])

# Buscar patrón sospechoso: read -> read (sin write en el medio)
for i in range(len(all_calls) - 1):
    curr_func = all_calls[i][1]
    next_func = all_calls[i+1][1]
    if "read" in curr_func and "read" in next_func:
        print(f"Suspicious pattern at {all_calls[i][0]}")
```

#### 3. Verificar reparación

Después de agregar protección de bloqueo, prueba nuevamente:

```bash
peeka-cli watch "app.data.read" --times 100 | \
  jq 'select(.type == "observation") | .data_version' | \
  uniq -c
```

La salida muestra que las versiones de datos son consistentes, no hay competencia.

---

## Escenario 6: Analizar distribución de parámetros

### Descripción del Problema

Necesitas entender la distribución de parámetros de funciones para optimizar la estrategia de caché.

### Pasos de Solución

#### 1. Recolectar datos de parámetros

```bash
peeka-cli watch "app.service.query" --times 1000 > params.jsonl
```

#### 2. Analizar distribución

```bash
# Extraer el primer parámetro
cat params.jsonl | \
  jq 'select(.type == "observation") | .args[0]' | \
  sort | uniq -c | sort -rn | head -10
```

Salida:
```
    245 "user_type_A"
    198 "user_type_B"
     87 "user_type_C"
     45 "user_type_D"
     ...
```

#### 3. Visualización

```python
# visualize.py
import json
from collections import Counter
import matplotlib.pyplot as plt

params = []
with open("params.jsonl") as f:
    for line in f:
        msg = json.loads(line)
        if msg.get("type") == "observation":
            params.append(msg["args"][0])

counter = Counter(params)
labels, values = zip(*counter.most_common(10))

plt.bar(labels, values)
plt.xlabel("Parameter Value")
plt.ylabel("Frequency")
plt.title("Parameter Distribution")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig("param_dist.png")
```

**Conclusión**: `user_type_A` y `user_type_B` representan la proporción más alta, se debe priorizar el caché.

---

## Escenario 7: Alertas en tiempo real en entorno de producción

### Descripción del Problema

Necesitas monitorear funciones clave en tiempo real en entorno de producción y alertar automáticamente cuando hay anomalías.

### Pasos de Solución

#### 1. Escribir script de monitoreo

```bash
#!/bin/bash
# monitor_and_alert.sh

peeka-cli monitor "app.api.critical" --interval 10 | \
while read -r line; do
    # Analizar JSON
    avg_rt=$(echo "$line" | jq -r '.avg_rt // 0')
    fail=$(echo "$line" | jq -r '.fail // 0')

    # Condición de alerta
    if (( $(echo "$avg_rt > 500" | bc -l) )); then
        echo "ALERTA: Alta latencia detectada: ${avg_rt}ms" | \
          mail -s "Peeka Alert" ops@example.com
    fi

    if (( fail > 0 )); then
        echo "ALERTA: ${fail} fallos detectados" | \
          mail -s "Peeka Alert" ops@example.com
    fi
done
```

#### 2. Ejecutar en segundo plano

```bash
nohup ./monitor_and_alert.sh > alert.log 2>&1 &
```

#### 3. Integrar en sistema de monitoreo

```python
# prometheus_exporter.py
from prometheus_client import Gauge, start_http_server
import json
import subprocess

# Definir métricas
api_latency = Gauge('api_critical_latency_ms', 'API critical latency')
api_failures = Gauge('api_critical_failures', 'API critical failures')

# Iniciar servidor HTTP
start_http_server(8000)

# Leer salida de Peeka
proc = subprocess.Popen(
    ['peeka-cli', 'monitor', 'app.api.critical', '--interval', '10'],
    stdout=subprocess.PIPE,
    text=True
)

for line in proc.stdout:
    msg = json.loads(line)
    if msg.get("type") == "observation":
        api_latency.set(msg.get("avg_rt", 0))
        api_failures.set(msg.get("fail", 0))
```

---

## Resumen de Mejores Prácticas

### 1. Reducir el alcance paso a paso

```bash
# De grueso a fino
monitor → watch → trace → stack
```

### 2. Usar filtrado condicional

```bash
# Evitar demasiados datos
--condition "cost > 100"
--times 10
```

### 3. Guardar datos de observación

```bash# Conveniente para análisis offline
peeka-cli watch "func" > data.jsonl
```

### 4. Combinar cadena de herramientas

```bash
# Aprovecha al máximo las herramientas Unix
peeka-cli watch "func" | jq | awk | gnuplot
```

### 5. Integración automatizada

```python
# Integrar en CI/CD
python -m peeka.analyze --baseline baseline.jsonl --current current.jsonl
```

---

## Más Recursos

- [Referencia de Comandos]({% link es/commands/index.md %}) - Documentación detallada de comandos
- [Diseño de Arquitectura]({% link es/architecture.md %}) - Conoce los principios de implementación
- [Resolución de Problemas]({% link es/troubleshooting.md %}) - Solución de problemas comunes
