import sys

# Execute a print statement in a remote Python process with PID 12345
script = "script.py"
# with open(script, "w") as f:
#    f.write("print('Hello from remote execution!')")
try:
    sys.remote_exec(72996, script)
except Exception as e:
    print(f"Failed to execute code: {e}")
