---
layout: default
title: búsqueda
parent: Referencia de Comandos
nav_order: 9
---

# Comando `sc` / `sm` - Búsqueda de Clases y Métodos
{: .no_toc }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Introducción

Los comandos `sc` (Search Class) y `sm` (Search Method) se usan para **buscar clases y métodos en un proceso Python en ejecución**, ayudando a los desarrolladores a entender rápidamente la estructura del código, descubrir APIs disponibles y localizar funciones objetivo.

**Funcionalidades Principales**:
- **sc**: Buscar clases en módulos cargados
- **sm**: Buscar métodos dentro de clases
- Soporte para coincidencia de patrones con comodines (`*`, `?`)
- Mostrar información detallada de clases/métodos (ruta de archivo, docstrings, etc.)
- Límite de resultados (evita salida excesiva)
- Ideal para exploración de código y análisis dinámico

**Escenarios Típicos**:
- Explorar bases de código desconocidas (descubrir qué clases y métodos existen)
- Encontrar la implementación de funcionalidades específicas (buscar todas las clases `*Handler`)
- Obtener firmas de funciones (para usar con los comandos `watch`, `stack`, etc.)
- Verificar si un módulo está cargado
- Aprender APIs de bibliotecas de terceros

## Uso en TUI

**Nota**: Los comandos de búsqueda (sc/sm) **no tienen una vista dedicada en TUI**, pero se pueden ejecutar a través del cuadro de entrada de comandos:

- Presiona `:` en la interfaz principal de TUI para entrar en modo comando
- Ingresa `sc <patrón>` o `sm <patrón-clase>` para ejecutar la búsqueda
- Los resultados se muestran en el área de salida de comandos

**Operaciones Comunes**:
- Comando sc: `: sc "myapp.*" -d --limit 20`
- Comando sm: `: sm "myapp.User" --method-pattern "get*"`

**Recomendación**: Los comandos de búsqueda se usan principalmente para exploración de código, se recomienda usar el modo CLI para facilitar el uso de tuberías y filtrado de resultados.

**Comandos CLI equivalentes**: Todos los ejemplos a continuación usan comandos CLI para demostración.
---

## Escenarios de Uso

### 1. Explorar una Base de Código Desconocida

**Escenario**: Has tomado un proyecto nuevo y necesitas entender rápidamente su estructura.

```bash
# Ver todas las clases de la aplicación (asumiendo que el módulo se llama myapp)
peeka-cli sc "myapp.*"

# Salida:
# myapp.api.UserHandler
# myapp.api.OrderHandler
# myapp.models.User
# myapp.models.Order
# myapp.utils.Helper
```

**Propósito**: Entender rápidamente qué módulos y clases tiene el proyecto.

### 2. Encontrar una Funcionalidad Específica

**Escenario**: Necesitas encontrar todas las clases manejadoras (Handler).

```bash
# Buscar todas las clases que terminan con Handler
peeka-cli sc "*Handler"

# Salida:
# myapp.api.UserHandler
# myapp.api.OrderHandler
# myapp.api.PaymentHandler
```

### 3. Obtener la Firma de un Método

**Escenario**: Quieres usar el comando `watch` para monitorear un método, pero no conoces su firma completa.

```bash
# Paso 1: Buscar la clase
peeka-cli sc "myapp.api.UserHandler"

# Paso 2: Buscar todos los métodos de la clase
peeka-cli sm "myapp.api.UserHandler.*"

# Salida:
# get (self, user_id: int) -> dict
# create (self, **data) -> dict
# update (self, user_id: int, **data) -> bool
# delete (self, user_id: int) -> bool

# Paso 3: Usar watch para monitorear
peeka-cli watch "myapp.api.UserHandler.get"
```

### 4. Verificar si un Módulo está Cargado

**Escenario**: Sospechas que un módulo no se ha cargado y por eso la funcionalidad no funciona.

```bash
# Buscar clases del módulo objetivo
peeka-cli sc "myapp.plugins.payment.*"

# Si la salida está vacía, el módulo no está cargado
# Si hay salida, el módulo ya está cargado
```

### 5. Aprender APIs de Bibliotecas de Terceros

**Escenario**: Quieres saber qué clases y métodos tiene la biblioteca `requests`.

```bash
# Ver todas las clases del módulo requests
peeka-cli sc "requests.*" -d

# Ver todos los métodos de la clase Session
peeka-cli sm "requests.Session.*"

# Salida:
# get (self, url, **kwargs) -> Response
# post (self, url, data=None, json=None, **kwargs) -> Response
# put (self, url, data=None, **kwargs) -> Response
# ...
```

---

## Formato del Comando

### sc - Buscar Clases

```bash
# Primero debes adjuntar al proceso objetivo
peeka-cli attach <pid>

# Luego ejecutar el comando sc
peeka-cli sc <pattern> [options]
```

**Parámetros Requeridos**:
- `pattern`: Patrón de clase (soporta comodines)

**Parámetros Opcionales**:
- `-d, --detail`: Mostrar información detallada (ruta de archivo, docstring)
- `--limit`: Límite de resultados (predeterminado 50)

### sm - Buscar Métodos

```bash
# Primero debes adjuntar al proceso objetivo
peeka-cli attach <pid>

# Luego ejecutar el comando sm
peeka-cli sm <class_pattern> [options]
```

**Parámetros Requeridos**:
- `class_pattern`: Patrón de clase (soporta comodines)

**Parámetros Opcionales**:
- `--method-pattern`: Patrón de método (predeterminado `*`, coincide todos los métodos)
- `-d, --detail`: Mostrar información detallada (módulo, docstring)

---

## Comando sc - Buscar Clases

### Uso Básico

```bash
# Buscar una clase específica
peeka-cli sc "myapp.User"

# Buscar todas las clases bajo un módulo
peeka-cli sc "myapp.models.*"

# Buscar todas las clases que terminan con Handler
peeka-cli sc "*Handler"

# Mostrar información detallada
peeka-cli sc "myapp.models.*" -d
```

### Campos de Salida

**Modo Básico** (sin `-d`):
```json
{
  "status": "success",
  "classes": [
    {"name": "myapp.models.User"},
    {"name": "myapp.models.Order"}
  ],
  "count": 2,
  "limit": 50
}
```

**Modo Detallado** (con `-d`):
```json
{
  "status": "success",
  "classes": [
    {
      "name": "myapp.models.User",
      "module": "myapp.models",
      "file": "/app/myapp/models.py",
      "docstring": "User model class representing a system user."
    }
  ],
  "count": 1,
  "limit": 50
}
```

### Ejemplos de Patrones

| Patrón | Ejemplo de Coincidencia | Descripción |
|---------|----------|------|
| `json.*` | `json.JSONEncoder`, `json.JSONDecoder` | Todas las clases en el módulo json |
| `myapp.models.*` | `myapp.models.User`, `myapp.models.Order` | Todas las clases en el módulo myapp.models |
| `*Handler` | `UserHandler`, `OrderHandler` | Todas las clases que terminan con Handler |
| `*Command` | `WatchCommand`, `StackCommand` | Todas las clases que terminan con Command |
| `collections.Ordered*` | `collections.OrderedDict` | Clases que empiezan con Ordered en el módulo collections |

---

## Comando sm - Buscar Métodos

### Uso Básico

```bash
# Buscar todos los métodos de una clase
peeka-cli sm "myapp.User.*"

# Escritura equivalente (usando --method-pattern)
peeka-cli sm "myapp.User" --method-pattern "*"

# Buscar un método específico
peeka-cli sm "myapp.User.get"

# Buscar métodos que empiezan con get_
peeka-cli sm "myapp.User" --method-pattern "get_*"

# Mostrar información detallada
peeka-cli sm "myapp.User.*" -d
```

### Campos de Salida

**Modo Básico** (sin `-d`):
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict"
    },
    {
      "name": "create",
      "signature": "(self, **data) -> dict"
    }
  ],
  "count": 2,
  "limit": 50
}
```

**Modo Detallado** (con `-d`):
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict",
      "module": "myapp.models",
      "class": "User",
      "docstring": "Get user by ID.\n\nArgs:\n    user_id: User ID\n\nReturns:\n    User dict or None"
    }
  ],
  "count": 1,
  "limit": 50
}
```

### Ejemplos de Combinación de Patrones

| Patrón de Clase | Patrón de Método | Ejemplo de Coincidencia |
|---------------|----------------|----------|
| `myapp.User` | `*` | Todos los métodos de la clase User |
| `myapp.User` | `get*` | `get`, `get_by_id`, `get_all` |
| `myapp.User` | `*_by_id` | `get_by_id`, `delete_by_id` |
| `myapp.*Handler` | `handle` | El método handle de todas las clases Handler |
| `json.JSONEncoder` | `encode*` | `encode`, `encode_object` |

---

## Sintaxis de Patrones

### Comodines Soportados

| Comodín | Descripción | Ejemplo |
|--------|------|------|
| `*` | Coincide cualquier longitud de caracteres (incluyendo vacío) | `myapp.*` coincide con `myapp.User`, `myapp.Order` |
| `?` | Coincide un solo carácter | `User?` coincide con `User1`, `User2` |
| `[seq]` | Coincide cualquier carácter en seq | `User[12]` coincide con `User1`, `User2` |
| `[!seq]` | Coincide cualquier carácter que no esté en seq | `User[!0]` coincide con `User1`, `User2` (no coincide `User0`) |

### Tipos de Patrones

#### 1. Nombre Completo Cualificado

```bash
# Coincidencia exacta
peeka-cli sc "myapp.models.User"
peeka-cli sm "myapp.models.User.get"
```

#### 2. Comodines a Nivel de Módulo

```bash
# Todas las clases bajo el módulo
peeka-cli sc "myapp.models.*"

# Comodines multinivel
peeka-cli sc "myapp.*.User"  # Clase User en cualquier submódulo de myapp
```

#### 3. Comodines en Nombres de Clase

```bash
# Coincidencia por prefijo
peeka-cli sc "*Handler"       # Todas las clases Handler
peeka-cli sc "myapp.*Handler" # Todas las clases Handler bajo myapp

# Coincidencia por sufijo
peeka-cli sc "User*"          # User, UserHandler, UserModel

# Coincidencia por medio
peeka-cli sc "*User*"         # UserHandler, AdminUser, User
```

#### 4. Comodines en Nombres de Métodos

```bash
# Patrón de método para el comando sm
peeka-cli sm "myapp.User" --method-pattern "get*"
peeka-cli sm "myapp.User" --method-pattern "*_by_id"
peeka-cli sm "myapp.User" --method-pattern "is_*"
```

---

## Formato de Salida

### Salida del Comando sc

**Modo Básico**:
```json
{
  "status": "success",
  "classes": [
    {"name": "myapp.models.User"},
    {"name": "myapp.models.Order"},
    {"name": "myapp.api.UserHandler"}
  ],
  "count": 3,
  "limit": 50
}
```

**Modo Detallado** (`-d`):
```json
{
  "status": "success",
  "classes": [
    {
      "name": "myapp.models.User",
      "module": "myapp.models",
      "file": "/app/myapp/models.py",
      "docstring": "User model representing a system user.\n\nAttributes:\n    id: User ID\n    username: Username"
    }
  ],
  "count": 1,
  "limit": 50
}
```

### Salida del Comando sm

**Modo Básico**:
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict"
    },
    {
      "name": "create",
      "signature": "(self, **data) -> dict"
    },
    {
      "name": "update",
      "signature": "(self, user_id: int, **data) -> bool"
    }
  ],
  "count": 3,
  "limit": 50
}
```

**Modo Detallado** (`-d`):
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict",
      "module": "myapp.models",
      "class": "User",
      "docstring": "Get user by ID.\n\nArgs:\n    user_id: User ID\n\nReturns:\n    User dict or None if not found"
    }
  ],
  "count": 1,
  "limit": 50
}
```

---

## Ejemplos de Uso

### Ejemplo 1: Encontrar Todas las Clases de Modelo de la Aplicación

```bash
peeka-cli sc "myapp.models.*" | jq -r '.classes[].name'
```

**Salida**:
```
myapp.models.User
myapp.models.Order
myapp.models.Product
myapp.models.Payment
```

### Ejemplo 2: Encontrar Todas las Clases Handler y Obtener Información Detallada

```bash
peeka-cli sc "*Handler" -d | jq .
```

**Salida**:
```json
{
  "status": "success",
  "classes": [
    {
      "name": "myapp.api.UserHandler",
      "module": "myapp.api",
      "file": "/app/myapp/api.py",
      "docstring": "Handles user-related API requests."
    },
    {
      "name": "myapp.api.OrderHandler",
      "module": "myapp.api",
      "file": "/app/myapp/api.py",
      "docstring": "Handles order-related API requests."
    }
  ],
  "count": 2
}
```

### Ejemplo 3: Encontrar Todos los Métodos de una Clase

```bash
peeka-cli sm "myapp.User.*" | jq -r '.methods[] | "\(.name)\(.signature)"'
```

**Salida**:
```
get(self, user_id: int) -> dict
create(self, **data) -> dict
update(self, user_id: int, **data) -> bool
delete(self, user_id: int) -> bool
is_active(self) -> bool
```

### Ejemplo 4: Encontrar Todos los Métodos que Empiezan con get_

```bash
peeka-cli sm "myapp.User" --method-pattern "get_*" | jq -r '.methods[].name'
```

**Salida**:
```
get_by_id
get_by_username
get_all
get_active_users
```

### Ejemplo 5: Explorar una Biblioteca de Terceros (requests)

```bash
# Ver qué clases tiene el módulo requests
peeka-cli sc "requests.*" | jq -r '.classes[].name'

# Salida:
# requests.Session
# requests.Response
# requests.Request
# requests.PreparedRequest

# Ver métodos de la clase Session
peeka-cli sm "requests.Session" --method-pattern "*" | \
  jq -r '.methods[] | "\(.name)\(.signature)"'

# Salida:
# get(self, url, **kwargs) -> Response
# post(self, url, data=None, json=None, **kwargs) -> Response
# ...
```

### Ejemplo 6: Combinar con el Comando watch

**Escenario**: Después de encontrar el método objetivo, usa `watch` para monitorear.

```bash
# Paso 1: Buscar todos los métodos de procesamiento de órdenes
peeka-cli sm "myapp.Order" --method-pattern "*process*"

# Salida:
# process_payment
# process_refund
# process_shipment

# Paso 2: Seleccionar el método objetivo y monitorear
peeka-cli watch "myapp.Order.process_payment" -n 10
```

---

## Flujos de Trabajo Completos

### Flujo 1: Explorar una Base de Código Desconocida

**Objetivo**: Entender rápidamente la estructura del proyecto y las clases principales.

```bash
# Paso 1: Listar todas las clases de los módulos de la aplicación
peeka-cli sc "myapp.*" > classes.json

# Paso 2: Agrupar por módulo y contar
jq -r '.classes[].name | split(".") | .[0:2] | join(".")' classes.json | \
  sort | uniq -c

# Salida:
#   12 myapp.api
#    8 myapp.models
#    5 myapp.utils
#    3 myapp.services

# Paso 3: Ver clases detalladas de cada módulo
peeka-cli sc "myapp.api.*" -d | \
  jq -r '.classes[] | "\(.name)\n  \(.docstring)\n"'
```

### Flujo 2: Localizar la Implementación de una Funcionalidad Específica

**Objetivo**: Encontrar todas las clases y métodos que implementan la funcionalidad de pago.

```bash
# Paso 1: Buscar todas las clases relacionadas con payment
peeka-cli sc "*payment*" -d

# Paso 2: Después de encontrar la clase objetivo, ver sus métodos
peeka-cli sm "myapp.payment.PaymentProcessor.*" -d

# Paso 3: Ver información detallada de un método específico
peeka-cli sm "myapp.payment.PaymentProcessor.charge" -d | \
  jq -r '.methods[0].docstring'
```

### Flujo 3: Verificar Refactorización de Código

**Objetivo**: Después de refactorizar, verificar si las clases antiguas fueron eliminadas y las nuevas cargadas.

```bash
# Paso 1: Buscar la clase antigua (no debería encontrarla)
peeka-cli sc "myapp.OldUserHandler"
# Salida: {"status":"success","classes":[],"count":0}

# Paso 2: Buscar la clase nueva (debería encontrarla)
peeka-cli sc "myapp.NewUserHandler" -d

# Paso 3: Comparar métodos de clases nuevas y antiguas
peeka-cli sm "myapp.NewUserHandler.*" > new_methods.json
# Compara old_methods.json y new_methods.json
```

### Flujo 4: Aprender API de una Biblioteca de Terceros

**Objetivo**: Aprender las clases y métodos principales del framework Flask.

```bash
# Paso 1: Ver qué clases tiene Flask
peeka-cli sc "flask.*" | jq -r '.classes[].name'

# Salida:
# flask.Flask
# flask.Blueprint
# flask.Request
# flask.Response

# Paso 2: Ver todos los métodos de la clase Flask
peeka-cli sm "flask.Flask.*" | \
  jq -r '.methods[] | "\(.name)\(.signature)"'

# Paso 3: Ver documentación de un método específico
peeka-cli sm "flask.Flask.route" -d | \
  jq -r '.methods[0].docstring'
```

---

## Notas Importantes

### 1. Solo se Puede Buscar en Módulos Cargados

**Importante**: Los comandos `sc` y `sm` **solo pueden buscar en módulos que ya han sido importados**.

```bash
# Si el módulo myapp.plugin no ha sido importado, no se encontrará
peeka-cli sc "myapp.plugin.*"
# Salida: {"classes": [], "count": 0}
```

**Solución**:
- Activa la funcionalidad para que el módulo sea importado (ej: accede a la API relacionada)
- O verifica en el código que el módulo efectivamente será importado

### 2. Los Métodos Mágicos no se Muestran por Defecto

**Comportamiento Predeterminado**: El comando `sm` no muestra métodos mágicos (`__init__`, `__str__`, etc.).

```bash
# No mostrará __init__, __str__, __repr__, etc.
peeka-cli sm "myapp.User.*"
```

**Razón**: Los métodos mágicos usualmente no son puntos de entrada a la lógica de negocio, filtrarlos reduce el ruido.

### 3. Límite de Cantidad de Resultados

**Límite Predeterminado**: Máximo 50 resultados son devueltos.

```bash
# Si hay más de 50 coincidencias, solo se devuelven las primeras 50
peeka-cli sc "*" --limit 50
```

**Ajustar el Límite**:
```bash
# Aumentar el límite a 200
peeka-cli sc "*" --limit 200
```

**Notas**:
- Un límite demasiado grande puede causar salida excesiva y disminución del rendimiento
- Se recomienda usar patrones más específicos en lugar de aumentar el límite

### 4. La Ruta del Archivo Puede ser None

**Razón**: Algunas clases (como clases integradas, extensiones C) no tienen un archivo Python correspondiente.

```bash
peeka-cli sc "builtins.dict" -d

# Salida:
# {"name": "builtins.dict", "file": null, ...}
```

### 5. La Firma Puede no ser Obtenible

**Razón**: Algunos métodos (como extensiones C, builtins) no pueden obtener la firma a través de `inspect.signature()`.

```bash
peeka-cli sm "builtins.dict.get"

# Salida:
# {"name": "get", "signature": null}
```

### 6. Impacto en el Rendimiento

**Grado de Impacto**:
- Los comandos `sc` y `sm` iteran sobre `sys.modules`, pueden necesitar algunos cientos de milisegundos
- Cuantos más resultados, más tiempo de salida
- En general, el impacto en el rendimiento es despreciable (operación de una sola vez)

**Recomendaciones**:
- Usa patrones específicos para reducir el rango de búsqueda
- Evita llamadas frecuentes (como en un bucle)

---

## Preguntas Frecuentes

### P1: ¿Por qué no se encuentra una clase?

**Posibles Causas**:
1. **Módulo no importado**: El módulo que contiene la clase no ha sido cargado en memoria
2. **Patrón incorrecto**: El patrón no coincide con el nombre completo cualificado de la clase
3. **Resultado supera el límite**: La cantidad de resultados supera `--limit`

**Métodos de Diagnóstico**:
```bash
# Método 1: Verificar si el módulo ya está importado
python3 -c "import sys; print('myapp.models' in sys.modules)"

# Método 2: Usa un patrón más flexible
peeka-cli sc "*User*"

# Método 3: Aumenta el límite
peeka-cli sc "myapp.*" --limit 200
```

### P2: ¿Cómo buscar todas las clases en todos los módulos?

**Respuesta**: Usa el comodín `*`.

```bash
peeka-cli sc "*" --limit 200
```

**Advertencia**:
- La cantidad de resultados puede ser muy grande (incluye biblioteca estándar y bibliotecas de terceros)
- Se recomienda usar patrones más específicos

### P3: ¿Por qué el comando sm no muestra el método __init__?

**Razón**: Los métodos mágicos son filtrados por defecto.

**Si necesitas ver métodos mágicos**:
- La versión actual no soporta (futuramente se puede agregar el parámetro `--show-magic`)
- Puedes usar código Python para verlos:
  ```python
  import inspect
  print([m for m in dir(MyClass) if m.startswith('__')])
  ```

### P4: ¿Cómo buscar métodos que coincidan tanto por nombre de clase como por nombre de método?

**Método**: Usa la combinación de dos parámetros del comando `sm`.

```bash
# Buscar el método handle en todas las clases Handler
# Nota: Necesitas conocer el nombre del módulo específico
peeka-cli sm "myapp.api.*Handler" --method-pattern "handle"
```

**Restricción**: `class_pattern` debe incluir el nombre del módulo, no puede usar solo `*Handler`.

### P5: ¿Cómo exportar los resultados de búsqueda a un archivo?

**Método**: Usa redireccionamiento o `jq`.

```bash
# Exportar todas las clases a un archivo
peeka-cli sc "myapp.*" > classes.json

# Exportar lista de nombres de clases (texto plano)
peeka-cli sc "myapp.*" | jq -r '.classes[].name' > class_names.txt

# Exportar tabla de firmas de métodos
peeka-cli sm "myapp.User.*" | \
  jq -r '.methods[] | "\(.name)\(.signature)"' > user_methods.txt
```

### P6: ¿Se puede buscar clases de la biblioteca estándar?

**Respuesta**: Sí, siempre y cuando el módulo haya sido importado.

```bash
# Buscar clases del módulo json
peeka-cli sc "json.*"

# Buscar clases del módulo collections
peeka-cli sc "collections.*"

# Buscar clases del módulo logging
peeka-cli sc "logging.*"
```

---

## Técnicas Avanzadas

### 1. Generar Documentación API del Proyecto

**Escenario**: Generar automáticamente una lista de clases y métodos del proyecto.

```bash
#!/bin/bash
# generate_api_doc.sh

PID=12345
OUTPUT="api_documentation.md"

echo "# Documentación API" > $OUTPUT
echo "" >> $OUTPUT

# Obtener todas las clases
classes=$(peeka-cli sc "myapp.*" | jq -r '.classes[].name')

for class in $classes; do
  echo "## $class" >> $OUTPUT
  echo "" >> $OUTPUT

  # Obtener información detallada de la clase
  peeka-cli sc "$class" -d | \
    jq -r '.classes[0].docstring // "Sin descripción"' >> $OUTPUT
  echo "" >> $OUTPUT

  # Obtener todos los métodos de la clase
  echo "### Métodos" >> $OUTPUT
  echo "" >> $OUTPUT
  peeka-cli sm "$class.*" -d | \
    jq -r '.methods[] | "- `\(.name)\(.signature)`\n  \(.docstring // "Sin descripción")\n"' >> $OUTPUT
  echo "" >> $OUTPUT
done

echo "Documentación generada: $OUTPUT"
```

### 2. Script de Verificación de Refactorización

**Escenario**: Después de refactorizar, verificar automáticamente si los métodos de clases nuevas y antiguas son consistentes.

```bash
#!/bin/bash
# verify_refactor.sh

PID=12345
OLD_CLASS="myapp.OldUserHandler"
NEW_CLASS="myapp.NewUserHandler"

# Obtener métodos de la clase antigua
old_methods=$(peeka-cli sm "$OLD_CLASS.*" 2>/dev/null | \
  jq -r '.methods[].name' | sort)

# Obtener métodos de la clase nueva
new_methods=$(peeka-cli sm "$NEW_CLASS.*" | \
  jq -r '.methods[].name' | sort)

# Comparar
if [ "$old_methods" == "$new_methods" ]; then
  echo "✅ PASS: Las firmas de métodos coinciden"
else
  echo "❌ FAIL: Las firmas de métodos difieren"
  echo "Métodos antiguos:"
  echo "$old_methods"
  echo "Métodos nuevos:"
  echo "$new_methods"
fi
```

### 3. Encontrar Métodos Abstractos no Implementados

**Escenario**: Verificar qué clases heredaron de una clase abstracta pero no implementaron todos los métodos abstractos.

```bash
#!/bin/bash
# find_abstract_violations.sh

PID=12345
ABSTRACT_CLASS="myapp.BaseHandler"

# Obtener todos los métodos de la clase abstracta
abstract_methods=$(peeka-cli sm "$ABSTRACT_CLASS.*" | \
  jq -r '.methods[].name' | sort)

# Encontrar todas las subclases
subclasses=$(peeka-cli sc "*Handler" | \
  jq -r '.classes[].name' | grep -v "$ABSTRACT_CLASS")

for subclass in $subclasses; do
  # Obtener métodos de la subclase
  impl_methods=$(peeka-cli sm "$subclass.*" | \
    jq -r '.methods[].name' | sort)

  # Verificar si implementó todos los métodos abstractos
  missing=$(comm -23 <(echo "$abstract_methods") <(echo "$impl_methods"))

  if [ -n "$missing" ]; then
    echo "⚠️  $subclass faltan métodos:"
    echo "$missing"
  fi
done
```

### 4. Exploración de Módulos Importados Dinámicamente

**Escenario**: El módulo objetivo no está cargado, impórtalo y luego busca.

```bash
#!/bin/bash
# explore_module.sh

PID=12345
MODULE="myapp.plugins.experimental"

# Importar el módulo a través de código Python (requiere Python 3.14+ o método GDB)
# Aquí se asume que el módulo será importado al activar alguna funcionalidad

# Esperar a que el módulo se cargue (sondeo)
for i in {1..10}; do
  classes=$(peeka-cli sc "$MODULE.*" | jq -r '.count')
  if [ "$classes" -gt 0 ]; then
    echo "Módulo cargado exitosamente"
    peeka-cli sc "$MODULE.*" -d
    break
  fi
  echo "Esperando a que el módulo se cargue... ($i/10)"
  sleep 2
done
```

### 5. Integración con IDE

**Escenario**: Generar datos de autocompletado disponibles para IDE.

```bash
#!/bin/bash
# generate_autocomplete.sh

PID=12345

# Generar datos de autocompletado en formato JSON
peeka-cli sc "myapp.*" | \
  jq -r '.classes[] | .name' | \
  while read class; do
    peeka-cli sm "$class.*" | \
      jq -r ".methods[] | {class: \"$class\", method: .name, signature: .signature}"
  done | jq -s . > autocomplete_data.json
```

### 6. Monitorear Carga de Módulos

**Escenario**: Monitorear en tiempo real qué nuevos módulos/clases ha cargado la aplicación.

```bash
#!/bin/bash
# monitor_module_loading.sh

PID=12345
INTERVAL=5

# Guardar estado inicial
peeka-cli sc "*" | jq -r '.classes[].name' | sort > initial_classes.txt

while true; do
  sleep $INTERVAL

  # Obtener lista actual de clases
  peeka-cli sc "*" | jq -r '.classes[].name' | sort > current_classes.txt

  # Encontrar clases nuevas agregadas
  new_classes=$(comm -13 initial_classes.txt current_classes.txt)

  if [ -n "$new_classes" ]; then
    echo "[$(date)] Nuevas clases cargadas:"
    echo "$new_classes"
  fi

  cp current_classes.txt initial_classes.txt
done
```

---

## Resumen

Los comandos `sc` y `sm` son herramientas potentes para exploración de código y análisis dinámico, particularmente adecuados para:
- Explorar bases de código desconocidas
- Encontrar la implementación de funcionalidades específicas
- Obtener firmas de métodos (para otros comandos)
- Verificar si módulos están cargados
- Aprender APIs de bibliotecas de terceros

**Mejores Prácticas**:
- Usa patrones específicos para reducir el rango de búsqueda
- Combina con el parámetro `-d` para obtener información detallada
- Usa `jq` para potentes procesamientos de datos
- Combina con los comandos `watch`, `stack`, etc.
- Exporta resultados de búsqueda para análisis posterior

**Siguientes Pasos**:
- Conoce el comando [`watch`](watch) (observar llamadas a funciones)
- Conoce el comando [`stack`](stack) (rastrear pila de llamadas)
- Conoce el comando [`monitor`](monitor) (monitoreo de rendimiento)
- Referente a [Guía para Desarrolladores de Agentes de IA](../ai-skill.md)
