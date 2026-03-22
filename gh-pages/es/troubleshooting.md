---
layout: default
title: Resolución de Problemas
nav_order: 9
---

# Resolución de Problemas
{: .no_toc }

Problemas comunes y sus soluciones.
{: .fs-6 .fw-300 }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Problemas al Adjuntar

### Error: Operation not permitted

**Síntomas**:
```
Error: Operation not permitted: ptrace access denied
```

**Causa**: Permisos insuficientes, no se puede adjuntar al proceso objetivo.

**Soluciones**:

#### Opción 1: Usar el mismo usuario

```bash
# Confirmar propietario del proceso objetivo
ps -o user= -p <pid>

# Ejecutar Peeka con el mismo usuario
peeka-cli attach <pid>
```

#### Opción 2: Usar sudo

```bash
sudo peeka-cli attach <pid>
```

#### Opción 3: Ajustar ptrace_scope

```bash
# Verificar configuración actual
cat /proc/sys/kernel/yama/ptrace_scope

# Modificar temporalmente (para pruebas)
echo 1 | sudo tee /proc/sys/kernel/yama/ptrace_scope

# Modificar permanentemente
echo "kernel.yama.ptrace_scope = 1" | sudo tee /etc/sysctl.d/10-ptrace.conf
sudo sysctl -p /etc/sysctl.d/10-ptrace.conf
```

#### Opción 4: Configuración SELinux (RHEL/Fedora)

```bash
# Verificar estado de SELinux
getenforce

# Permitir ptrace temporalmente
sudo setsebool -P deny_ptrace off

# O crear una política SELinux
```

### Error: Process not found

**Síntomas**:
```
Error: Process 12345 not found
```

**Causa**: El PID no existe o el proceso ya terminó.

**Solución**:

```bash
# Confirmar si el proceso existe
ps -p 12345

# Volver a buscar el PID
ps aux | grep "your_app"
pgrep -f "your_app.py"
```

### Error: Python debugging symbols not found (Python < 3.14)

**Síntomas**:
```
Error: Python debugging symbols not found. Install python3-dbg.
```

**Causa**: Los símbolos de depuración de Python no están instalados (requerido por la alternativa GDB).

**Solución**:

```bash
# Debian/Ubuntu
sudo apt-get update
sudo apt-get install python3-dbg

# RHEL/CentOS/Fedora
sudo yum install python3-debuginfo

# Verificar instalación
python3 -c "import sys; print(hasattr(sys, 'gettotalrefcount'))"
# Debe mostrar True
```

### Error: GDB not found (Python < 3.14)

**Síntomas**:
```
Error: GDB not found. Please install GDB.
```

**Causa**: GDB no está instalado.

**Solución**:

```bash
# Debian/Ubuntu
sudo apt-get install gdb

# RHEL/CentOS
sudo yum install gdb

# macOS
brew install gdb

# Verificar versión (se necesita 7.3+)
gdb --version
```

### Error: Timeout attaching to process

**Síntomas**:
```
Error: Timeout attaching to process after 30 seconds
```

**Causa**:
1. El proceso objetivo está bloqueado o no responde
2. El timeout de adjunte es demasiado corto
3. La carga del sistema es demasiado alta

**Solución**:

```bash
# Opción 1: Aumentar el tiempo de espera
peeka-cli attach <pid> --timeout 60

# Opción 2: Verificar estado del proceso
ps -p <pid> -o stat=
# D: Sueño ininterrumpido (puede estar bloqueado)
# R/S: Funcionamiento normal

# Opción 3: Verificar carga del sistema
top
uptime
```

---

## Problemas de Observación

### No se observan datos

**Síntomas**: Después de iniciar el comando watch, no hay salida de datos de observación.

**Causa**:
1. El nombre de la función está escrito incorrectamente
2. La función no está siendo llamada
3. La expresión condicional es demasiado estricta
4. El número de observaciones ha alcanzado el límite superior

**Solución**:

#### Verificar nombre de función

```bash
# Usa sc/sm para buscar el nombre correcto de la función
peeka-cli sc "Calculator"
peeka-cli sm "add"

# Usa el nombre completo calificado
peeka-cli watch "demo.Calculator.add"  # ✅
peeka-cli watch "Calculator.add"        # ❌
```

#### Confirmar que la función está siendo llamada

```bash
# Verificar si el proceso objetivo está en ejecución
ps -p <pid>

# Verificar registros del proceso
tail -f /var/log/your_app.log
```

#### Simplificar expresión condicional

```bash
# Primero observa sin condiciones
peeka-cli watch "demo.func" --times 5

# Después de confirmar que hay datos, agrega la condición
peeka-cli watch "demo.func" --condition "cost > 100" --times 5
```

#### Aumentar número de observaciones

```bash
# Por defecto -1 (infinito)
peeka-cli watch "demo.func"

# O especifica explícitamente
peeka-cli watch "demo.func" --times 100
```

### Datos de observación incompletos

**Síntomas**: Los parámetros o valores de retorno observados se muestran como `<truncated>` o incompletos.

**Causa**: Límite de profundidad de salida.

**Solución**:

```bash
# Aumenta la profundidad de salida (por defecto 2)
peeka-cli watch "demo.func" --depth 5

# Explicación de profundidad:
# 1: Solo muestra el tipo
# 2: Muestra una capa de estructura
# 5+: Muestra anidamiento profundo
```

### Error de expresión condicional

**Síntomas**:
```
Error: Invalid condition expression: name 'invalid_var' is not defined
```

**Causa**: En la expresión condicional se usó una variable que no existe o una función no segura.

**Solución**:

#### Variables disponibles

```bash
# ✅ Variables correctas
params      # Lista de parámetros
kwargs      # Parámetros de palabras clave
returnObj   # Valor de retorno
throwExp    # Objeto de excepción
cost        # Tiempo de ejecución (milisegundos)
target      # Objeto objetivo (método de instancia)
```

#### Funciones seguras

```bash
# ✅ Funciones permitidas
len(), str(), int(), float(), bool()
type(), isinstance()
min(), max(), sum()

# ❌ Funciones no permitidas
eval(), exec(), compile()
open(), read(), write()
__import__()
```

#### Ejemplos

```bash
# ✅ Correcto
--condition "len(params) > 2"
--condition "params[0] > 100 and cost > 50"
--condition "returnObj is not None"

# ❌ Incorrecto
--condition "my_var > 100"           # my_var no existe
--condition "eval('1+1')"            # eval no permitido
--condition "open('/etc/passwd')"    # open no permitido
```

---

## Problemas de Rendimiento

### El proceso objetivo se vuelve lento

**Síntomas**: Después de adjuntar Peeka, la respuesta del proceso objetivo se vuelve lenta.

**Causa**:
1. El comando trace tiene un sobrecoste demasiado grande (Python < 3.12)
2. La frecuencia de observación es demasiado alta
3. La profundidad de salida es demasiado grande

**Solución**:

#### Usar Python 3.12+

El comando trace en Python 3.12+ usa la API `sys.monitoring`, el sobrecoste es < 5%.

#### Limitar frecuencia de observación

```bash
# ✅ Limita el número de observaciones
peeka-cli watch "func" --times 10

# ✅ Usa filtrado condicional
peeka-cli watch "func" --condition "cost > 100"

# ❌ Observación infinita en funciones de alta frecuencia
peeka-cli watch "high_frequency_func"
```

#### Reducir profundidad de salida

```bash
# ✅ Usa profundidad por defecto
peeka-cli watch "func"  # depth=2

# ❌ Profundidad demasiado grande
peeka-cli watch "func" --depth 10
```

#### Detener observaciones que no necesitas

```bash
# Detener watch
peeka-cli reset "func"

# O desadjuntar el proceso
peeka-cli detach <pid>
```

### El cliente Peeka responde lentamente

**Síntomas**: La ejecución del comando Peeka es muy lenta, la transmisión de datos tiene gran latencia.

**Causa**:
1. El volumen de datos de observación es demasiado grande
2. El búfer de Unix Socket está lleno
3. La carga de CPU es demasiado alta

**Solución**:

```bash
# Reducir volumen de datos
peeka-cli watch "func" --times 10 --condition "cost > 100"

# Verificar recursos del sistema
top
df -h

# Limpiar archivos socket antiguos
rm -f /tmp/peeka_*.sock
```

---

## Problemas de Salida

### Error de análisis JSON

**Síntomas**:
```
Error: Expecting value: line 1 column 1 (char 0)
```

**Causa**: La salida contiene contenido no JSON (como sentencias print).

**Solución**:

```bash
# Extraer solo líneas JSON
peeka-cli watch "func" | grep '^{' | jq

# O usar filtrado con Python
peeka-cli watch "func" | python -c '
import sys, json
for line in sys.stdin:
    try:
        msg = json.loads(line)
        print(json.dumps(msg))
    except:
        pass
'
```

### Salida con caracteres corruptos

**Síntomas**: La salida contiene caracteres corruptos.

**Causa**: Problema de codificación.

**Solución**:

```bash
# Establecer locale correcto
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# O usar procesamiento con Python
peeka-cli watch "func" | python -c '
import sys
for line in sys.stdin:
    print(line, end="")
' 2>&1 | tee output.log
```

---

## Problemas con Docker

### No se puede adjuntar dentro del contenedor Docker

**Síntomas**:
```
Error: Operation not permitted (Docker)
```

**Causa**: El contenedor carece de la capability SYS_PTRACE.

**Solución**:

#### docker run

```bash
docker run --cap-add=SYS_PTRACE --security-opt seccomp=unconfined your-image
```

#### docker-compose.yml

```yaml
services:
  app:
    image: your-image
    cap_add:
      - SYS_PTRACE
    security_opt:
      - seccomp=unconfined
```

#### Kubernetes

```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: app
    securityContext:
      capabilities:
        add: ["SYS_PTRACE"]
```

---

## Problemas con TUI

### Visualización anormal de TUI

**Síntomas**: La interfaz TUI se muestra desordenada o no se renderiza correctamente.

**Causa**: Problema de compatibilidad del terminal.

**Solución**:

```bash
# Verificar si el tipo de terminal soporta 256 colores
echo $TERM

# O usa el modo CLI
peeka-cli watch "func"
```

### Colores anormales de TUI dentro de contenedor Docker

**Síntomas**: Después de entrar al contenedor a través de `docker exec`, los colores de la interfaz TUI se pierden o los colores de Header/Footer no se pueden distinguir del cuerpo principal.

**Causa**: `docker exec` no hereda las variables de entorno de terminal del host (`TERM`, `COLORTERM`), por defecto `TERM=dumb` dentro del contenedor, Textual no puede detectar el soporte de truecolor.

**Solución**:

La imagen de prueba de Peeka tiene incorporado `TERM=xterm-256color` y `COLORTERM=truecolor`, después de entrar al contenedor con `docker exec` TUI se puede usar directamente, no necesita configuración adicional.

### TUI se bloquea

**Síntomas**: La interfaz TUI no responde.

**Causa**:
1. El flujo de datos es demasiado rápido
2. El hilo en segundo plano está bloqueado

**Solución**:

```bash
# Usa Ctrl+C para salir

# Usa CLI como alternativa
peeka-cli watch "func" --times 10
```

---

## Otros Problemas

### Conflicto de archivo Socket

**Síntomas**:
```
Error: Address already in use: /tmp/peeka_12345.sock
```

**Causa**: La salida anormal de la última vez no limpió el archivo socket.

**Solución**:

```bash
# Eliminar el archivo socket antiguo
rm -f /tmp/peeka_12345.sock

# O usa un directorio socket diferente
peeka-cli attach 12345 --socket-dir /tmp/my_peeka
```

### Consumo de memoria demasiado alto

**Síntomas**: El consumo de memoria de Peeka o del proceso objetivo es demasiado alto.

**Causa**: El búfer de datos de observación es demasiado grande.

**Solución**:

```bash
# Limitar el número de observaciones
peeka-cli watch "func" --times 100

# Restablecer observaciones periódicamente
peeka-cli reset "func"

# O desconectar la conexión
peeka-cli detach <pid>
```

### No se encuentra el módulo

**Síntomas**:
```
Error: No module named 'peeka'
```

**Causa**: Problema de instalación.

**Solución**:

```bash
# Reinstalar
pip uninstall peeka
pip install peeka

# O usa uv
uv pip install peeka

# Verificar instalación
python -c "import peeka; print(peeka.__version__)"
```

---

## Obtener Ayuda

Si ninguna de las soluciones anteriores resuelve tu problema:

1. **Ver registros**:
   ```bash
   peeka-cli --verbose attach <pid>
   ```

2. **GitHub Issues**:
   [https://github.com/wwulfric/peeka/issues](https://github.com/wwulfric/peeka/issues)

3. **Proporcionar información**:
   - Sistema operativo y versión
   - Versión de Python
   - Versión de Peeka
   - Información completa del error
   - Pasos para reproducir

4. **Discusión comunitaria**:
   - GitHub Discussions
   - Stack Overflow (etiqueta: `peeka`)

---

## Documentación Relacionada

- [Guía de Instalación]({% link es/installation.md %})
- [Inicio Rápido]({% link es/quickstart.md %})
- [Referencia de Comandos]({% link es/commands/index.md %})
