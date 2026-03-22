---
layout: default
title: inspect
parent: Referencia de Comandos
nav_order: 8
---

# inspect - Inspección de objetos en tiempo de ejecución
{: .no_toc }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Introducción del Comando

El comando `inspect` proporciona la función de **inspección de objetos en tiempo de ejecución**, permite ver el estado de objetos de un proceso Python en ejecución sin modificar el código. Soporta tres operaciones:

| Operación         | Función                 | Uso Típico                     |
|------------------|-------------------------|--------------------------------|
| **get**          | Obtener valor de atributo de módulo/clase | Ver configuración, constantes, variables de estado |
| **instances**    | Buscar instancias de tipo | Resolución de fugas de memoria, rastreo de objetos |
| **count**        | Contar número de instancias | Evaluación rápida del número de objetos |

---

## Escenarios de Uso

### 1. Verificación de configuración

Ver valores de configuración en tiempo de ejecución en entorno de producción, no necesita reiniciar el proceso:

```bash
peeka inspect --action get --target "app.config.DEBUG"
```

### 2. Resolución de fugas de memoria

Encontrar todas las instancias de un tipo específico, verificar si hay objetos no liberados:

```bash
peeka inspect --action instances --type myapp.User --limit 10
```

### 3. Estadísticas de objetos

Contar rápidamente el número de objetos de un tipo para evaluar el uso de memoria:

```bash
peeka inspect --action count --type list
```

### 4. Diagnóstico de estado

Ver variables de estado en tiempo de ejecución para diagnosticar el comportamiento de la aplicación:

```bash
peeka inspect --action get --target "sys.path"
```

---

## Uso en TUI

En modo TUI, presiona la tecla **`8`** para cambiar a la **vista Inspect**, proporciona las siguientes funciones interactivas:

- **Selección de operación**: Cambia visualmente entre operaciones get/instances/count
- **Operación get**:
  - Ingresa la ruta objetivo (como `sys.version`, `module.attr`)
  - Configura la profundidad de salida (depth)
  - Muestra valores de atributos e información de tipo
- **Operación instances**:
  - Ingresa el nombre de la clase (como `myapp.User`)
  - Configura límite de número de resultados, expresión de filtrado
  - Muestra lista de instancias y atributos
  - Soporta --gc-first (ejecuta GC antes de escanear)
- **Operación count**:
  - Ingresa el nombre de la clase (como `list`, `dict`)
  - Conteo rápido de número de instancias
- **Operaciones rápidas**:
  - Después de ingresar parámetros, presiona Enter para ejecutar
  - Presiona `c` para vaciar resultados

**Equivalente CLI**: Todos los ejemplos a continuación usan comandos CLI para demostrar, TUI proporciona una interfaz gráfica con la misma funcionalidad.

## Formato del Comando

```bash
# Primero debes adjuntar al proceso objetivo
peeka-cli attach <pid>

# Luego ejecuta el comando inspect
peeka-cli inspect --action <action> [options]
```

### Parámetros Básicos

| Parámetro       | Descripción      | Requerido | Valor por defecto |
|-----------------|------------------|-----------|-------------------|
| `--action`      | Tipo de operación | No        | `get`             |

### Tipos de Operación action

| Action         | Descripción          | Parámetro Requerido |
|----------------|----------------------|---------------------|
| **get**        | Obtener valor de atributo | `--target`          |
| **instances**  | Buscar instancias    | `--type`            |
| **count**      | Contar instancias    | `--type`            |

---

## Descripción de Parámetros

### Parámetros de operación get

| Parámetro      | Descripción               | Ejemplo              |
|----------------|---------------------------|----------------------|
| `--target`     | Ruta objetivo (separada por puntos) | `sys.version`        |
| `--depth`      | Profundidad de anidamiento de salida | `--depth 3`       |

**Reglas de resolución de target**:

- El primer segmento debe ser un módulo en `sys.modules`
- Los segmentos posteriores buscan en cadena mediante `getattr()`
- **No soporta** búsqueda de claves de diccionario (como `config["debug"]`)

Ejemplo:

- `sys.version` → `getattr(sys.modules["sys"], "version")`
- `myapp.Config.DEBUG` → `getattr(getattr(sys.modules["myapp"], "Config"), "DEBUG")`

### Parámetros de operación instances

| Parámetro          | Descripción         | Valor por defecto | Rango            |
|--------------------|---------------------|------------------|------------------|
| `--type`           | Nombre del tipo     | -                | Requerido        |
| `--limit`          | Límite de número de resultados | `10`       | 1-1000           |
| `--depth`          | Profundidad de anidamiento de salida | `2`     | 0-10             |
| `--filter-express` | Expresión de filtrado | Ninguno       | Sintaxis SimpleEval |
| `--gc-first`       | Ejecuta GC antes de escanear | `False`   | -                |

**Reglas de resolución de type**:

- Tipos incorporados: `str`, `int`, `list`, `dict`, `set`, `tuple`, `bytes`, `bool`, `float`
- Tipos personalizados: `module.ClassName` (el módulo debe estar cargado)
- **No soporta** importación dinámica de módulos

### Parámetros de operación count

| Parámetro          | Descripción         | Valor por defecto |
|--------------------|---------------------|------------------|
| `--type`           | Nombre del tipo     | -                |
| `--filter-express` | Expresión de filtrado | Ninguno       |
| `--gc-first`       | Ejecuta GC antes de escanear | `False`   |

**Nota especial**: La operación `count` **recorre todos** los objetos (sin límite), solo cuenta no almacena objetos, el sobrecoste de memoria es extremadamente pequeño.

### Expresión de Filtrado

La expresión de filtrado usa el evaluador seguro **SimpleEval**, la sintaxis soportada es:

| Sintaxis      | Descripción                                  | Ejemplo                            |
|---------------|----------------------------------------------|------------------------------------|
| `obj.*` | Atributo de objeto                              | `obj.value`                       |
| Comparación    | `>`, `<`, `==`, `!=`                | `obj.age > 18`                |
| Lógica         | `and`, `or`, `not`                  | `obj.active and obj.age > 18` |
| Aritmética     | `+`, `-`, `*`, `/`                  | `obj.score * 2 > 100`         |
| Llamada a función | `len()`, `str()`, `int()`, `bool()` | `len(obj.items) > 0`          |

**Restricciones de seguridad**:

- ❌ Prohíbe `eval()`, `exec()`, `compile()`
- ❌ Prohíbe `__import__`, `open()`, `__class__`
- ❌ Prohíbe acceder a atributos privados (`__*__`)

**Manejo de errores**:

- Error de sintaxis: **todo el comando falla**
- Error en tiempo de ejecución (como atributo no existe): **salta este objeto**

---

## Formato de Salida

### Respuesta get

```json
{
  "status": "success",
  "action": "get",
  "target": "sys.version",
  "type": "str",
  "value": "3.14.2 (main, Jan  1 2026, 10:00:00) [GCC 11.4.0]"
}
```

| Campo       | Descripción                     |
|-------------|---------------------------------|
| `status`    | Estado: `success` o `error`     |
| `action`    | Tipo de operación                |
| `target`    | Ruta objetivo consultada          |
| `type`      | Nombre del tipo del valor         |
| `value`     | Valor del atributo (límite de profundidad) |

### Respuesta instances

```json
{
  "status": "success",
  "action": "instances",
  "class_name": "list",
  "count": 5,
  "limit": 10,
  "truncated": false,
  "instances": [
    {
      "type": "list",
      "value": [
        1,
        2,
        3
      ]
    },
    {
      "type": "list",
      "value": [
        "a",
        "b"
      ]
    }
  ]
}
```

| Campo           | Descripción                           |
|----------------|---------------------------------------|
| `class_name`   | Tipo consultado                        |
| `count`        | Número de instancias devueltas (`== len(instances)`) |
| `limit`        | Límite de número solicitado                      |
| `truncated`    | ¿Hay más instancias (`true`/`false`)      |
| `instances`    | Arreglo de instancias (límite de profundidad)                   |

**Significado de truncated**:

- `true`: Hay más instancias coincident en el montículo (número desconocido)
- `false`: Se han devuelto todas las instancias coincident rastreadas por GC

### Respuesta count

```json
{
  "status": "success",
  "action": "count",
  "class_name": "list",
  "count": 240
}
```

| Campo           | Descripción         |
|----------------|---------------------|
| `class_name`   | Tipo consultado      |
| `count`        | Número total de instancias rastreadas por GC |

### Respuesta error

```json
{
  "status": "error",
  "action": "get",
  "error": "Cannot resolve target: Module 'nonexistent' not loaded in target process"
}
```

---

## Ejemplos de Uso

### Ejemplo 1: Ver información del sistema

```bash
# Ver versión de Python
peeka inspect --action get --target "sys.version"

# Ver sys.path
peeka inspect --action get --target "sys.path" --depth 3
```

**Salida**:

```json
{
  "status": "success",
  "action": "get",
  "target": "sys.path",
  "type": "list",
  "value": [
    "/usr/lib/python3.14",
    "/home/user/project",
    "... (truncated)"
  ]
}
```

### Ejemplo 2: Ver valor de configuración

```bash
# Ver configuración de la aplicación
peeka inspect --action get --target "myapp.config.DEBUG"

# Ver constante de clase
peeka inspect --action get --target "myapp.Database.POOL_SIZE"
```

### Ejemplo 3: Resolución de fuga de memoria

```bash
# Encontrar todas las instancias de User
peeka inspect --action instances --type myapp.User --limit 20

# Filtrar usuarios activos
peeka inspect --action instances --type myapp.User \
  --filter-express "obj.active == True" --limit 10

# Filtrar objetos grandes
peeka inspect --action instances --type list \
  --filter-express "len(obj) > 100" --limit 5
```

**Salida**:

```json
{
  "status": "success",
  "action": "instances",
  "class_name": "myapp.User",
  "count": 20,
  "limit": 20,
  "truncated": true,
  "instances": [
    {
      "type": "myapp.User",
      "value": "<User(id=1, name='Alice', active=True)>"
    }
  ]
}
```

### Ejemplo 4: Estadísticas de objetos

```bash
# Contar todas las instancias de list
peeka inspect --action count --type list

# Contar instancias de dict
peeka inspect --action count --type dict

# Contar objetos que cumplen condiciones específicas
peeka inspect --action count --type myapp.Connection \
  --filter-express "obj.closed == False"
```

**Salida**:

```json
{
  "status": "success",
  "action": "count",
  "class_name": "list",
  "count": 240
}
```

### Ejemplo 5: Uso combinado con jq

```bash
# Extraer campo value
peeka inspect --action get --target "sys.version" | jq -r '.value'

# Contar número de instancias
peeka inspect --action count --type list | jq '.count'

# Hermosquear salida
peeka inspect --action instances --type dict --limit 3 | jq .
```

---

## Flujo Completo de Diagnóstico

### Escenario: Resolución de fuga de memoria

**Problema**: La memoria en entorno de producción sigue creciendo, se sospecha que las instancias de alguna clase no se liberan.

**Paso 1: Contar número de objetos**

```bash
# Contar periódicamente el tipo sospechoso
peeka inspect --action count --type myapp.Cache
# Salida: {"count": 1500}

# Después de 5 minutos vuelve a contar
peeka inspect --action count --type myapp.Cache
# Salida: {"count": 1800}  ← ¡Sigue creciendo!
```

**Paso 2: Ver muestra de instancias**

```bash
# Obtener las primeras 10 instancias
peeka inspect --action instances --type myapp.Cache --limit 10 | jq .

# Ver objetos grandes
peeka inspect --action instances --type myapp.Cache \
  --filter-express "len(obj.data) > 1000" --limit 5
```

**Paso 3: Verificar configuración**

```bash
# Ver configuración de caché
peeka inspect --action get --target "myapp.cache_config.MAX_SIZE"
# ¡Descubres que MAX_SIZE no tiene efecto!
```

**Paso 4: Verificar reparación**

Después de reparar el código y volver a desplegar, vuelve a contar:

```bash
peeka inspect --action count --type myapp.Cache
# Salida: {"count": 100}  ← Vuelve a la normalidad
```

---

## Notas

### ⚠️ Restricciones de rastreo de GC

`gc.get_objects()` **solo devuelve objetos rastreados por GC**:

| Tipo                              | ¿Se rastrea? | Resultado instances/count |
|-----------------------------------|--------------|--------------------------|
| `list`, `dict`, `set`, `tuple` | ✅ Sí        | Confiable                |
| Instancias de clases personalizadas | ✅ Sí        | Confiable                |
| `str`, `int`, `float`, `bytes` | ❌ No        | Puede ser 0 o incompleto  |

**Recomendaciones**:

- Resolución de fugas de memoria: Prioriza **tipos contenedores** o **clases personalizadas**
- Contar cadenas/enteros: El resultado **no es confiable**, solo para referencia

### ⚠️ Reglas de resolución de Target

El parámetro `--target` usa la cadena de `getattr()`, **no soporta claves de diccionario**:

```bash
# ❌ Error: no soporta sintaxis de clave de diccionario
peeka inspect --action get --target 'config["debug"]'

# ✅ Correcto: Primero obtén el diccionario, verifica manualmente
peeka inspect --action get --target "config" | jq '.value.debug'
```

### ⚠️ Restricciones de carga de módulos

El parámetro `--type` **no importa dinámicamente módulos**:

```bash
# ❌ Error: La consulta falla cuando myapp no está cargado
peeka inspect --action instances --type myapp.User

# ✅ Correcto: Asegúrate de que el módulo myapp ya está importado en el proceso objetivo
# (debe haber un import myapp en el código objetivo)
```

### ⚠️ Impacto en el rendimiento

| Operación      | Recorre el montículo            | Impacto en el rendimiento         |
|---------------|-------------------------------|----------------------------------|
| `get`         | ❌ No                         | Extremadamente bajo (< 1ms)    |
| `instances`   | ✅ Parcial (hasta el límite) | Medio (10-100ms) |
| `count`       | ✅ Completo                    | Alto (50-500ms) |

**Recomendaciones**:

- La operación `count` puede tardar más en procesos con mucha memoria
- En entorno de producción presta atención a la frecuencia, evita afectar el rendimiento

### ⚠️ Seguridad de expresión de filtrado

La expresión de filtrado usa **SimpleEval** para prevenir inyección de código:

```bash
# ✅ Seguro: operaciones permitidas por SimpleEval
peeka inspect --action instances --type myapp.User \
  --filter-express "obj.age > 18 and obj.active"

# ❌ Prohibido: ataque de inyección de código
peeka inspect --action instances --type myapp.User \
  --filter-express "__import__('os').system('rm -rf /')"
# Error: Invalid filter expression: __import__ not allowed
```

---

## Preguntas Frecuentes

### P1: instances devuelve count: 0, pero estoy seguro que hay objetos

**R**: Puede ser por las siguientes razones:

1. **El objeto no es rastreado por GC** (como `str`, `int`)
   ```bash
   # str/int puede no ser confiable
   peeka inspect --action count --type str  # Puede ser 0

   # Mejor usa tipos contenedores
   peeka inspect --action count --type list  # Confiable
   ```

2. **Módulo no cargado**
   ```bash
   # Confirma que el módulo está importado
   peeka inspect --action get --target "list(sys.modules.keys())" | grep myapp
   ```

3. **filter-express filtró todos los objetos**
   ```bash
   # Prueba primero sin filtro
   peeka inspect --action instances --type myapp.User --limit 5
   ```

### P2: La consulta target falló "Module not loaded"

**R**: El módulo objetivo no está importado en el proceso.

**Solución**:

```bash
# Verifica módulos cargados
peeka inspect --action get --target "list(sys.modules.keys())" | grep myapp

# Si el módulo no está cargado, necesitas agregar un import en el código objetivo
```

### P3: Error de sintaxis en filter-express

**R**: SimpleEval solo soporta sintaxis limitada.

**Errores comunes**:

```bash
# ❌ No soporta comprensión de listas
--filter-express "[x for x in obj.items]"

# ✅ Usa len() en su lugar
--filter-express "len(obj.items) > 0"

# ❌ No soporta sintaxis de clave de diccionario
--filter-express "obj['key'] > 0"

# ✅ Usa sintaxis de atributos
--filter-express "obj.key > 0"
```

### P4: La operación count es muy lenta

**R**: `count` recorre todo el montículo, es más lento cuando hay muchos objetos.

**Sugerencias de optimización**:

```bash
# Usa instances en su lugar (con limit)
peeka inspect --action instances --type list --limit 10

# O ejecuta count durante el período de baja carga empresarial
```

### P5: truncated de instances siempre es true

**R**: Indica que las instancias coincidentes exceden el `limit`.

**Solución**:

```bash
# Aumenta el límite (máximo 1000)
peeka inspect --action instances --type list --limit 1000

# O usa un filtro para reducir el alcance
peeka inspect --action instances --type list \
  --filter-express "len(obj) > 100" --limit 10
```

---

## Técnicas Avanzadas

### Técnica 1: Monitoreo periódico del número de objetos

```bash
#!/bin/bash
# monitor_objects.sh - Monitorear cambios en el número de objetos

PID=12345
TYPE="myapp.Connection"

while true; do
  COUNT=$(peeka inspect --action count --type $TYPE | jq '.count')
  echo "$(date): $TYPE count = $COUNT"
  sleep 60
done
```

### Técnica 2: Usar get y instances en combinación

```bash
# Primero consulta la configuración
CONFIG=$(peeka inspect --action get --target "myapp.config.MAX_CONNECTIONS" | jq '.value')

# Luego cuenta el número real de conexiones
ACTUAL=$(peeka inspect --action count --type myapp.Connection | jq '.count')

# Compara
echo "Configuración: $CONFIG, Real: $ACTUAL"
```

### Técnica 3: Usar gc-first para obtener conteo exacto

```bash
# Antes de GC
peeka inspect --action count --type myapp.Cache
# Salida: {"count": 1500}

# Después de forzar GC
peeka inspect --action count --type myapp.Cache --gc-first
# Salida: {"count": 1200}  ← Se limpiaron objetos no referenciados
```

### Técnica 4: Expresiones de filtrado complejas

```bash
# Filtrado de múltiples condiciones
peeka inspect --action instances --type myapp.User \
  --filter-express "obj.age > 18 and obj.active and len(obj.name) > 0" \
  --limit 10

# Operaciones aritméticas
peeka inspect --action instances --type myapp.Score \
  --filter-express "obj.math + obj.english > 180" \
  --limit 5
```

### Técnica 5: Exportar para análisis

```bash
# Exportar instances a un archivo
peeka inspect --action instances --type myapp.User --limit 100 > users.json

# Análisis offline
jq '.instances | map(.value.age) | add / length' users.json  # Promedio de edad
jq '.instances | map(select(.value.active == true)) | length' users.json  # Número de usuarios activos
```

---

## Resumen

### Funcionalidades Centrales

| Operación         | Uso                     | Rendimiento | Recorre montículo |
|-------------------|-------------------------|-------------|------------------|
| **get**           | Ver atributo/configuración | Muy rápido | ❌   |
| **instances**     | Resolución de memoria    | Medio       | Parcial  |
| **count**         | Estadísticas de objetos    | Lento       | Completo  |

### Flujo Típico de Uso

1. **Verificación rápida**: `get` ver configuración y estado
2. **Evaluación de cantidad**: `count` cuenta número de objetos
3. **Análisis detallado**: `instances` obtiene muestra de instancias
4. **Filtrado y selección**: `--filter-express` reduce el alcance

### Mejores Prácticas

✅ **Recomendado**:

- Usa tipos contenedores (list, dict) para instances/count
- Combina jq para procesar salida JSON
- Monitorea periódicamente el número de objetos clave
- Usa expresiones de filtrado para localizar problemas con precisión

❌ **Evitar**:

- Ejecuta count frecuentemente (impacto en el rendimiento)
- Usa instances para str/int (no es confiable)
- Usa lógica compleja en expresiones de filtrado
- Olvida verificar si el módulo ya está cargado

### Comandos Relacionados

- `memory` - Análisis y rastreo de memoria
- `sc` - Buscar clases
- `sm` - Buscar métodos
