---
layout: default
title: attach
parent: Referencia de Comandos
nav_order: 1
---

# attach - Adjuntar al proceso objetivo
{: .no_toc }

Inyecta el Agente Peeka en el proceso Python objetivo y establece un canal de diagnóstico.
{: .fs-6 .fw-300 }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Descripción General

El comando `attach` es el primer paso para usar Peeka, inyecta el código del Agente Peeka en el proceso objetivo y inicia el servidor Unix Domain Socket, estableciendo un canal de comunicación para los comandos de diagnóstico posteriores.

### Principio de Funcionamiento

**Python 3.14+**:
- Usa la API `sys.remote_exec()` de PEP 768
- Seguro, eficiente, soporte oficial

**Python 3.9-3.13**:
- Usa el mecanismo GDB + ptrace
- Alternativa de compatibilidad

## Uso en TUI

**TUI se adjunta automáticamente al iniciar**: Simplemente ejecuta el comando `peeka` para iniciar TUI, y mostrará automáticamente el selector de procesos:

1. Ejecuta `peeka` (sin parámetros)
2. Selecciona el proceso objetivo en el selector de procesos
3. Presiona Enter para adjuntar automáticamente y entrar en la interfaz principal

**Características de TUI**:
- Lista de procesos se actualiza en tiempo real
- Muestra PID del proceso, línea de comandos, uso de CPU/memoria
- Soporta filtrado de búsqueda (ingresa palabras clave para filtrar)
- Verifica permisos automáticamente (muestra disponibilidad de PEP 768 o GDB)

**Equivalente CLI**: Todos los ejemplos a continuación usan comandos CLI para demostrar, TUI proporciona una interfaz gráfica con la misma funcionalidad.

---

## Sintaxis

```bash
peeka-cli attach <pid> [options]
```

### Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `pid` | int | ✅ | PID del proceso objetivo |

### Opciones

| Opción | Descripción | Valor por defecto |
|--------|-------------|-------------------|
| `--timeout` | Tiempo de espera para adjunte (segundos) | 30 |
| `--socket-dir` | Directorio de archivos Socket | `/tmp` |

---

## Ejemplos de Uso

### Adjunte Básico

```bash
# Adjuntar al proceso 12345
peeka-cli attach 12345
```

Salida:
```json
{"type":"status","level":"info","message":"Attaching to process 12345"}
{"type":"status","level":"info","message":"Using PEP 768 remote_exec"}
{"type":"success","command":"attach","data":{"pid":12345,"socket":"/tmp/peeka_12345.sock"}}
```

### Encontrar PID del proceso

```bash
# Usa ps para encontrar
ps aux | grep python

# Usa pgrep
pgrep -f "my_app.py"

# Usa pidof
pidof python3
```

### Adjuntar y ejecutar comando inmediatamente

```bash
# Adjuntar y observar inmediatamente
peeka-cli attach 12345 && peeka-cli watch "app.func"
```

---

## Requisitos de Permisos

### Sistema Linux

#### Mismo Usuario

La forma más simple es usar el mismo usuario para ejecutar Peeka:

```bash
# El proceso objetivo y Peeka se ejecutan con user1
user1$ python my_app.py  # PID: 12345
user1$ peeka-cli attach 12345  # ✅ Éxito
```

#### Diferente Usuario (necesita sudo)

```bash
# El proceso objetivo se ejecuta con user1, necesita sudo
user1$ python my_app.py  # PID: 12345
user2$ sudo peeka-cli attach 12345  # ✅ Éxito
```

#### Configuración ptrace_scope

Verifica la configuración actual:
```bash
cat /proc/sys/kernel/yama/ptrace_scope
```

| Valor | Descripción | Disponibilidad de Peeka |
|-------|-------------|-------------------------|
| 0 | Sin restricción (no recomendado) | ✅ Todos los usuarios pueden adjuntar |
| 1 | Solo procesos padre-hijo o CAP_SYS_PTRACE | ✅ Configuración recomendada |
| 2 | Solo CAP_SYS_PTRACE | ✅ Necesita sudo |
| 3 | Totalmente deshabilitado | ❌ No se puede usar |

Modificación temporal (para pruebas):
```bash
echo 1 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

Modificación permanente:
```bash
echo "kernel.yama.ptrace_scope = 1" | sudo tee /etc/sysctl.d/10-ptrace.conf
sudo sysctl -p /etc/sysctl.d/10-ptrace.conf
```

### Contenedores Docker

Necesitas agregar la capability `SYS_PTRACE`:

```bash
# Agregar al ejecutar el contenedor
docker run --cap-add=SYS_PTRACE your-image

# docker-compose.yml
services:
  app:
    cap_add:
      - SYS_PTRACE
    security_opt:
      - seccomp=unconfined
```

### Sistema SELinux

Verifica el estado de SELinux:
```bash
getenforce  # Enforcing, Permissive, Disabled
```

Permitir ptrace temporalmente:
```bash
sudo setsebool -P deny_ptrace off
```

---

## Formato de Salida

### Respuesta Exitosa

```json
{
  "type": "success",
  "command": "attach",
  "data": {
    "pid": 12345,
    "socket": "/tmp/peeka_12345.sock",
    "python_version": "3.12.0",
    "attach_method": "remote_exec"
  }
}
```

### Respuesta de Error

```json
{
  "type": "error",
  "command": "attach",
  "error": "Operation not permitted: ptrace access denied"
}
```

---

## Resolución de Problemas

### Error: Operation not permitted

**Causa**: Permisos insuficientes

**Solución**:
1. Usa el mismo usuario o sudo
2. Verifica la configuración de ptrace_scope
3. Verifica la configuración de SELinux

```bash
# Verificar propietario del proceso
ps -o user= -p 12345

# Usa sudo
sudo peeka-cli attach 12345

# Relajar restricción ptrace (para pruebas)
echo 1 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

### Error: Process not found

**Causa**: El PID no existe o ya terminó

**Solución**:
```bash
# Confirmar que el proceso existe
ps -p 12345

# Volver a buscar el PID
pgrep -f "my_app.py"
```

### Error: Python debugging symbols not found (Python < 3.14)

**Causa**: Faltan símbolos de depuración de Python

**Solución**:
```bash
# Debian/Ubuntu
sudo apt-get install python3-dbg

# RHEL/CentOS
sudo yum install python3-debuginfo
```

### Error: GDB not found (Python < 3.14)

**Causa**: GDB no está instalado

**Solución**:
```bash
# Debian/Ubuntu
sudo apt-get install gdb

# RHEL/CentOS
sudo yum install gdb
```

### Error: Timeout attaching to process

**Causa**: Tiempo de espera agotado (el proceso objetivo puede estar bloqueado)

**Solución**:
```bash
# Aumentar tiempo de espera
peeka-cli attach 12345 --timeout 60

# Verificar estado del proceso objetivo
ps -p 12345 -o stat=
```

---

## Consideraciones de Seguridad

### Aislamiento de Procesos

- Peeka solo puede adjuntar a procesos locales
- No soporta adjunte remoto
- Unix Domain Socket solo es accesible localmente

### Mínimos Permisos

- En entorno de producción se recomienda usar el mismo usuario para ejecutar
- Evita usar permisos de root
- Desadjunta (detach) procesos que ya no necesitan diagnóstico oportunamente

### Seguridad de Inyección de Código

- El código del Agente solo ejecuta funciones de diagnóstico
- No modifica la lógica de negocio
- Todas las inyecciones se pueden restaurar mediante el comando reset

---

## Comandos Relacionados

- [detach]({% link es/commands/detach.md %}) - Desadjuntar del proceso
- [watch]({% link es/commands/watch.md %}) - Observar llamadas a funciones
- [reset]({% link es/commands/reset.md %}) - Restablecer inyección

---

## Referencias

- [PEP 768 - Secure External Debugger](https://peps.python.org/pep-0768/)
- [Linux ptrace(2) Manual](https://man7.org/linux/man-pages/man2/ptrace.2.html)
- [Yama LSM Documentation](https://www.kernel.org/doc/html/latest/admin-guide/LSM/Yama.html)
