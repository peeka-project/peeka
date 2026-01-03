"""
Agent Code - Runs inside target process
This code is injected into the target process and handles command execution
"""
import sys
import socket
import json
import tempfile
import threading
import traceback
from pathlib import Path


# Peeka Agent - runs in target process
class PeekaAgent:
    """Agent running inside target process"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.running = True
        self.sock_path = f"/tmp/peeka_{session_id}.sock"
        self.server = None
        self.command_handlers = {}
        self._register_handlers()

    def _register_handlers(self):
        """Register command handlers"""
        from peeka.commands.watch import WatchCommand
        self.command_handlers['watch'] = WatchCommand()

    def start(self):
        """Start agent server"""
        try:
            # Create Unix domain socket
            self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

            # Remove old socket if exists
            if Path(self.sock_path).exists():
                Path(self.sock_path).unlink()

            self.server.bind(self.sock_path)
            self.server.listen(1)

            # Mark as ready
            Path(f"/tmp/peeka_{self.session_id}.ready").touch()

            # Run in background thread
            thread = threading.Thread(target=self._accept_loop, daemon=True)
            print("[peeka Agent] Started and listening for connections")
            thread.start()
            print("[peeka Agent] Ready for commands")

        except Exception as e:
            print(f"[peeka Agent] Start failed: {e}", file=sys.stderr)
            traceback.print_exc()

    def _accept_loop(self):
        """Accept client connections"""
        while self.running:
            try:
                conn, _ = self.server.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(conn,),
                    daemon=True
                ).start()
            except Exception as e:
                if self.running:
                    print(f"[peeka Agent] Accept error: {e}", file=sys.stderr)

    def _handle_client(self, conn):
        """Handle client requests"""
        try:
            while True:
                # Receive command (length-prefixed JSON)
                length_bytes = conn.recv(4)
                if not length_bytes:
                    break

                length = int.from_bytes(length_bytes, 'big')
                data = conn.recv(length).decode('utf-8')
                command = json.loads(data)

                # Execute command
                result = self._execute_command(command)

                # Send response
                response = json.dumps(result).encode('utf-8')
                conn.sendall(len(response).to_bytes(4, 'big'))
                conn.sendall(response)

        except Exception as e:
            print(f"[peeka Agent] Client error: {e}", file=sys.stderr)
        finally:
            conn.close()

    def _execute_command(self, command: dict) -> dict:
        """Execute diagnostic command"""
        cmd_type = command.get('type')

        handler = self.command_handlers.get(cmd_type)
        if handler:
            try:
                return handler.execute(command)
            except Exception as e:
                return {
                    'status': 'error',
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }
        else:
            return {
                'status': 'error',
                'error': f'Unknown command type: {cmd_type}'
            }

    def stop(self):
        """Stop agent"""
        self.running = False
        if self.server:
            self.server.close()


# Initialize and start agent
try:
    agent = PeekaAgent("{{SESSION_ID}}")
    agent.start()

    # Store in global to prevent garbage collection
    if not hasattr(sys, '_peeka_agents'):
        sys._peeka_agents = {}
    sys._peeka_agents["{{SESSION_ID}}"] = agent

except Exception as e:
    print(f"[peeka Agent] Initialization failed: {e}", file=sys.stderr)
    traceback.print_exc()