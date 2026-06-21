import os
import signal
import sys
import time

signal.signal(signal.SIGTERM, signal.SIG_IGN)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from peeka.core.agent import PeekaAgent  # noqa: E402

PeekaAgent(os.getpid())
while True:
    time.sleep(0.1)
