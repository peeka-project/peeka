---
layout: default
title: monitor
parent: Referencia de Comandos
nav_order: 5
---

# monitor - Estadísticas de rendimiento
{: .no_toc }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Introducción

El comando `monitor` recolecta y genera salida periódicamente de estadísticas de rendimiento de funciones, incluyendo conteo de llamadas, tasas de éxito/fracaso, tiempos de respuesta y otras métricas clave. Esta es una herramienta ligera de monitoreo de rendimiento adecuada para operación a largo plazo en entornos de producción.

**Características Principales**:
- Salida periódica de estadísticas de rendimiento de funciones (predeterminado cada 60 segundos)
- Estadísticas de conteo de llamadas, tasas de éxito/fracaso
- Estadísticas de tiempos de respuesta (promedio, mínimo, máximo)
- Diseño ligero (no registra datos de observación detallados, solo estadísticas)
- Soporta monitoreo de múltiples funciones simultáneamente
- Ciclo de monitoreo y duración configurables

**Diferencia con el comando watch**:
- `watch`: Registra **información detallada para cada llamada** (argumentos, valores de retorno, pilas de llamadas, etc.)
- `monitor`: Solo registra **datos estadísticos** (conteo de llamadas, tiempos de respuesta, etc.), genera resúmenes periódicos

## Uso en TUI

En modo TUI, presiona **`5`** para cambiar a la **Vista Monitor**, que proporciona las siguientes características interactivas:

- **Entrada de Patrón**: Soporta autocompletado de nombres de funciones (obtenido desde el proceso objetivo en tiempo real)
- **Configuración de Parámetros**: Configuración visual para intervalo de salida, conteo de ciclos de monitoreo
- **Visualización de Estadísticas**: Muestra en tiempo real métricas de rendimiento
  - Conteo de llamadas (total, éxito, fracaso)
  - Tasa de fracaso (fail_rate), tiempos de respuesta (promedio/mínimo/máximo)
  - Contador de ciclos y tiempo de intervalo
- **Atajos de Teclado**:
  - Enter después de ingresar el patrón para iniciar el monitoreo
  - Presiona `s` para detener el monitoreo
  - Presiona `c` para limpiar estadísticas

**Equivalente CLI**: Todos los ejemplos a continuación usan comandos CLI para demostración; TUI proporciona la misma funcionalidad con una interfaz gráfica.

---

## Escenarios de Uso

### 1. Monitoreo de Rendimiento en Entorno de Producción

**Escenario**: Monitoreo a largo plazo de métricas de rendimiento de funciones críticas, detección oportuna de degradación de rendimiento.

```bash
# Salida de estadísticas una vez cada 60 segundos, operación continua
peeka-cli monitor "myapp.api.handle_request" --interval 60
```

**Ejemplo de Salida**:
```json
{
  "watch_id": "monitor_a1b2c3d4",
  "cycle": 1,
  "total": 1234,
  "success": 1200,
  "fail": 34,
  "fail_rate": 0.0275,
  "rt_avg": 45.678,
  "rt_min": 5.123,
  "rt_max": 234.567
}
```

**Interpretación**:
- 1234 llamadas totales dentro de 1 minuto
- 1200 exitosas, 34 fallidas (tasa de fracaso 2.75%)
- Tiempo de respuesta promedio 45.678 milisegundos
- El más rápido 5.123 milisegundos, el más lento 234.567 milisegundos

### 2. Verificación de Salud de Servicio

**Escenario**: Monitorear tasa de fracaso de funciones centrales, alertar cuando se excede el umbral.

```bash
# Salida una vez cada 30 segundos, continuar 10 veces (5 minutos)
peeka-cli monitor "myapp.payment.process" \
  --interval 30 -c 10 | \
  jq -r 'select(.fail_rate > 0.05) | "ALERTA: Tasa de fracaso \(.fail_rate*100)%\"'
```

**Efecto**: Genera salida de información de alerta cuando la tasa de fracaso excede el 5%.

### 3. Establecer Línea Base de Rendimiento

**Escenario**: Establecer línea base de rendimiento bajo carga normal para comparación de rendimiento posterior.

```bash
# Monitorear durante 1 hora (60 veces, una vez por minuto)
peeka-cli monitor "myapp.db.execute_query" \
  --interval 60 -c 60 > baseline.jsonl

# Analizar datos
jq -s '{
  avg_rt: (map(.rt_avg) | add / length),
  avg_total: (map(.total) | add / length),
  max_fail_rate: (map(.fail_rate) | max)
}' baseline.jsonl
```

**Salida**:
```json
{
  "avg_rt": 12.345,
  "avg_total": 567,
  "max_fail_rate": 0.0123
}
```

### 4. Monitoreo Comparativo de Múltiples Funciones

**Escenario**: Monitorear múltiples funciones simultáneamente, comparar diferencias de rendimiento.

```bash
# Terminal 1: Monitorear API v1
peeka-cli monitor "myapp.api.v1.handler" --interval 30 > api_v1.jsonl &

# Terminal 2: Monitorear API v2
peeka-cli monitor "myapp.api.v2.handler" --interval 30 > api_v2.jsonl &

# Terminal 3: Comparación en tiempo real
while true; do
  v1=$(tail -1 api_v1.jsonl | jq -r '.rt_avg')
  v2=$(tail -1 api_v2.jsonl | jq -r '.rt_avg')
  echo "v1: ${v1}ms, v2: ${v2}ms"
  sleep 30
done
```

### 5. Monitoreo Durante Prueba de Carga

**Escenario**: Monitoreo en tiempo real de rendimiento de funciones durante prueba de carga, observar comportamiento del sistema.

```bash
# Monitorear función central, salida una vez cada 10 segundos
peeka-cli monitor "myapp.process" --interval 10 | \
  jq -r '"\(.cycle): \(.total) llamadas, \(.rt_avg)ms promedio, \(.fail_rate*100)% fracaso"'
```

**Salida**:
```
1: 123 llamadas, 45.67ms promedio, 1.2% fracaso
2: 234 llamadas, 67.89ms promedio, 2.3% fracaso
3: 345 llamadas, 89.01ms promedio, 3.4% fracaso
...
```

---

## Formato del Comando

```bash
peeka-cli attach <pid>
peeka-cli monitor <pattern> [options]
```

**Parámetros Opcionales**:
- `--interval`: Intervalo de salida (segundos, predeterminado 60)
- `-c, --cycles`: Número de ciclos de monitoreo (-1 para ilimitado, predeterminado -1)

---

## Referencia de Parámetros

### pattern - Patrón de Función

Especifica la función objetivo a monitorear, formato igual que el comando `watch`.

| Formato | Descripción | Ejemplo |
|--------|-------------|---------|
| `module.function` | Función a nivel de módulo | `myapp.utils.calculate` |
| `module.Class.method` | Método de clase | `myapp.models.User.save` |
| `module.Class.static_method` | Método estático | `myapp.utils.Helper.validate` |

**Notas**:
- Debe usar nombre completamente calificado (comenzando desde la raíz del módulo)
- No se soportan comodines
- La función objetivo debe estar cargada en memoria

### --interval - Intervalo de Salida

Controla la frecuencia de salida de datos estadísticos (unidad: segundos).

| Valor | Descripción | Escenario de Uso |
|-------|-------------|----------|
| `10` | Salida una vez cada 10 segundos | Prueba de carga, monitoreo en tiempo real |
| `30` | Salida una vez cada 30 segundos | Monitoreo de alta frecuencia |
| `60` (predeterminado) | Salida una vez cada 60 segundos | Monitoreo regular en entorno de producción |
| `300` | Salida una vez cada 5 minutos | Análisis de tendencias a largo plazo |

**Ejemplos**:
```bash
# Monitoreo de alta frecuencia (cada 10 segundos)
peeka-cli monitor "myapp.api.handler" --interval 10

# Monitoreo a largo plazo (cada 5 minutos)
peeka-cli monitor "myapp.batch.process" --interval 300
```

**Notas**:
- Intervalo más corto = datos de salida más frecuentes (recomienda establecer basado en frecuencia de llamada de función)
- Intervalo demasiado corto puede resultar en muy pocas llamadas por ciclo, limitando significancia estadística
- Intervalo demasiado largo puede perder cambios importantes de rendimiento

### -c, --cycles - Número de Ciclos de Monitoreo

Controla la cantidad de ciclos que continúa el monitoreo.

| Valor | Descripción | Escenario de Uso |
|-------|-------------|----------|
| `-1` (predeterminado) | Monitoreo ilimitado | Monitoreo continuo en entorno de producción |
| `1` | Monitorear 1 ciclo luego detenerse | Vista rápida de estado actual |
| `10` | Monitorear 10 ciclos luego detenerse | Monitoreo de duración fija |
| `60` | Monitorear 60 ciclos luego detenerse | Monitoreo de 1 hora (interval=60) |

**Ejemplos**:
```bash
# Monitorear una vez luego detenerse (ver estadísticas del 1 minuto actual)
peeka-cli monitor "myapp.func" --interval 60 -c 1

# Monitorear durante 10 minutos (10 veces, una vez por minuto)
peeka-cli monitor "myapp.func" --interval 60 -c 10

# Monitoreo continuo (hasta que se detenga manualmente)
peeka-cli monitor "myapp.func" --interval 60
```

**Cálculo de Duración Total**:
- Duración total = `interval` × `cycles`
- Ejemplo: `--interval 60 -c 10` = 10 minutos
- Ejemplo: `--interval 30 -c 120` = 1 hora

---

## Descripción de Métricas

### Métricas Básicas

| Métrica | Tipo | Descripción |
|--------|------|-------------|
| `total` | int | Conteo total de llamadas en el ciclo actual |
| `success` | int | Conteo de llamadas exitosas (ninguna excepción lanzada) |
| `fail` | int | Conteo de llamadas fallidas (excepción lanzada) |

### Métricas Derivadas

| Métrica | Tipo | Fórmula | Descripción |
|--------|------|---------|-------------|
| `fail_rate` | float | `fail / total` | Tasa de fracaso (0-1, 4 decimales) |
| `rt_avg` | float | `sum(duration) / total` | Tiempo de respuesta promedio (milisegundos, 3 decimales) |
| `rt_min` | float | `min(duration)` | Tiempo de respuesta mínimo (milisegundos, 3 decimales) |
| `rt_max` | float | `max(duration)` | Tiempo de respuesta máximo (milisegundos, 3 decimales) |

### Metadatos

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `watch_id` | string | Identificador único para la tarea de monitoreo |
| `cycle` | int | Número de ciclo actual (comienza desde 1) |

---

## Formato de Salida

El comando `monitor` genera salida en formato JSON Lines (una línea por ciclo), facilitando procesamiento en streaming.

### Ejemplo Completo de Salida

```json
{
  "watch_id": "monitor_a1b2c3d4",
  "cycle": 1,
  "total": 1234,
  "success": 1200,
  "fail": 34,
  "fail_rate": 0.0275,
  "rt_avg": 45.678,
  "rt_min": 5.123,
  "rt_max": 234.567
}
```

### Descripción de Campos

| Campo | Tipo | Descripción | Ejemplo |
|-------|------|-------------|---------|
| `watch_id` | string | Identificador único para la tarea de monitoreo | `"monitor_a1b2c3d4"` |
| `cycle` | int | Número de ciclo (comienza desde 1) | `1`, `2`, `3`... |
| `total` | int | Conteo total de llamadas en el ciclo actual | `1234` |
| `success` | int | Conteo de llamadas exitosas | `1200` |
| `fail` | int | Conteo de llamadas fallidas | `34` |
| `fail_rate` | float | Tasa de fracaso (0-1) | `0.0275` (2.75%) |
| `rt_avg` | float | Tiempo de respuesta promedio (milisegundos) | `45.678` |
| `rt_min` | float | Tiempo de respuesta mínimo (milisegundos) | `5.123` |
| `rt_max` | float | Tiempo de respuesta máximo (milisegundos) | `234.567` |

### Descripción de Ciclo Estadístico

**Importante**: Los datos estadísticos para cada ciclo son **acumulativos** (desde el inicio del monitoreo hasta el momento actual).

```json
// Ciclo 1 (0-60 segundos)
{"cycle": 1, "total": 100, "rt_avg": 50}

// Ciclo 2 (0-120 segundos, acumulativo)
{"cycle": 2, "total": 250, "rt_avg": 55}

// Ciclo 3 (0-180 segundos, acumulativo)
{"cycle": 3, "total": 400, "rt_avg": 53}
```

**Para calcular datos de ciclo individual**:
```bash
# Calcular nuevas llamadas agregadas en el ciclo 2
total_cycle2 - total_cycle1 = 250 - 100 = 150
```

---

## Ejemplos de Uso

### Ejemplo 1: Monitoreo Básico

**Escenario**: Monitorear función de entrada de API, salida de estadísticas una vez por minuto.

```bash
peeka-cli monitor "myapp.api.handle_request" --interval 60
```

**Salida**:
```json
{"watch_id":"monitor_a1b2c3d4","cycle":1,"total":1234,"success":1200,"fail":34,"fail_rate":0.0275,"rt_avg":45.678,"rt_min":5.123,"rt_max":234.567}
{"watch_id":"monitor_a1b2c3d4","cycle":2,"total":2456,"success":2400,"fail":56,"fail_rate":0.0228,"rt_avg":48.123,"rt_min":5.123,"rt_max":345.678}
{"watch_id":"monitor_a1b2c3d4","cycle":3,"total":3678,"success":3600,"fail":78,"fail_rate":0.0212,"rt_avg":46.890,"rt_min":5.123,"rt_max":345.678}
...
```

### Ejemplo 2: Monitoreo de Duración Fija

**Escenario**: Monitorear durante 5 minutos (5 veces, una vez por minuto).

```bash
peeka-cli monitor "myapp.payment.charge" --interval 60 -c 5
```

**Comportamiento**:
- Genera salida de 5 datos estadísticos
- Se detiene automáticamente después de la quinta salida
- Duración total de monitoreo: 5 minutos

### Ejemplo 3: Monitoreo en Tiempo Real (Alta Frecuencia)

**Escenario**: Monitoreo en tiempo real durante prueba de carga, salida una vez cada 10 segundos.

```bash
peeka-cli monitor "myapp.process" --interval 10 | \
  jq -r '"\(.cycle): \(.total) llamadas, \(.rt_avg)ms promedio, \(.fail) fracasos"'
```

**Salida**:
```
1: 123 llamadas, 45.67ms promedio, 2 fracasos
2: 278 llamadas, 52.34ms promedio, 5 fracasos
3: 456 llamadas, 58.90ms promedio, 8 fracasos
...
```

### Ejemplo 4: Alerta de Tasa de Fracaso

**Escenario**: Monitorear tasa de fracaso, emitir alerta cuando excede 5%.

```bash
peeka-cli monitor "myapp.critical_func" --interval 30 | \
  jq -r 'if .fail_rate > 0.05 then
            "⚠️  ALERTA: Tasa de fracaso \(.fail_rate * 100)% en ciclo \(.cycle)"
          else
            "✅  Saludable: \(.fail_rate * 100)% tasa de fracaso"
          end'
```

**Salida**:
```
✅  Saludable: 1.2% tasa de fracaso
✅  Saludable: 2.3% tasa de fracaso
⚠️  ALERTA: Tasa de fracaso 6.7% en ciclo 3
```

### Ejemplo 5: Tendencia de Tiempo de Respuesta

**Escenario**: Monitorear cambios de tiempo de respuesta, graficar gráfico de tendencia.

```bash
# Monitorear durante 30 minutos (30 veces, una vez por minuto)
peeka-cli monitor "myapp.db.query" --interval 60 -c 30 | \
  jq -r '"\(.cycle) \(.rt_avg)"' > rt_trend.dat

# Usa gnuplot para graficar tendencia (requiere instalación de gnuplot)
gnuplot <<EOF
set terminal png size 800,600
set output 'rt_trend.png'
set xlabel 'Ciclo'
set ylabel 'Tiempo de Respuesta (ms)'
set title 'Tendencia de Tiempo de Respuesta'
plot 'rt_trend.dat' with lines
EOF
```

### Ejemplo 6: Combinado con el comando watch

**Escenario**: Primero usa `monitor` para descubrir problemas de rendimiento, luego usa `watch` para investigación profunda.

```bash
# Paso 1: Iniciar monitoreo, descubrir tiempo de respuesta anormal
peeka-cli monitor "myapp.process" --interval 60 | \
  jq -r 'select(.rt_avg > 100)'
# Salida: {"cycle": 5, "rt_avg": 234.567, ...}

# Paso 2: Usa watch para ver información detallada de llamada
peeka-cli watch "myapp.process" -n 10
# Analizar argumentos, valores de retorno, tiempo de ejecución

# Paso 3: Detener monitoreo después de localizar el problema
# (Ctrl+C o usa parámetro cycles)
```

---

## Flujos de Trabajo de Monitoreo Completos

### Flujo de Trabajo 1: Establecer Línea Base de Rendimiento en Producción

**Objetivo**: Establecer línea base de rendimiento bajo carga normal para comparación de rendimiento posterior.

```bash
# Paso 1: Monitorear función central durante 1 hora
peeka-cli monitor "myapp.api.handle_request" \
  --interval 60 -c 60 > baseline_$(date +%Y%m%d).jsonl

# Paso 2: Calcular estadísticas de línea base
jq -s '{
  avg_total: (map(.total) | add / length),
  avg_rt: (map(.rt_avg) | add / length),
  p50_rt: (map(.rt_avg) | sort)[30],
  p95_rt: (map(.rt_avg) | sort)[57],
  max_fail_rate: (map(.fail_rate) | max)
}' baseline_$(date +%Y%m%d).jsonl > baseline_summary.json

# Paso 3: Ver línea base
cat baseline_summary.json
```

**Salida**:
```json
{
  "avg_total": 567.8,
  "avg_rt": 45.678,
  "p50_rt": 44.123,
  "p95_rt": 67.890,
  "max_fail_rate": 0.0123
}
```

### Flujo de Trabajo 2: Detección de Degradación de Rendimiento

**Objetivo**: Comparar rendimiento actual con línea base, detectar degradación de rendimiento.

```bash
# Paso 1: Cargar datos de línea base
baseline_rt=$(jq -r '.avg_rt' baseline_summary.json)
echo "RT promedio de línea base: ${baseline_rt}ms"

# Paso 2: Monitoreo y comparación en tiempo real
peeka-cli monitor "myapp.api.handle_request" --interval 60 | \
  jq -r --arg baseline "$baseline_rt" '
    if .rt_avg > ($baseline | tonumber * 1.5) then
      "⚠️  DEGRADACIÓN: \(.rt_avg)ms (línea base: \($baseline)ms)"
    else
      "✅  Normal: \(.rt_avg)ms"
    end
  '
```

**Salida**:
```
✅  Normal: 47.123ms
✅  Normal: 48.567ms
⚠️  DEGRADACIÓN: 89.012ms (línea base: 45.678ms)
```

### Flujo de Trabajo 3: Comparación de Rendimiento de Múltiples Funciones

**Objetivo**: Comparar diferencias de rendimiento entre diferentes implementaciones (ej., API v1 vs v2).

```bash
# Paso 1: Monitorear dos funciones simultáneamente
peeka-cli monitor "myapp.api.v1.handler" --interval 30 > v1.jsonl &
peeka-cli monitor "myapp.api.v2.handler" --interval 30 > v2.jsonl &

# Paso 2: Esperar para recolectar datos (10 minutos)
sleep 600

# Paso 3: Detener monitoreo
kill %1 %2

# Paso 4: Análisis comparativo
echo "API v1:"
jq -s 'map(.rt_avg) | add / length' v1.jsonl
echo "API v2:"
jq -s 'map(.rt_avg) | add / length' v2.jsonl
```

**Salida**:
```
API v1:
67.890
API v2:
45.123
```

**Conclusión**: v2 tiene mejor rendimiento que v1 (33% más rápido en promedio).

### Flujo de Trabajo 4: Monitoreo de Prueba de Carga

**Objetivo**: Monitorear rendimiento del sistema durante prueba de carga, observar curva de rendimiento.

```bash
# Paso 1: Iniciar monitoreo (alta frecuencia, cada 10 segundos)
peeka-cli monitor "myapp.process" --interval 10 > load_test.jsonl &

# Paso 2: Iniciar prueba de carga (otra terminal)
# ab -n 10000 -c 100 http://localhost:8000/api/endpoint

# Paso 3: Observación en tiempo real de métricas de rendimiento
tail -f load_test.jsonl | \
  jq -r '"\(.cycle): \(.total) llamadas, \(.rt_avg)ms promedio, \(.fail_rate*100)% fracaso"'

# Paso 4: Detener monitoreo después de que finalice la prueba
kill %1

# Paso 5: Analizar curva de rendimiento
jq -r '"\(.cycle) \(.total) \(.rt_avg) \(.fail_rate)"' load_test.jsonl > metrics.dat
```

---

## Notas Importantes

### 1. Impacto en el Rendimiento

**Grado de Impacto**:
- **Registro estadístico**: Cada llamada agrega aproximadamente 0.1-0.2ms de sobrecoste
- **Cómputo estadístico**: Cada ciclo aproximadamente 0.01ms (despreciable)
- **Salida JSON**: Cada ciclo aproximadamente 0.1ms (despreciable)

**Sobrecoste Total**: Aproximadamente 0.1-0.2ms por llamada (10 veces más ligero que el comando `watch`)

**Ventajas**:
- No registra datos detallados, uso de memoria mínimo
- Adecuado para operación a largo plazo, impacto de rendimiento despreciable
- Adecuado para monitoreo de funciones de alta frecuencia

### 2. Datos Estadísticos son Acumulativos

**Importante**: Los datos estadísticos de `monitor` son **acumulativos**, no por ciclo.

```json
// Ciclo 1: Acumulado 0-60 segundos
{"cycle": 1, "total": 100}

// Ciclo 2: Acumulado 0-120 segundos (no solo los segundos 61-120)
{"cycle": 2, "total": 250}
```

**Cálculo de Datos de Ciclo Individual**:
```bash
# Extraer conteo de llamadas de ciclo individual
jq -s '[.[0].total] + [range(1; length) |
  {cycle: .[.].cycle, calls: .[.].total - .[-1].total}]' monitor.jsonl
```

### 3. Estadísticas de Tiempo de Respuesta

**Método de Cálculo de rt_avg**:
- Promedio acumulado: `sum(todas las duraciones de llamada) / total`
- No es promedio móvil ponderado
- No es promedio de ciclo individual

**Ejemplo**:
```json
// Ciclo 1: 100 llamadas, promedio 50ms
{"cycle": 1, "total": 100, "rt_avg": 50}

// Ciclo 2: 100 nuevas llamadas, promedio 60ms
// Promedio acumulado = (100*50 + 100*60) / 200 = 55ms
{"cycle": 2, "total": 200, "rt_avg": 55}
```

### 4. Definición de Fracaso

**Reglas de Conteo de fail**:
- Función lanza excepción → `fail` +1
- Función retorna normalmente → `success` +1
- Incluso si retorna `None` o código de error, mientras no haya excepción, cuenta como `success`

**Notas**:
- Si la aplicación usa códigos de error en lugar de excepciones, el conteo de `fail` puede ser 0
- Recomienda combinar con análisis de lógica de negocio para autenticidad verdadera de `success`

### 5. Detener Monitoreo

**Método 1**: Usa parámetro `-c` para limitar el conteo de ciclos (detención automática)
```bash
peeka-cli monitor "myapp.func" --interval 60 -c 10
```

**Método 2**: Ctrl+C manual (no afecta al proceso objetivo)
```bash
peeka-cli monitor "myapp.func" --interval 60
# Presiona Ctrl+C para detener
```

**Importante**:
- Después de detener el monitoreo, la función objetivo vuelve al estado original (sin impacto en el rendimiento)
- Los datos estadísticos no se persisten (necesitas guardar la salida manualmente)
- Múltiples tareas de monitoreo son independientes

### 6. Múltiples Tareas de Monitoreo

**Soporte**: Se pueden iniciar múltiples tareas `monitor` para monitorear diferentes funciones simultáneamente.

```bash
# Terminal 1: Monitorear API
peeka-cli monitor "myapp.api.handler" --interval 60

# Terminal 2: Monitorear base de datos
peeka-cli monitor "myapp.db.query" --interval 60

# Terminal 3: Monitorear caché
peeka-cli monitor "myapp.cache.get" --interval 60
```

**Notas**:
- Cada tarea recolecta estadísticas de forma independiente, sin interferencia mutua
- Más funciones monitoreadas = sobrecoste de rendimiento acumulado
- Recomienda monitorear no más de 10 funciones

---

## Preguntas Frecuentes

### P1: ¿Cómo ver tareas de monitoreo actuales?

**Método 1**: Usa acción `status` (si CLI lo soporta)
```bash
peeka-cli reset -l
```

**Método 2**: Verificar si el proceso tiene conexiones de cliente correspondientes
```bash
ps aux | grep "peeka-cli monitor" | grep 12345
```

**Método 3**: Ver conexiones de socket del proceso objetivo
```bash
lsof -p 12345 | grep peeka
```

### P2: ¿Cómo calcular conteo de llamadas para ciclo individual?

**Método**: Usa `jq` para calcular la diferencia entre ciclos adyacentes.

```bash
jq -s '
  [range(0; length)] | map({
    cycle: .[.].cycle,
    calls: (if . == 0 then .[0].total else .[.].total - .[.-1].total end),
    rt_avg: .[.].rt_avg
  })
' monitor.jsonl
```

**Salida**:
```json
[
  {"cycle": 1, "calls": 100, "rt_avg": 50},
  {"cycle": 2, "calls": 150, "rt_avg": 55},
  {"cycle": 3, "calls": 200, "rt_avg": 53}
]
```

### P3: ¿Por qué rt_avg cayó repentinamente?

**Posibles Razones**:
1. **Nuevas llamadas tienen tiempo de respuesta más rápido**: El promedio acumulado se reduce
2. **Caché entra en efecto**: Llamadas posteriores golpean la caché
3. **Carga disminuyó**: Recursos del sistema suficientes, respuesta más rápida

**Método de Solución de Problemas**:
```bash
# Ver cambios en rt_min y rt_max
jq -r '"\(.cycle) \(.rt_min) \(.rt_avg) \(.rt_max)"' monitor.jsonl
```

**Ejemplo**:
```
1  5.123  50.000  234.567
2  5.123  48.000  234.567  ← rt_avg cae, pero rt_min/max sin cambios
3  2.456  35.000  234.567  ← rt_min cae, indicando nuevas llamadas más rápidas
```

### P4: ¿Cómo monitorear funciones async?

**Respuesta**: El comando `monitor` soporta funciones async (async def).

```bash
peeka-cli monitor "myapp.async_handler" --interval 60
```

**Notas**:
- Las estadísticas reflejan el **tiempo de ejecución real** de la función async (excluye tiempo de espera)
- Si la función tiene `await` internamente, el tiempo de espera no se incluye en `rt_avg`

### P5: ¿Por qué el número total es grande pero la salida es escasa?

**Razón**: `monitor` solo genera salida de **estadísticas periódicas**, no cada llamada.

- `total` es el conteo acumulativo de llamadas
- Solo genera salida de 1 estadística por `interval`
- Si necesitas información detallada por llamada, usa el comando `watch`

### P6: ¿Puedo monitorear funciones de la biblioteca estándar?

**Respuesta**: Sí, pero ten en cuenta el impacto en el rendimiento.

```bash
# Monitorear json.dumps (puede tener frecuencia de llamada extremadamente alta)
peeka-cli monitor "json.dumps" --interval 10 -c 6
```

**Advertencia**:
- Las funciones de la biblioteca estándar generalmente tienen frecuencia de llamada extremadamente alta
- Incluso el `monitor` ligero puede tener sobrecoste acumulado notable
- Recomienda probar primero con `--interval 10 -c 1`, observar conteo `total`

---

## Técnicas Avanzadas

### 1. Tablero de Rendimiento en Tiempo Real

**Escenario**: Usa el comando `watch` de shell para crear tablero en tiempo real.

```bash
#!/bin/bash
# dashboard.sh

PID=12345
PATTERN="myapp.api.handler"
LOG="monitor.jsonl"

# Iniciar monitoreo (en segundo plano)
peeka-cli monitor "$PATTERN" --interval 10 > $LOG &
MONITOR_PID=$!

# Tablero de visualización en tiempo real
while kill -0 $MONITOR_PID 2>/dev/null; do
  clear
  echo "=== Tablero de Rendimiento ==="
  echo ""
  tail -1 $LOG | jq -r '
    "Ciclo: \(.cycle)",
    "Llamadas Totales: \(.total)",
    "Tasa de Éxito: \((1 - .fail_rate) * 100)%",
    "Tasa de Fracaso: \(.fail_rate * 100)%",
    "RT Promedio: \(.rt_avg)ms",
    "RT Mínimo: \(.rt_min)ms",
    "RT Máximo: \(.rt_max)ms"
  '
  sleep 10
done
```

### 2. Integración con Prometheus

**Escenario**: Exportar datos de monitoreo a Prometheus.

```bash
#!/bin/bash
# export_to_prometheus.sh

PID=12345
PATTERN="myapp.api.handler"
METRICS_FILE="/var/lib/node_exporter/textfile_collector/peeka.prom"

peeka-cli monitor "$PATTERN" --interval 60 | \
  jq -r '
    "peeka_calls_total{pattern=\"\($PATTERN)\"} \(.total)",
    "peeka_success_total{pattern=\"\($PATTERN)\"} \(.success)",
    "peeka_fail_total{pattern=\"\($PATTERN)\"} \(.fail)",
    "peeka_fail_rate{pattern=\"\($PATTERN)\"} \(.fail_rate)",
    "peeka_rt_avg_ms{pattern=\"\($PATTERN)\"} \(.rt_avg)",
    "peeka_rt_min_ms{pattern=\"\($PATTERN)\"} \(.rt_min)",
    "peeka_rt_max_ms{pattern=\"\($PATTERN)\"} \(.rt_max)"
  ' > $METRICS_FILE
```

**Ejemplos de Consulta Prometheus**:
```promql
# Alerta de tasa de fracaso
rate(peeka_fail_total[5m]) / rate(peeka_calls_total[5m]) > 0.05

# Tendencia de tiempo de respuesta
peeka_rt_avg_ms{pattern="myapp.api.handler"}
```

### 3. Detección de Regresión de Rendimiento

**Escenario**: Detectar automáticamente degradación de rendimiento después de cada despliegue.

```bash
#!/bin/bash
# regression_test.sh

PID=12345
PATTERN="myapp.api.handler"
BASELINE="baseline_rt.txt"

# Leer línea base
baseline_rt=$(cat $BASELINE)

# Monitorear durante 5 minutos
current_rt=$(peeka-cli monitor "$PATTERN" --interval 60 -c 5 | \
  jq -s 'map(.rt_avg) | add / length')

# Comparar
if (( $(echo "$current_rt > $baseline_rt * 1.2" | bc -l) )); then
  echo "❌ REGRESIÓN: $current_rt ms (línea base: $baseline_rt ms)"
  exit 1
else
  echo "✅ PASS: $current_rt ms (línea base: $baseline_rt ms)"
  exit 0
fi
```

### 4. Estadísticas Agregadas de Múltiples Funciones

**Escenario**: Monitorear múltiples funciones, agregar datos estadísticos.

```bash
# Monitorear 3 funciones (en paralelo)
peeka-cli monitor "myapp.api.v1" --interval 60 -c 10 > v1.jsonl &
peeka-cli monitor "myapp.api.v2" --interval 60 -c 10 > v2.jsonl &
peeka-cli monitor "myapp.api.v3" --interval 60 -c 10 > v3.jsonl &

# Esperar a que termine
wait

# Agregar estadísticas
jq -s '
  reduce .[] as $item ({};
    .total += $item.total |
    .success += $item.success |
    .fail += $item.fail
  ) |
  .fail_rate = .fail / .total
' v1.jsonl v2.jsonl v3.jsonl
```

### 5. Script de Alerta Automática

**Escenario**: Enviar alertas automáticamente cuando se detectan anomalías (Slack, email, etc.).

```bash
#!/bin/bash
# alert_on_degradation.sh

PID=12345
PATTERN="myapp.critical"
THRESHOLD_RT=100      # Umbral de tiempo de respuesta (milisegundos)
THRESHOLD_FAIL=0.05   # Umbral de tasa de fracaso (5%)

peeka-cli monitor "$PATTERN" --interval 60 | \
  jq -r --arg rt "$THRESHOLD_RT" --arg fail "$THRESHOLD_FAIL" '
    if .rt_avg > ($rt | tonumber) or .fail_rate > ($fail | tonumber) then
      "ALERTA: ciclo=\(.cycle), rt=\(.rt_avg)ms, fail=\(.fail_rate*100)%"
    else
      empty
    end
  ' | \
  while read line; do
    # Enviar alerta (ejemplo: Slack)
    curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
      -H 'Content-Type: application/json' \
      -d "{\"text\": \"$line\"}"
  done
```

### 6. Análisis de Datos Históricos

**Escenario**: Analizar datos históricos de monitoreo, encontrar patrones de rendimiento.

```bash
# Recolectar 1 semana de datos de monitoreo
for day in {1..7}; do
  peeka-cli monitor "myapp.func" --interval 3600 -c 24 > \
    monitor_day${day}.jsonl
  sleep 86400  # 1 día
done

# Analizar rendimiento a la misma hora cada día
for hour in {0..23}; do
  echo -n "Hora $hour: "
  jq -s --arg h "$hour" 'map(select(.cycle == ($h | tonumber + 1))) |
    map(.rt_avg) | add / length' monitor_day*.jsonl
done
```

---

## Resumen

El comando `monitor` es una herramienta potente para monitoreo de rendimiento en entornos de producción, especialmente adecuada para:
- Monitoreo de rendimiento a largo plazo
- Establecer líneas base de rendimiento
- Detección de degradación de rendimiento
- Monitoreo en tiempo real durante prueba de carga
- Integración con sistemas de monitoreo como Prometheus

**Mejores Prácticas**:
- Elige `--interval` apropiado basado en frecuencia de llamada de función (recomienda 30-60 segundos)
- Usa `-c` para limitar el conteo de ciclos (evita olvidar detener)
- Salida a archivo (`> monitor.jsonl`) para análisis posterior
- Combina con `jq` para potente análisis de datos
- Usa con el comando `watch` (primero `monitor` para descubrir problemas, luego `watch` para investigación profunda)

**Siguientes Pasos**:
- Conoce el comando [`watch`](watch) (observa información detallada de funciones)
- Conoce el comando [`stack`](stack) (rastrea pilas de llamadas)
- Conoce el comando [`memory`](memory) (análisis de memoria)
- Referente a [Guía para Desarrolladores de Agentes de IA](../ai-skill.md)
