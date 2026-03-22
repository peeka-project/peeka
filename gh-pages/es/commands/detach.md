---
layout: default
title: detach
parent: Referencia de Comandos
nav_order: 13
---

# detach - Desadjuntar del proceso objetivo
{: .no_toc }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

## Introducción

El comando `detach` se usa para separar el Agente Peeka del proceso objetivo, detener todas las actividades de diagnóstico y restaurar el proceso objetivo a su estado original. Este comando limpia todas las lógicas de observación inyectadas, cierra el servicio del Agente y elimina archivos temporales, asegurando que el proceso objetivo no se vea afectado.

## Escenarios de Uso

- **Diagnóstico completado**: Salir limpiamente después de completar el trabajo de diagnóstico
- **Evitar consumo de recursos**: Liberar memoria y descriptores de archivos ocupados por el Agente
- **Restaurar estado original**: Eliminar todas las mejoras de funciones y lógicas de observación
- **Cambiar proceso objetivo**: Separarse del proceso actual y prepararse para adjuntar a otros procesos

## Formato del Comando

```bash
peeka-cli attach <pid>    # Primero adjunta al proceso objetivo
# ... ejecuta comandos de diagnóstico ...
peeka-cli detach          # Después de completar, separa
```

**Nota**: El comando `detach` no tiene parámetros.

## Proceso de Desadjunte

El comando `detach` ejecuta las siguientes operaciones de limpieza:

1. **Detener todas las observaciones activas**:
   - Detener todas las observaciones `watch`
   - Detener todos los rastreos `trace`
   - Detener todas las capturas `stack`
   - Detener todos los monitoreos `monitor`
   - Detener el análisis de rendimiento `top`

2. **Restaurar funciones mejoradas**:
   - Llama a `injector.uninject_all()` para eliminar todos los decoradores
   - Restaura las funciones a su estado original (elimina el envoltorio `__peeka_original__`)

3. **Limpiar datos de observación**:
   - Vacía el búfer de observación
   - Cancela todos los registros de ID de watch

4. **Cerrar servicio del Agente**:
   - Cierra el Unix Domain Socket
   - Detiene el hilo de escucha del Agente
   - Elimina el archivo socket (`/tmp/peeka_<pid>.sock`

5. **Liberar recursos**:
   - Limpia búferes de memoria
   - Cierra descriptores de archivos
   - Detiene hilos en segundo plano

## Uso Básico

### 1. Desadjunte normal

```bash
# Primero adjunta al proceso objetivo
peeka-cli attach 12345

# Ejecuta comandos de diagnóstico
peeka-cli watch "mymodule.func" -n 10
peeka-cli monitor "mymodule.func" --interval 1 -c 5

# Después de completar, separa
peeka-cli detach
```

**Ejemplo de salida**:

```json
{
  "type": "success",
  "command": "detach",
  "data": {
    "pid": 12345,
    "message": "Detached from process 12345"
  }
}
```

### 2. Fallo en el desadjunte

Si ocurre un error durante el proceso de desadjunte:

```json
{
  "type": "error",
  "command": "detach",
  "error": "Failed to restore function: mymodule.func"
}
```

**Forma de manejo:
- Si el error no es crítico (por ejemplo, la restauración de una función falló), el Agente continuará limpiando otros recursos
- Si el error es crítico (por ejemplo, falla al cerrar el socket), se recomienda reiniciar el proceso objetivo

## Uso en TUI

En modo TUI:

1. Inicia TUI:
   ```bash
   peeka  # o python -m peeka.tui
   ```

2. Después de conectarte al proceso objetivo, presiona la tecla **`1`** para volver a la vista Dashboard

3. En Dashboard, ingresa el comando:
   ```
   detach
   ```

4. O simplemente presiona la tecla **`q`** para salir de TUI (ejecutará detach automáticamente)

## Notas

1. **Limpieza automática**:
   - El Agente Peeka hará todo lo posible para realizar la limpieza cuando sale anormalmente (best-effort)
   - Pero no garantiza una recuperación al 100%, se recomienda usar el comando `detach` para salir normalmente

2. **Restauración de funciones**:
   - En la mayoría de los casos, la función se restaurará completamente a su estado original
   - En muy raras ocasiones, si la función fue modificada simultáneamente por otro código al mismo tiempo, puede que no se recupere completamente

3. **Pérdida de datos de observación**:
   - Después de `detach`, todos los datos de observación no consumidos se vaciarán
   - Si necesitas conservar los datos, asegúrate de que todos los datos se hayan guardado antes de `detach`

4. **Limpieza de archivo Socket**:
   - El archivo Socket (`/tmp/peeka_<pid>.sock`) se eliminará automáticamente
   - Si el proceso sale anormalmente, puede que necesites limpiar manualmente

5. **Recuperación de rendimiento**:
   - Después de `detach`, el rendimiento del proceso objetivo debería recuperar inmediatamente al nivel original
   - Si todavía hay problemas de rendimiento, puede que sea un problema del propio proceso objetivo

6. **Readjunte**:
   - Después de `detach` puedes volver a `attach` al mismo proceso
   - Cada `attach` creará un nuevo archivo socket y una nueva instancia de Agente

7. **Terminación del proceso**:
   - Si el proceso objetivo termina antes de `detach`, el Agente limpiará automáticamente
   - No necesitas ejecutar `detach` manualmente

## Relación con el comando attach

`attach` y `detach` son operaciones emparejadas:

```bash
# Ciclo de vida
peeka-cli attach <pid>    # Inyecta Agente, inicia servicio
# ... operaciones de diagnóstico ...
peeka-cli detach          # Limpia Agente, restaura el estado original
```

**Comparación de uso de recursos:

| Estado        | Archivo Socket | Consumo de memoria | Mejora de funciones | Hilos en segundo plano |
|---------------|----------------|-------------------|--------------------|-----------------------|
| Antes de attach | Ninguno        | 0                 | Ninguno             | 0                     |
| Después de attach | Existe         | ~10MB             | Según comando      | 1-5                   |
| Después de detach | Ninguno        | 0                 | Ninguno             | 0                     |

## Resolución de Problemas

### 1. El comando detach no responde

```bash
# Forzar terminación del Agente (no recomendado)
kill -9 <pid_of_agent_thread>
```

### 2. El archivo Socket no se limpió

```bash
# Eliminar manualmente el archivo socket
rm /tmp/peeka_<pid>.sock
```

### 3. La función no se restauró

Si el comportamiento de la función es anormal después de `detach`:

1. Verifica si hay otras herramientas de diagnóstico adjuntadas simultáneamente
2. Reinicia el proceso objetivo
3. Verifica si la versión de Peeka es compatible con la versión de Python objetivo

### 4. La memoria no se liberó

Si la memoria del proceso objetivo no disminuye después de `detach`:

- Esto puede ser un comportamiento normal de la gestión de memoria de Python
- El intérprete de Python no libera inmediatamente la memoria al sistema operativo
- Puedes activar la recolección de basura manualmente: `peeka-cli memory --action gc` (antes de detach)

## Requisitos de Permisos

El comando `detach` requiere:
- Ya has `attach` exitosamente al proceso objetivo
- Mantienes conexión con el proceso objetivo (socket disponible)

**No necesita** permisos adicionales, porque la operación de limpieza se ejecuta dentro del proceso objetivo.
