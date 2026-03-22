---
layout: default
title: logger
parent: Referencia de Comandos
nav_order: 6
---

# logger - Ajuste dinámico de nivel de registro
{: .no_toc }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Introducción del Comando

El comando `logger` se usa para ver y ajustar dinámicamente el nivel de registro de aplicaciones Python en tiempo de ejecución, no necesita reiniciar el proceso ni modificar archivos de configuración. Es una herramienta potente para resolver problemas en entornos de producción.

**Funcionalidades principales**:
- Enumera todos los loggers y su nivel de registro actual
- Consulta información de configuración de un logger específico
- Modifica dinámicamente el nivel de registro del logger
- Soporta coincidencia de patrones con comodines para múltiples loggers
- Entra en vigor inmediatamente sin reiniciar el proceso

**Escenarios típicos**:
- Habilitar temporalmente registros DEBUG en entorno de producción para resolver problemas
- Cerrar registros demasiado verbosos de bibliotecas de terceros
- Ajustar dinámicamente el nivel de registro para optimizar el rendimiento
- Diagnosticar problemas de pérdida de registros (verificar configuración del logger)

## Uso en TUI

En modo TUI, presiona la tecla **`7`** para cambiar a la **vista Logger**, proporciona las siguientes funciones interactivas:

- **Visualización de lista de Logger**: Carga y muestra automáticamente todos los loggers y su nivel actual
  - Ordenados por nombre de logger
  - Muestra nombre de logger, nivel actual, valor numérico del nivel
  - Botón de actualización en tiempo real (Refresh)
- **Modificación de nivel**: Después de seleccionar el logger puedes ajustar el nivel rápidamente
  - Soporta DEBUG, INFO, WARNING, ERROR, CRITICAL
  - Entra en vigor inmediatamente después de modificar
- **Filtrado por patrón**: Soporta filtrado de loggers con comodines fnmatch (`*` y `?`)
- **Operaciones rápidas**:
  - Flechas arriba/abajo para seleccionar logger
  - Enter para modificar el nivel del logger seleccionado
  - Presiona `r` para actualizar la lista de loggers

**Equivalente CLI**: Todos los ejemplos a continuación usan comandos CLI para demostrar, TUI proporciona una interfaz gráfica con la misma funcionalidad.

---

## Escenarios de Uso

### 1. Habilitar temporalmente registros de depuración en entorno de producción

**Escenario**: Ocurrió un problema en entorno de producción, necesitas habilitar temporalmente registros DEBUG para resolver el problema, pero no puedes reiniciar el servicio.

```bash
# Paso 1: Ver nivel de registro actual
peeka-cli logger --action get --logger myapp.payment

# Salida:
# {"status": "success", "name": "myapp.payment", "level": "INFO", "level_num": 20}

# Paso 2: Habilitar temporalmente nivel DEBUG
peeka-cli logger --action set --logger myapp.payment --level DEBUG

# Salida:
# {"status": "success", "name": "myapp.payment", "old_level": "INFO", "new_level": "DEBUG"}

# Paso 3: Después de resolver el problema, restaurar el nivel original
peeka-cli logger --action set --logger myapp.payment --level INFO
```

**Efecto**: Entra en vigor inmediatamente, no necesita reiniciar el proceso, el archivo de registro comienza a output información detallada de depuración.

### 2. Cerrar registros verbosos de bibliotecas de terceros

**Escenario**: Bibliotecas de terceros (como urllib3, boto3) output una gran cantidad de registros DEBUG, que inundan los registros de la aplicación.

```bash
# Ver todos los loggers que contienen "urllib3"
peeka-cli logger --action list --pattern "urllib3*"

# Cerrar registros de depuración de urllib3
peeka-cli logger --action set --logger urllib3 --level WARNING

# Tratar boto3 de la misma manera
peeka-cli logger --action set --logger botocore --level WARNING
```

**Efecto**: La biblioteca de terceros solo output registros de nivel WARNING y superior, los registros de la aplicación son claramente visibles.

### 3. Diagnosticar problema de pérdida de registros

**Escenario**: El registro de algún módulo no tiene salida, se sospecha que es un problema de configuración del logger.

```bash
# Paso 1: Verificar si el logger existe
peeka-cli logger --action get --logger myapp.missing_logs

# Si la salida es "Logger not found", indica que el logger no está inicializado
# Si la salida es nivel ERROR, indica que la configuración del nivel de registro es demasiado alta

# Paso 2: Ver todos los loggers, encontrar posiblemente relacionados
peeka-cli logger --action list --pattern "myapp.*"

# Paso 3: Reducir el nivel o crear el logger (el set lo crea automáticamente si no existe)
peeka-cli logger --action set --logger myapp.missing_logs --level DEBUG
```

### 4. Ver en lote niveles de registro de módulos de aplicación

**Escenario**: Verificar si la configuración de registro de todos los módulos de la aplicación cumple con las expectativas.

```bash
# Ver todos los loggers de la aplicación (suponiendo que todos empiezan con "myapp")
peeka-cli logger --action list --pattern "myapp.*" | jq .
```

Salida formateada de lista de loggers, conveniente para verificar la configuración.

### 5. Optimización de rendimiento: Cerrar registros innecesarios

**Escenario**: En entorno de producción se descubre que la E/S de registros se convirtió en el cuello de botella, necesitas cerrar temporalmente algunos registros.

```bash
# Promover el nivel de registro de todos los módulos no centrales a WARNING
peeka-cli logger --action set --logger myapp.analytics --level WARNING
peeka-cli logger --action set --logger myapp.reporting --level WARNING
peeka-cli logger --action set --logger myapp.metrics --level WARNING
```

---

## Formato del Comando

```bash
peeka-cli logger [--action ACTION] [options]
```

**Requerido**:
- Necesitas usar primero `peeka-cli attach <pid>` para adjuntar al proceso objetivo

**Parámetros opcionales**:
- `--action`: Tipo de operación (`list`, `get`, `set`, por defecto `list`)
- `--logger`: Nombre del logger (requerido para acciones `get` y `set`)
- `--level`: Nivel de registro (requerido para acción `set`)
- `--pattern`: Patrón de coincidencia (opcional para acción `list`)

---

## Descripción de las Acciones

### 1. list - Enumerar todos los loggers

**Uso**: Ver todos los loggers inicializados en el proceso y su nivel de registro actual.

**Sintaxis**:
```bash
peeka-cli logger --action list [--pattern <pattern>]
```

**Parámetros**:
- `--pattern` (opcional): Patrón de estilo fnmatch (soporta comodines `*` y `?`)

**Ejemplo**:
```bash
# Enumerar todos los loggers
peeka-cli logger --action list

# Solo enumerar loggers en el espacio de nombres myapp
peeka-cli logger --action list --pattern "myapp.*"

# Enumerar todos los loggers que contienen "db"
peeka-cli logger --action list --pattern "*db*"
```

**Salida**:
```json
{
  "status": "success",
  "loggers": [
    {"name": "myapp.auth", "level": "INFO", "level_num": 20},
    {"name": "myapp.db", "level": "WARNING", "level_num": 30},
    {"name": "myapp.api", "level": "DEBUG", "level_num": 10}
  ],
  "count": 3
}
```

### 2. get - Consultar logger específico

**Uso**: Ver configuración detallada de un logger.

**Sintaxis**:
```bash
peeka-cli logger --action get --logger <name>
```

**Parámetros**:
- `--logger` (requerido): Nombre completo del logger (no soporta comodines)

**Ejemplo**:
```bash
peeka-cli logger --action get --logger myapp.payment
```

**Salida (exitosa)**:
```json
{
  "status": "success",
  "name": "myapp.payment",
  "level": "INFO",
  "level_num": 20
}
```

**Salida (fallida)**:
```json
{
  "status": "error",
  "error": "Logger not found: myapp.payment"
}
```

### 3. set - Modificar nivel de logger

**Uso**: Modificar dinámicamente el nivel de registro del logger, entra en vigor inmediatamente.

**Sintaxis**:
```bash
peeka-cli logger --action set --logger <name> --level <level>
```

**Parámetros**:
- `--logger` (requerido): Nombre del logger (se crea automáticamente si no existe)
- `--level` (requerido): Nuevo nivel de registro (ver niveles soportados a continuación)

**Niveles de registro soportados**:

| Nivel     | Valor | Descripción                     |
|----------|-------|-------------------------------|
| `DEBUG`   | 10    | Información detallada de depuración |
| `INFO`    | 20    | Mensajes informativos generales    |
| `WARNING` | 30    | Mensajes de advertencia (nivel por defecto) |
| `ERROR`   | 40    | Mensajes de error                 |
| `CRITICAL`| 50    | Errores graves                   |
| `NOTSET`  | 0     | Sin configuración (hereda del padre) |

**Ejemplo**:
```bash
# Habilitar registros DEBUG
peeka-cli logger --action set --logger myapp.auth --level DEBUG

# Cerrar registros INFO (solo retiene advertencias y errores)
peeka-cli logger --action set --logger myapp.reporting --level WARNING

# Restaurar nivel por defecto
peeka-cli logger --action set --logger myapp.auth --level INFO
```

**Salida**:
```json
{
  "status": "success",
  "name": "myapp.auth",
  "old_level": "INFO",
  "new_level": "DEBUG",
  "old_level_num": 20,
  "new_level_num": 10
}
```

**Notas**:
- El nombre del logger no distingue mayúsculas/minúsculas (internamente se convierte a mayúsculas)
- Si el logger no existe, se crea automáticamente (usando `logging.getLogger(name)`)
- La modificación entra en vigor inmediatamente, no necesita reiniciar el proceso
- No persiste (después de reiniciar el proceso se restaura la configuración original)

---

## Descripción de Parámetros

### --pattern - Patrón de Coincidencia

Usado para la acción `list`, filtra la lista de loggers.

**Comodines soportados**:
- `*`: Coincide con cualquier longitud de caracteres (incluyendo cadena vacía)
- `?`: Coincide con un solo caracter
- `[seq]`: Coincide con cualquier caracter en seq
- `[!seq]`: Coincide con cualquier caracter que no esté en seq

**Ejemplo**:
| Patrón     | Coincide ejemplo               | No coincide ejemplo        |
|-----------|------------------------------|--------------------------|
| `myapp.*` | `myapp.auth`, `myapp.db`     | `myapp`, `webapp.auth`   |
| `*db*`    | `myapp.db`, `database`, `mongodb` | `myapp.cache`           |
| `myapp.api.v?` | `myapp.api.v1`, `myapp.api.v2` | `myapp.api.v10`         |
| `myapp.[ad]*` | `myapp.auth`, `myapp.db` | `myapp.cache`           |

**Uso**:
```bash
# Enumerar todos los loggers en el espacio de nombres myapp
peeka-cli logger --action list --pattern "myapp.*"

# Enumerar todos los loggers relacionados con base de datos
peeka-cli logger --action list --pattern "*db*"

# Enumerar todos los loggers de versiones de API
peeka-cli logger --action list --pattern "*.api.v?"
```

### --logger - Nombre de Logger

Especifica el nombre completo del logger a operar.

**Especificación de nomenclatura**:
- Usualmente usa la ruta del módulo (como `myapp.module.submodule`)
- Práctica estándar de Python: `logger = logging.getLogger(__name__)`
- Bibliotecas de terceros usualmente usan el nombre del paquete (como `urllib3`, `boto3`)

**Cómo encontrar el nombre del logger**:
```bash
# Método 1: Enumerar todos los loggers, encontrar el objetivo
peeka-cli logger --action list | jq -r '.loggers[].name'

# Método 2: Usar coincidencia de patrones para reducir el alcance
peeka-cli logger --action list --pattern "myapp.payment*"

# Método 3: Ver llamadas a getLogger en el código
grep -r "getLogger" myapp/ | grep -v ".pyc"
```

### --level - Nivel de Registro

Especifica el nuevo nivel de registro (solo para acción `set`).

**Recomendaciones de selección de nivel**:

| Escenario                                   | Nivel recomendado | Descripción                     |
|---------------------------------------------|------------------|---------------------------------|
| Operación normal en entorno de producción    | `INFO`           | Registra información empresarial clave |
| Resolución de problemas en entorno de producción | `DEBUG`        | Habilitar temporalmente registros detallados |
| Optimización de rendimiento (reducir registros) | `WARNING`    | Solo registra situaciones anómalas |
| Cerrar registros de bibliotecas de terceros | `ERROR` o `CRITICAL` | Solo registra errores graves |
| Heredar configuración del logger padre       | `NOTSET`         | Usa el nivel del logger padre |

**Relación de herencia de niveles**:
```
root logger (por defecto WARNING)
  └─ myapp (INFO)
      ├─ myapp.auth (DEBUG) ← Usa su propio nivel
      └─ myapp.db (NOTSET)  ← Hereda INFO de myapp
```

---

## Formato de Salida

### Salida acción list

```json
{
  "status": "success",
  "loggers": [
    {
      "name": "myapp.auth",
      "level": "INFO",
      "level_num": 20
    },
    {
      "name": "myapp.db",
      "level": "DEBUG",
      "level_num": 10
    }
  ],
  "count": 2
}
```

**Descripción de campos**:
- `status`: Estado de la operación (`success` o `error`)
- `loggers`: Lista de loggers (ordenados por nombre)
- `name`: Nombre completo del logger
- `level`: Nombre del nivel de registro (como `INFO`)
- `level_num`: Valor numérico del nivel de registro (como `20`)
- `count`: Número de loggers coincidentes

### Salida acción get

**Exitoso**:
```json
{
  "status": "success",
  "name": "myapp.payment",
  "level": "INFO",
  "level_num": 20
}
```

**Fallido** (logger no existe):
```json
{
  "status": "error",
  "error": "Logger not found: myapp.payment"
}
```

### Salida acción set

**Exitoso**:
```json
{
  "status": "success",
  "name": "myapp.auth",
  "old_level": "INFO",
  "new_level": "DEBUG",
  "old_level_num": 20,
  "new_level_num": 10
}
```

**Fallido** (nivel inválido):
```json
{
  "status": "error",
  "error": "Invalid level: INVALID. Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL, NOTSET"
}
```

---

## Ejemplos de Uso

### Ejemplo 1: Ver toda la configuración de loggers

```bash
peeka-cli logger --action list | jq .
```

**Salida**:
```json
{
  "status": "success",
  "loggers": [
    {"name": "root", "level": "WARNING", "level_num": 30},
    {"name": "myapp", "level": "INFO", "level_num": 20},
    {"name": "myapp.auth", "level": "INFO", "level_num": 20},
    {"name": "myapp.db", "level": "WARNING", "level_num": 30},
    {"name": "urllib3.connectionpool", "level": "WARNING", "level_num": 30}
  ],
  "count": 5
}
```

### Ejemplo 2: Habilitar temporalmente registros DEBUG para resolver problemas

```bash
# 1. Ver nivel actual
peeka-cli logger --action get --logger myapp.payment
# Salida: {"status": "success", "name": "myapp.payment", "level": "INFO", ...}

# 2. Habilitar DEBUG
peeka-cli logger --action set --logger myapp.payment --level DEBUG
# Salida: {"status": "success", "old_level": "INFO", "new_level": "DEBUG"}

# 3. Monitorear archivo de registro al mismo tiempo en otra terminal
tail -f /var/log/myapp.log | grep -A 5 -B 5 "payment"

# 4. Reproducir el problema (activar el flujo de pago)

# 5. Después de resolver el problema, restaurar el nivel original
peeka-cli logger --action set --logger myapp.payment --level INFO
```

### Ejemplo 3: Cerrar registros verbosos de bibliotecas de terceros

```bash
# Ver todos los loggers de bibliotecas de terceros con nivel DEBUG
peeka-cli logger --action list --pattern "*" | \
  jq -r '.loggers[] | select(.level == "DEBUG") | .name'

# Cierra en lote (solo retiene WARNING y superior)
for logger in urllib3 botocore requests; do
  peeka-cli logger --action set --logger "$logger" --level WARNING
done
```

### Ejemplo 4: Verificar si el logger existe

```bash
# Método 1: Usar acción get
result=$(peeka-cli logger --action get --logger myapp.missing 2>&1)
echo "$result" | jq -r .status
# Salida: error (si no existe)

# Método 2: Enumerar todos y buscar
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.name == "myapp.missing")'
# Sin salida (si no existe)
```

### Ejemplo 5: Crear un nuevo logger y establecer nivel

```bash
# La acción set crea automáticamente el logger si no existe
peeka-cli logger --action set --logger myapp.new_module --level DEBUG

# Verificar que la creación fue exitosa
peeka-cli logger --action get --logger myapp.new_module
# Salida: {"status": "success", "name": "myapp.new_module", "level": "DEBUG", ...}
```

### Ejemplo 6: Ver en lote configuración de módulos específicos

```bash
# Ver niveles de registro de todos los submódulos de myapp.api
peeka-cli logger --action list --pattern "myapp.api.*" | \
  jq -r '.loggers[] | "\(.name): \(.level)"'
```

**Salida**:
```
myapp.api.v1: INFO
myapp.api.v2: DEBUG
myapp.api.auth: WARNING
```

---

## Flujo Completo de Diagnóstico

### Flujo 1: Resolución de problemas en entorno de producción

**Escenario**: Ocurrió un fallo de pago en entorno de producción, necesitas habilitar temporalmente registros de depuración para localizar el problema.

```bash
# Paso 1: Ver nivel de registro actual del módulo de pago
peeka-cli logger --action get --logger myapp.payment
# Salida: {"level": "INFO"}

# Paso 2: Habilitar registros DEBUG
peeka-cli logger --action set --logger myapp.payment --level DEBUG

# Paso 3: Monitorear archivo de registro al mismo tiempo
tail -f /var/log/myapp.log | grep -A 5 -B 5 "payment"

# Paso 4: Reproducir el problema (activar el flujo de pago)

# Paso 5: Ver registros de depuración, localizar el problema

# Paso 6: Después de resolver el problema, restaurar el nivel original
peeka-cli logger --action set --logger myapp.payment --level INFO
```

### Flujo 2: Diagnóstico de pérdida de registros

**Escenario**: El registro de algún módulo no tiene salida en absoluto, necesitas verificar la causa.

```bash
# Paso 1: Verificar si el logger existe
peeka-cli logger --action get --logger myapp.analytics
# Si la salida es "Logger not found", indica que no está inicializado

# Paso 2: Ver nivel del logger padre
peeka-cli logger --action get --logger myapp
# Salida: {"level": "WARNING"}

# Paso 3: Crear el logger y establecer nivel DEBUG
peeka-cli logger --action set --logger myapp.analytics --level DEBUG

# Paso 4: Verificar que los registros comienzan a salir
tail -f /var/log/myapp.log | grep analytics
```

### Flujo 3: Optimización de rendimiento - Reducir E/S de registros

**Escenario**: La carga del sistema es alta, la E/S de registros se convirtió en el cuello de botella, necesitas cerrar temporalmente algunos registros.

```bash
# Paso 1: Ver todos los loggers con nivel DEBUG
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.level == "DEBUG") | .name'

# Salida:
# myapp.api
# myapp.cache
# myapp.db
# myapp.reporting

# Paso 2: Mantener DEBUG en módulos centrales (api, db), cerrar otros
peeka-cli logger --action set --logger myapp.cache --level WARNING
peeka-cli logger --action set --logger myapp.reporting --level WARNING

# Paso 3: Observar cambios en la carga del sistema
# (usando top, htop o sistema de monitoreo)

# Paso 4: Si necesitas recuperar, restaura
peeka-cli logger --action set --logger myapp.cache --level DEBUG
peeka-cli logger --action set --logger myapp.reporting --level DEBUG
```

### Flujo 4: Ajuste en lote de registros de bibliotecas de terceros

**Escenario**: Múltiples bibliotecas de terceros output una gran cantidad de registros de depuración, necesitas cerrarlos en lote.

```bash
# Paso 1: Enumerar todos los loggers que no son de la aplicación (usualmente son de terceros)
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.name | startswith("myapp") | not) | .name'

# Salida:
# urllib3
# urllib3.connectionpool
# botocore
# requests

# Paso 2: Establecer en lote a WARNING
cat <<'EOF' | bash
for logger in urllib3 urllib3.connectionpool botocore requests; do
  peeka-cli logger --action set --logger "$logger" --level WARNING
  echo "Set $logger to WARNING"
done
EOF

# Paso 3: Verificar
peeka-cli logger --action list --pattern "*" | \
  jq -r '.loggers[] | select(.name | startswith("myapp") | not) | "\(.name): \(.level)"'
```

---

## Notas

### 1. Temporalidad de las modificaciones

**Importante**: Las modificaciones del comando logger **no persisten**.

- La modificación entra en vigor inmediatamente, pero después de reiniciar el proceso se restaurará la configuración original
- Para modificaciones permanentes necesitas actualizar el archivo de configuración (como `logging.conf` o `logging.basicConfig()` en el código)

### 2. Influencia del logger root

El **logger root** es el padre por defecto de todos los loggers:

- Nivel por defecto es `WARNING`
- Todos los loggers que no tienen un nivel establecido explícitamente heredan del logger root
- Modificar el logger root influye en todos los loggers hijos (a menos que el logger hijo tenga un nivel explícito)

**Ejemplo**:
```bash
# Ver logger root
peeka-cli logger --action get --logger root

# Habilitar DEBUG global (usa con precaución!)
peeka-cli logger --action set --logger root --level DEBUG
```

**Advertencia**: Modificar el logger root puede causar una explosión de registros, solo úsalo cuando sea necesario.

### 3. Momento de creación del Logger

**Nota**: `list` y `get` solo pueden ver loggers **inicializados**.

- El Logger se crea cuando se llama por primera vez `logging.getLogger(name)`
- Si el código aún no se ha ejecutado hasta el módulo relacionado, el logger no aparecerá en la lista
- La acción `set` crea automáticamente el logger si no existe

### 4. Mecanismo de herencia de niveles

Reglas de herencia de niveles de registro de Python:
```
root (WARNING)
  └─ myapp (INFO)
       ├─ myapp.auth (DEBUG)    ← Usa su propio nivel
       ├─ myapp.db (NOTSET)     ← Hereda INFO de myapp
       └─ myapp.cache (NOTSET)  ← Hereda INFO de myapp
```

**Nivel que entra en vigor realmente**:
- `myapp.auth`: DEBUG (nivel propio)
- `myapp.db`: INFO (heredado de myapp)
- `myapp.cache`: INFO (heredado de myapp)

### 5. Influencia de Handlers

**Nota**: El comando logger solo modifica el **nivel** del logger, no modifica la configuración de handlers.

- Incluso si el nivel del logger es DEBUG, si el nivel del handler es INFO, los registros DEBUG aún no se outputearán
- Verifica la configuración del handler: `logger.handlers[0].level` (necesitas verlo en el código)

### 6. Impacto en el rendimiento

Modificar el nivel del logger en sí mismo **no tiene sobrecoste de rendimiento**, pero el cambio de nivel de registro influye:
- **Reducir el nivel** (como INFO → DEBUG): Aumenta la cantidad de registros, aumenta el sobrecoste de E/S
- **Promover el nivel** (como DEBUG → WARNING): Disminuye la cantidad de registros, mejora el rendimiento

**Recomendaciones**:
- Restaura el nivel original inmediatamente después de completar la depuración
- Evita tener habilitado el nivel DEBUG por mucho tiempo
- Verifica periódicamente el tamaño del archivo de registro

---

## Preguntas Frecuentes

### P1: ¿Por qué después de modificar el nivel del logger los registros aún no tienen salida?

**Posibles causas**:
1. **Nivel de Handler demasiado alto**: El nivel del logger es DEBUG, pero el nivel del handler es INFO
2. **El registro no se ha refrescado**: Algunos handlers tienen búfer, necesitas esperar el refresco
3. **Nombre del logger incorrecto**: El nombre del logger usado realmente es inconsistente con el modificado
4. **Nivel del logger padre demasiado alto**: Incluso si el logger hijo es DEBUG, el padre filtró el mensaje

**Método de diagnóstico**:
```bash
# 1. Confirmar que el nivel del logger se modificó
peeka-cli logger --action get --logger myapp.target

# 2. Verificar el nivel del logger padre
peeka-cli logger --action get --logger myapp

# 3. Verificar el nivel del logger root
peeka-cli logger --action get --logger root

# 4. Verificar todos los loggers (confirmar que el nombre es correcto)
peeka-cli logger --action list --pattern "myapp.*"
```

### P2: ¿Cómo modificar múltiples loggers en lote?

**Método 1**: Usar bucle de shell
```bash
for logger in myapp.auth myapp.db myapp.cache; do
  peeka-cli logger --action set --logger "$logger" --level DEBUG
done
```

**Método 2**: Leer desde archivo
```bash
# Contenido del archivo loggers.txt:
# myapp.auth
# myapp.db
# myapp.cache

while read logger; do
  peeka-cli logger --action set --logger "$logger" --level DEBUG
done < loggers.txt
```

**Método 3**: Consulta dinámica y modificación en lote
```bash
# Cambia todos los loggers con nivel INFO a DEBUG
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.level == "INFO") | .name' | \
  while read logger; do
    peeka-cli logger --action set --logger "$logger" --level DEBUG
  done
```

### P3: ¿La modificación influye en otros procesos?

**Respuesta**: No.

- La configuración del logger de cada proceso es independiente
- La modificación solo influye en el proceso con el PID especificado
- Los otros procesos no se ven afectados por los cambios

### P4: ¿Cómo restaurar todos los loggers al estado original?

**Método**: Reinicia el proceso (la configuración del logger se volverá a cargar).

**Nota**: El comando logger no proporciona la función de "instantánea de recuperación", se recomienda:
1. Registra el nivel original antes de modificar
2. O reinicia directamente el proceso para restaurar la configuración

**Ejemplo (registrando nivel original)**:
```bash
# Guarda la configuración actual antes de modificar
peeka-cli logger --action list > logger_backup.json

# Restaura después de modificar
jq -r '.loggers[] | "\(.name) \(.level)"' logger_backup.json | \
  while read name level; do
    peeka-cli logger --action set --logger "$name" --level "$level"
  done
```

### P5: ¿Por qué el patrón no encuentra coincidencia con el logger?

**Posibles causas**:
1. **Error de sintaxis de patrón**: fnmatch no soporta expresiones regulares, solo soporta `*` y `?`
2. **Logger no inicializado**: El código aún no se ha ejecutado hasta ese módulo
3. **Problema de mayúsculas/minúsculas**: El nombre del logger distingue mayúsculas/minúsculas

**Método de depuración**:
```bash
# 1. Enumerar todos los loggers (sin usar patrón)
peeka-cli logger --action list | jq -r '.loggers[].name'

# 2. Confirmar el nombre exacto del logger objetivo

# 3. Usar el patrón correcto
peeka-cli logger --action list --pattern "myapp.*"
```

### Q6: ¿Se puede crear un logger que no existe?

**Respuesta**: Sí, usa la acción `set`.

```bash
# Crea un nuevo logger y establece el nivel
peeka-cli logger --action set --logger myapp.new_logger --level DEBUG

# Verificar
peeka-cli logger --action get --logger myapp.new_logger
# Salida: {"status": "success", "name": "myapp.new_logger", "level": "DEBUG"}
```

**Nota**:
- El logger recién creado no se volverá a crear automáticamente después de reiniciar el proceso
- El código de la aplicación necesita llamar explícitamente `logging.getLogger(name)` para poder usar este logger

---

## Técnicas Avanzadas

### 1. Script de conmutación dinámica de nivel de registro

**Escenario**: Necesitas abrir/cerrar frecuentemente registros de depuración, escribe un script automatizado.

```bash
#!/bin/bash
# toggle_debug.sh - Conmuta el nivel de registro de myapp.payment

PID=12345
LOGGER="myapp.payment"

current=$(peeka-cli logger --action get --logger $LOGGER | jq -r .level)

if [ "$current" == "DEBUG" ]; then
  echo "Disabling DEBUG..."
  peeka-cli logger --action set --logger $LOGGER --level INFO
else
  echo "Enabling DEBUG..."
  peeka-cli logger --action set --logger $LOGGER --level DEBUG
fi
```

### 2. Monitorear cambios de nivel de registro

**Escenario**: Verificar periódicamente la configuración de loggers para asegurar que no hay DEBUG habilitado accidentalmente en producción.

```bash
#!/bin/bash
# check_debug_loggers.sh - Verificar todos los loggers con nivel DEBUG

PID=12345

debug_loggers=$(peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.level == "DEBUG") | .name')

if [ -n "$debug_loggers" ]; then
  echo "WARNING: Found DEBUG loggers in production:"
  echo "$debug_loggers"
  # Envía alerta (como Slack, correo electrónico, etc.)
else
  echo "All loggers are at safe levels."
fi
```

### 3. Integración con Prometheus

**Escenario**: Exporta la configuración de logger a monitoreo de Prometheus.

```bash
#!/bin/bash
# export_logger_metrics.sh

PID=12345

peeka-cli logger --action list | \
  jq -r '.loggers[] | "logger_level{name=\"\(.name)\"} \(.level_num)"' \
  > /var/lib/node_exporter/textfile_collector/logger_levels.prom
```

**Consulta Prometheus**:
```promql
# Consultar todos los loggers con nivel DEBUG
logger_level{level="10"}

# Regla de alarma (detectar logger DEBUG en producción)
ALERT ProductionDebugLogger
  IF logger_level{name=~"myapp.*", level="10"} > 0
  FOR 5m
  ANNOTATIONS {
    summary = "Production logger at DEBUG level",
    description = "Logger {{ $labels.name }} is at DEBUG level in production.",
  }
```

### 4. Análisis de distribución de niveles de registro

**Escenario**: Estadísticas de distribución de niveles de registro de la aplicación.

```bash
peeka-cli logger --action list --pattern "myapp.*" | \
  jq -r '.loggers[] | .level' | sort | uniq -c
```

**Salida**:
```
     12 DEBUG
     45 INFO
      8 WARNING
```

### 5. Redirección temporal de registros

**Escenario**: Ajusta temporalmente el nivel de registro de un módulo, y redirecciona la salida a un archivo separado.

```bash
# 1. Habilitar registros DEBUG
peeka-cli logger --action set --logger myapp.payment --level DEBUG

# 2. Monitorear registros en otra terminal
tail -f /var/log/myapp.log | grep "payment" > payment_debug.log

# 3. Reproducir el problema

# 4. Detener monitoreo (Ctrl+C)

# 5. Restaurar nivel de registro
peeka-cli logger --action set --logger myapp.payment --level INFO
```

### 6. Script de restauración automática

**Escenario**: Habilita DEBUG y se recupera automáticamente después de 5 minutos, evita olvidar de cerrar.

```bash
#!/bin/bash
# temp_debug.sh - Habilita DEBUG temporalmente, se recupera automáticamente después de 5 minutos

PID=$1
LOGGER=$2
DURATION=${3:-300}  # Por defecto 5 minutos

# Guarda nivel original
original=$(peeka-cli logger --action get --logger $LOGGER | jq -r .level)
echo "Original level: $original"

# Habilita DEBUG
peeka-cli logger --action set --logger $LOGGER --level DEBUG
echo "DEBUG enabled. Will auto-restore in $DURATION seconds..."

# Espera en segundo plano y recupera
(
  sleep $DURATION
  peeka-cli logger --action set --logger $LOGGER --level $original
  echo "Restored to $original"
) &
```

**Uso**:
```bash
./temp_debug.sh 12345 myapp.payment 300
```

---

## Resumen

El comando `logger` es una herramienta potente para diagnóstico de registros en entorno de producción, especialmente adecuado para:
- Habilitar temporalmente registros de depuración para resolver problemas
- Cerrar registros verbosos de bibliotecas de terceros
- Ajustar dinámicamente el nivel de registro para optimizar el rendimiento
- Diagnosticar problemas de pérdida de registros

**Mejores prácticas**:
- Registra el nivel original antes de modificar (conveniente para recuperar)
- Restaura el nivel original inmediatamente después de completar la depuración
- Evita tener habilitado DEBUG por mucho tiempo (explosión de registros)
- Usa `--pattern` para filtrar loggers (mejora la eficiencia)
- Combina con `jq` para potentes análisis de datos

**Siguientes pasos**:
- Conoce el comando [`watch`](watch.md) (observar llamadas a funciones)
- Conoce el comando [`stack`](stack.md) (rastrear pila de llamadas)
- Conoce el comando [`memory`](memory.md) (análisis de memoria)
