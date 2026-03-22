---
layout: default
title: reset
parent: Referencia de Comandos
nav_order: 13
---

# reset - Restablecer inyección
{: .no_toc }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

## Introducción

El comando `reset` se usa para **restaurar métodos mejorados a su estado original**, eliminando la lógica de observación inyectada por comandos como `watch` y `stack`. Este es un comando de limpieza que puede restablecer selectivamente todas las mejoras o solo aquellas que coincidan con patrones específicos.

## Uso en TUI

**Nota**: El comando reset **no tiene una vista dedicada en TUI**, pero se puede ejecutar a través del cuadro de entrada de comandos:

- Presiona `:` en la interfaz principal de TUI para entrar en modo comando
- Ingresa el comando `reset` para ejecutar

**Operaciones Comunes**:
- Listar todas las mejoras: `: reset --list` o `: reset -l`
- Restablecer todas las mejoras: `: reset`
- Restablecer patrón específico: `: reset "myapp.service.*"`

**Atajos**: Cada vista típicamente tiene un botón "Detener" independiente, no necesita ingresar el comando reset manualmente.

**Comandos CLI equivalentes**: Todos los ejemplos a continuación usan comandos CLI para demostración.

## Escenarios de Uso

- **Limpieza después de diagnóstico**: Eliminar toda la lógica de observación inyectada después de completar la solución de problemas
- **Reconfigurar observaciones**: Restablecer mejoras existentes antes de volver a observar con parámetros diferentes
- **Limpieza selectiva**: Eliminar solo mejoras de módulos o clases específicas preservando las otras
- **Ver estado actual**: Listar todas las mejoras activas actualmente para entender el estado del sistema
- **Restauración de rendimiento**: Eliminar lógica de observación para eliminar el sobrecoste de rendimiento

## Formato del Comando

```bash
peeka-cli attach <pid>
peeka-cli reset [pattern] [options]
```

**Prerrequisitos**: Primero debe usar `peeka-cli attach <pid>` para adjuntar al proceso objetivo

### Parámetros

| Parámetro | Descripción | Valor por defecto | Ejemplo |
|-----------|-------------|-----------------|---------|
| `pattern` | Patrón de coincidencia opcional (soporta comodines) | Ninguno | `"myapp.service.*"` |
| `-l, --list` | Listar mejoras actuales sin restablecerlas | - | `--list` |

### Reglas de Coincidencia de Patrones

El parámetro `pattern` soporta comodines de estilo shell de Unix (basado en fnmatch):

| Comodín | Significado | Ejemplo | Coincide |
|---------|---------|---------|---------|
| `*` | Coincide cualquier carácter | `myapp.service.*` | `myapp.service.UserService` |
| `?` | Coincide un solo carácter | `myapp.?.query` | `myapp.a.query`, `myapp.b.query` |
| Ninguno | Coincidencia exacta | `myapp.service.UserService.query` | Solo coincidencia de patrón exacta |

**Nota**: La coincidencia de patrones se realiza contra **patrones almacenados**, no contra nombres de funciones.

## Formato de Salida

### Respuesta de Operación reset

```json
{
  "status": "success",
  "action": "reset",
  "affected": [
    {
      "watch_id": "watch_a1b2c3d4",
      "pattern": "myapp.service.UserService.query"
    },
    {
      "watch_id": "watch_e5f6g7h8",
      "pattern": "myapp.service.UserService.update"
    }
  ],
  "count": 2
}
```

**Descripción de Campos**:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `status` | string | Estado de la operación (`success`/`error`) |
| `action` | string | Tipo de operación (`reset`) |
| `affected` | array | Lista de mejoras restablecidas |
| `count` | int | Cantidad de restablecimientos exitosos |

**Elementos del Arreglo affected**:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `watch_id` | string | ID de sesión de observación |
| `pattern` | string | Patrón de coincidencia de función original |
| `error` | string | (Opcional) Error en fallo de restablecimiento |

### Respuesta de Operación list

```json
{
  "status": "success",
  "action": "list",
  "enhanced": [
    {
      "watch_id": "watch_a1b2c3d4",
      "pattern": "myapp.service.UserService.query",
      "command": "watch",
      "count": 42
    },
    {
      "watch_id": "stack_i9j0k1l2",
      "pattern": "myapp.handler.process",
      "command": "stack",
      "count": 15
    }
  ],
  "total": 2
}
```

**Descripción de Campos**:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `status` | string | Estado de la operación |
| `action` | string | Tipo de operación (`list`) |
| `enhanced` | array | Lista de mejoras actual |
| `total` | int | Cantidad total de mejoras |

**Elementos del Arreglo enhanced**:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `watch_id` | string | ID de sesión de observación |
| `pattern` | string | Patrón de coincidencia de función |
| `command` | string | Comando que creó la mejora (`watch`/`stack`) |
| `count` | int | Cantidad de observaciones capturadas |

## Ejemplos de Uso

### Ejemplo 1: Restablecer Todas las Mejoras

```bash
# Restablecer todas las mejoras
peeka-cli reset
```

**Salida**:

```json
{
  "status": "success",
  "action": "reset",
  "affected": [
    {"watch_id": "watch_001", "pattern": "myapp.service.query"},
    {"watch_id": "watch_002", "pattern": "myapp.handler.process"},
    {"watch_id": "stack_003", "pattern": "myapp.api.handle"}
  ],
  "count": 3
}
```

**Escenarios de Uso**:
- Limpieza completa después de diagnóstico
- Restaurar el sistema al estado sin observación
- Eliminar todo el sobrecoste de rendimiento

### Ejemplo 2: Restablecer por Patrón

```bash
# Restablecer solo mejoras del módulo myapp.service
peeka-cli reset "myapp.service.*"

# Restablecer todos los métodos de una clase específica
peeka-cli reset "myapp.service.UserService.*"

# Restablecer método específico
peeka-cli reset "myapp.service.UserService.query"
```

**Salida** (coincide 2 mejoras):

```json
{
  "status": "success",
  "action": "reset",
  "affected": [
    {"watch_id": "watch_001", "pattern": "myapp.service.UserService.query"},
    {"watch_id": "watch_002", "pattern": "myapp.service.UserService.update"}
  ],
  "count": 2
}
```

**Escenarios de Uso**:
- Limpieza selectiva de módulos específicos
- Preservar observaciones en otros módulos
- Reconfigurar parámetros de observación para funciones específicas

### Ejemplo 3: Sin Patrón Coincidente

```bash
# El patrón no coincide con ninguna mejora
peeka-cli reset "nonexistent.*"
```

**Salida**:

```json
{
  "status": "success",
  "action": "reset",
  "affected": [],
  "count": 0
}
```

### Ejemplo 4: Listar Mejoras Actuales

```bash
# Ver todas las mejoras activas
peeka-cli reset --list
```

**Salida**:

```json
{
  "status": "success",
  "action": "list",
  "enhanced": [
    {
      "watch_id": "watch_a1b2c3d4",
      "pattern": "myapp.service.UserService.query",
      "command": "watch",
      "count": 42
    },
    {
      "watch_id": "stack_i9j0k1l2",
      "pattern": "myapp.handler.process",
      "command": "stack",
      "count": 15
    }
  ],
  "total": 2
}
```

**Escenarios de Uso**:
- Entender el estado actual del sistema
- Verificar si las observaciones siguen activas
- Decidir qué mejoras necesitan ser restablecidas

### Ejemplo 5: Listar Sin Mejoras

```bash
# Cuando no hay mejoras activas
peeka-cli reset --list
```

**Salida**:

```json
{
  "status": "success",
  "action": "list",
  "enhanced": [],
  "total": 0
}
```

### Ejemplo 6: Usando con jq

```bash
# Extraer conteo de reset
peeka-cli reset | jq '.count'
# Salida: 3

# Extraer lista de patrones afectados
peeka-cli reset "myapp.*" | jq -r '.affected[].pattern'
# Salida:
# myapp.service.query
# myapp.handler.process

# Contar mejoras actuales
peeka-cli reset --list | jq '.total'
# Salida: 5

# Ver mejoras de comando específico
peeka-cli reset --list | jq '.enhanced[] | select(.command == "watch")'

# Ordenar por conteo de observación
peeka-cli reset --list | jq '.enhanced | sort_by(.count) | reverse'
```

## Flujos de Trabajo Típicos

### Flujo de Trabajo 1: Limpieza Después de Diagnóstico

```bash
# 1. Iniciar diagnóstico
peeka-cli watch "myapp.service.query" -n 100

# 2. Ver datos de observación (se detiene automáticamente después de 100 veces)
# ... analizar datos ...

# 3. Limpiar todas las mejoras después del diagnóstico
peeka-cli reset

# Verificar
peeka-cli reset --list
# Salida: {"total": 0}
```

### Flujo de Trabajo 2: Reconfigurar Observaciones

```bash
# 1. Actualmente observando (profundidad 2)
peeka-cli watch "myapp.service.query" -x 2

# 2. Necesitas salida más profunda (profundidad 3)
# Primero restablecer la observación actual
peeka-cli reset "myapp.service.query"

# 3. Volver a observar con nuevos parámetros
peeka-cli watch "myapp.service.query" -x 3
```

### Flujo de Trabajo 3: Diagnóstico de Múltiples Módulos

```bash
# 1. Observar múltiples módulos
peeka-cli watch "myapp.service.*" &
peeka-cli watch "myapp.handler.*" &
peeka-cli watch "myapp.api.*" &

# 2. Después de diagnosticar el módulo service, limpiar solo service
peeka-cli reset "myapp.service.*"

# 3. Continuar observando otros módulos
# Las observaciones de handler y api siguen ejecutándose

# 4. Limpiar todo cuando termina
peeka-cli reset
```

### Flujo de Trabajo 4: Verificación Periódica de Estado

```bash
#!/bin/bash
# check_enhancements.sh - Verificación periódica de estado de mejoras

while true; do
  TOTAL=$(peeka-cli reset --list | jq '.total')
  echo "$(date): Mejoras activas = $TOTAL"

  if [ "$TOTAL" -gt 10 ]; then
    echo "Advertencia: Demasiadas mejoras, considerar limpieza"
  fi

  sleep 300  # Verificar cada 5 minutos
done
```

## Notas Importantes

### ⚠️ Comando monitor No Afectado

El comando `reset` **solo afecta las mejoras creadas por los comandos `watch` y `stack`**. El comando `monitor` usa un mecanismo de rastreo independiente y no será limpiado por reset.

```bash
# monitor no se ve afectado
peeka-cli monitor "myapp.service.query" --interval 60  # Iniciar monitoreo

peeka-cli reset                        # Reset no detiene el monitor

# Necesitas detener monitor por separado (Ctrl+C)
```

### ⚠️ Reglas de Coincidencia de Patrones

Los patrones coinciden con **patrones almacenados**, no con nombres de funciones:

```bash
# Asumiendo que se ejecutó previamente:
peeka-cli watch "myapp.service.UserService.query"

# ✅ Correcto: Coincide patrón almacenado
peeka-cli reset "myapp.service.*"              # Coincidencia exitosa
peeka-cli reset "myapp.service.UserService.*"  # Coincidencia exitosa

# ❌ Incorrecto: Intenta coincidir nombre de clase (no funcionará)
peeka-cli reset "UserService.*"                # Sin coincidencia
```

### ⚠️ Reset es Irreversible

Las operaciones de reset eliminan inmediatamente la lógica de mejora y **no se pueden deshacer**. Para continuar observando, debes volver a ejecutar los comandos `watch` o `stack`.

```bash
# Necesitas volver a observar después de reset
peeka-cli reset "myapp.service.query"
peeka-cli watch "myapp.service.query" -n 100  # Volver a iniciar observación
```

### ⚠️ Restauración de Rendimiento

Después de reset, las funciones vuelven al estado original con eliminación inmediata del sobrecoste de rendimiento:

| Estado | Sobrecoste de Rendimiento |
|-------|---------------------|
| Antes de mejora | 0% |
| Durante observación watch | 2-5% |
| Después de reset | 0% |

### ⚠️ Seguridad de Concurrencia

El comando reset es seguro para hilos, pero pueden ocurrir casos borde en escenarios de alta concurrencia:

- Durante reset, las observaciones en curso todavía pueden producir datos
- Las llamadas inmediatamente después de reset usarán la función original

## Preguntas Frecuentes

### P1: ¿Cuál es la diferencia entre reset y detener el streaming de observación?

**R**:

- `reset`: Elimina el decorador inyectado de la función objetivo, elimina permanentemente la lógica de mejora
- `Ctrl+C` (o cerrar CLI): Detiene el streaming de datos del cliente, pero la lógica de mejora sigue activa en el proceso objetivo

**Explicación de Secuencia**:

```
Ctrl+C detiene cliente de streaming: Datos de observación dejan de regresar, pero la mejora sigue ejecutándose
reset elimina mejora: Elimina el decorador del proceso objetivo, restaura completamente la función original
```

**Uso Recomendado**:

- Pausa temporal de observación: Usa `Ctrl+C` (solo desconecta cliente)
- Limpieza completa de mejoras: Usa el comando `reset` (elimina la lógica inyectada)
- Continuar diagnóstico en otras funciones: Usa `reset` primero, luego reinicia otras observaciones

```bash
# Método 1: Pausa temporal (desconexión de cliente)
# Ctrl+C

# Método 2: Limpieza completa (elimina mejora)
peeka-cli reset "myapp.service.*"
```

### P2: ¿Cómo restablecer watch_id específico?

**R**: reset no soporta directamente el parámetro watch_id, pero puedes usar coincidencia de patrón exacta:

```bash
# 1. Ver patrón correspondiente a watch_id
peeka-cli reset --list | jq '.enhanced[] | select(.watch_id == "watch_001")'
# Salida: {"watch_id": "watch_001", "pattern": "myapp.service.query", ...}

# 2. Restablecer usando patrón exacto
peeka-cli reset "myapp.service.query"
```

**O usa directamente coincidencia exacta con watch_id**:

```bash
peeka-cli reset "watch_001"
```

### P3: ¿Reset afecta a las funciones en ejecución?

**R**: No. Reset solo reemplaza referencias de funciones, no interrumpirá las llamadas en ejecución.

**Explicación de Secuencia**:

```
Tiempo T0: Función A comienza ejecución (usa versión mejorada)
Tiempo T1: Ejecuta reset (reemplaza referencia de función)
Tiempo T2: Función A continúa ejecución (todavía usa versión mejorada, ya entró)
Tiempo T3: Función A termina (produce datos de observación)
Tiempo T4: Nueva llamada a Función A (usa versión original)
```

### P4: ¿No hay coincidencia de patrón es un error?

**R**: No es un error, devuelve `count: 0`.

```bash
peeka-cli reset "nonexistent.*"
# Salida: {"status": "success", "count": 0}
```

Este es un comportamiento esperado, conveniente para uso en scripts (no genera error sin coincidencia).

### P5: ¿Cómo restablecer todos los watch pero mantener los stack?

**R**: La versión actual no soporta filtrado por tipo de comando, pero se puede lograr indirectamente a través de coincidencia de patrones:

```bash
# Si watch y stack usan módulos diferentes
peeka-cli reset "myapp.service.*"  # Asumiendo que solo watch observa este módulo
```

**Plan Futuro**: Soportar parámetro `--command watch` para filtrado.

### P6: ¿Qué pasa si la salida de reset --list es demasiado grande?

**R**: Usa jq para filtrar:

```bash
# Solo ver mejoras de comando watch
peeka-cli reset --list | jq '.enhanced[] | select(.command == "watch")'

# Solo ver mejoras de módulo específico
peeka-cli reset --list | jq '.enhanced[] | select(.pattern | startswith("myapp.service"))'

# Ordenar por conteo de observación
peeka-cli reset --list | jq '.enhanced | sort_by(.count) | reverse'
```

## Resumen

El comando `reset` es una herramienta potente para la gestión de mejoras en entornos de producción, particularmente adecuada para:
- Limpieza después de diagnóstico
- Reconfigurar parámetros de observación
- Limpieza selectiva de módulos
- Inspección de estado del sistema

**Mejores Prácticas**:
- Registrar estado antes de modificar (para fácil restauración)
- Restaurar inmediatamente el nivel original después de depurar
- Usar `--pattern` para filtrar (mejora la eficiencia)
- Combinar con `jq` para potente análisis de datos

**Siguientes Pasos**:
- Conoce el comando [`watch`](watch) (observar llamadas a funciones)
- Conoce el comando [`stack`](stack) (rastrear pilas de llamadas)
- Conoce el comando [`monitor`](monitor) (monitoreo de rendimiento)
- Referente a [Guía para Desarrolladores de Agentes de IA](../ai-skill.md)
