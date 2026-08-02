#!/bin/bash
# Permanent 24/7 VPS Background Services for OFC Movies Server & ngrok Tunnel

pkill -9 -f "python3 /root/server.py" 2>/dev/null
pkill -9 -f "ngrok http 3000" 2>/dev/null
sleep 1

> /root/server.log
> /root/ngrok.log

# 1. Start Python Server 24/7 in detached background loop
setsid nohup bash -c '
while true; do
    python3 /root/server.py >> /root/server.log 2>&1
    sleep 2
done
' > /dev/null 2>&1 &

sleep 2

# 2. Start ngrok Tunnel 24/7 in detached background loop
setsid nohup bash -c '
while true; do
    ngrok http 3000 >> /root/ngrok.log 2>&1
    sleep 3
done
' > /dev/null 2>&1 &

echo "Permanent 24/7 VPS Services Launched!"
