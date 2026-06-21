import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from peeka.core.agent import PeekaAgent

PeekaAgent(os.getpid())
while True:
    time.sleep(0.1)
