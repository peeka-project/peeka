---
layout: default
title: Habilidad para Agentes de IA
nav_order: 7
---

# Habilidad para Agentes de IA
{: .no_toc }

Haz que tu asistente de programación de IA aprenda a usar Peeka para diagnosticar problemas en aplicaciones Python.
{: .fs-6 .fw-300 }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## ¿Qué es la habilidad peeka-diagnostics?

`peeka-diagnostics` es un **archivo de habilidad para Agentes de IA** (SKILL.md). Después de instalarlo, tu asistente de programación de IA (como OpenCode, Cursor, Cline, etc.) podrá:

- **Juicio automático**: Seleccionar el comando peeka correcto según los síntomas del problema (solicitudes lentas, fugas de memoria, interbloqueos, etc.)
- **Ejecutar diagnóstico**: Adjuntarse a procesos Python en ejecución a través de `peeka-cli` y recolectar datos en tiempo real
- **Analizar resultados**: Realizar análisis estructurado usando la salida JSONL y `jq`
- **Solución paso a paso**: Seguir el playbook de diagnóstico incorporado (análisis de rendimiento, resolución de excepciones, análisis de memoria, análisis de hilos)

El archivo de habilidad cubre los 14 comandos CLI completos de Peeka, e incluye descripciones completas de parámetros, métodos de análisis con jq, sintaxis de expresiones condicionales y protocolos de seguridad.

---

## Resumen del Contenido de la Habilidad

### Árbol de Decisión de Diagnóstico

La habilidad tiene una tabla de mapeo incorporada de síntomas a comandos, la IA seleccionará automáticamente la ruta de diagnóstico según los síntomas:

| Síntoma | Comando Recomendado | Objetivo |
|---------|---------------------|----------|
| Respuesta lenta / alta latencia | `watch` → `trace` | Localizar llamadas lentas |
| Valor de retorno incorrecto / bug lógico | `watch` observar entrada y salida | Asociar entrada con salida |
| Excepción / error | `watch -e` → `stack` | Encontrar ubicación y causa de la excepción |
| Crecimiento de memoria / fuga | `memory` comandos de serie | Encontrar asignaciones de memoria y poseedores |
| CPU alta | `top` → `trace` | Encontrar rutas de puntos calientes de CPU |
| Interbloqueo / bloqueo | `thread` → `stack` | Encontrar puntos de contención de bloqueos |

### 4 Playbooks de Diagnóstico

| Playbook | Escenario | Flujo Principal |
|----------|-----------|-----------------|
| A: Análisis de Rendimiento | Interfaz lenta, función tarda demasiado | watch filtrar llamadas lentas → trace descomponer árbol de llamadas → localizar cuello de botella |
| B: Resolución de Excepciones | Error en entorno de producción | watch -e capturar excepción → stack obtener pila de llamadas → analizar causa raíz |
| C: Análisis de Memoria | Crecimiento continuo de memoria | memory iniciar rastreo → múltiples instantáneas → diff comparación → referrers buscar referencias |
| D: Análisis de Hilos | Interbloqueo, hilo bloqueado | thread listar estados → filtrar WAITING → stack obtener pila |

### Capacidad de Análisis JSONL

Toda la salida CLI está en formato JSONL, la IA usará `jq` para realizar análisis estructurado:

```bash
# Filtrar llamadas lentas
peeka-cli watch "module.func" -n 10 | jq 'select(.type == "observation" and .cost > 100)'

# Extraer información de excepción
peeka-cli watch "module.func" -e -n 5 | jq 'select(.success == false) | {func: .func_name, error: .exception}'

# Análisis top de memoria
peeka-cli memory --action top | jq '.data.top_allocations[:5]'
```

---

## Método de Instalación

### Requisitos Previos

- Peeka ya está instalado (ver [Guía de Instalación](installation))
- Usar un asistente de programación de IA que soporte Skill/SKILL.md

### Método 1: Instalación a nivel de proyecto (recomendado)

Copia el archivo de habilidad al directorio `.agents/skills/` de tu proyecto:

```bash
# Ejecutar en la raíz del proyecto
mkdir -p .agents/skills/peeka-diagnostics

# Copiar el archivo de habilidad desde el repositorio de Peeka
curl -o .agents/skills/peeka-diagnostics/SKILL.md \
  https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md
```

Estructura de directorios después de la instalación:

```
your-project/
├── .agents/
│   └── skills/
│       └── peeka-diagnostics/
│           └── SKILL.md
├── src/
│   └── ...
└── ...
```

### Método 2: Instalación global

Si tu herramienta de IA admite un directorio global de habilidades (como `~/.config/opencode/skills/`), puedes instalarlo en una ubicación global:

```bash
mkdir -p ~/.config/opencode/skills/peeka-diagnostics
curl -o ~/.config/opencode/skills/peeka-diagnostics/SKILL.md \
  https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md
```

---

## Modo de Uso

### OpenCode

En OpenCode, carga la habilidad a través de `load_skills`:

```typescript
task(
  category="deep",
  load_skills=["peeka-diagnostics"],
  prompt="Mi API responde lentamente, ayúdame a diagnosticar con peeka el PID 12345"
)
```

O refiérete directamente en la conversación:

```
@peeka-diagnostics La memoria de mi servicio Python sigue creciendo, el PID es 54321, ayúdame a solucionarlo
```

### Otras herramientas de IA

Para Cursor, Cline u otras herramientas de IA que admitan instrucciones personalizadas:

1. Asegúrate de que el archivo de habilidad esté en `.agents/skills/peeka-diagnostics/SKILL.md`
2. La herramienta de IA descubrirá y cargará la habilidad automáticamente
3. Cuando describas problemas relacionados con el diagnóstico de Python, la IA aplicará automáticamente el conocimiento en la habilidad

### Palabras Clave de Activación

Las siguientes palabras clave activarán a la IA para usar la habilidad peeka-diagnostics:

- `debug python`, `diagnose python`
- `slow app`, `memory leak`, `high CPU`
- `trace function`, `watch expression`
- `thread deadlock`, `runtime debugging`
- `profile python`, `peeka`

---

## Ejemplos de Escenarios de Uso

### Escenario 1: Diagnosticar interfaz lenta

> "Mi tiempo de respuesta de la interfaz /api/users aumentó de 50ms a 2s, el PID del proceso objetivo es 12345, ayúdame a solucionarlo"

La IA automáticamente:
1. `peeka-cli attach 12345`
2. `peeka-cli sc "*user*"` para encontrar clases relacionadas
3. `peeka-cli watch "myapp.api.users.get_users" -n 5 --condition "cost > 100"` para filtrar solicitudes lentas
4. `peeka-cli trace "myapp.api.users.get_users" -n 3 -d 5` para descomponer el árbol de llamadas
5. Analizar la salida JSONL y localizar la subfunción cuello de botella
6. Limpieza con `peeka-cli reset && peeka-cli detach`

### Escenario 2: Diagnosticar fuga de memoria

> "Después de varias horas de ejecución, la memoria de mi servicio Python aumentó de 200MB a 2GB, PID 54321"

La IA automáticamente:
1. Adjuntar el proceso e iniciar tracemalloc
2. Tomar múltiples instantáneas con intervalos y comparar con diff
3. Usar `memory --action top` para encontrar las mayores fuentes de asignación
4. Usar `memory --action referrers` para rastrear la cadena de referencias
5. Emitir informe de análisis y sugerencias de reparación

### Escenario 3: Diagnosticar interbloqueo de hilos

> "Mi servicio está bloqueado, todas las solicitudes se agotan el tiempo de espera, PID 33333"

La IA automáticamente:
1. `peeka-cli thread` enumera todos los estados de hilos
2. Filtrar hilos en estado `WAITING`
3. Obtener información detallada de la pila de hilos sospechosos
4. Analizar la contención de bloqueos y dar sugerencias

---

## Mantenimiento del Archivo de Habilidad

### Actualizar la habilidad

Cuando Peeka lance una nueva versión, actualiza el archivo de habilidad:

```bash
curl -o .agents/skills/peeka-diagnostics/SKILL.md \
  https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md
```

### Extensión Personalizada

El archivo de habilidad es Markdown puro, puedes extenderlo según las necesidades de tu proyecto:

- Agregar patrones de diagnóstico específicos del proyecto
- Agregar accesos directos para patrones de funciones comunes
- Complementar pasos de resolución de problemas específicos del proyecto

---

## Preguntas Frecuentes

### ¿La IA no usa peeka para diagnosticar?

- Confirma que el archivo de habilidad se instaló correctamente en `.agents/skills/peeka-diagnostics/SKILL.md`
- Menciona explícitamente palabras clave relacionadas con diagnóstico y depuración de Python en el prompt
- Confirma que `peeka-cli` está instalado y disponible

### ¿La ejecución del comando de diagnóstico de IA falló?

- Verifica que Peeka esté instalado correctamente: `peeka-cli --help`
- Confirma que el proceso objetivo todavía está en ejecución: `ps -p <pid>`
- Verifica los permisos (ptrace_scope, CAP_SYS_PTRACE)

### ¿Dónde puedo encontrar el archivo de habilidad?

- **Repositorio GitHub**: [peeka/.agents/skills/peeka-diagnostics/SKILL.md](https://github.com/wwulfric/peeka/tree/master/.agents/skills/peeka-diagnostics)
- **Dirección de descarga directa**: `https://raw.githubusercontent.com/wwulfric/peeka/master/.agents/skills/peeka-diagnostics/SKILL.md`
