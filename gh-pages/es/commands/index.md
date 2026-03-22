---
layout: default
title: Referencia de Comandos
nav_order: 4
has_children: true
permalink: /es/commands
---

# Referencia de Comandos
{: .no_toc }

Peeka proporciona una serie de potentes comandos de diagnóstico, cada comando se centra en un escenario de diagnóstico específico. Este documento cubre los 13 comandos centrales.
{: .fs-6 .fw-300 }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Resumen de Comandos

| Comando | Función | Escenario de Aplicación |
|---------|---------|-------------------------|
| [attach]({% link es/commands/attach.md %}) | Adjuntar al proceso objetivo | Primer paso para todos los escenarios |
| [watch]({% link es/commands/watch.md %}) | Observar llamadas a funciones | Ver parámetros, valores de retorno, tiempo de ejecución |
| [trace]({% link es/commands/trace.md %}) | Rastrear cadena de llamadas | Analizar relación de llamadas de funciones y distribución de tiempo consumido |
| [stack]({% link es/commands/stack.md %}) | Rastrear pila de llamadas | Rastrear quién llamó a la función |
| [monitor]({% link es/commands/monitor.md %}) | Estadísticas de rendimiento | Monitorear en tiempo real métricas de rendimiento de funciones |
| [logger]({% link es/commands/logger.md %}) | Gestión de registros | Ajustar dinámicamente el nivel de registro |
| [memory]({% link es/commands/memory.md %}) | Análisis de memoria | Analizar uso de memoria y fugas |
| [inspect]({% link es/commands/inspect.md %}) | Inspección de objetos | Inspeccionar atributos de objetos en tiempo de ejecución |
| [search]({% link es/commands/search.md %}) | Buscar clases y métodos (sc/sm) | Exploración y descubrimiento de código |
| [thread]({% link es/commands/thread.md %}) | Análisis de hilos | Enumerar hilos y ver pila de hilos |
| [top]({% link es/commands/top.md %}) | Muestreo de rendimiento de funciones | Análisis de puntos calientes de rendimiento a nivel de función |
| [detach]({% link es/commands/detach.md %}) | Desconectar conexión | Salir de forma segura de la sesión de diagnóstico |
| [reset]({% link es/commands/reset.md %}) | Restablecer inyección | Restaurar funciones observadas |

---

## Parámetros Generales

Todos los comandos comparten el siguiente formato de parámetros:

### Formato de Pattern

Patrón para especificar la función objetivo:

```bash
# Método de clase
module.ClassName.method_name

# Función de módulo
module.function_name

# Soporta comodines
module.ClassName.*
module.*
*.method_name
```

### Formato de Salida

Todos los comandos generan salida en formato JSONL (JSON Lines), un objeto JSON por línea:

```json
{"type":"status","level":"info","message":"..."}
{"type":"success","command":"attach","data":{...}}
{"type":"observation","watch_id":"...","data":{...}}
```

### Tipos de Mensaje

| Tipo | Descripción |
|------|-------------|
| `status` | Información de estado (no crítica) |
| `success` | Comando exitoso |
| `error` | Comando falló |
| `event` | Evento de control (started, stopped) |
| `observation` | Datos de observación |
| `result` | Resultado de consulta |

---

## Flujo de Uso de Comandos

### Flujo de Diagnóstico Estándar

```bash
# 1. Adjuntar al proceso
peeka-cli attach <pid>

# 2. Usar comando de diagnóstico específico
peeka-cli watch "module.func"

# 3. Analizar resultados
peeka-cli watch "module.func" | jq 'select(.type == "observation")'

# 4. (Opcional) Restablecer inyección
peeka-cli reset "module.func"
```

### Flujo Interactivo TUI

```bash
# Iniciar TUI
peeka

# Usa teclas numéricas para cambiar de vista
# 1 - Panel Dashboard
# 2 - Vista Watch de observación
# 3 - Vista Trace de rastreo
# 4 - Vista Stack de pila de llamadas
# 5 - Vista Monitor de monitoreo de rendimiento
# 6 - Vista Memory de análisis de memoria
# 7 - Vista Logger de gestión de registros
# 8 - Vista Agent Log de registros del Agente
# 9 - Vista Threads de análisis de hilos
# 0 - Vista Top de puntos calientes de funciones
```

Para más detalles, consulta [Guía de Uso de TUI]({% link es/tui.md %}).

---

## Expresiones Condicionales

Muchos comandos soportan el parámetro `--condition`, que se usa para filtrar resultados de observación.

### Variables Disponibles

| Variable | Descripción | Tipo |
|----------|-------------|------|
| `params` | Lista de parámetros de función | list |
| `kwargs` | Diccionario de parámetros de palabras clave | dict |
| `returnObj` | Valor de retorno | any |
| `throwExp` | Objeto de excepción | Exception or None |
| `cost` | Tiempo de ejecución (milisegundos) | float |
| `target` | Objeto objetivo (método de instancia) | object |

### Ejemplos de Condiciones

```bash
# Filtrado de parámetros
--condition "params[0] > 100"
--condition "len(params) > 2"
--condition "kwargs.get('debug') == True"

# Filtrado de valor de retorno
--condition "returnObj is not None"
--condition "len(returnObj) > 10"

# Filtrado de tiempo de ejecución
--condition "cost > 100"  # Más de 100ms
--condition "cost > 10 and cost < 100"  # 10-100ms

# Filtrado de excepción
--condition "throwExp is not None"
--condition "type(throwExp).__name__ == 'ValueError'"

# Combinar condiciones
--condition "params[0] > 100 and cost > 50"
--condition "len(params) > 2 or returnObj is None"
```

### Restricciones de Seguridad

La expresión condicional usa la biblioteca `simpleeval` para evaluación segura, no soporta:

- ❌ Funciones peligrosas como `__import__`, `eval`, `exec`
- ❌ Operaciones de archivos (`open`, `read`, `write`)
- ❌ Operaciones de reflexión (`__class__`, `__subclasses__`)
- ✅ Operaciones aritméticas, comparación, operaciones lógicas
- ✅ Operaciones de cadenas, indexación de listas
- ✅ Funciones incorporadas seguras (`len`, `str`, `int`, etc.)

---

## Impacto en el Rendimiento

| Comando | Sobrecoste de rendimiento | Descripción |
|---------|---------------------------|-------------|
| `watch` | < 1% | Inyección de decorador, sobrecoste extremadamente pequeño |
| `trace` | < 5% (3.12+) | Usa la API sys.monitoring |
| `trace` | < 20% (3.9-3.11) | Usa sys.settrace |
| `stack` | < 1% | Solo captura pila de llamadas |
| `monitor` | < 1% | Estadísticas periódicas |
| `logger` | 0% | No afecta el rendimiento |
| `memory` | Configurable | Depende de la frecuencia de muestreo |

---

## Siguientes Pasos

Selecciona el comando que necesitas para ver la documentación detallada:

- [attach - Adjuntar al proceso]({% link es/commands/attach.md %})
- [watch - Observar llamadas a funciones]({% link es/commands/watch.md %})
- [trace - Rastrear cadena de llamadas]({% link es/commands/trace.md %})
- [stack - Rastrear pila de llamadas]({% link es/commands/stack.md %})
- [monitor - Monitoreo de rendimiento]({% link es/commands/monitor.md %})
- [logger - Gestión de registros]({% link es/commands/logger.md %})
- [memory - Análisis de memoria]({% link es/commands/memory.md %})
- [inspect - Inspección de objetos]({% link es/commands/inspect.md %})
- [search - Buscar clases y métodos]({% link es/commands/search.md %})
- [reset - Restablecer inyección]({% link es/commands/reset.md %})
- [thread - Análisis de hilos]({% link es/commands/thread.md %})
- [top - Muestreo de rendimiento de funciones]({% link es/commands/top.md %})
- [detach - Desconectar conexión]({% link es/commands/detach.md %})

O consulta [Inicio Rápido]({% link es/quickstart.md %}) para conocer el método de uso básico.
