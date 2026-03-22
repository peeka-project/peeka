---
layout: default
title: Diseño de Arquitectura
nav_order: 8
---

# Diseño de Arquitectura
{: .no_toc }

Conoce en profundidad los principios de diseño, arquitectura y detalles de implementación de Peeka.
{: .fs-6 .fw-300 }

## Tabla de Contenidos
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Objetivos de Diseño

El diseño del Agente Peeka sigue estos objetivos centrales:

### Baja Intrusión

La ejecución del Agente no debe afectar significativamente el rendimiento y la funcionalidad del proceso objetivo. Según la experiencia de la industria, el sobrecoste de rendimiento de una herramienta de diagnóstico en producción debe controlarse dentro del **5%**. Peeka garantiza que el impacto de las operaciones de diagnóstico en el proceso objetivo se minimiza a través de un mecanismo de inyección de decoradores cuidadosamente diseñado y una estrategia de almacenamiento en búfer de datos de observación.

### Alta Confiabilidad

El Agente debe mantener un funcionamiento estable en diversas situaciones anómalas y no debe causar que el proceso objetivo se bloquee o se vuelva anormal debido a sus propios errores. Durante el diseño se presta especial atención a la gestión de recursos, incluida la correcta liberación de recursos del sistema como memoria, descriptores de archivos e hilos, para evitar problemas de estabilidad a largo plazo causados por fugas de recursos.

### Tiempo Real

Los datos de diagnóstico se pueden transmitir al cliente en tiempo real, permitiendo a los desarrolladores observar inmediatamente los cambios en el comportamiento del proceso objetivo. Esto es especialmente importante para localizar problemas intermitentes. Peeka adopta un protocolo de comunicación de flujo basado en Unix Domain Socket, logrando una latencia de transmisión de datos de **nivel de milisegundos**.

### Extensibilidad

La arquitectura del Agente puede admitir convenientemente nuevos comandos de diagnóstico y extensiones de funcionalidad sin necesidad de refactorizar a gran escala el código existente. Adopta un diseño modular, separando preocupaciones como comunicación, ejecución de comandos y observación, e interactúa a través de interfaces claramente definidas.

---

## Arquitectura General

```
┌─────────────────────────────────────────────────────────────┐
│                        User Space                            │
│                                                               │
│  ┌──────────────┐                    ┌──────────────┐       │
│  │  CLI/TUI     │                    │ Target       │       │
│  │              │                    │ Process      │       │
│  │  - peeka-cli │                    │              │       │
│  │  - peeka     │                    │ ┌──────────┐ │       │
│  └──────┬───────┘                    │ │  Agent   │ │       │
│         │                            │ │ (injected)│ │       │
│         │ Unix Domain Socket         │ └────┬─────┘ │       │
│         │ /tmp/peeka_<pid>.sock      │      │       │       │
│         └────────────────────────────┼──────┘       │       │
│                                      │              │       │
│  ┌─────────────────┐                 │ ┌──────────┐ │       │
│  │ AgentClient     │←────JSON────────┤ │ Commands │ │       │
│  │                 │                 │ │          │ │       │
│  │ - send_command  │                 │ │ - watch  │ │       │
│  │ - recv_response │                 │ │ - trace  │ │       │
│  └─────────────────┘                 │ │ - stack  │ │       │
│                                      │ │ - monitor│ │       │
│                                      │ │ - logger │ │       │
│                                      │ │ - memory │ │       │
│                                      │ │ - inspect│ │       │
│                                      │ │ - thread │ │       │
│                                      │ │ - top    │ │       │
│                                      │ │ - sc/sm  │ │       │
│                                      │ │ - reset  │ │       │
│                                      │ │ - detach │ │       │
│                                      │ └──────────┘ │       │
│                                      │              │       │
│                                      │ ┌──────────┐ │       │
│                                      │ │ Injector │ │       │
│                                      │ │          │ │       │
│                                      │ │ Function │ │       │
│                                      │ │ Wrapping │ │       │
│                                      │ └──────────┘ │       │
│                                      └──────────────┘       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      Kernel Space                            │
│                                                               │
│  ┌──────────────────────────────────────────┐               │
│  │  Process Attachment                       │               │
│  │                                           │               │
│  │  Python 3.14+:  sys.remote_exec()        │               │
│  │  Python < 3.14: GDB + ptrace             │               │
│  └──────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

---

## Componentes Centrales

### 1. Adjuntar Proceso (attach.py)

Responsable de inyectar el código del Agente en el proceso objetivo.

#### Python 3.14+

Usa la API `sys.remote_exec()` de PEP 768:

```python
import sys

# Inyectar y ejecutar código del Agente
sys.remote_exec(pid, agent_script_path)
```

**Ventajas**:
- Soporte oficial, seguro y confiable
- Sin dependencias externas (GDB)
- Compatible multiplataforma

#### Python 3.9-3.13

Usa el plan alternativo GDB + ptrace:

```python
# 1. Adjuntar GDB al proceso
gdb -p <pid>

# 2. Obtener el GIL
call PyGILState_Ensure()

# 3. Ejecutar código Python
call PyRun_SimpleString("exec(open('/path/agent.py').read())")

# 4. Liberar el GIL
call PyGILState_Release(gil_state)

# 5. Desadjuntar
detach
quit
```

**Requisitos**:
- GDB 7.3+
- Símbolos de depuración de Python
- Permiso CAP_SYS_PTRACE

### 2. Núcleo del Agente (agent.py)

Código central inyectado en el proceso objetivo, responsable de:

#### Servidor Socket

```python
import socket
import threading

class PeekaAgent:
    def __init__(self):
        self.socket_path = f"/tmp/peeka_{os.getpid()}.sock"
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.socket_path)
        self.server.listen(1)

    def start(self):
        # Ejecutar en un hilo en segundo plano, no bloquea el hilo principal
        thread = threading.Thread(target=self._serve, daemon=True)
        thread.start()
```

#### Distribución de Comandos

```python
def _handle_command(self, command: dict) -> dict:
    cmd_type = command.get("command")
    handler = self.handlers.get(cmd_type)

    if handler:
        return handler.execute(command.get("params", {}))
    else:
        return {"status": "error", "error": f"Unknown command: {cmd_type}"}
```

#### Gestión de Recursos

- Búfer de datos de observación de tamaño fijo (10000 entradas por defecto)
- Limpieza automática de observaciones expiradas
- Apagado elegante de hilos

### 3. Inyector de Decoradores (injector.py)

Envuelve dinámicamente funciones objetivo, agregando lógica de observación.

#### Envoltorio de Función

```python
class DecoratorInjector:
    def inject_function(self, func, observer):
        original_func = func

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Observación en la entrada
            if observer.at_enter:
                observer.on_enter(args, kwargs)

            try:
                # Ejecutar la función original
                result = original_func(*args, **kwargs)

                # Observación exitosa
                if observer.at_exit:
                    observer.on_exit(result)

                return result
            except Exception as e:
                # Observación de excepción
                if observer.at_exception:
                    observer.on_exception(e)
                raise

        return wrapper
```

#### Restauración Segura

```python
def restore_function(self, target):
    # Restaurar la función original
    if hasattr(target, '__wrapped__'):
        original = target.__wrapped__
        # Reemplazo seguro (maneja varios casos límite)
        ...
```

### 4. Cliente (client.py)

Biblioteca cliente para comunicarse con el Agente.

#### Cliente Sincrónico

```python
class AgentClient:
    def send_command(self, command: dict) -> dict:
        # Enviar comando (prefijo de longitud + JSON)
        msg = json.dumps(command).encode()
        self.sock.sendall(len(msg).to_bytes(4, 'big') + msg)

        # Recibir respuesta
        length = int.from_bytes(self.sock.recv(4), 'big')
        response = self.sock.recv(length)
        return json.loads(response)
```

#### Cliente de Streaming

```python
class StreamingAgentClient(AgentClient):
    def stream_observations(self):
        # Generador, recibe datos de observación en tiempo real
        while True:
            msg = self._recv_message()
            if msg.get("type") == "observation":
                yield msg
            elif msg.get("type") == "event":
                if msg["event"] == "watch_stopped":
                    break
```

### 5. Sistema de Comandos (commands/)

Implementación modular de comandos.

#### Clase Base

```python
class BaseCommand(ABC):
    def __init__(self, agent: "PeekaAgent"):
        self.agent = agent

    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecutar comando y devolver resultado"""
        pass
```

#### Registro de Comandos

```python
def _register_handlers(self):
    from peeka.commands.watch import WatchCommand
    from peeka.commands.trace import TraceCommand
    # ... importación retardada para evitar dependencias circulares

    self.handlers = {
        "watch": WatchCommand(self),
        "trace": TraceCommand(self),
        # ...
    }
```

---

## Protocolo de Comunicación

### Formato de Mensaje

Todos los mensajes usan el formato **prefijo de longitud + JSON**:

```
┌─────────────┬─────────────────────────┐
│  Length     │   JSON Payload          │
│  (4 bytes)  │   (variable length)     │
└─────────────┴─────────────────────────┘
```

### Formato de Solicitud

```json
{
  "command": "watch",
  "params": {
    "pattern": "module.func",
    "times": 10,
    "condition": "cost > 100"
  }
}
```

### Formato de Respuesta

#### Respuesta Exitosa

```json
{
  "status": "success",
  "data": {
    "watch_id": "watch_001",
    "pattern": "module.func"
  }
}
```

#### Respuesta de Error

```json
{
  "status": "error",
  "error": "Cannot find target: invalid.pattern",
  "traceback": "..."
}
```

#### Observación en Streaming

```json
{
  "type": "observation",
  "watch_id": "watch_001",
  "timestamp": 1705586200.123,
  "func_name": "module.func",
  "args": [1, 2],
  "result": 3,
  "duration_ms": 0.123
}
```

---

## Mecanismos de Seguridad

### 1. Seguridad de Expresiones (safeeval/)

Evaluación segura de expresiones basada en la biblioteca `simpleeval`.

#### Lista Blanca AST

Solo permite nodos AST seguros:

```python
SAFE_NODES = {
    ast.Expression, ast.Compare, ast.BinOp, ast.UnaryOp,
    ast.Num, ast.Str, ast.NameConstant, ast.Name,
    ast.List, ast.Tuple, ast.Dict, ast.Subscript,
    # ... otros nodos seguros
}
```

#### Protección de Atributos

Bloquea acceso a atributos peligrosos:

```python
UNSAFE_ATTRS = {
    '__class__', '__subclasses__', '__bases__',
    '__import__', '__builtins__', '__globals__'
}
```

#### Lista Negra de Funciones

Deshabilita funciones peligrosas:

```python
UNSAFE_FUNCTIONS = {
    'eval', 'exec', 'compile', 'open',
    '__import__', 'input', 'globals', 'locals'
}
```

### 2. Límites de Recursos

#### Búfer de Memoria

```python
class ObservationManager:
    def __init__(self, max_size=10000):
        self.buffer = collections.deque(maxlen=max_size)
```

#### Control de Tiempo de Espera

```python
@timeout(seconds=30)
def execute_command(command):
    # La ejecución de comandos tiene protección por timeout
    pass
```

### 3. Captura de Excepciones

#### Tres Capas de Protección

1. **Módulo central**: Lanza excepciones, falla rápido
2. **Capa de comandos**: Captura y devuelve diccionario de error
3. **Capa de Agente**: Protección final, agrega traceback

```python
try:
    result = command.execute(params)
except Exception as e:
    result = {
        "status": "error",
        "error": str(e),
        "traceback": traceback.format_exc()
    }
```

---

## Optimizaciones de Rendimiento

### 1. Inyección de Decoradores

- Usa `functools.wraps` para preservar metadatos
- Minimiza el sobrecoste del envoltorio (< 1%)
- Compilación condicional (solo inyecta cuando es necesario)

### 2. API sys.monitoring (Python 3.12+)

El comando trace usa la API `sys.monitoring`:

```python
import sys

def trace_callback(code, instruction_offset, args):
    # Callback de bajo costo
    pass

sys.monitoring.use_tool_id(sys.monitoring.PROFILER_ID, "peeka")
sys.monitoring.register_callback(
    sys.monitoring.PROFILER_ID,
    sys.monitoring.events.CALL,
    trace_callback
)
```

**Comparación de Rendimiento**:
- `sys.monitoring`: < 5% de sobrecoste
- `sys.settrace`: < 20% de sobrecoste (Python 3.9-3.11)

### 3. Transmisión en Streaming

- Usa generadores para evitar acumulación de memoria
- Baja latencia de transmisión con Unix Domain Socket
- Parseo JSON en streaming

---

## Desarrollo de Extensiones

### Agregar un Nuevo Comando

1. Crear clase de comando:

```python
# peeka/commands/mycommand.py
from peeka.commands.base import BaseCommand
from typing import Dict, Any

class MyCommand(BaseCommand):
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Implementar lógica del comando
            result = self._do_work(params)
            return {"status": "success", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}
```

2. Registrar en el Agente:

```python
# peeka/core/agent.py
def _register_handlers(self):
    from peeka.commands.mycommand import MyCommand
    self.handlers["mycommand"] = MyCommand(self)
```

3. Agregar interfaz CLI:

```python
# peeka/cli/main.py
parser.add_subcommand("mycommand", help="My new command")
```

### Agregar una Vista TUI

1. Crear clase de vista:

```python
# peeka/tui/views/myview.py
from textual.widgets import Static

class MyView(Static):
    def compose(self):
        yield Label("My View")
```

2. Registrar atajo de teclado:

```python
# peeka/tui/screens/main.py
BINDINGS = [
    ("5", "show_myview", "My View"),
]
```

---

## Referencias

- [PEP 768 - Secure External Debugger](https://peps.python.org/pep-0768/)
- [PEP 669 - Low Impact Monitoring](https://peps.python.org/pep-0669/)
- [Documentación de simpleeval](https://github.com/danthedeckie/simpleeval)
