---
layout: default
title: Inicio
nav_order: 1
description: "Peeka - Herramienta de diagnóstico en tiempo de ejecución para Python con observación de funciones no intrusiva basada en PEP 768"
permalink: /
---

# Peeka
{: .fs-9 }

> *Peek-a-boo* — El nombre proviene del juego infantil "escondite". Una herramienta de diagnóstico para encontrar errores ocultos, como el momento sorpresa cuando encuentras a alguien en el escondite.

Es una herramienta de diagnóstico en tiempo de ejecución basada en PEP 768 (el protocolo de depuración remota de Python 3.14), que proporciona observación de funciones no intrusiva.
{: .fs-6 .fw-300 }

[Inicio rápido](#inicio-rápido){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[Ver en GitHub](https://github.com/wwulfric/peeka){: .btn .fs-5 .mb-4 .mb-md-0 }

---

{: .note }
> 🌐 **Idioma / Language**: Esta documentación también está disponible en [中文 (Chino)](/peeka/) y [English (Inglés)](/peeka/en/).

---

## ¿Qué es Peeka?

Peeka es una herramienta que proporciona capacidades de diagnóstico en tiempo real a desarrolladores Python en entornos de producción. **Sin necesidad de modificar el código objetivo**, puede observar y diagnosticar dinámicamente aplicaciones Python en ejecución.

### ¿Por qué necesitas Peeka?

Los métodos tradicionales de depuración de Python enfrentan muchos desafíos en entornos de producción:

- **No puedes detener el servicio** — La depuración con puntos de interrupción bloquea el proceso
- **Problemas intermitentes** — Necesitas observar bajo carga real
- **Dificultad para modificar código** — No puedes desplegar libremente en producción

Peeka está diseñado específicamente para resolver estos desafíos de diagnóstico en entornos de producción.

---

## Características principales

### 🔍 Observación no intrusiva
{: .text-delta }

- No necesitas modificar el código objetivo
- Inyección dinámica de lógica de observación en tiempo de ejecución
- Restauración completa después del diagnóstico

### ⚡ Diagnóstico en tiempo real
{: .text-delta }

- Latencia de transmisión de datos a nivel de milisegundos
- Transmisión en streaming de datos de observación
- Salida en formato JSON fácil de integrar con otras herramientas

### 🛡️ Listo para producción
{: .text-delta }

- Sobrecarga de rendimiento < 5%
- Captura completa de excepciones y mecanismo de recuperación
- Búfer de memoria fijo para prevenir la expansión de memoria

### 🎯 Filtrado condicional
{: .text-delta }

- Filtrado seguro de expresiones (basado en simpleeval)
- Sintaxis flexible de filtrado (parámetros, valores de retorno, tiempo de ejecución, etc.)
- Bloquea todos los ataques de inyección de código (`__import__`, `eval`, `exec`, etc.)

---

## Inicio rápido

### Instalación

```bash
pip install peeka
```

### Uso básico

#### 1. Conectar al proceso objetivo

```bash
peeka-cli attach <pid>
```

#### 2. Observar llamadas a funciones

```bash
# Observar 5 llamadas
peeka-cli watch "module.Class.method" --times 5

# Filtrado condicional
peeka-cli watch "module.Class.method" --condition "len(params) > 2"

# Observación en streaming en tiempo real
peeka-cli watch "module.Class.method"
```

#### 3. Procesar datos

```bash
# Extraer resultados con jq
peeka-cli watch "module.func" | jq 'select(.type == "observation") | .data.result'

# Filtrar llamadas lentas
peeka-cli watch "module.func" | jq 'select(.type == "observation" and .data.duration_ms > 1)'
```

---

## Funcionalidades principales

| Comando | Funcionalidad | Estado |
|---------|----------|--------|
| `attach` | Conectar al proceso objetivo | ✅ |
| `watch` | Observar llamadas a funciones (parámetros, valores de retorno, tiempo) | ✅ |
| `trace` | Rastrear cadena de llamadas y tiempo de ejecución | ✅ |
| `stack` | Rastrear pila de llamadas | ✅ |
| `monitor` | Monitorear estadísticas de rendimiento | ✅ |
| `logger` | Ajustar nivel de registro dinámicamente | ✅ |
| `memory` | Análisis de memoria | ✅ |
| `inspect` | Inspeccionar objetos en tiempo de ejecución | ✅ |
| `sc/sm` | Buscar clases y métodos | ✅ |
| `reset` | Restablecer extensiones | ✅ |
| `thread` | Análisis de hilos | ✅ |
| `top` | Muestreo de rendimiento a nivel de función | ✅ |
| `detach` | Terminar sesión de diagnóstico de forma segura | ✅ |

[Ver referencia completa de comandos]({% link es/commands/index.md %}){: .btn .btn-outline }

### 🎨 Interfaz TUI interactiva
{: .text-delta }

Además de los comandos CLI, Peeka también proporciona una rica interfaz TUI (interfaz de usuario de texto):

- **Selector de procesos** — Muestra automáticamente la lista de procesos del sistema, con filtrado de búsqueda
- **11 vistas dedicadas** — Panel, watch, trace, stack, monitor, logger, memory, inspect, thread, top, **Agent Log**
- **Transmisión de datos en tiempo real** — Streaming de datos de observación, con soporte para pausa/reanudación/limpieza
- **Autocompletado** — Obtiene clases y métodos dinámicamente desde el proceso objetivo
- **Soporte de temas** — Múltiples temas de colores incorporados

```bash
# Iniciar TUI
peeka

# Cambiar de vista con teclas numéricas
# 1/2/3/4/5/6/7/8/9/0/8
```

[Ver guía completa de uso de TUI]({% link es/tui.md %}){: .btn .btn-outline }

---

---

## Aspectos técnicos destacados

### Protocolo de depuración remota de Python 3.14 (PEP 768)

La función principal `sys.remote_exec(pid, script_path)` es la clave de todo el sistema, encapsula la compleja lógica de conexión al proceso, inyección de código y programación de ejecución.

**Retroceso para Python < 3.14**: Para versiones antiguas de Python, usa el mecanismo GDB + ptrace (referencia: pyrasite).

### Socket de dominio Unix

Usamos sockets de dominio Unix como mecanismo principal de comunicación entre procesos:

- Mayor eficiencia de transmisión — no necesita pila de protocolo de red
- Mayor seguridad — solo accesible por procesos locales
- Simple y confiable — prefijo de longitud + formato JSON

### Evaluación segura de condiciones

Implementamos filtrado condicional seguro basado en la biblioteca simpleeval:

- Lista blanca AST — solo permite operaciones seguras
- Protección de atributos — bloquea ataques de reflexión
- Lista negra de funciones — desactiva funciones peligrosas

[Aprender sobre arquitectura]({% link es/architecture.md %}){: .btn .btn-outline }

---

## Versiones de Python soportadas

| Versión de Python | Mecanismo de conexión | Requisitos |
|------------------|---------------------|--------------|
| 3.14+ | PEP 768 `sys.remote_exec` | Ninguno |
| 3.9-3.13 | Retroceso GDB + ptrace | GDB, python3-dbg, CAP_SYS_PTRACE |

---

## Licencia

Peeka es código abierto bajo la [Licencia Apache 2.0](https://github.com/wwulfric/peeka/blob/main/LICENSE).

---

## Agradecimientos

- Evaluación de seguridad: [simpleeval](https://github.com/danthedeckie/simpleeval)
- Protocolo de depuración remota: [PEP 768](https://peps.python.org/pep-0768/)
