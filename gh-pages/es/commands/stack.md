---
layout: default
title: stack
parent: Referencia de Comandos
nav_order: 4
---

# stack - Rastrear pila de llamadas
{: .no_toc }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Introducción

El comando `stack` captura la pila de llamadas completa cuando se invoca una función, ayudando a los desarrolladores a rastrear la ruta de llamada de la función. Esta es una potente herramienta de depuración, especialmente útil para analizar cadenas de llamadas complejas y localizar la causa raíz de los problemas.

**Características Principales**:
- Captura la pila de llamadas completa cuando se llama a una función
- Muestra nombres de archivos, números de línea, nombres de funciones y fragmentos de código en la cadena de llamadas
- Soporta filtrado condicional (capturar solo bajo condiciones específicas)
- Profundidad de pila configurable (evita salida excesiva)
- Salida en streaming en tiempo real (formato JSON)

**Diferencia con el comando watch**:
- `watch`: Observa **argumentos, valores de retorno, tiempo de ejecución** de la función
- `stack`: Observa **ruta de llamada** de la función (desde dónde fue llamada)

## Uso en TUI

En modo TUI, presiona **`4`** para cambiar a la **Vista Stack**, que proporciona las siguientes características interactivas:

- **Entrada de Patrón**: Soporta autocompletado de nombres de funciones (obtenido desde el proceso objetivo en tiempo real)
- **Configuración de Parámetros**: Configuración visual para cantidad de capturas, expresiones condicionales, profundidad de pila
- **Visualización de Pila de Llamadas**: Muestra en tiempo real pilas de llamadas en formato de tabla
  - Muestra nombres de archivos, números de línea, nombres de funciones, fragmentos de código
  - Cada captura muestra la cadena de llamadas completa (desde la más interna hasta la más externa)
- **Atajos de Teclado**:
  - Enter después de ingresar el patrón para comenzar a capturar
  - Presiona `c` para limpiar registros de captura
  - Presiona Delete para eliminar el registro seleccionado
  - Teclas de flecha Arriba/Abajo para navegar niveles de pila

**Equivalente CLI**: Todos los ejemplos a continuación usan comandos CLI para demostración; TUI proporciona la misma funcionalidad con una interfaz gráfica.

---

## Escenarios de Uso

### 1. Rastrear Orígenes de Llamada

**Escenario**: Una función es llamada desde múltiples lugares, necesita localizar rutas de llamada específicas.

```bash
# Ver dónde se llama a la función process_order
peeka-cli stack "myapp.orders.process_order"
```

**Ejemplo de Salida**:
```json
{
  "location": "AtEnter",
  "pattern": "myapp.orders.process_order",
  "params": [{"order_id": 12345}],
  "stack": [
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 156,
      "function": "create_order_view",
      "code_context": "result = process_order(order_data)"
    },
    {
      "filename": "/app/myapp/middleware/auth.py",
      "lineno": 45,
      "function": "check_permissions",
      "code_context": "return handler(request)"
    },
    {
      "filename": "/usr/lib/python3.14/http/server.py",
      "lineno": 89,
      "function": "handle_request",
      "code_context": "self.handle_one_request()"
    }
  ],
  "thread_id": 140234567890,
  "thread_name": "Thread-5"
}
```

### 2. Analizar Llamadas Recursivas

**Escenario**: Función recursiva causa desbordamiento de pila, necesita analizar profundidad de recursión y patrones.

```bash
# Limitar profundidad de pila a 20 niveles para evitar salida excesiva
peeka-cli stack "myapp.utils.recursive_func" --depth 20
```

### 3. Localizar Rutas de Llamada de Excepciones

**Escenario**: La función tiene errores bajo condiciones específicas, necesita rastrear la cadena de llamadas cuando ocurre el error.

```bash
# Solo capturar pila cuando user_id es 999
peeka-cli stack "myapp.auth.check_permission" \
  --condition "params[0] == 999"
```

### 4. Analizar Rutas de Llamada Calientes

**Escenario**: Análisis de rendimiento, encontrar qué rutas llaman a una función con mayor frecuencia.

```bash
# Capturar las primeras 100 llamadas, luego analizar distribución de rutas
peeka-cli stack "myapp.db.execute_query" -n 100 | \
  jq -r '.stack[0] | "\(.filename):\(.lineno)"' | \
  sort | uniq -c | sort -rn
```

### 5. Rastreo de Llamadas entre Módulos

**Escenario**: En arquitectura de microservicios, rastrear propagación de solicitudes entre módulos.

```bash
# Rastrear cadena de llamadas de función de entrada de API
peeka-cli stack "myapp.api.handle_request"
```

---

## Formato del Comando

```bash
peeka-cli attach <pid>
peeka-cli stack <pattern> [options]
```

**Parámetros Requeridos**:
- `pattern`: Patrón de función objetivo (ej., `module.Class.method`)

**Parámetros Opcionales**:
- `-n, --times`: Número de capturas (-1 para ilimitado, predeterminado -1)
- `--condition`: Expresión de condición (capturar solo cuando se cumple la condición)
- `--depth`: Límite de profundidad de pila (predeterminado 10)

---

## Referencia de Parámetros

### pattern - Patrón de Función

Especifica la función objetivo a rastrear, soporta los siguientes formatos:

| Formato | Descripción | Ejemplo |
|--------|-------------|---------|
| `module.function` | Función a nivel de módulo | `myapp.utils.calculate` |
| `module.Class.method` | Método de clase | `myapp.models.User.save` |
| `module.Class.static_method` | Método estático | `myapp.utils.Helper.validate` |

**Notas**:
- Debe usar nombre completamente calificado (comenzando desde la raíz del módulo)
- No se soportan comodines (igual que el comando `watch`)
- La función objetivo debe estar cargada en memoria

### --times, -n - Número de Capturas

Controla el número de capturas para evitar generar cantidades masivas de datos.

| Valor | Comportamiento | Escenario de Uso |
|-------|----------|----------|
| `-1` (predeterminado) | Captura ilimitada | Monitoreo continuo, solución de problemas en producción |
| `1` | Capturar una vez y detenerse | Solo necesita ver la pila de llamadas una vez |
| `N` | Capturar N veces y detenerse | Análisis de muestreo, estadísticas de distribución de rutas |

**Ejemplos**:
```bash
# Solo capturar la primera invocación
peeka-cli stack "myapp.func" -n 1

# Capturar 50 muestras
peeka-cli stack "myapp.func" -n 50
```

### --condition - Expresión de Condición

Captura la pila solo cuando se cumple la condición, evitando datos irrelevantes.

**Variables Disponibles**:
- `params`: Argumentos posicionales de la función (tupla)
- `kwargs`: Argumentos de palabra clave de la función (dict)
- `target`: El objeto `self` para métodos de instancia

**Operadores Soportados**:
- Comparación: `==`, `!=`, `>`, `<`, `>=`, `<=`
- Lógica: `and`, `or`, `not`
- Pertenencia: `in`, `not in`
- Cadena: `str(x).startswith()`, `str(x).endswith()`
- Longitud: `len(params)`, `len(kwargs)`
- Acceso de índice: `params[0]`, `kwargs.get('key')`

**Ejemplos**:
```bash
# Solo capturar cuando el primer argumento es mayor que 100
peeka-cli stack "myapp.func" --condition "params[0] > 100"

# Solo capturar cuando el número de parámetros es mayor que 2
peeka-cli stack "myapp.func" --condition "len(params) > 2"

# Solo capturar cuando el ID de usuario es el valor especificado
peeka-cli stack "myapp.check_permission" \
  --condition "kwargs.get('user_id') == 999"

# Condición compuesta
peeka-cli stack "myapp.process" \
  --condition "params[0] > 10 and len(params) < 5"
```

**Seguridad**:
- Implementado basado en la biblioteca `simpleeval`, todas las operaciones peligrosas deshabilitadas
- No permitido: `eval`, `exec`, `__import__`, `open`, `compile`
- Acceso no permitido a: `__class__`, `__subclasses__`
- Solo soporta operaciones seguras en lista blanca

### --depth - Límite de Profundidad de Pila

Controla el número de niveles de pila de llamadas capturados para evitar salida excesiva.

| Valor | Descripción | Escenario de Uso |
|-------|-------------|----------|
| `10` (predeterminado) | 10 niveles de pila | Escenarios generales de depuración |
| `5` | 5 niveles de pila | Solo importan los pocos niveles más recientes |
| `20` | 20 niveles de pila | Análisis de recursión profunda |
| `50` | 50 niveles de pila | Escenarios extremos (no recomendado) |

**Notas**:
- La profundidad de pila comienza a contar desde el **llamador** de la función objetivo (excluye la propia función objetivo)
- Mayor profundidad = mayor volumen de datos de salida
- Recomienda establecer una profundidad razonable basada en necesidades reales (5-20 niveles)

**Ejemplos**:
```bash
# Solo ver los 3 niveles de llamador más recientes
peeka-cli stack "myapp.func" --depth 3

# Análisis de recursión profunda (hasta 30 niveles)
peeka-cli stack "myapp.recursive_func" --depth 30
```

---

## Formato de Salida

El comando `stack` genera salida en formato JSON Lines (un objeto JSON por línea), facilitando el procesamiento en streaming y la integración con herramientas.

### Ejemplo Completo de Salida

```json
{
  "watch_id": "watch_20260131_001",
  "timestamp": 1738339200.123456,
  "location": "AtEnter",
  "pattern": "myapp.orders.process_order",
  "params": [
    {"order_id": 12345, "amount": 99.99}
  ],
  "kwargs": {
    "priority": "high"
  },
  "target": {
    "__attrs__": {
      "user_id": 999,
      "session": "<Session object>"
    }
  },
  "stack": [
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 156,
      "function": "create_order_view",
      "code_context": "result = process_order(order_data)"
    },
    {
      "filename": "/app/myapp/middleware/rate_limiter.py",
      "lineno": 78,
      "function": "rate_limit_decorator",
      "code_context": "return func(*args, **kwargs)"
    },
    {
      "filename": "/app/myapp/middleware/auth.py",
      "lineno": 45,
      "function": "check_permissions",
      "code_context": "return handler(request)"
    }
  ],
  "thread_id": 140234567890,
  "thread_name": "ThreadPoolExecutor-3",
  "cost": 0.0
}
```

### Descripción de Campos

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `watch_id` | string | Identificador único para la tarea de observación |
| `timestamp` | float | Marca de tiempo Unix (segundos, con decimales) |
| `location` | string | Ubicación del punto de observación (`AtEnter` indica entrada de función) |
| `pattern` | string | Patrón de función objetivo |
| `params` | array | Argumentos posicionales de la función |
| `kwargs` | object | Argumentos de palabra clave de la función |
| `target` | object | El objeto `self` para métodos de instancia (solo métodos de clase) |
| `stack` | array | Arreglo de marcos de pila de llamadas (campo más importante) |
| `thread_id` | int | ID de hilo |
| `thread_name` | string | Nombre de hilo |
| `cost` | float | Tiempo de ejecución (milisegundos, 0.0 en `AtEnter`) |

### Elementos del Arreglo de Pila

Cada marco de pila contiene los siguientes campos:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `filename` | string | Ruta absoluta al archivo de código fuente |
| `lineno` | int | Número de línea del código fuente |
| `function` | string | Nombre de función/método |
| `code_context` | string | Contenido del código fuente de esa línea (recortado) |

**Orden de Marcos de Pila**:
- `stack[0]`: **Llamador más reciente** (ubicación que llamó directamente a la función objetivo)
- `stack[1]`: Llamador del llamador
- `stack[n]`: Las entradas posteriores están más cerca de la raíz de la cadena de llamadas

---

## Ejemplos de Uso

### Ejemplo 1: Rastreo Básico de Pila de Llamadas

**Escenario**: Ver dónde se llama a la función `calculate_price`.

```bash
peeka-cli stack "myapp.pricing.calculate_price"
```

**Salida**:
```json
{
  "watch_id": "watch_001",
  "timestamp": 1738339200.123,
  "location": "AtEnter",
  "pattern": "myapp.pricing.calculate_price",
  "params": [{"product_id": 789, "quantity": 5}],
  "stack": [
    {
      "filename": "/app/myapp/api/cart.py",
      "lineno": 234,
      "function": "checkout",
      "code_context": "total = calculate_price(cart_items)"
    },
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 89,
      "function": "checkout_view",
      "code_context": "result = cart.checkout()"
    }
  ],
  "thread_id": 140234567890,
  "thread_name": "MainThread"
}
```

**Interpretación**:
- `calculate_price` fue llamada por la función `checkout` en `cart.py:234`
- `checkout` fue llamada por `checkout_view` en `views.py:89`

### Ejemplo 2: Filtrado Condicional

**Escenario**: Solo rastrear llamadas con argumentos negativos (posibles casos de excepción).

```bash
peeka-cli stack "myapp.utils.process_value" \
  --condition "params[0] < 0" \
  -n 10
```

**Salida** (solo genera salida cuando el argumento es negativo):
```json
{
  "watch_id": "watch_002",
  "timestamp": 1738339201.456,
  "location": "AtEnter",
  "pattern": "myapp.utils.process_value",
  "params": [-5],
  "stack": [
    {
      "filename": "/app/myapp/data/processor.py",
      "lineno": 67,
      "function": "validate_input",
      "code_context": "result = process_value(user_input)"
    }
  ],
  "thread_id": 140234567891,
  "thread_name": "WorkerThread-2"
}
```

**Uso**: Localizar rápidamente el origen de entrada anormal.

### Ejemplo 3: Limitar Profundidad de Pila

**Escenario**: Solo importan los 3 niveles de llamador más recientes.

```bash
peeka-cli stack "myapp.db.execute_query" --depth 3
```

**Salida**:
```json
{
  "watch_id": "watch_003",
  "timestamp": 1738339202.789,
  "location": "AtEnter",
  "pattern": "myapp.db.execute_query",
  "params": ["SELECT * FROM users WHERE id = ?", [999]],
  "stack": [
    {
      "filename": "/app/myapp/models/user.py",
      "lineno": 123,
      "function": "get_by_id",
      "code_context": "return db.execute_query(sql, params)"
    },
    {
      "filename": "/app/myapp/api/users.py",
      "lineno": 45,
      "function": "get_user",
      "code_context": "user = User.get_by_id(user_id)"
    },
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 78,
      "function": "user_profile_view",
      "code_context": "return get_user(request.user_id)"
    }
  ]
}
```

### Ejemplo 4: Capturar una Vez y Detenerse

**Escenario**: Solo necesita ver la pila de llamadas una vez para confirmar la ruta de llamada.

```bash
peeka-cli stack "myapp.cache.get" -n 1
```

**Comportamiento**: Se detiene automáticamente el rastreo después de capturar la primera invocación, sin más salida.

### Ejemplo 5: Combinado con Análisis jq

**Escenario**: Extraer todos los orígenes de llamada, analizar qué archivo llama a la función objetivo con mayor frecuencia.

```bash
peeka-cli stack "myapp.logger.log" -n 100 | \
  jq -r '.stack[0] | "\(.filename):\(.lineno)"' | \
  sort | uniq -c | sort -rn | head -10
```

**Salida**:
```
     45 /app/myapp/api/views.py:123
     23 /app/myapp/middleware/auth.py:67
     12 /app/myapp/utils/helper.py:234
     ...
```

**Interpretación**: `views.py:123` es el origen de llamada más frecuente (45 veces).

### Ejemplo 6: Rastrear Llamadas Multihilo

**Escenario**: Analizar qué hilos llamaron a la función objetivo.

```bash
peeka-cli stack "myapp.shared.resource.access" -n 50 | \
  jq -r '.thread_name' | sort | uniq -c
```

**Salida**:
```
     30 WorkerThread-1
     15 WorkerThread-2
      5 MainThread
```

---

## Flujos de Trabajo de Diagnóstico Completos

### Flujo de Trabajo 1: Localizar Rutas de Llamada de Excepciones

**Problema**: Una función lanza excepciones bajo circunstancias específicas, necesita encontrar qué ruta de llamada la activa.

```bash
# Paso 1: Iniciar rastreo (solo capturar llamadas con parámetros de excepción)
peeka-cli stack "myapp.payment.charge" \
  --condition "params[0] <= 0" \
  -n 20

# Paso 2: Esperar reproducción del problema (salida continua a archivo)
peeka-cli stack "myapp.payment.charge" \
  --condition "params[0] <= 0" > stack_trace.jsonl

# Paso 3: Analizar rutas de llamada
jq -r '.stack[] | "\(.filename):\(.lineno) - \(.function)"' stack_trace.jsonl

# Paso 4: Encontrar fuentes de excepción más frecuentes
jq -r '.stack[0] | "\(.filename):\(.lineno)"' stack_trace.jsonl | \
  sort | uniq -c | sort -rn
```

**Ejemplo de Resultado**:
```
     12 /app/myapp/api/refund.py:89
      3 /app/myapp/jobs/reconcile.py:234
```

**Conclusión**: `refund.py:89` es la principal fuente de problemas, verifica la lógica de validación de entrada allí.

### Flujo de Trabajo 2: Análisis de Rutas de Puntos Calientes de Rendimiento

**Problema**: Una función de consulta de base de datos es llamada frecuentemente, necesita encontrar qué rutas son las que consumen más tiempo.

```bash
# Paso 1: Capturar pilas de llamada de 200 invocaciones
peeka-cli stack "myapp.db.query" -n 200 > query_stacks.jsonl

# Paso 2: Analizar distribución de rutas de llamada
jq -r '.stack[0:3] | map("\(.filename):\(.lineno)") | join(" -> ")' \
  query_stacks.jsonl | sort | uniq -c | sort -rn | head -10

# Paso 3: Optimizar rutas de alta frecuencia (ej., agregar almacenamiento en caché)
```

**Ejemplo de Salida**:
```
     89 /app/myapp/api/list.py:123 -> /app/myapp/models/user.py:45
     34 /app/myapp/api/search.py:67 -> /app/myapp/models/user.py:45
     12 /app/myapp/jobs/sync.py:234 -> /app/myapp/models/user.py:45
```

**Conclusión**: La ruta `list.py:123` tiene la mayor proporción (89 veces), priorizar optimizar esta ruta.

### Flujo de Trabajo 3: Análisis de Profundidad de Recursión

**Problema**: Función recursiva causa desbordamiento de pila, necesita analizar profundidad de recursión.

```bash
# Paso 1: Capturar pilas de llamada profundas (profundidad establecida en 50)
peeka-cli stack "myapp.tree.traverse" --depth 50 -n 10 > recursion.jsonl

# Paso 2: Calcular profundidad de pila para cada invocación
jq '.stack | length' recursion.jsonl

# Paso 3: Encontrar la llamada más profunda
jq -s 'max_by(.stack | length)' recursion.jsonl > deepest.json

# Paso 4: Analizar ruta de la llamada más profunda
jq '.stack[] | "\(.function) at \(.filename):\(.lineno)"' deepest.json
```

**Ejemplo de Salida**:
```
traverse at /app/myapp/tree.py:45
traverse at /app/myapp/tree.py:45
traverse at /app/myapp/tree.py:45
... (repetido 48 veces)
process_tree at /app/myapp/api/views.py:123
```

**Conclusión**: Profundidad de recursión alcanzó 48 niveles, necesita optimizar la condición de terminación o cambiar a implementación iterativa.

---

## Notas Importantes

### 1. Impacto en el Rendimiento

**Grado de Impacto**:
- **Capturando marcos de pila**: Cada captura agrega aproximadamente 0.5-2ms de sobrecoste (depende de la profundidad de pila)
- **Serialización JSON**: Aproximadamente 0.2-0.5ms por captura
- **Transmisión de red**: Aproximadamente 0.1-0.3ms por captura (Unix Domain Socket)

**Sobrecoste Total**: Aproximadamente 1-3ms por captura (funciones de alta frecuencia pueden acumular hasta 5-10% de CPU)

**Recomendaciones de Optimización**:
- Usa `--condition` para reducir la frecuencia de captura
- Establece una `--depth` razonable (predeterminado 10 niveles generalmente suficiente)
- Evita rastrear funciones de ultra alta frecuencia (ej., funciones llamadas decenas de miles de veces por segundo)
- Usa `-n` para limitar el número de capturas (detener inmediatamente después de depurar)

### 2. Volumen de Datos de Salida

**Estimación de Volumen de Datos**:
- Cada marco de pila aproximadamente 200-300 bytes (JSON)
- Pila de llamadas de 10 niveles aproximadamente 2-3 KB
- 1000 capturas aproximadamente 2-3 MB

**Recomendaciones de Gestión**:
- Salida a archivo: `peeka-cli stack ... > output.jsonl`
- Limpia regularmente archivos de salida
- Usa procesamiento en streaming (`jq`) en lugar de cargar todos los datos a la vez

### 3. Seguridad de Hilos

**Notas**:
- En entornos multihilo, pilas de llamadas de diferentes hilos se intercalarán en la salida
- Usa los campos `thread_id` y `thread_name` para distinguir hilos
- Puede filtrar hilos específicos con `jq`:
  ```bash
  peeka-cli stack "myapp.func" | \
    jq 'select(.thread_name == "WorkerThread-1")'
  ```

### 4. Limitaciones de Expresiones de Condición

**Limitaciones**:
- No soporta la variable `cost` (porque `stack` solo captura en la entrada de la función, la ejecución aún no se ha completado)
- No soporta acceder a valores de retorno (`returnObj` no disponible)
- No soporta llamadas a métodos de objetos complejos (ej., `params[0].some_method()`)

**Variables Disponibles**: Solo `params`, `kwargs`, `target`

### 5. Límite de Cantidad de Marcos de Pila

**Limitaciones**:
- Máximo predeterminado 10 niveles (ajustable vía `--depth`)
- La profundidad máxima de recursión predeterminada del intérprete de Python es 1000 (`sys.getrecursionlimit()`)
- No se recomienda establecer `--depth` más allá de 50 (volumen de datos excesivo)

---

## Preguntas Frecuentes

### ¿Cómo detener un rastreo de pila en ejecución?

**Método 1**: Usa Ctrl+C para interrumpir el cliente (no afecta al proceso objetivo)

**Notas**:
- Después de detener el rastreo, la función objetivo vuelve al estado original (sin impacto en el rendimiento)
- El proceso objetivo no se ve afectado

### ¿Por qué el campo code_context es None?

**Razones**:
- El archivo de código fuente es inaccesible (ej., código `.pyc` compilado)
- El archivo de código fuente ha sido eliminado o movido
- Módulos integrados de Python (extensiones C)

**Soluciones**:
- Asegúrate de que el archivo de código fuente existe y es accesible
- Para módulos de extensión C, no se puede obtener contenido del código fuente (comportamiento normal)

### ¿Se pueden usar los comandos stack y watch simultáneamente?

**Respuesta**: Sí, se pueden usar simultáneamente.

**Ejemplo**:
```bash
# Terminal 1: Rastrear pila de llamadas
peeka-cli stack "myapp.func" > stack.jsonl

# Terminal 2: Observar argumentos y valores de retorno
peeka-cli watch "myapp.func" > watch.jsonl
```

**Notas**:
- Ambos comandos inyectarán dos decoradores (el impacto en el rendimiento se acumula)
- Recomienda usar según sea necesario, evitar rastreo excesivo

### ¿Cómo rastrear pilas de llamadas de funciones de la biblioteca estándar?

**Respuesta**: Sí, pero requiere la ruta completa del módulo.

**Ejemplos**:
```bash
# Rastrear pila de llamadas de json.dumps
peeka-cli stack "json.dumps" --depth 5

# Rastrear método info del módulo logging
peeka-cli stack "logging.Logger.info" --depth 3
```

**Notas**:
- Las funciones de la biblioteca estándar generalmente tienen frecuencia de llamada extremadamente alta, recomienda usar filtrado condicional y límites de conteo
- Algunas funciones de extensión C no se pueden rastrear (ej., `time.sleep`)

---

## Técnicas Avanzadas

### 1. Desduplicación y Ordenación de Rutas de Llamada

**Escenario**: Analizar todas las rutas de llamada diferentes, ordenadas por frecuencia.

```bash
peeka-cli stack "myapp.db.query" -n 500 | \
  jq -r '.stack[0:3] | map("\(.filename):\(.lineno)") | join(" -> ")' | \
  sort | uniq -c | sort -rn > call_paths.txt
```

**Ejemplo de Salida**:
```
   123 /app/api/users.py:45 -> /app/models/user.py:78
    67 /app/api/orders.py:123 -> /app/models/order.py:56
    34 /app/jobs/sync.py:234 -> /app/models/user.py:78
```

### 2. Visualización de Árboles de Llamada

**Escenario**: Generar diagramas de árbol de llamada (requiere herramientas adicionales como `graphviz`).

```bash
# Paso 1: Extraer relaciones de llamada
peeka-cli stack "myapp.func" -n 100 | \
  jq -r '.stack[] | "\(.function) -> \(.filename):\(.lineno)"' > edges.txt

# Paso 2: Usa graphviz para generar diagrama (necesitas escribir un script personalizado)
# O usa herramientas en línea como https://dreampuf.github.io/GraphvizOnline/
```

### 3. Monitoreo de Frecuencia de Llamada en Tiempo Real

**Escenario**: Mostrar recuento de llamadas por segundo en tiempo real.

```bash
peeka-cli stack "myapp.api.handle_request" | \
  jq -r .timestamp | \
  awk '{
    sec = int($1)
    count[sec]++
  } END {
    for (s in count) print s, count[s]
  }'
```

### 4. Filtrado de Marcos de Pila de Bibliotecas de Terceros

**Escenario**: Solo importa el código de la aplicación, ignorar bibliotecas de terceros (ej., Django, Flask).

```bash
peeka-cli stack "myapp.views.index" --depth 20 | \
  jq '.stack |= map(select(.filename | startswith("/app/myapp")))'
```

### 5. Análisis de Cadena de Llamadas entre Procesos

**Escenario**: Combinar con registros para rastrear cadenas de llamadas entre procesos.

**Método**:
1. Inicia `stack` rastreo en cada servicio
2. Usa `trace_id` unificado (extraer de `params` o `kwargs`)
3. Fusiona salidas de diferentes servicios, agrupa por `trace_id`

```bash
# Servicio A
peeka-cli stack "service_a.process" | \
  jq --arg service "A" '. + {service: $service}' > trace_a.jsonl

# Servicio B
peeka-cli stack "service_b.handle" | \
  jq --arg service "B" '. + {service: $service}' > trace_b.jsonl

# Fusionar y analizar
cat trace_a.jsonl trace_b.jsonl | \
  jq -s 'group_by(.params[0].trace_id)'
```

### 6. Integración con Prometheus

**Escenario**: Exportar estadísticas de rutas de llamada a monitoreo Prometheus.

```bash
# Ejemplo de script (requiere implementación personalizada)
peeka-cli stack "myapp.api.endpoint" -n 1000 | \
  jq -r '.stack[0] | "\(.filename):\(.lineno)"' | \
  sort | uniq -c | \
  awk '{print "call_path_count{path=\""$2"\"} "$1}' > metrics.prom
```

**Ejemplo de Salida** (formato Prometheus):
```
call_path_count{path="/app/api/users.py:45"} 123
call_path_count{path="/app/api/orders.py:67"} 78
```

---

## Resumen

El comando `stack` es una herramienta potente para rastrear rutas de llamada de funciones, especialmente adecuada para:
- Localizar orígenes de llamada de excepciones
- Analizar cadenas de llamada complejas
- Análisis de rutas de puntos calientes de rendimiento
- Diagnóstico de profundidad de recursión

**Mejores Prácticas**:
- Usa filtrado condicional para reducir datos irrelevantes
- Establece una profundidad de pila razonable (5-20 niveles)
- Limita el número de capturas (evita generar datos masivos)
- Combina con `jq` para potente análisis de datos
- Detén el rastreo rápidamente después de depurar

**Siguientes Pasos**:
- Conoce el comando [`watch`](watch) (observa argumentos y valores de retorno)
- Conoce el comando [`memory`](memory) (análisis de memoria)
- Referente a [Guía para Desarrolladores de Agentes de IA](../ai-skill.md)
