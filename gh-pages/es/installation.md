---
layout: default
title: Guía de Instalación
nav_order: 2
---

# Guía de Instalación
{: .no_toc }

Esta guía te ayudará a instalar y configurar Peeka en diferentes entornos.
{: .fs-6 .fw-300 }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Requisitos del Sistema

### Requisitos Básicos

- **Versión de Python**: Python 3.9 o superior
- **Sistema Operativo**: Linux (recomendado), macOS
- **Permisos**: Se necesitan permisos para adjuntarse al proceso objetivo (mismo UID o CAP_SYS_PTRACE)

### Comparación de Versiones de Python

| Versión de Python | Mecanismo de Adjunte | Requisitos Adicionales |
|-------------------|-----------------------|-------------------------|
| **3.14+** | PEP 768 `sys.remote_exec` | Ninguno |
| **3.9-3.13** | Alternativa GDB + ptrace | GDB, python3-dbg, CAP_SYS_PTRACE |

---

## Métodos de Instalación

### Instalación con pip (recomendado)

#### Versión básica (solo CLI)

```bash
pip install peeka
```

#### Versión completa (incluye TUI)

```bash
pip install peeka[tui]
```

### Instalación con uv

```bash
# Versión básica
uv pip install peeka

# Versión completa (incluye TUI)
uv pip install "peeka[tui]"

# Entorno de desarrollo (desde código fuente)
uv sync --dev
```

### Instalación desde código fuente

```bash
# Clonar el repositorio
git clone https://github.com/wwulfric/peeka.git
cd peeka

# Instalar (versión básica)
uv pip install -e .

# Instalar (incluye TUI)
uv pip install -e ".[tui]"

# Entorno de desarrollo (dependencias completas)
uv sync --dev
```

---

## Configuración Adicional para Python < 3.14

Para versiones de Python 3.9-3.13, necesitas instalar GDB y símbolos de depuración de Python.

### Debian/Ubuntu

```bash
sudo apt-get update
sudo apt-get install gdb python3-dbg
```

### RHEL/CentOS/Fedora

```bash
sudo yum install gdb python3-debuginfo
```

### macOS

```bash
brew install gdb

# El primer uso necesita autorizar GDB
# Referencia: https://sourceware.org/gdb/wiki/PermissionsDarwin
```

---

## Configuración de Permisos

### Sistema Linux

#### Relajar temporalmente la restricción ptrace (solo para pruebas)

```bash
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

#### Configuración permanente (recomendado para producción)

Edita `/etc/sysctl.d/10-ptrace.conf`:

```
kernel.yama.ptrace_scope = 1
```

Luego aplica la configuración:

```bash
sudo sysctl -p /etc/sysctl.d/10-ptrace.conf
```

#### Sistema SELinux (Fedora/RHEL)

```bash
# Verificar estado de SELinux
getenforce

# Permitir ptrace temporalmente
sudo setsebool -P deny_ptrace off

# O crear una política SELinux para procesos específicos
```

### Contenedores Docker

Agrega el parámetro `--cap-add=SYS_PTRACE` al ejecutar tu contenedor Docker:

```bash
docker run --cap-add=SYS_PTRACE your-image
```

O configúralo en docker-compose.yml:

```yaml
services:
  app:
    image: your-image
    cap_add:
      - SYS_PTRACE
    security_opt:
      - seccomp=unconfined
```

---

## Verificar la Instalación

### Verificar versión

```bash
peeka-cli --version
```

### Ejecutar prueba

```bash
# Iniciar aplicación de demostración
python -m peeka.examples.demo --mode loop

# En otra terminal prueba adjuntar
peeka-cli attach <pid>
```

### Verificar dependencias

```bash
# Verificar versión de Python
python --version

# Verificar GDB (Python < 3.14)
gdb --version

# Verificar símbolos de depuración de Python (Python < 3.14)
python -c "import sys; print(hasattr(sys, 'gettotalrefcount'))"
```

---

## Preguntas Frecuentes

### Adjunte falló: permisos insuficientes

**Mensaje de error**:
```
Error: Operation not permitted
```

**Solución**:
1. Asegúrate de tener el mismo UID que el proceso objetivo o usa sudo
2. Verifica la configuración de ptrace_scope
3. Para Docker, asegúrate de haber agregado CAP_SYS_PTRACE

### Python < 3.14: no se encuentran los símbolos de depuración

**Mensaje de error**:
```
Error: Python debugging symbols not found
```

**Solución**:
```bash
# Debian/Ubuntu
sudo apt-get install python3-dbg

# RHEL/CentOS
sudo yum install python3-debuginfo
```

### Versión de GDB demasiado antigua

**Mensaje de error**:
```
Error: GDB version 7.3+ required
```

**Solución**:
```bash
# Actualizar GDB
sudo apt-get update
sudo apt-get install --only-upgrade gdb

# O compila la última versión desde código fuente
```

### macOS: GDB necesita autorización

**Mensaje de error**:
```
Error: Unable to find Mach task port for process-id
```

**Solución**:
Consulta [GDB on macOS](https://sourceware.org/gdb/wiki/PermissionsDarwin) para realizar la autorización de firma de código.

---

## Siguientes Pasos

Después de completar la instalación, puedes:

- [Inicio Rápido]({% link es/quickstart.md %}) - Aprender el uso básico
- [Referencia de Comandos]({% link es/commands/index.md %}) - Ver todos los comandos disponibles
- [Ejemplos y Tutoriales]({% link es/examples.md %}) - Escenarios prácticos de aplicación

---

## Obtener Ayuda

Si encuentras problemas durante la instalación:

1. Consulta [Resolución de Problemas]({% link es/troubleshooting.md %})
2. Pregunta en [GitHub Issues](https://github.com/wwulfric/peeka/issues)
