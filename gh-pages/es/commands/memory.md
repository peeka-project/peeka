---
layout: default
title: memory
parent: Referencia de Comandos
nav_order: 7
---

# memory - Análisis de memoria
{: .no_toc }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

## Introducción

El comando `memory` se usa para analizar el **uso de memoria** en procesos Python en ejecución, proporcionando 10 operaciones de diagnóstico: resumen de memoria, control de rastreo, análisis de asignaciones, gestión de instantáneas, comparación de instantáneas, consultas de cadenas de referencias, exportación de instantáneas y estadísticas de GC. Esta es la herramienta principal de diagnóstico de memoria de Peeka, adecuada para solución de problemas de fugas de memoria y optimización de rendimiento en entornos de producción.

## Uso en TUI

En modo TUI, presiona la tecla **`6`** para cambiar a la **Vista Memory**, que proporciona 4 pestañas y características interactivas ricas:

#### Pestaña Resumen (Resumen de Memoria)

- Muestra RSS del proceso (memoria física) en MB
- Gráfico Sparkline de tendencia RSS (últimos 100 puntos de muestra)
- Memoria rastreada actual / memoria pico de tracemalloc
- Contadores de tres generaciones de GC (gen0, gen1, gen2)
- Tabla **Objetos Principales por Tamaño**: tipo, conteo, Δconteo, tamaño, Δtamaño
  - Delta calculado automáticamente en cada actualización (rojo = crecimiento, verde = disminución)
  - Encabezados de columna ordenables

#### Pestaña Asignaciones (Puntos Calientes de Asignación)

- Requiere que el rastreo se haya iniciado primero
- Muestra las N principales asignaciones de memoria: Ranking, Tamaño, Conteo, Ubicación (archivo:línea)
- Se sincroniza con actualizaciones de actualización automática

#### Pestaña Diff (Comparación de Instantáneas)

- **Botón Snap**: Tomar instantánea de tracemalloc (máximo 2, FIFO)
- **Botón Diff**: Comparar dos instantáneas, la tabla muestra Ubicación, ΔTamaño, Nuevo, Viejo, ΔConteo
- Datos delta con codificación de colores (rojo = crecimiento, verde = disminución)

#### Pestaña Referencias (Análisis de Cadena de Referencias)

- Ingresa nombre de tipo (ej., `dict`, `MyClass`)
- **Botón Referrers**: Vista de árbol de quién referencia objetos de ese tipo (encontrar causa raíz de fuga)
- **Botón Referents**: Vista de árbol de qué objetos referencian objetos de ese tipo (analizar estructura de objeto)

#### Controles y Atajos de Teclado

| Control | Atajo | Función |
|---------|:----------:|----------|
| Actualizar | `r` | Actualizar manualmente resumen + asignaciones |
| Rastrear | `T` | Iniciar/detener rastreo de tracemalloc |
| GC | `g` | Activar actualización de estadísticas de GC |
| Volcar | — | Exportar archivo de instantánea a disco |
| Auto | `a` | Actualización automática (intervalo de 5 segundos) |
| Entrada nframe | — | Establecer profundidad de pila de tracemalloc (1-50) |
| Entrada límite | — | Establecer conteo de visualización de GC/asignación (1-100) |

**Comandos CLI equivalentes**: Todos los ejemplos a continuación usan comandos CLI para demostración. TUI proporciona la misma funcionalidad con una interfaz gráfica.

## Escenarios de Uso

- **Diagnóstico de fuga de memoria**: Ver qué ubicaciones de código asignan la mayor cantidad de memoria
- **Optimización de rendimiento**: Identificar puntos calientes de asignación de memoria, optimizar uso de memoria
- **Análisis de GC**: Contar cantidades de tipos de objetos, descubrir conteos anormales de objetos
- **Comparación de instantáneas**: Exportar múltiples instantáneas para comparación fuera de línea del crecimiento de memoria
- **Monitoreo RSS**: Ver uso de memoria física (RSS) del proceso

## Formato del Comando

```bash
peeka-cli attach <pid>
peeka-cli memory [options]
```

### Parámetros

| Parámetro | Descripción | Valor por defecto | Ejemplo |
|-----------|-------------|-------------------|---------|
| `--action` | Tipo de operación de memoria | `overview` | `--action start` |
| `--nframe` | Profundidad de pila de llamadas de tracemalloc | `25` | `--nframe 50` |
| `--group-by` | Método de agrupación de asignaciones | `lineno` | `--group-by filename` |
| `--limit` | Límite de conteo de resultados | `20` | `--limit 50` |
| `--filename` | Nombre de archivo de instantánea | Generado automáticamente | `--filename snapshot1` |
| `--type-name` | Nombre de tipo (para referrers/referents) | - | `--type-name dict` |
| `--max-depth` | Profundidad de recursión de cadena de referencias | `2` | `--max-depth 3` |
| `--max-per-level` | Máximo de entradas por nivel | `10` | `--max-per-level 20` |

### Tipos de Operación action

| Acción | Descripción | Requiere start | Propósito Principal |
|--------|-------------|----------------|--------------|
| **overview** | Resumen de memoria | ❌ No | Ver RSS, estado de GC, estado de tracemalloc |
| **start** | Iniciar rastreo | - | Habilitar rastreo de memoria de tracemalloc |
| **stop** | Detener rastreo | ❌ No | Cerrar tracemalloc, liberar sobrecoste de rastreo |
| **top** | N principales asignaciones | ✅ Sí | Ver puntos calientes de asignación de memoria (por ubicación de código) |
| **dump** | Exportar instantánea | ✅ Sí | Guardar instantánea para análisis fuera de línea |
| **gc** | Estadísticas de GC | ❌ No | Contar cantidades de tipos de objetos |
| **snapshot** | Instantánea de memoria | ✅ Sí | Guardar instantánea en memoria (FIFO, máximo 2) |
| **diff** | Comparación de instantáneas | ✅ Sí | Comparar las dos últimas instantáneas para cambios de memoria |
| **referrers** | Consulta de referentes | ❌ No | Encontrar quién mantiene objetos del tipo especificado (investigación de fugas) |
| **referents** | Consulta de referentes | ❌ No | Encontrar qué objetos referencia el tipo especificado (análisis de estructura) |

## Uso Básico

### 1. Resumen de Memoria (overview)

Ver el estado actual de memoria del proceso, **no necesita iniciar rastreo**.

```bash
# Ver resumen de memoria (acción predeterminada)
peeka-cli memory --action overview

# O usa otra acción
peeka-cli memory --action start
```

**Ejemplo de Salida**:

```json
{
  "status": "success",
  "action": "overview",
  "timestamp": 1738328400.0,
  "pid": 12345,
  "rss_bytes": 524288000,
  "rss_source": "procfs",
  "tracemalloc": {
    "enabled": false,
    "current_bytes": null,
    "peak_bytes": null
  },
  "gc": {
    "enabled": true,
    "counts": [150, 10, 2],
    "stats": [
      {"collections": 45, "collected": 1234, "uncollectable": 0},
      {"collections": 4, "collected": 89, "uncollectable": 0},
      {"collections": 0, "collected": 0, "uncollectable": 0}
    ]
  }
}
```

**Descripción de Campos**:

| Campo | Descripción | Valor de Ejemplo |
|-------|-------------|---------------|
| `rss_bytes` | Memoria física del proceso (bytes) | `524288000` (500 MB) |
| `rss_source` | Fuente de RSS | `"procfs"` or `"resource_maxrss"` |
| `tracemalloc.enabled` | Si tracemalloc está ejecutándose | `true` / `false` |
| `tracemalloc.current_bytes` | Memoria actualmente rastreada (solo cuando se está rastreando) | `123456789` |
| `tracemalloc.peak_bytes` | Memoria pico (solo cuando se está rastreando) | `234567890` |
| `gc.enabled` | Si GC está habilitado | `true` / `false` |
| `gc.counts` | Contadores de GC (gen0, gen1, gen2) | `[150, 10, 2]` |
| `gc.stats` | Estadísticas de GC por generación | Ver tabla abajo |

**Campos de estadísticas de GC**:

| Campo | Descripción |
|-------|-------------|
| `collections` | Número de ejecuciones de GC para esta generación |
| `collected` | Número de objetos colectados |
| `uncollectable` | Número de objetos no colectables (advertencia: posible fuga) |

### 2. Iniciar Rastreo de Memoria (start)

Habilita el módulo `tracemalloc` de Python para comenzar a rastrear asignaciones de memoria.

```bash
# Usa profundidad predeterminada (25 niveles de pila de llamadas)
peeka-cli memory --action start

# Profundidad de pila de llamadas personalizada (1-50)
peeka-cli memory --action start --nframe 50
```

**Ejemplo de Salida**:

```json
{
  "status": "success",
  "action": "start",
  "message": "tracemalloc started successfully",
  "nframe": 25
}
```

**Descripción de Parámetros**:

- `--nframe`: Profundidad de pila de llamadas (1-50), predeterminado 25
  - Mayor profundidad = rastreo más detallado pero mayor sobrecoste
  - Recomendado: producción 25, desarrollo/depuración 50

**Idempotencia**:

Si tracemalloc ya está ejecutándose, llamar `start` nuevamente no generará error:

```json
{
  "status": "success",
  "action": "start",
  "message": "tracemalloc is already running",
  "was_already_running": true
}
```

**Impacto en el Rendimiento**:

- **Sobrecoste**: aproximadamente 5-10% de sobrecoste de rendimiento y memoria
- **Recomendación**: Iniciar durante horas de menor actividad, o habilitar solo brevemente

### 3. Detener Rastreo de Memoria (stop)

Cierra `tracemalloc` y libera el sobrecoste de rastreo.

```bash
peeka-cli memory --action stop
```

**Ejemplo de Salida**:

```json
{
  "status": "success",
  "action": "stop",
  "message": "tracemalloc stopped successfully",
  "was_running": true
}
```

**Notas Importantes**:

- ⚠️ **Pérdida de datos después de detener**: detener limpia todos los datos de rastreo
- 📝 **Exportar antes de detener**: si necesitas preservar datos, ejecuta `dump` primero
- ✅ **Operación idempotente**: detener no genera error incluso si no se está ejecutando

```bash
# Flujo correcto: exportar primero, luego detener
peeka-cli memory --action dump --filename production_snapshot
peeka-cli memory --action stop
```

### 4. Ver N Principales Asignaciones de Memoria (top)

Muestra ubicaciones de código con mayor uso de memoria (**requiere iniciar primero**).

```bash
# Ver top 20 asignaciones (agrupación predeterminada por número de línea)
peeka-cli memory --action top

# Ver top 50 asignaciones
peeka-cli memory --action top --limit 50

# Agrupar por nombre de archivo (ver qué módulo usa más)
peeka-cli memory --action top --group-by filename --limit 30
```

**Ejemplo de Salida** (agrupado por número de línea):

```json
{
  "status": "success",
  "action": "top",
  "group_by": "lineno",
  "limit": 20,
  "total_size_bytes": 245760000,
  "allocations": [
    {
      "rank": 1,
      "size_bytes": 24641536,
      "count": 1024,
      "traceback": [
        {"filename": "/app/models.py", "lineno": 145}
      ]
    },
    {
      "rank": 2,
      "size_bytes": 15925248,
      "count": 512,
      "traceback": [
        {"filename": "/app/cache.py", "lineno": 89}
      ]
    }
  ]
}
```

**Descripción de Campos**:

| Campo | Descripción |
|-------|-------------|
| `rank` | Ranking (descendente por size_bytes) |
| `size_bytes` | Bytes totales usados por este punto de asignación |
| `count` | Número de bloques de asignación |
| `traceback` | Pila de llamadas (arreglo, el más antiguo primero) |

**Comparación de Modo group-by**:

| Modo | Descripción | Escenario de Uso |
|------|-------------|----------|
| `lineno` | Agrupar por línea de código | Localizar líneas de código específicas |
| `filename` | Agrupar por archivo | Localizar módulos problemáticos |

**Ejemplo** (agrupado por nombre de archivo):

```bash
peeka-cli memory --action top --group-by filename --limit 10
```

```json
{
  "allocations": [
    {
      "rank": 1,
      "size_bytes": 104857600,
      "count": 5120,
      "traceback": [
        {"filename": "/app/models.py", "lineno": 1}
      ]
    }
  ]
}
```

> Nota: Cuando se agrupa por nombre de archivo, el campo `lineno` es 1 (no tiene significado real)

**Manejo de Errores**:

Si se llama a `top` sin iniciar el rastreo:

```json
{
  "status": "error",
  "action": "top",
  "error": "tracemalloc is not running. Run 'memory start' first."
}
```

### 5. Exportar Instantánea de Memoria (dump)

Guarda la instantánea de memoria actual en un archivo (**requiere iniciar primero**).

```bash
# Nombre de archivo generado automáticamente (marca de tiempo)
peeka-cli memory --action dump

# Especificar nombre de archivo
peeka-cli memory --action dump --filename my_snapshot

# Con protección de recorrido de ruta (extrae automáticamente basename)
peeka-cli memory --action dump --filename "../etc/passwd"
# En realidad se guarda como: /tmp/passwd.snapshot
```

**Ejemplo de Salida**:

```json
{
  "status": "success",
  "action": "dump",
  "file_path": "/tmp/peeka_dump_20260131_165420.snapshot",
  "size_bytes": 1048576
}
```

**Formato de Archivo**:

- **Formato**: Instantánea binaria de tracemalloc de Python (`.snapshot`)
- **Carga**: Usa `tracemalloc.Snapshot.load()` para cargar
- **Ubicación**: Directorio especificado por la variable de entorno `PEEKA_DUMP_DIR`, predeterminado `/tmp`

**Contenido de la Instantánea**:

- ✅ Todas las asignaciones de memoria activas actualmente
- ✅ Pila de llamadas para cada punto de asignación
- ✅ Tamaños y conteos de asignaciones
- ❌ **No es incremental**: instantánea completa en el momento actual

**Ejemplo de Análisis Fuera de Línea**:

```python
import tracemalloc

# Cargar instantánea
snapshot = tracemalloc.Snapshot.load('/tmp/peeka_dump_20260131_165420.snapshot')

# Agrupar por número de línea, ver top 10
stats = snapshot.statistics('lineno')
for stat in stats[:10]:
    print(f"{stat.size / 1024 / 1024:.1f} MB - {stat.count} blocks")
    print(f"  {stat.traceback[0].filename}:{stat.traceback[0].lineno}")
```

**Comparación de Instantáneas** (análisis incremental):

```python
# Cargar dos instantáneas
snapshot1 = tracemalloc.Snapshot.load('before.snapshot')
snapshot2 = tracemalloc.Snapshot.load('after.snapshot')

# Calcular diferencia
diff = snapshot2.compare_to(snapshot1, 'lineno')

# Ver crecimiento de memoria
for stat in diff[:10]:
    print(f"{stat.size_diff / 1024 / 1024:+.1f} MB - {stat.filename}:{stat.lineno}")
```

**Protección de Seguridad**:

- ✅ **Protección de recorrido de ruta**: Usa `os.path.basename()` automáticamente para extraer nombre de archivo
- ✅ **Restricción de directorio**: Solo puede escribir en `PEEKA_DUMP_DIR` o `/tmp`
- ✅ **Extensión automática**: El nombre de archivo obtiene automáticamente sufijo `.snapshot`

### 6. Estadísticas de Objetos GC (gc)

Cuenta cantidades de cada tipo de objeto (**no necesita iniciar**).

```bash
# Ver top 20 tipos de objetos (predeterminado)
peeka-cli memory --action gc

# Ver top 50 tipos de objetos
peeka-cli memory --action gc --limit 50
```

**Ejemplo de Salida**:

```json
{
  "status": "success",
  "action": "gc",
  "limit": 20,
  "total_objects": 1523891,
  "objects_by_type": [
    {"rank": 1, "type": "dict", "count": 345612},
    {"rank": 2, "type": "list", "count": 198234},
    {"rank": 3, "type": "tuple", "count": 156789},
    {"rank": 4, "type": "str", "count": 123456},
    {"rank": 5, "type": "function", "count": 89012},
    {"rank": 6, "type": "User", "count": 50000}
  ]
}
```

**Descripción de Campos**:

| Campo | Descripción |
|-------|-------------|
| `total_objects` | Total de objetos rastreados por GC |
| `objects_by_type` | Lista de tipos de objetos ordenada por conteo |
| `rank` | Ranking (descendente por conteo, ascendente por tipo si hay empate) |
| `type` | Nombre de tipo de objeto (`type(obj).__name__`) |
| `count` | Número de objetos de este tipo |

**Escenarios de Uso**:

- **Solución de problemas de fuga de memoria**: Descubrir crecimiento anormal de conteo de objetos
  ```bash
  # Ejemplo: Se encontraron 50000 objetos User (posiblemente no liberados)
  ```
- **Análisis de ciclo de vida de objetos**: Observar creación y destrucción de objetos
- **Monitoreo de caché**: Verificar si los objetos de caché son excesivos

**Nota de Rendimiento**:

- ⚠️ **Mayor sobrecoste**: `gc.get_objects()` devuelve todos los objetos (posiblemente millones)
- 📊 **Usar con cuidado en producción**: Recomienda durante horas de menor actividad o bajo tráfico
- ✅ **Tiene límite máximo**: Devuelve máximo 100 elementos (evita salida excesiva)

**Diferencia con top**:

| Dimensión | Comando `top` | Comando `gc` |
|-----------|---------------|--------------|
| **Requiere start** | ✅ Sí | ❌ No |
| **Muestra** | **Ubicaciones** de asignación de memoria (líneas de código) | Cantidades de **tipos** de objetos |
| **Qué indica** | Qué línea de código asignó cuánta memoria | Cuántos objetos de cada tipo existen |
| **Qué no indica** | Tipos de objetos | Cuánta memoria usa cada objeto |
| **Fuente de datos** | `tracemalloc` | `gc.get_objects()` |

### 7. Instantánea de Memoria (snapshot)

Guarda una instantánea de tracemalloc en memoria para comparación diff posterior (**requiere iniciar primero**).

```bash
# Tomar una instantánea (máximo 2 almacenadas, FIFO)
peeka-cli memory --action snapshot
```

**Ejemplo de Salida**:

```json
{
  "status": "success",
  "action": "snapshot",
  "snapshot_count": 1,
  "timestamp": 1738328400.0
}
```

**Notas de Uso**:

- Las instantáneas se almacenan en la memoria del Agente (no se escriben en disco), máximo 2 almacenadas
- Cuando se exceden 2, la instantánea más antigua se descarta automáticamente (FIFO)
- Se usa con `diff` para analizar cambios de memoria en un período de tiempo
- Para persistir instantáneas en disco, usa `dump` en su lugar

### 8. Comparación de Instantáneas (diff)

Compara cambios de memoria entre las dos últimas instantáneas (**requiere al menos 2 instantáneas tomadas primero**).

```bash
# Tomar dos instantáneas primero
peeka-cli memory --action snapshot
# ... esperar algún tiempo ...
peeka-cli memory --action snapshot

# Comparar diferencias
peeka-cli memory --action diff
```

**Ejemplo de Salida**:

```json
{
  "status": "success",
  "action": "diff",
  "diffs": [
    {
      "location": "/app/models.py:145",
      "size_diff": 1048576,
      "size_new": 2097152,
      "size_old": 1048576,
      "count_diff": 512,
      "count_new": 1024,
      "count_old": 512
    },
    {
      "location": "/app/cache.py:89",
      "size_diff": -524288,
      "size_new": 524288,
      "size_old": 1048576,
      "count_diff": -256,
      "count_new": 256,
      "count_old": 512
    }
  ]
}
```

**Descripción de Campos**:

| Campo | Descripción |
|-------|-------------|
| `location` | Ubicación de código (filename:lineno) |
| `size_diff` | Cambio de tamaño de memoria (positivo = crecimiento, negativo = disminución) |
| `size_new` | Tamaño de memoria en la nueva instantánea |
| `size_old` | Tamaño de memoria en la vieja instantánea |
| `count_diff` | Cambio de conteo de bloques de asignación |
| `count_new` | Conteo de bloques de asignación en la nueva instantánea |
| `count_old` | Conteo de bloques de asignación en la vieja instantánea |

**Notas Importantes**:

- Los resultados se agrupan por `lineno`, se devuelven máximo 50 entradas
- `size_diff > 0` indica crecimiento de memoria — foco clave para investigación de fugas
- A diferencia de la comparación fuera de línea de `dump`, `diff` se completa en línea sin exportar archivos

### 9. Consulta de Referentes (referrers)

Encuentra quién mantiene objetos del tipo especificado (**no necesita iniciar**). Útil para rastrear referencias de objetos cuando se investigan fugas de memoria.

```bash
# Encontrar quién referencia objetos de tipo dict
peeka-cli memory --action referrers --type-name dict

# Aumentar profundidad de recursión y conteo por nivel
peeka-cli memory --action referrers --type-name MyClass --max-depth 3 --max-per-level 15
```

**Ejemplo de Salida**:

```json
{
  "status": "success",
  "action": "referrers",
  "target": {
    "type": "MyClass",
    "repr_short": "<MyClass object at 0x7f...>",
    "count": 500
  },
  "referrers": [
    {
      "type": "dict",
      "repr_short": "{'user': <MyClass object at 0x7f...>, ...}",
      "referrers": [
        {
          "type": "list",
          "repr_short": "[{'user': <MyClass ...>}, ...] (len=500)"
        }
      ]
    }
  ]
}
```

**Descripción de Parámetros**:

| Parámetro | Descripción | Rango | Valor predeterminado |
|-----------|-------------|-------|---------|
| `--type-name` | Nombre de tipo de objeto objetivo | Cualquier nombre de tipo | **Requerido** |
| `--max-depth` | Profundidad de búsqueda recursiva | 1-3 | 2 |
| `--max-per-level` | Máximo de referentes por nivel | 1-20 | 10 |

**Escenarios de Uso**:

- Después de descubrir crecimiento anormal de conteo de objetos, usa `referrers` para rastrear quién mantiene esos objetos
- Usa con el comando `gc`: primero usa `gc` para encontrar tipos anormales, luego usa `referrers` para rastrear la cadena de referencias

### 10. Consulta de Referentes (referents)

Encuentra qué objetos referencia el tipo especificado (**no necesita iniciar**). Útil para analizar estructura interna y tenencia de objetos.

```bash
# Encontrar qué objetos referencia el tipo dict
peeka-cli memory --action referents --type-name dict

# Profundidad personalizada
peeka-cli memory --action referents --type-name MyCache --max-depth 3
```

**Ejemplo de Salida**:

```json
{
  "status": "success",
  "action": "referents",
  "target": {
    "type": "MyCache",
    "repr_short": "<MyCache object at 0x7f...>",
    "count": 1
  },
  "referents": [
    {
      "type": "dict",
      "repr_short": "{'items': [...], 'max_size': 10000}",
      "referents": [
        {
          "type": "list",
          "repr_short": "[<Item ...>, <Item ...>, ...] (len=9500)"
        }
      ]
    }
  ]
}
```

**Diferencia con referrers**:

| Dimensión | `referrers` | `referents` |
|-----------|-------------|-------------|
| **Dirección** | Hacia arriba: quién me referencia | Hacia abajo: qué yo referencia |
| **Propósito** | Investigar causa raíz de fuga | Analizar estructura de objeto |
| **Pregunta Típica** | ¿Por qué este objeto no se colecta? | ¿Qué contiene internamente este objeto? |

## Flujo de Trabajo de Diagnóstico Completo

### Escenario 1: Solución de Problemas de Fuga de Memoria

```bash
# 1. Ver estado actual de memoria
peeka-cli memory --action overview

# 2. Verificar anomalías en conteos de objetos con estadísticas de GC
peeka-cli memory --action gc --limit 50

# 3. Iniciar rastreo
peeka-cli memory --action start --nframe 50

# 4. Esperar algún tiempo (dejar que el problema se reproduzca)
sleep 300  # 5 minutos

# 5. Tomar primera instantánea de memoria
peeka-cli memory --action snapshot

# 6. Continuar esperando
sleep 300

# 7. Tomar segunda instantánea de memoria
peeka-cli memory --action snapshot

# 8. Comparación en línea de dos instantáneas (no necesita exportar archivos)
peeka-cli memory --action diff

# 9. Ver puntos calientes principales de asignación
peeka-cli memory --action top --limit 30

# 10. Rastrear cadena de referencias para tipos sospechosos
peeka-cli memory --action referrers --type-name MyClass --max-depth 3

# 11. Exportar instantánea para análisis fuera de línea (opcional)
peeka-cli memory --action dump --filename snapshot_leak

# 12. Detener rastreo
peeka-cli memory --action stop
```

### Escenario 2: Optimización de Rendimiento

```bash
# 1. Iniciar rastreo
peeka-cli memory --action start

# 2. Ejecutar prueba de rendimiento
# ... activar operaciones de negocio ...

# 3. Ver puntos calientes de memoria (agrupados por archivo)
peeka-cli memory --action top --group-by filename --limit 20

# 4. Ver líneas de código específicas (agrupadas por número de línea)
peeka-cli memory --action top --group-by lineno --limit 50

# 5. Detener rastreo
peeka-cli memory --action stop
```

### Escenario 3: Monitoreo Periódico

```bash
#!/bin/bash
# Script de instantánea de memoria programada

PID=12345
SNAPSHOT_DIR="/data/memory_snapshots"

# Iniciar rastreo (primera vez)
peeka-cli memory --action start

# Exportar instantánea cada hora
while true; do
  timestamp=$(date +%Y%m%d_%H%M%S)
  peeka-cli memory --action dump --filename "snapshot_$timestamp"
  sleep 3600
done
```

## Formato de Salida

Todas las acciones devuelven formato JSON con campos que incluyen:

### Campos Comunes

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `status` | string | `"success"` or `"error"` |
| `action` | string | Tipo de operación ejecutada |
| `error` | string | Mensaje de error (solo en fallo) |

### Ejemplo de Respuesta de Error

```json
{
  "status": "error",
  "action": "top",
  "error": "tracemalloc is not running. Run 'memory start' first."
}
```

## Impacto en el Rendimiento

### Sobrecoste de tracemalloc

| Escenario | Sobrecoste | Notas |
|----------|----------|-------|
| **tracemalloc no iniciado** | 0% | overview/gc no tienen sobrecoste adicional |
| **Start tracemalloc (nframe=25)** | 5-8% | Rastrea asignaciones de memoria y pilas de llamadas |
| **Start tracemalloc (nframe=50)** | 8-12% | Pilas de llamadas más profundas tienen mayor sobrecoste |
| **Operación dump** | < 1% | Sobrecoste momentáneo de exportación de instantánea |
| **Operación gc** | 2-5% | Atraviesa todos los objetos, sobrecoste momentáneo |

### Mejores Prácticas

1. **Iniciar bajo demanda**:
   ```bash
   # ❌ Incorrecto: mantener rastreo a largo plazo
   peeka-cli memory --action start
   # ... ejecutar permanentemente ...

   # ✅ Correcto: iniciar brevemente, detener inmediatamente después del diagnóstico
   peeka-cli memory --action start
   sleep 300  # 5 minutos
   peeka-cli memory --action dump --filename snapshot
   peeka-cli memory --action stop
   ```

2. **Elegir nframe apropiado**:
   ```bash
   # Producción: usa 25 predeterminado
   peeka-cli memory --action start

   # Desarrollo/depuración: usa pilas de llamadas más profundas
   peeka-cli memory --action start --nframe 50
   ```

3. **Usar gc durante horas de menor actividad**:
   ```bash
   # La operación gc tiene mayor sobrecoste, recomienda ejecución en horas de menor actividad
   peeka-cli memory --action gc --limit 30
   ```

4. **Exportar instantáneas periódicamente**:
   ```bash
   # Exportar cada 1 hora para análisis de tendencias
   while true; do
     peeka-cli memory --action dump --filename "snapshot_$(date +%H)"
     sleep 3600
   done
   ```

## Variables de Entorno

| Variable | Valor predeterminado | Descripción |
|----------|---------|-------------|
| `PEEKA_DUMP_DIR` | `/tmp` | Directorio de guardado de archivos de instantáneas |

**Ejemplo**:

```bash
# Directorio de instantáneas personalizado
export PEEKA_DUMP_DIR=/data/peeka_dumps
peeka-cli memory --action dump
# Archivo guardado en: /data/peeka_dumps/peeka_dump_*.snapshot
```

## Problemas Comunes

### 1. dump falla: "tracemalloc is not running"

**Causa**: dump se ejecutó sin iniciar tracemalloc.

**Solución**:

```bash
# Iniciar rastreo primero
peeka-cli memory --action start

# Luego exportar instantánea
peeka-cli memory --action dump
```

### 2. resultados de top vacíos

**Posibles Causas**:

- Acaba de iniciar tracemalloc, aún no ha capturado asignaciones
- El proceso tiene muy pocas asignaciones de memoria

**Solución**:

```bash
# Esperar algún tiempo luego verificar
peeka-cli memory --action start
sleep 60
peeka-cli memory --action top
```

### 3. archivo dump demasiado grande

**Causa**: Rastreado demasiado tiempo, demasiados registros de asignación.

**Solución**:

- Reducir el tiempo de rastreo (detener puntualmente)
- Reducir profundidad nframe
- Exportar periódicamente y limpiar (stop + start)

### 4. comando gc muy lento

**Causa**: `gc.get_objects()` necesita atravesar todos los objetos.

**Solución**:

- Ejecutar durante horas de menor actividad
- Reducir el parámetro limit
- Evitar llamadas de alta frecuencia

### 5. valores de RSS y tracemalloc difieren significativamente

**Causa**:

- **RSS**: Memoria física ocupada por el proceso (incluye código, pila, bibliotecas compartidas)
- **tracemalloc**: Solo rastrea asignaciones de montón de Python

**Situación Normal**:

```
RSS: 500 MB
tracemalloc: 200 MB  # Solo memoria de objetos Python
```

**Fuentes de la Diferencia**:

- Bibliotecas compartidas (ej., numpy, torch)
- Memoria asignada directamente por extensiones C
- Memoria propia del intérprete
- Memoria de pila

### 6. ¿Dónde está el archivo dump?

**Ubicación Predeterminada**: `/tmp/peeka_dump_*.snapshot`

**Método de Búsqueda**:

```bash
# Ver último archivo dump
ls -lt /tmp/peeka_dump_*.snapshot | head -1

# Directorio personalizado
export PEEKA_DUMP_DIR=/data/dumps
peeka-cli memory --action dump
ls -lt /data/dumps/
```

## Consejos Avanzados

### 1. Script de Monitoreo Automatizado de Memoria

```bash
#!/bin/bash
# memory_monitor.sh - Monitoreo automático de memoria

PID=$1
ALERT_THRESHOLD=1000000000  # 1GB

peeka-cli memory --action overview | \
  jq -r '.rss_bytes' | \
  while read rss; do
    if [ $rss -gt $ALERT_THRESHOLD ]; then
      echo "Alerta: RSS > 1GB, capturando instantánea..."
      peeka-cli memory --action start
      sleep 30
      peeka-cli memory --action dump --filename "alert_$(date +%s)"
      peeka-cli memory --action stop
    fi
  done
```

### 2. Análisis de Tasa de Crecimiento de Memoria

```python
# analyze_growth.py
import json
import sys

snapshots = sys.argv[1:]  # Múltiples rutas de archivos de instantáneas

sizes = []
for snapshot in snapshots:
    data = json.load(open(snapshot))
    sizes.append(data['rss_bytes'])

# Calcular tasa de crecimiento
for i in range(1, len(sizes)):
    growth = (sizes[i] - sizes[i-1]) / sizes[i-1] * 100
    print(f"Instantánea {i}: +{growth:.2f}%")
```

### 3. Integrar con Prometheus

```python
# prometheus_exporter.py
from prometheus_client import Gauge
import subprocess
import json
import time

rss_gauge = Gauge('process_rss_bytes', 'Process RSS memory', ['pid'])
tracemalloc_gauge = Gauge('tracemalloc_bytes', 'Tracemalloc memory', ['pid', 'type'])

def collect_metrics(pid):
    result = subprocess.check_output(['peeka', 'memory', '--pid', str(pid)])
    data = json.loads(result)

    rss_gauge.labels(pid=pid).set(data['rss_bytes'])

    if data['tracemalloc']['enabled']:
        tracemalloc_gauge.labels(pid=pid, type='current').set(
            data['tracemalloc']['current_bytes']
        )
        tracemalloc_gauge.labels(pid=pid, type='peak').set(
            data['tracemalloc']['peak_bytes']
        )

while True:
    collect_metrics(12345)
    time.sleep(15)
```

## Referencias

- [Documentación de tracemalloc de Python](https://docs.python.org/3/library/tracemalloc.html)
- [Documentación del módulo gc de Python](https://docs.python.org/3/library/gc.html)
- [Diseño de Arquitectura de Peeka](../architecture.md)
- [Guía para Desarrolladores de Agentes de IA](../ai-skill.md)

## Registro de Cambios

| Versión | Fecha | Actualizaciones |
|---------|------|---------|
| 0.1.0 | 2026-01 | Versión inicial, soporta 10 operaciones de memoria |
