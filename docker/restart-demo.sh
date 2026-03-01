#!/bin/bash
pkill -f 'demo.py --mode loop' 2>/dev/null
sleep 0.5
python /app/examples/demo.py --mode loop >>/tmp/demo.log 2>&1 &
echo "demo.py started (pid=$!), log: /tmp/demo.log"
