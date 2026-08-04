#!/bin/bash
# Roleigh QuanTrader Worker — Auto-restart wrapper
# This script starts the worker and restarts it if it crashes

echo "=========================================="
echo "Starting Roleigh QuanTrader Worker"
echo "Time: $(date)"
echo "=========================================="

cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run the migration first
echo "[STARTUP] Running database migration..."
python -c "
from core.database import engine, migrate_db
import sqlalchemy
migrate_db()
print('[STARTUP] Migration complete')

# Verify last_heartbeat column exists
with engine.connect() as conn:
    result = conn.execute(sqlalchemy.text(
        \"SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='last_heartbeat'\"
    )).fetchall()
    if result:
        print('[STARTUP] last_heartbeat column: OK')
    else:
        print('[STARTUP] Creating last_heartbeat column...')
        is_pg = 'postgresql' in str(engine.url).lower() or 'postgres' in str(engine.url).lower()
        ts = 'TIMESTAMP' if is_pg else 'DATETIME'
        conn.execute(sqlalchemy.text(f'ALTER TABLE users ADD COLUMN last_heartbeat {ts}'))
        conn.commit()
        print('[STARTUP] last_heartbeat column: CREATED')
"

MAX_RESTARTS=5
RESTART_COUNT=0
RESTART_DELAY=10

while [ $RESTART_COUNT -lt $MAX_RESTARTS ]; do
    echo "[WORKER] Starting worker (attempt $((RESTART_COUNT+1))/$MAX_RESTARTS)..."
    python worker.py
    
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
