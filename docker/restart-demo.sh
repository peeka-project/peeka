#!/bin/bash
pkill -f '/opt/demo.py --mode loop' 2>/dev/null
sleep 0.5
python /opt/demo.py --mode loop >>/tmp/demo.log 2>&1 &
echo "demo.py started (pid=$!), log: /tmp/demo.log"
