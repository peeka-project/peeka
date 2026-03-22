---
layout: default
title: thread
parent: Referencia de Comandos
nav_order: 11
---

# Comando `thread` - Listar e Inspeccionar Hilos
{: .no_toc }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

## Introducción

El comando `thread` se usa para **enumerar todos los hilos en el proceso objetivo y verificar la pila de llamadas de hilos específicos**. Este comando ayuda a los desarrolladores a localizar rápidamente el estado de los hilos, diagnosticar interbloqueos y analizar causas de bloqueo.

## Escenarios de Uso

- **Enumeración de hilos**: Listar rápidamente todos los hilos en el proceso y su estado
- **Filtrado por estado**: Filtrar hilos por estado (RUNNABLE/WAITING/TIMED_WAITING)
- **Inspección de pila**: Ver la pila de llamadas completa de un hilo específico, localizar la posición de ejecución del código
- **Diagnóstico de interbloqueos**: Analizar el estado de los hilos para descubrir interbloqueos potenciales o problemas de bloqueo
- **Depuración concurrente**: Entender el estado de ejecución y la distribución de hilos en programas multihilo

## Formato del Comando

```bash
peeka-cli attach <pid>    # Primero adjuntar al proceso objetivo
peeka-cli thread [options]
```

### Descripción de Parámetros

| Parámetro      | Descripción                                          | Valor por defecto | Ejemplo             |
|---------------|-----------------------------------------------------|-------------------|---------------------|
| `--tid`       | ID de hilo, usado para ver detalles de la pila de un hilo específico | Ninguno           | `--tid 123456`      |
| `--state`     | Filtrar hilos por estado (RUNNABLE / WAITING / TIMED_WAITING) | Ninguno           | `--state WAITING`   |
| `--sort-by`   | Campo de ordenación (tid / name / state)            | `tid`             | `--sort-by name`    |
| `--depth`     | Límite de profundidad de pila (solo para vista de detalles) | `50`              | `--depth 30`        |

### Descripción de Estados de Hilo

Peeka deduce automáticamente el estado del hilo analizando la pila de llamadas actual:

| Estado             | Descripción                                      | Escenarios Típicos                 |
|--------------------|------------------------------------------------|-------------------------------------|
| `RUNNABLE`         | El hilo está en ejecución o en estado ejecutable | Ejecutando código normalmente      |
| `WAITING`          | El hilo está esperando (espera indefinida)      | `wait()`, `join()`, `lock`, etc.   |
| `TIMED_WAITING`    | El hilo está en espera temporizada              | `sleep()`, `poll()`, etc.          |

**Algoritmo de deducción de estado**: Revisa los 3 marcos de llamada en la cima de la pila del hilo y coincide patrones de bloqueo según el nombre de la función y el nombre del módulo (como `select`, `poll`, `wait`, `sleep`, etc.).

## Uso Básico

### 1. Listar Todos los Hilos

```bash
# Primero adjuntar al proceso objetivo
peeka-cli attach 12345

# Listar todos los hilos
peeka-cli thread
```

**Ejemplo de Salida**:

```json
{
  "status": "success",
  "action": "list",
  "total": 10,
  "threads": [
    {
      "tid": 140234567890,
      "native_id": 12345,
      "name": "MainThread",
      "daemon": false,
      "alive": true,
      "state": "RUNNABLE",
      "stack_depth": 15,
      "top_frame": {
        "filename": "/app/main.py",
        "lineno": 42,
        "funcname": "process_request"
      }
    },
    {
      "tid": 140234567891,
      "native_id": 12346,
      "name": "WorkerThread-1",
      "daemon": true,
      "alive": true,
      "state": "WAITING",
      "stack_depth": 8,
      "top_frame": {
        "filename": "/usr/lib/python3.12/threading.py",
        "lineno": 629,
        "funcname": "wait"
      }
    }
  ]
}
```

**Descripción de Campos**:

| Campo           | Descripción                                  | Valor de Ejemplo             |
|-----------------|----------------------------------------------|------------------------------|
| `tid`           | ID de hilo (identificador Python)            | `140234567890`               |
| `native_id`     | ID de hilo nativo (Python 3.8+, puede ser None) | `12345`                   |
| `name`          | Nombre del hilo                              | `"MainThread"`               |
| `daemon`        | Si es un hilo demonio                        | `false`                      |
| `alive`         | Si el hilo sigue vivo                        | `true`                       |
| `state`         | Estado deducido del hilo                     | `"RUNNABLE"`                 |
| `stack_depth`   | Profundidad de la pila de llamadas           | `15`                         |
| `top_frame`     | Información del marco superior de la pila (filename / lineno / funcname) | `{"filename": "...", ...}` |

### 2. Filtrar Hilos por Estado Específico

```bash
# Mostrar solo hilos en espera
peeka-cli thread --state WAITING

# Mostrar solo hilos en sueño
peeka-cli thread --state TIMED_WAITING

# Mostrar solo hilos en ejecución
peeka-cli thread --state RUNNABLE
```

### 3. Ver Detalles de la Pila de un Hilo Específico

```bash
# Ver la pila completa del hilo 140234567890
peeka-cli thread --tid 140234567890

# Limitar la profundidad de la pila a 30 niveles
peeka-cli thread --tid 140234567890 --depth 30
```

**Ejemplo de Salida** (vista de detalles):

```json
{
  "status": "success",
  "action": "detail",
  "thread": {
    "tid": 140234567890,
    "native_id": 12345,
    "name": "MainThread",
    "daemon": false,
    "alive": true,
    "state": "WAITING",
    "stack_depth": 8,
    "stack": [
      {
        "filename": "/usr/lib/python3.12/queue.py",
        "lineno": 171,
        "funcname": "get",
        "locals_keys": ["self", "block", "timeout"]
      },
      {
        "filename": "/app/worker.py",
        "lineno": 25,
        "funcname": "worker_loop",
        "locals_keys": ["queue", "item", "result"]
      },
      {
        "filename": "/app/main.py",
        "lineno": 100,
        "funcname": "run",
        "locals_keys": ["self", "config"]
      }
    ]
  }
}
```

**Descripción del Campo `stack`**:

| Campo          | Descripción                                   | Valor de Ejemplo                 |
|----------------|-----------------------------------------------|----------------------------------|
| `filename`     | Ruta del archivo fuente                       | `"/app/worker.py"`               |
| `lineno`       | Número de línea                               | `25`                             |
| `funcname`     | Nombre de la función                          | `"worker_loop"`                  |
| `locals_keys`  | Lista de nombres de variables locales (límite 20) | `["queue", "item", "result"]`  |

### 4. Ordenar por Campo

```bash
# Ordenar por nombre de hilo
peeka-cli thread --sort-by name

# Ordenar por estado de hilo
peeka-cli thread --sort-by state

# Ordenar por ID de hilo (predeterminado)
peeka-cli thread --sort-by tid
```

## Formato de Salida

### Salida list (modo lista)

```json
{
  "status": "success",
  "action": "list",
  "total": 10,
  "threads": [
    {
      "tid": 140234567890,
      "native_id": 12345,
      "name": "MainThread",
      "daemon": false,
      "alive": true,
      "state": "RUNNABLE",
      "stack_depth": 15,
      "top_frame": {
        "filename": "/app/main.py",
        "lineno": 42,
        "funcname": "process_request"
      }
    }
  ]
}
```

### Salida detail (modo detalles)

```json
{
  "status": "success",
  "action": "detail",
  "thread": {
    "tid": 140234567890,
    "native_id": 12345,
    "name": "MainThread",
    "daemon": false,
    "alive": true,
    "state": "WAITING",
    "stack_depth": 8,
    "stack": [
      {
        "filename": "/usr/lib/python3.12/queue.py",
        "lineno": 171,
        "funcname": "get",
        "locals_keys": ["self", "block", "timeout"]
      }
    ]
  }
}
```

## Uso en TUI

En modo TUI, puedes ver información de hilos a través de la interfaz interactiva:

1. Iniciar TUI:
   ```bash
   peeka  # o python -m peeka.tui
   ```

2. Conectarse al proceso objetivo (ingresa PID o selecciona un proceso)

3. Presiona la tecla **`9`** para cambiar a la **vista Threads**

4. Funcionalidades:
   - Mostrar en tiempo real la lista de todos los hilos
   - Filtrar hilos por estado
   - Seleccionar un hilo para ver detalles de la pila
   - Soporte para ordenar por nombre, estado, ID

## Notas Importantes

1. **Precisión de la deducción de estado**:
   - El estado del hilo se deduce analizando la pila de llamadas, puede haber errores
   - Solo revisa los 3 marcos superiores de la pila, bloqueos profundos pueden no ser reconocidos
   - El estado RUNNABLE incluye tanto los que están ejecutándose como los que son ejecutables

2. **Disponibilidad de native_id**:
   - El campo `native_id` solo está disponible en Python 3.8+
   - En versiones antiguas de Python este campo es `null`

3. **Límite de variables locales**:
   - El campo `locals_keys` en la vista de detalles muestra máximo 20 nombres de variables locales
   - Los valores de las variables no se obtienen, para evitar activar efectos secundarios

4. **Impacto en el rendimiento**:
   - La obtención de información de hilos usa `sys._current_frames()` y `threading.enumerate()`
   - El costo de rendimiento es extremadamente bajo, pero puede haber retardo cuando hay una gran cantidad de hilos (>1000)

5. **Requisitos de permisos**:
   - Necesitas usar primero el comando `attach` para adjuntar al proceso objetivo
   - Los requisitos de permisos para adjuntar se describen en la [documentación del comando attach](attach)
