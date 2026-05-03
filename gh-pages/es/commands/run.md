---
layout: default
title: run
parent: Referencia de Comandos
nav_order: 14
---

# run - Ejecutar script con Peeka inyectado
{: .no_toc }

## Tabla de contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}


## Descripción

El comando `run` **ejecuta un script Python con Peeka inyectado desde el inicio**, sin necesidad de que el proceso esté en ejecución previamente. Ideal para observar **código en tiempo de importación**, **lógica de inicialización** o **scripts de corta duración** donde no es posible hacer `attach` una vez iniciado.

A diferencia del flujo `attach`, `run` proporciona capacidad de diagnóstico completa desde la primera línea del script.


## Casos de uso

- **Observación en tiempo de importación**: Capturar carga de módulos, inicialización de clases y otra lógica que solo se ejecuta una vez al inicio
- **Scripts de corta duración**: Procesos que terminan demasiado rápido para hacer `attach` manualmente
- **Trabajos por lotes**: Diagnóstico de tareas cron, pipelines de datos y scripts de una sola ejecución
- **Depuración en CI/CD**: Capturar el comportamiento de funciones en pipelines automatizados sin modificar el código
- **Reproducir bugs de inicio**: Controlar las condiciones de inicio con precisión para reproducir problemas que solo ocurren en el arranque

## Formato del comando

```bash
peeka-cli run <script> [script_args] -- <command> [command_options]
```

`--` es el separador obligatorio: a su izquierda van el script y sus argumentos; a su derecha van el comando Peeka y sus opciones.

### Parámetros

| Parámetro          | Descripción                                          | Por defecto |
|--------------------|------------------------------------------------------|-------------|
| `script`           | Ruta al script Python a ejecutar                     | —           |
| `script_args`      | Argumentos que se pasan al script (opcional)         | —           |
| `--`               | Separador obligatorio                                | —           |
| `command`          | Comando Peeka (watch / trace / stack)                | —           |
| `command_options`  | Opciones del comando Peeka                           | —           |
| `--output-file`    | Escribir salida JSONL en archivo en vez de stdout    | —           |

### Subcomandos soportados

| Subcomando | Propósito                                               |
|------------|---------------------------------------------------------|
| `watch`    | Observar llamadas a funciones (args, retorno, duración) |
| `trace`    | Trazar árbol de llamadas con desglose temporal          |
| `stack`    | Capturar la pila de llamadas en la entrada de la función|

## Ejemplos

### Ejemplo 1: Uso más sencillo

```bash
peeka-cli run myscript.py -- watch "mymodule.MyClass.init_db"
```

Observa `init_db` desde el momento en que el script arranca.

### Ejemplo 2: Pasar argumentos al script

```bash
peeka-cli run myscript.py --env production --config /etc/app.yml -- watch "mymodule.func"
```

`--env` y `--config` van al script; `watch "mymodule.func"` es el comando Peeka.

### Ejemplo 3: Trazar árbol de llamadas

```bash
peeka-cli run myscript.py -- trace "mymodule.func" -d 3
```

Traza el árbol de llamadas de `mymodule.func` hasta 3 niveles de profundidad.

### Ejemplo 4: Filtrado por condición

```bash
peeka-cli run myscript.py -- watch "mymodule.func" --condition "params[0] > 100"
```

Solo captura las llamadas cuyo primer argumento es mayor que 100.

### Ejemplo 5: Salida a archivo

```bash
peeka-cli run myscript.py -- watch "mymodule.func" --output-file observations.jsonl
```

Escribe todos los datos de observación en `observations.jsonl`. El stdout del script no se ve afectado.

### Ejemplo 6: Limitar número de observaciones

```bash
peeka-cli run myscript.py -- watch "mymodule.func" -n 10
```

Se detiene automáticamente tras 10 capturas.

### Ejemplo 7: Capturar pila de llamadas

```bash
peeka-cli run myscript.py -- stack "mymodule.func" -n 3
```

Captura la pila de llamadas en la entrada de `mymodule.func`, 3 veces.

## run vs attach

| Característica        | `run`                           | `attach`                         |
|-----------------------|---------------------------------|----------------------------------|
| Estado del proceso    | Lanzado por Peeka               | Ya en ejecución                  |
| Ventana de observación| Desde la primera línea          | Desde el momento del attach      |
| Mejor para            | Scripts cortos, lógica de inicio| Servicios de larga duración      |
| Cómo iniciar          | `peeka-cli run script.py -- …`  | `peeka-cli attach <pid>`         |
| Requiere ptrace/PEP768| No (inyección directa)          | Sí                               |

**Recomendación**:
- Servicios en producción, daemons → usar `attach`
- Scripts, trabajos por lotes, diagnóstico de fase de inicio → usar `run`

## Notas importantes

### ⚠️ El separador `--` es obligatorio

```bash
# ✅ Correcto: -- separa los args del script del comando Peeka
peeka-cli run myscript.py arg1 -- watch "mymodule.func"

# ❌ Incorrecto: sin -- se produce un error de análisis
peeka-cli run myscript.py arg1 watch "mymodule.func"
```

### ⚠️ La observación termina cuando el script finaliza

Cuando el script termina (normalmente o con error), la observación se detiene automáticamente. Para observación continua, use `attach` con un proceso de larga duración.

### ⚠️ --output-file solo afecta la salida de Peeka

`--output-file` redirige los datos de diagnóstico JSONL de Peeka al archivo especificado. El stdout/stderr del propio script no se ve afectado.

## Comandos relacionados

- [`attach`](attach.md) - Conectarse a un proceso en ejecución
- [`watch`](watch.md) - Observar llamadas a funciones
- [`trace`](trace.md) - Trazar árbol de llamadas
- [`stack`](stack.md) - Capturar pila de llamadas
