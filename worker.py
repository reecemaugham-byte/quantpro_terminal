"""
Roleigh QuanTrader — 24/7 Background Worker (FIXED)
"""

import time
import datetime
import json
import traceback
import logging
import threading
import os
import signal
from contextlib import contextmanager

from core.database import SessionLocal, User
from trading_engine import TradingEngine
from utils import safe_decrypt

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('worker.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

active_engines = {}
HEARTBEAT_RUNNING = True
RESTART_REQUESTED = threading.Event()


@contextmanager
def db_session():
    """Context manager that ALWAYS closes the session."""
    session = SessionLocal()
    try:
        yield session
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        raise
    finally:
        session.close()


def get_or_create_engine(user):
    """Create engine for user, recreate if settings changed."""
    username = user.username
    
    # Compute hash of current DB settings to detect changes
    current_settings_hash = None
    if hasattr(user, 'settings_json') and user.settings_json:
        current_settings_hash = hash(user.settings_json)

    if username in active_engines:
        engine = active_engines[username]
        # If settings changed in the UI, recreate the engine
        if hasattr(engine, '_settings_hash') and engine._settings_hash != current_settings_hash:
            logger.info(f"🔄 Settings changed for {username}, recreating engine...")
            stop_engine(username)
            # Fall through to create new engine
        else:
            return engine

    logger.info(f"Initializing engine for {username}...")
    engine = TradingEngine()
    engine.set_username(username)
    engine._settings_hash = current_settings_hash
    active_engines[username] = engine
    return engine


def connect_engine(engine, user):
    api_key = safe_decrypt(user.alpaca_api_key or "")
    secret_key = safe_decrypt(user.alpaca_secret_key or "")
    if not api_key or not secret_key:
        return False, "Missing Alpaca API keys"
    trading_mode = getattr(user, 'trading_mode', 'paper') or 'paper'
    is_live = trading_mode == "live"
    success = engine.connect_encrypted(api_key, secret_key, live_mode=is_live)
    return success, "Connected" if success else engine.status_message


def stop_engine(username):
    if username in active_engines:
        logger.info(f"🛑 Stopping engine for {username}...")
        try:
            engine = active_engines[username]
            engine.running = False
            engine._stop_event.set()
            if engine._thread and engine._thread.is_alive():
                engine._thread.join(timeout=5)
        except Exception as e:
            logger.warning(f"Error stopping engine for {username}: {e}")
        finally:
            del active_engines[username]


def load_settings_from_db(engine, username):
    """
    Load settings from DB. DB is the single source of truth.
    Does NOT call engine.save_settings() to avoid file cross-contamination.
    """
    try:
        with db_session() as db:
            user = db.query(User).filter(User.username == username).first()
            if user and hasattr(user, 'settings_json') and user.settings_json:
                saved = json.loads(user.settings_json)
                # ✅ DB settings OVERRIDE engine defaults — key by key
                for key, value in saved.items():
                    if isinstance(value, dict) and isinstance(engine.settings.get(key), dict):
                        engine.settings[key] = {**engine.settings[key], **value}
                    else:
                        engine.settings[key] = value
                engine._settings_hash = hash(user.settings_json)
                logger.info(f"✅ Loaded {len(saved)} settings from DB for {username} (DB wins)")
                return True
            else:
                # No settings in DB — check for scan_full_universe default
                if 'scan_full_universe' not in engine.settings or engine.settings.get('scan_full_universe') is None:
                    engine.settings['scan_full_universe'] = True
                logger.info(f"⚠️ No settings in DB for {username}, using defaults")
                return False
    except Exception as e:
        logger.warning(f"Could not load DB settings for {username}: {e}")
        return False


def save_settings_to_db(username, settings_dict):
    try:
        with db_session() as db:
            user = db.query(User).filter(User.username == username).first()
            if user and hasattr(user, 'settings_json'):
                user.settings_json = json.dumps(settings_dict)
                db.commit()
                logger.info(f"💾 Saved settings to DB for {username}")
    except Exception as e:
        logger.warning(f"Could not save settings to DB for {username}: {e}")


def update_user_status(username, status_message):
    """Helper to update a user's bot_status safely."""
    try:
        with db_session() as db:
            from sqlalchemy import text
            # Try last_heartbeat first, fall back to last_login
            try:
                db.execute(text(
                    "UPDATE users SET bot_status=:status, last_heartbeat=:now WHERE username=:uname"
                ), {"status": status_message[:500], "now": datetime.datetime.now(), "uname": username})
                db.commit()
            except Exception:
                # Column might not exist yet
                db.rollback()
                db.execute(text(
                    "UPDATE users SET bot_status=:status, last_login=:now WHERE username=:uname"
                ), {"status": status_message[:500], "now": datetime.datetime.now(), "uname": username})
                db.commit()
    except Exception as e:
        logger.warning(f"Could not update status for {username}: {e}")


def heartbeat_loop():
    """Independent heartbeat thread — updates every 30s."""
    global HEARTBEAT_RUNNING
    logger.info("💓 Heartbeat thread started (updates every 30s)")
    
    while HEARTBEAT_RUNNING:
        try:
            with db_session() as db:
                from sqlalchemy import text
                active_users = db.query(User).filter(User.bot_running == True, User.is_active == True).all()
                now = datetime.datetime.now()
                for user in active_users:
                    try:
                        try:
                            db.execute(text(
                                "UPDATE users SET last_heartbeat=:now WHERE username=:uname"
                            ), {"now": now, "uname": user.username})
                        except Exception:
                            db.rollback()
                            db.execute(text(
                                "UPDATE users SET last_login=:now WHERE username=:uname"
                            ), {"now": now, "uname": user.username})
                    except Exception as e:
                        logger.warning(f"Heartbeat update failed for {user.username}: {e}")
                try:
                    db.commit()
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Heartbeat loop error: {e}")
        
        time.sleep(30)


def run_worker():
    global HEARTBEAT_RUNNING
    logger.info("=" * 60)
    logger.info("Roleigh QuanTrader Worker Started (FIXED)")
    logger.info(f"Time: {datetime.datetime.now()}")
    logger.info("=" * 60)
    
    # ✅ Write PID file for force restart
    pid_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'worker.pid')
    try:
        with open(pid_path, 'w') as f:
            f.write(str(os.getpid()))
        logger.info(f"📌 Worker PID: {os.getpid()} written to {pid_path}")
    except Exception as e:
        logger.warning(f"Could not write PID file: {e}")
    
    # Start heartbeat thread
    heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True, name="heartbeat")
    heartbeat_thread.start()
    logger.info("💓 Heartbeat thread launched")
    
    # ✅ Signal handler for force restart
    def handle_restart_signal(signum, frame):
        logger.info("🔄 Restart signal received, clearing all engines...")
        for username in list(active_engines.keys()):
            stop_engine(username)
        RESTART_REQUESTED.set()
    
    try:
        signal.signal(signal.SIGUSR1, handle_restart_signal)
        logger.info("📡 Registered SIGUSR1 for force restart")
    except (OSError, ValueError):
        logger.info("📡 SIGUSR1 not available on this platform")
    
    cycle = 0
    
    while True:
        if RESTART_REQUESTED.is_set():
            RESTART_REQUESTED.clear()
            logger.info("🔄 Force restart: all engines cleared, will re-initialize")
        
        cycle += 1
        
        try:
            # ✅ Detach users from DB session before processing
            with db_session() as db:
                active_users = db.query(User).filter(User.bot_running == True).all()
                
                if not active_users:
                    if cycle % 6 == 0:
                        logger.info(f"[{datetime.datetime.now()}] No active bots. Waiting...")
                    time.sleep(10)
                    continue
                
                # Eagerly load data we need before session closes
                user_list = []
                for user in active_users:
                    user_data = {
                        'username': user.username,
                        'alpaca_api_key': user.alpaca_api_key,
                        'alpaca_secret_key': user.alpaca_secret_key,
                        'trading_mode': getattr(user, 'trading_mode', 'paper') or 'paper',
                        'settings_json': getattr(user, 'settings_json', None),
                    }
                    user_list.append(user_data)
            
            logger.info(f"\n{'='*40}")
            logger.info(f"[{datetime.datetime.now()}] Cycle #{cycle} - {len(user_list)} active bot(s)")
            logger.info(f"{'='*40}")
            
            for user_data in user_list:
                username = user_data['username']
                try:
                    class UserProxy:
                        """Lightweight proxy object for passing user data to get_or_create_engine."""
                        pass
                    proxy = UserProxy()
                    
                    proxy.username = user_data['username']
                    proxy.alpaca_api_key = user_data['alpaca_api_key']
                    proxy.alpaca_secret_key = user_data['alpaca_secret_key']
                    proxy.trading_mode = user_data['trading_mode']
                    proxy.settings_json = user_data['settings_json']
                    
                    engine = get_or_create_engine(proxy)
                    
                    if not engine.connected:
                        logger.info(f"Connecting {username}...")
                        success, msg = connect_engine(engine, proxy)
                        if not success:
                            logger.error(f"Connection failed for {username}: {msg}")
                            update_user_status(username, f"❌ Connection failed: {msg[:80]}")
                            continue
                        logger.info(f"✅ Connected {username}")
                    
                    # ✅ Load settings from DB — DB is source of truth
                    load_settings_from_db(engine, username)
                    
                    # ✅ Only clear price/position caches, NOT universe cache
                    engine.invalidate_all_caches()
                    
                    # Check if universe mode changed — if so, clear universe cache
                    prev_mode = engine.settings.get("_prev_scan_full_universe", None)
                    curr_mode = engine.settings.get("scan_full_universe", True)
                    if prev_mode is not None and prev_mode != curr_mode:
                        logger.info(f"🔄 {username}: Scan mode changed from {'Universe' if prev_mode else 'Watchlist'} to {'Universe' if curr_mode else 'Watchlist'}, clearing cache")
                        engine.invalidate_universe_cache()
                    engine.settings["_prev_scan_full_universe"] = curr_mode
                    
                    # Run cycle
                    engine.run_cycle()
                    
                    # Get status AFTER cycle
                    status_msg = engine.status_message
                    buy_count = sum(1 for s in engine.signals_found if s.get("signal") == "BUY")
                    sell_count = sum(1 for s in engine.signals_found if s.get("signal") == "SELL")
                    scan_mode = "Universe" if engine.settings.get("scan_full_universe", True) else "Watchlist"
                    
                    logger.info(f"✅ {username}: {status_msg}")
                    logger.info(f"   Signals: 🟢{buy_count} 🔴{sell_count} | P&L: ${engine.daily_pnl:+,.2f} | Mode: {scan_mode}")
                    
                    # Update status
                    detailed_status = (
                        f"✅ Cycle #{engine.cycle_count} | "
                        f"{status_msg[:120]} | "
                        f"🟢{buy_count} 🔴{sell_count} | "
                        f"P&L: ${engine.daily_pnl:+,.2f} | "
                        f"Mode: {scan_mode}"
                    )
                    update_user_status(username, detailed_status)
                    
                    # Save cycle timestamp to DB only (minimal update to avoid overwriting UI changes)
                    try:
                        with db_session() as db:
                            user = db.query(User).filter(User.username == username).first()
                            if user and hasattr(user, 'settings_json'):
                                current = json.loads(user.settings_json) if user.settings_json else {}
                                current["_last_cycle_time"] = datetime.datetime.now().isoformat()
                                current["_last_cycle_cycles"] = engine.cycle_count
                                current["_last_cycle_signals"] = len(engine.signals_found)
                                user.settings_json = json.dumps(current)
                                db.commit()
                    except Exception:
                        pass
                    
                except Exception as e:
                    logger.error(f"❌ Cycle error for {username}: {e}")
                    traceback.print_exc()
                    update_user_status(username, f"❌ Error: {str(e)[:200]}")
            
            # Stop engines for users who clicked Stop
            try:
                with db_session() as db:
                    from sqlalchemy import text
                    usernames_with_engines = list(active_engines.keys())
                    if usernames_with_engines:
                        stopped = db.query(User).filter(
                            User.bot_running == False,
                            User.username.in_(usernames_with_engines)
                        ).all()
                        
                        for row in stopped:
                            stopped_username = row.username
                            if stopped_username in active_engines:
                                logger.info(f"🛑 Stopping engine for {stopped_username} (user requested stop)")
                                stop_engine(stopped_username)
                                update_user_status(stopped_username, "Stopped")
            except Exception as e:
                logger.warning(f"Error checking stopped users: {e}")
        
        except Exception as e:
            logger.error(f"❌ Outer loop error: {e}")
            traceback.print_exc()
        
        # Calculate sleep time
        sleep_time = 300
        try:
            intervals = []
            for uname, eng in active_engines.items():
                interval = eng.settings.get("scan_interval_min", 8) * 60
                intervals.append(interval)
            if intervals:
                sleep_time = max(60, min(intervals))
        except Exception:
            pass
        
        logger.info(f"💤 Cycle #{cycle} complete. Sleeping {sleep_time}s...")
        for _ in range(sleep_time):
            if not HEARTBEAT_RUNNING:
                break
            time.sleep(1)

if __name__ == "__main__":
    try:
        run_worker()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user (KeyboardInterrupt)")
        HEARTBEAT_RUNNING = False
    except Exception as e:
        logger.critical(f"Worker crashed with fatal error: {e}")
        traceback.print_exc()
        HEARTBEAT_RUNNING = False
