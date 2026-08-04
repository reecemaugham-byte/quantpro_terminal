#!/bin/bash
echo "=========================================="
echo "Starting Roleigh QuanTrader Worker"
echo "Time: $(date)"
echo "=========================================="

cd /workspace

PYTHON=/workspace/.heroku/python/bin/python

# Run database migration first
echo "[STARTUP] Running database migration..."
$PYTHON -c "
from core.database import migrate_db
migrate_db()
print('[STARTUP] Migration complete')
"

MAX_RESTARTS=5
RESTART_COUNT=0
RESTART_DELAY=10

while [ $RESTART_COUNT -lt $MAX_RESTARTS ]; do
    echo "[WORKER] Starting worker (attempt $((RESTART_COUNT+1))/$MAX_RESTARTS)..."
    $PYTHON worker.py
    
    EXIT_CODE=$?
    echo "[WORKER] Worker exited with code $EXIT_CODE"
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[WORKER] Clean shutdown, not restarting."
        break
    fi
    
    RESTART_COUNT=$((RESTART_COUNT+1))
    echo "[WORKER] Crashed. Restarting in ${RESTART_DELAY}s... (attempt $RESTART_COUNT/$MAX_RESTARTS)"
    sleep $RESTART_DELAY
    RESTART_DELAY=$((RESTART_DELAY * 2))
done

if [ $RESTART_COUNT -ge $MAX_RESTARTS ]; then
    echo "[WORKER] Max restarts reached. Giving up."
    exit 1
fi
