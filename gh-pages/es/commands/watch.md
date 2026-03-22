---
layout: default
title: watch
parent: Referencia de Comandos
nav_order: 2
---

# watch - Observar llamadas a funciones
{: .no_toc }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

## Introducción

El comando `watch` se usa para observar la ejecución de funciones Python especificadas, capturando **parámetros de entrada**, **valores de retorno**, **información de excepciones**, **duración de ejecución** y otros datos. Este es el comando de diagnóstico principal de Peeka, adecuado para la solución de problemas en tiempo real y análisis de rendimiento en entornos de producción.

## Uso en TUI

En modo TUI, presiona la tecla **`2`** para cambiar a la **Vista Watch**, que proporciona las siguientes características interactivas:

- **Entrada de Patrón**: Soporta autocompletado de nombres de funciones (obtenido en tiempo real desde el proceso objetivo)
- **Configuración de Parámetros**: Configuración visual de profundidad, número de observaciones, puntos de observación, expresiones condicionales
- **Observación en Streaming en Tiempo Real**: Datos de observación mostrados en una tabla de streaming, actualización automática
- **Operaciones Rápidas**:
  - Presiona Enter después de ingresar el patrón para iniciar la observación
  - Presiona `s` para detener la observación actual
  - Presiona `c` para limpiar los registros de observación
  - Presiona `r` para actualizar la vista

**Comandos CLI equivalentes**: Todos los ejemplos a continuación usan comandos CLI para demostración. TUI proporciona la misma funcionalidad con una interfaz gráfica.

## Escenarios de Uso

- **Solución de Problemas**: Observar si las funciones son llamadas, si los parámetros son correctos, si los valores de retorno cumplen las expectativas
- **Análisis de Rendimiento**: Rastrear la duración de ejecución de la función, identificar llamadas lentas
- **Diagnóstico Condicional**: Solo observa llamadas que cumplen condiciones específicas (por ejemplo, parámetros mayores a un cierto valor)
- **Análisis de Excepciones**: Capturar información de excepciones y trazas de pila lanzadas por funciones
- **Monitoreo en Tiempo Real**: Salida de datos de observación en streaming, soporta formato JSON para fácil integración con sistemas de monitoreo

## Formato del Comando

```bash
peeka-cli attach <pid>    # Primero adjuntar al proceso objetivo
peeka-cli watch <pattern> [options]
```

### Parámetros

| Parámetro | Descripción | Valor por defecto | Ejemplo |
|-----------------------|----------------------------|---------|-----------------------------------------|
| `pattern` | Patrón de coincidencia de función | - | `module.Class.method` |
| `-x, --depth` | Profundidad de salida de objeto | `2` | `-x 3` |
| `-n, --times` | Número de observaciones (-1 para infinito) | `-1` | `-n 10` |
| `--condition` | Expresión de condición (soporta variable `cost`) | Ninguno | `--condition "params[0] > 100"` |
| `-b, --before` | Observar antes de la llamada a la función (AtEnter) | `false` | `-b` |
| `-e, --exception` | Solo observar cuando se lanza una excepción (AtExceptionExit) | `false` | `-e` |
| `-s, --success` | Solo observar en retorno exitoso (AtExit) | `false` | `-s` |
| `-f, --finish` | Observar después de que finalice la función (éxito o excepción) | `true` | `-f` |

**Nota**:

- Si no se especifican banderas `-b/-e/-s/-f`, el valor predeterminado es `-f` (observar todos los casos de finalización)
- El parámetro `--condition` todavía es soportado (por compatibilidad hacia atrás), se recomienda `--condition`

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

**Nota**: Debe usar la ruta completa del módulo (desde la raíz de importación), no se soportan comodines.

## Uso Básico

### 1. Observar Llamadas a Funciones

```bash
# Primero adjuntar al proceso objetivo
peeka-cli attach 12345

# Observar 5 llamadas
peeka-cli watch "calculator.Calculator.add" -n 5
```

**Ejemplo de Salida**:

```json
{
  "watch_id": "watch_a1b2c3d4",
  "timestamp": 1705586200.123,
  "location": "AtExit",
  "func_name": "calculator.Calculator.add",
  "params": [
    10,
    20
  ],
  "kwargs": {},
  "target": {
    "__attrs__": {
      "name": "calc1"
    }
  },
  "returnObj": 30,
  "success": true,
  "throwExp": null,
  "cost": 0.045,
  "thread_id": 140234567890,
  "thread_name": "MainThread"
}
```

**Descripción de Campos**:

| Campo | Descripción | Valor de Ejemplo |
|---------------|--------------------|------------------------------------------------|
| `watch_id` | ID de observación | `"watch_a1b2c3d4"` |
| `timestamp` | Marca de tiempo | `1705586200.123` |
| `location` | Ubicación de observación | `"AtEnter"` / `"AtExit"` / `"AtExceptionExit"` |
| `func_name` | Nombre de la función | `"module.Class.method"` |
| `params` | Argumentos posicionales | `[10, 20]` |
| `kwargs` | Argumentos de palabra clave | `{"debug": true}` |
| `target` | Objetivo (solo métodos de instancia, self) | `{"__attrs__": {...}}` |
| `returnObj` | Valor de retorno | `30` |
| `success` | Estado de éxito | `true` / `false` |
| `throwExp` | Información de excepción | `"ValueError: ..."` |
| `cost` | Duración de ejecución (ms) | `0.045` |
| `thread_id` | ID de hilo | `140234567890` |
| `thread_name` | Nombre de hilo | `"MainThread"` |

### 2. Ajustar Profundidad de Salida

```bash
# Profundidad 1: Solo mostrar tipos de objetos
peeka-cli watch "service.UserService.get_user" -x 1

# Profundidad 3: Mostrar 3 niveles de estructura anidada
peeka-cli watch "service.UserService.get_user" -x 3
```

**Comparación de Profundidad**:

```python
# Objeto original
user = {
    "id": 1,
    "name": "Alice",
    "profile": {
        "age": 25,
        "address": {
            "city": "Beijing"
        }
    }
}

# depth=1
{"id": 1, "name": "Alice", "profile": "{'age': 25, 'address': {...}}

# depth=2
{"id": 1, "name": "Alice", "profile": {"age": 25, "address": "{'city': 'Beijing'}"}}

# depth=3
{"id": 1, "name": "Alice", "profile": {"age": 25, "address": {"city": "Beijing"}}}
```

### 3. Observación Infinita (Salida en Streaming)

```bash
# Observación continua hasta que se detenga manualmente (Ctrl+C)
peeka-cli watch "api.handler.process_request"
```

Adecuado para:

- Monitoreo en tiempo real del entorno de producción
- Esperar a reproducir problemas intermitentes
- Recolección y análisis de datos a largo plazo

### 4. Observar Métodos Estáticos y Métodos de Clase

```bash
# Método estático
peeka-cli watch "utils.Helper.static_method"

# Método de clase
peeka-cli watch "models.User.from_dict"
```

## Control de Tiempo de Observación

Peeka soporta control del tiempo de observación, permitiendo observar en diferentes etapas de la ejecución de la función.

### Banderas de Tiempo de Observación

| Bandera | Descripción | Tiempo de Observación | Campo location | Datos Disponibles |
|-------------------|-------|--------|------------------------------|------------------------------|
| `-b, --before` | Antes de la llamada | En la entrada | `AtEnter` | `params`, `kwargs`, `target` |
| `-s, --success` | En éxito | Después del retorno normal | `AtExit` | Anterior + `returnObj`, `cost` |
| `-e, --exception` | En excepción | Después de la excepción | `AtExceptionExit` | Anterior + `throwExp`, `cost` |
| `-f, --finish` | En finalización | Éxito o excepción | `AtExit` / `AtExceptionExit` | Todos los campos |

**Comportamiento Predeterminado**: Si no se especifican banderas, el valor predeterminado es `-f` (observar todos los casos de finalización)

### Ejemplos de Uso

#### 1. Observar Estado de Entrada de Función (-b)

```bash
# Observar parámetros cuando se llama a la función
peeka-cli watch "service.UserService.update_user" -b
```

**Salida**:

```json
{
  "location": "AtEnter",
  "params": [{"id": 1, "name": "Alice"}],
  "kwargs": {"force": true},
  "target": {"__attrs__": {"db": "..."}},
  "returnObj": null,
  "cost": 0.0
}
```

**Escenarios de Uso**:

- Confirmar si la función es llamada
- Verificar si los parámetros de entrada son correctos
- Depurar lógica de entrada de función

#### 2. Solo Observar Retornos Exitosos (-s)

```bash
# Solo observar llamadas exitosas, ignorar excepciones
peeka-cli watch "api.handler.process" -s
```

**Salida** (solo éxito):

```json
{
  "location": "AtExit",
  "params": [{"user_id": 123}],
  "returnObj": {"status": "ok"},
  "success": true,
  "cost": 45.2
}
```

**Escenarios de Uso**:

- Analizar valores de retorno de llamadas exitosas
- Rastrear el rendimiento de llamadas exitosas
- Ignorar casos de excepción

#### 3. Solo Observar Casos de Excepción (-e)

```bash
# Solo observar llamadas que lanzan excepciones
peeka-cli watch "database.query" -e
```

**Salida** (solo excepción):

```json
{
  "location": "AtExceptionExit",
  "params": ["SELECT * FROM users"],
  "throwExp": "DatabaseError: Connection timeout",
  "success": false,
  "cost": 5000.0
}
```

**Escenarios de Uso**:

- Enfocarse en situaciones de error
- Analizar las condiciones bajo las cuales ocurren las excepciones
- Monitorear tasa de errores

#### 4. Observar Proceso de Ejecución Completo (-b -s)

```bash
# Observar tanto entrada como retorno exitoso
peeka-cli watch "calculator.calculate" -b -s
```

**Salida** (2 registros por llamada):

```json
// Registro 1: Entrada
{
  "location": "AtEnter",
  "params": [
    10,
    20
  ],
  "returnObj": null
}

// Registro 2: Salida
{
  "location": "AtExit",
  "params": [
    10,
    20
  ],
  "returnObj": 30,
  "cost": 0.123
}
```

**Escenarios de Uso**:

- Observar si los parámetros se modifican durante la ejecución de la función
- Rastrear completamente el flujo de ejecución de la función
- Analizar efectos secundarios de la función

#### 5. Observar Todos los Casos (-b -e -s)

```bash
# Observar casos de entrada, éxito y excepción
peeka-cli watch "service.critical_operation" -b -e -s
```

**Salida** (2 o 3 registros dependiendo del resultado de la ejecución):

- Siempre produce 1 registro `AtEnter`
- Éxito produce 1 registro `AtExit`
- Excepción produce 1 registro `AtExceptionExit`

**Escenarios de Uso**:

- Diagnóstico completo de funciones complejas
- Depuración en entorno de desarrollo
- Análisis profundo en entorno de producción

## Filtrado por Condiciones

### Sintaxis de Expresión de Condición

Peeka usa la biblioteca **simpleeval** para implementar evaluación segura de expresiones de condición, soporta la siguiente sintaxis:

#### Operaciones Soportadas

| Tipo | Operadores/Funciones | Ejemplo |
|---------|--------------------------------------------------------|--------------------------------------|
| **Comparación** | `>`, `<`, `>=`, `<=`, `==`, `!=` | `params[0] > 100` |
| **Lógica** | `and`, `or`, `not` | `params[0] > 10 and params[1] < 100` |
| **Aritmética** | `+`, `-`, `*`, `/`, `%`, `**` | `params[0] + params[1] > 100` |
| **Pertenencia** | `in`, `not in` | `'error' in str(result)` |
| **Funciones** | `len()`, `str()`, `int()`, `float()`, `bool()` | `len(params) > 2` |
| **Cadena** | `.startswith()`, `.endswith()`, `.upper()`, `.lower()` | `str(params[0]).startswith('test_')` |
| **Acceso** | `[]`, `.get()` | `kwargs.get('debug') == True` |

#### Variables Disponibles

| Variable | Descripción | Tipo | Tiempo Disponible |
|----------|------------|--------|------------------|
| `params` | Argumentos posicionales | tuple | Todo el tiempo |
| `kwargs` | Argumentos de palabra clave | dict | Todo el tiempo |
| `target` | Objetivo (self) | object | Todo el tiempo (solo métodos de instancia |
| `cost` | Duración de ejecución (ms) | float | Solo disponible con `-s/-e/-f` |

**Nota**:

- La variable `cost` solo está disponible después de que finalice la función (`-s/-e/-f`, no disponible con `-b`
- `target` solo está disponible al observar métodos de instancia, `None` para funciones a nivel de módulo o métodos estáticos

**Garantías de Seguridad**:

- ❌ Prohíbe `__import__`, `eval`, `exec`, `compile`, `open`
- ❌ Prohíbe acceder a atributos de reflexión como `__class__`, `__subclasses__`
- ❌ Prohíbe ejecutar código arbitrario

### Ejemplos de Filtrado por Condición

#### 1. Filtrado de Parámetros

```bash
# Solo observar llamadas donde el primer parámetro > 100
peeka-cli watch "calculator.multiply" --condition "params[0] > 100"

# Filtrado por cantidad de parámetros
peeka-cli watch "api.handler" --condition "len(params) > 3"

# Combinación de múltiples condiciones
peeka-cli watch "service.query" --condition "params[0] > 10 and params[1] < 100"
```

#### 2. Filtrado de Argumentos de Palabra Clave

```bash
# Solo observar llamadas con parámetro debug
peeka-cli watch "logger.log" --condition "kwargs.get('debug') == True"

# Verificar si existe el parámetro
peeka-cli watch "api.request" --condition "'user_id' in kwargs"
```

#### 3. Coincidencia de Cadenas

```bash
# Parámetro comienza con un prefijo específico
peeka-cli watch "db.query" --condition "str(params[0]).startswith('SELECT')"

# Parámetro contiene una subcadena específica
peeka-cli watch "handler.process" --condition "'error' in str(params[0])"
```

#### 4. Verificación de Tipo

```bash
# Filtrado por tipo de parámetro
peeka-cli watch "converter.convert" --condition "isinstance(params[0], dict)"
```

#### 5. Condiciones Complejas

```bash
# Combinar múltiples condiciones
peeka-cli watch "service.process" \
  --condition "len(params) > 2 and params[0] > 100 and 'debug' in kwargs"

# Operaciones de cadena
peeka-cli watch "parser.parse" \
  --condition "len(str(params[0])) > 50 and str(params[0]).endswith('.json')"
```

#### 6. Filtrado de Rendimiento (variable cost)

```bash
# Solo observar llamadas que exceden 100ms de tiempo de ejecución
peeka-cli watch "database.query" --condition "cost > 100"

# Combinar condiciones de rendimiento y parámetros
peeka-cli watch "api.handler" --condition "cost > 50 and len(params) > 0"

# Observar valores de retorno de llamadas lentas
peeka-cli watch "service.process" -s --condition "cost > 200"
```

**Nota**:

- La variable `cost` solo está disponible con `-s/-e/-f` (después de que finalice la función)
- Usar `cost` con `-b` hará que la condición siempre devuelva True (cost=0)

#### 7. Filtrado de Estado de Objeto (variable target)

```bash
# Solo observar llamadas con estado de objeto específico (solo métodos de instancia)
# Nota: La versión actual tiene target disponible pero no soporta navegación de propiedades (target.attr)
# Se puede verificar si target existe en la condición
peeka-cli watch "service.UserService.update" --condition "params[0] > 0"
```

**Limitaciones**:

- La versión actual tiene la variable `target` disponible, pero simpleeval no soporta navegación de propiedades (como `target.field_name`)
- Versiones futuras pueden expandirse para soportar acceso a propiedades de objetos

### Depuración de Expresiones de Condición

Si la expresión de condición no funciona, verifica:

1. **Error de sintaxis**: Verifica si la expresión se ajusta a la sintaxis de Python
2. **Ortografía de variable**: Confirma que usa `params` y `kwargs` (no `args`)
3. **Índice fuera de límites**: Asegúrate que `params[i]` no exceda los límites
4. **Error de tipo**: Ten en cuenta los tipos de parámetros reales
5. **Depuración de impresión**: Observa una vez sin condición, verifica el contenido real de params y kwargs

**Ejemplo**: Ver contenido real de parámetros

```bash
# Primero observa una vez sin condición
peeka-cli watch "mymodule.func" -n 1

# Salida:
# {"args": [100, "test"], "kwargs": {"debug": true}, ...}

# Luego escribe la condición basada en la salida real
peeka-cli watch "mymodule.func" --condition "params[0] > 50"
```

## Formato de Salida

### Descripción de Campos JSON

Cada llamada a función genera un registro JSON:

```json
{
  "watch_id": "watch_a1b2c3d4",
  "timestamp": 1705586200.123,
  "location": "AtExit",
  "func_name": "module.Class.method",
  "params": [1, 2],
  "kwargs": {"key": "value"},
  "target": {"__attrs__": {"field": "value"}},
  "returnObj": 42,
  "success": true,
  "throwExp": null,
  "cost": 1.234,
  "thread_id": 140234567890,
  "thread_name": "MainThread"
}
```

**Descripción de Campos**:

| Campo | Tipo | Descripción |
|---|---|---|
| `watch_id` | string | ID de sesión de observación |
| `timestamp` | float | Marca de tiempo de llamada (tiempo Unix) |
| `location` | string | Ubicación de observación (AtEnter/AtExit/AtExceptionExit) |
| `func_name` | string | Nombre completo de la función |
| `params` | array | Lista de argumentos posicionales |
| `kwargs` | object | Diccionario de argumentos de palabra clave |
| `target` | object | Objetivo (self, solo métodos de instancia) |
| `returnObj` | any | Valor de retorno (en éxito) |
| `success` | boolean | Estado de éxito de ejecución |
| `throwExp` | string | Información de excepción (en fallo) |
| `cost` | float | Duración de ejecución (milisegundos) |
| `thread_id` | int | ID de hilo |
| `thread_name` | string | Nombre de hilo |

### Captura de Excepción

Cuando la función lanza una excepción:

```json
{
  "watch_id": "watch_a1b2c3d4",
  "timestamp": 1705586200.123,
  "location": "AtExceptionExit",
  "func_name": "calculator.Calculator.divide",
  "params": [
    10,
    0
  ],
  "kwargs": {},
  "returnObj": null,
  "success": false,
  "throwExp": "ZeroDivisionError: division by zero",
  "cost": 0.032,
  "thread_id": 140234567890,
  "thread_name": "MainThread"
}
```

**Nota**: Peeka captura información de excepción pero **no suprime excepciones**, las excepciones todavía se lanzan normalmente.

## Procesamiento y Análisis de Datos

### Usar jq para Procesar JSON

```bash
# 1. Extraer valor de retorno
peeka-cli watch "calculator.add" | jq '.returnObj'

# 2. Extraer duración
peeka-cli watch "api.handler" | jq '.cost'

# 3. Filtrar llamadas lentas (duración > 100ms)
peeka-cli watch "db.query" | jq 'select(.cost > 100)'

# 4. Solo mostrar llamadas fallidas
peeka-cli watch "service.process" | jq 'select(.success == false)'

# 5. Formatear salida
peeka-cli watch "func" | jq '{time: .timestamp, cost: .cost, result: .returnObj}'
```

### Análisis Estadístico

```bash
# Contar número de llamadas
peeka-cli watch "func" -n 100 | wc -l

# Calcular duración promedio
peeka-cli watch "func" -n 100 | jq '.duration_ms' | \
  awk '{sum+=$1; count++} END {print "avg:", sum/count, "ms"}'

# Calcular tasa de éxito
peeka-cli watch "func" -n 100 | jq '.success' | \
  awk '{total++; if($1=="true") success++} END {print "success rate:", success/total*100, "%"}'

# Encontrar la llamada más lenta
peeka-cli watch "func" -n 100 | jq -s 'max_by(.duration_ms)'
```

### Guardar en Archivo

```bash
# Guardar en formato JSONL (un JSON por línea)
peeka-cli watch "func" > observations.jsonl

# Análisis posterior
cat observations.jsonl | jq 'select(.duration_ms > 10)'
```

### Monitoreo en Tiempo Real

```bash
# Monitoreo de tasa de errores en tiempo real
peeka-cli watch "api.handler" | \
  jq -r 'if .success then "✓" else "✗ " + .error end'

# Monitoreo de duración en tiempo real
peeka-cli watch "db.query" | \
  jq -r '"\(.timestamp | strftime("%H:%M:%S")) - \(.duration_ms)ms"'
```

## Impacto en el Rendimiento

### Sobrecarga de Rendimiento

| Escenario | Sobrecarga | Descripción |
|---------------------|-------|-------------|
| **Observación incondicional** | < 2% | Captura básica de parámetros y serialización |
| **Filtrado por condición** | < 3% | Sobrecarga agregada de evaluación de expresiones de condición |
| **Recorrido profundo (depth=3)** | < 5% | Recorrido profundo de objetos anidados |
| **Llamadas de alta frecuencia (>1000 QPS)** | 5-10% | Serialización de alta frecuencia y transmisión de red |

### Recomendaciones de Optimización de Rendimiento

1. **Usar filtrado por condición**: Evitar capturar todas las llamadas
   ```bash
   # Solo capturar llamadas lentas (realmente captura y luego filtra, recomienda otros métodos)
   # Mejor enfoque es combinar con filtrado de parámetros
   peeka-cli watch "func" --condition "params[0] > 1000" -n 100
   ```

2. **Limitar número de observaciones**: Usar parámetro `-n`
   ```bash
   peeka-cli watch "func" -n 50  # Solo observa 50 veces
   ```

3. **Reducir profundidad de salida**: Para objetos complejos
   ```bash
   peeka-cli watch "func" -x 1  # Solo muestra un nivel
   ```

4. **Evitar funciones de alta frecuencia**: No observa funciones llamadas miles de veces por segundo (como funciones de utilidad básicas)

5. **Detener la observación rápidamente**: Detener inmediatamente después de solucionar el problema
   ```bash
   # Ctrl+C para detener la observación
   ```

### Impacto en la Memoria

- **Tamaño de búfer**: Predeterminado 10000 registros de observación (aproximadamente 10-50MB)
- **Expulsión automática**: Descarta automáticamente datos antiguos cuando se excede el límite

## Preguntas Frecuentes

### 1. Sin Datos de Observación

**Posibles Razones**:

- Función no llamada
- Nombre de función mal escrito
- Expresión de condición demasiado estricta
- Límite de número de observaciones alcanzado (parámetro -n)

**Pasos de Solución de Problemas**:

```bash
# 1. Confirmar que el nombre de la función es correcto (usa verificación interactiva de Python)
python3 -c "import mymodule; print(mymodule.MyClass.my_method)"

# 2. Eliminar expresión de condición, observar una vez primero
peeka-cli watch "mymodule.func" -n 1

# 3. Verificar si el proceso existe
ps aux | grep 12345
```

### 2. Error de Expresión de Condición

**Errores Comunes**:

```bash
# ❌ Incorrecto: Usar operaciones prohibidas
--condition "__import__('os').system('ls')  # Bloqueado por seguridad

# ❌ Incorrecto: Índice fuera de límites
--condition "params[5] > 10"  # La función solo tiene 3 parámetros

# ❌ Incorrecto: Nombre de variable incorrecto
--condition "args[0] > 10"  # Debe usar params no args

# ✓ Correcto
--condition "len(params) > 2 and params[0] > 10"
```

**Método de Depuración**:

1. Primero observa una vez sin condición, ver los parámetros reales
2. Usa condición simple para probar (como `len(params) > 0`)
3. Aumenta gradualmente la complejidad de la condición

### 3. Profundidad de Salida Insuficiente

```bash
# Problema: El objeto se muestra como "{'key': {...}}"
peeka-cli watch "func" -x 2

# Solución: Aumentar profundidad
peeka-cli watch "func" -x 3
```

**Nota**: La profundidad máxima es 4 para prevenir problemas de rendimiento por recorrido profundo.

### 4. ¿Afectará la Observación al Negocio?

**Garantías de Seguridad**:

- ✓ Excepciones no suprimidas (se lanzan normalmente)
- ✓ Fallo de observación no afecta la ejecución de la función original
- ✓ Limpieza automática de recursos (memoria, conexiones)
- ✓ Bajo sobrecoste de rendimiento (< 5%)

**Mejores Prácticas**:

- Primero usa durante períodos de bajo tráfico
- Comienza observando funciones de baja frecuencia
- Usa filtrado por condición para reducir el volumen de datos
- Detén la observación rápidamente después de solucionar el problema

### 5. ¿Cómo Detener la Observación?

```bash
# Método 1: Ctrl+C para detener la observación actual

# Método 2: Usa el comando reset para eliminar la mejora de watch
peeka-cli reset "pattern"

# Método 3: Detener todas las observaciones (en modo interactivo)
# La CLI actual no soporta directamente, necesita detener la sesión actual vía Ctrl+C
```

## Técnicas Avanzadas

### 1. Observación Multiproceso

```bash
# Observación en paralelo de múltiples procesos
for pid in 12345 12346 12347; do
  peeka-cli attach $pid
  peeka-cli watch "api.handler" > "logs/watch_$pid.jsonl" 2>&1 &
done
```

### 2. Observación Programada

```bash
# Observar 100 veces cada hora
while true; do
  peeka-cli watch "scheduler.task" -n 100 >> hourly_samples.jsonl
  sleep 3600
done
```

### 3. Integración con Alertas

```bash
# Monitorear tasa de errores, alertar cuando se excede el umbral
peeka-cli watch "api.handler" | \
  jq -r 'select(.success == false) | .error' | \
  while read error; do
    echo "Alerta: $error" | mail -s "Error de API" admin@example.com
  done
```

### 4. Integración con Prometheus

```python
# Convertir datos de observación a métricas de Prometheus
import json
from prometheus_client import Counter, Histogram

call_counter = Counter('function_calls_total', 'Total calls', ['function', 'status'])
duration_histogram = Histogram('function_duration_seconds', 'Duration', ['function'])

for line in sys.stdin:
    data = json.loads(line)
    func = data['func_name']
    status = 'success' if data['success'] else 'error'

    call_counter.labels(function=func, status=status).inc()
    duration_histogram.labels(function=func).observe(data['duration_ms'] / 1000)
```

## Referencias

- [Documentación de simpleeval](https://github.com/danthedeckie/simpleeval)
- [Diseño de Arquitectura de Peeka](../architecture.md)
- [Guía para Desarrolladores de Agentes de IA](../ai-skill.md)

## Registro de Cambios

| Versión | Fecha | Actualizaciones |
|-------|---------|-------------------|
| 0.1.0 | 2025-01 | Versión inicial con funcionalidad básica de watch |
