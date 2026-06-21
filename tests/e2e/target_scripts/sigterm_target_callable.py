import os
import signal
import sys
import time

sentinel_path = os.environ.get("PEEKA_SENTINEL_PATH", "")

def _user_handler(signum: int, frame: object) -> None:
    if sentinel_path:
        with open(sentinel_path, "w") as f:
            f.write("handled")
    sys.exit(42)

signal.signal(signal.SIGTERM, _user_handler)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from peeka.core.agent import PeekaAgent  # noqa: E402

PeekaAgent(os.getpid())
while True:
    time.sleep(0.1)
