"""
Roleigh QuanTrader — 24/7 Background Worker
With independent heartbeat and auto-restart
"""

import time
import datetime
import json
import traceback
import logging
import threading
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

def get_or_create_engine(user):
    username = user.username
    if username in active_engines:
        return active_engines[username]
    logger.info(f"Initializing engine for {username}...")
    engine = TradingEngine()
    engine.set_username(username)
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


def load_settings_from_db_for_worker(engine, username):
    try:
        db = SessionLocal()
        user = db.query(User).filter(User.username == username).first()
        if user and hasattr(user, 'settings_json') and user.settings_json:
            saved = json.loads(user.settings_json)
            engine._deep_merge(engine.settings, saved)
            engine.save_settings()
            logger.info(f"✅ Loaded {len(saved)} settings from DB for {username}")
            db.close()
            return True
        db.close()
    except Exception as e:
        logger.warning(f"Could not load DB settings for {username}: {e}")
    return False

def save_settings_to_db_for_worker(username, settings_dict):
    try:
        db = SessionLocal()
        user = db.query(User).filter(User.username == username).first()
        if user and hasattr(user, 'settings_json'):
            user.settings_json = json.dumps(settings_dict)
            db.commit()
            logger.info(f"💾 Saved settings to DB for {username}")
        db.close()
    except Exception as e:
        logger.warning(f"Could not save settings to DB for {username}: {e}")

def heartbeat_loop():
    """Independent heartbeat thread — NEVER dies, runs every 30 seconds."""
    global HEARTBEAT_RUNNING
    logger.info("💓 Heartbeat thread started (updates every 30s)")
    
    while HEARTBEAT_RUNNING:
        try:
            db = SessionLocal()
            try:
                from sqlalchemy import text
                active_users = db.query(User).filter(User.bot_running == True).all()
                now = datetime.datetime.now()
                for user in active_users:
                    try:
                        db.execute(text("UPDATE users SET last_login=:now WHERE username=:uname"),
                                   {"now": now, "uname": user.username})  # <-- FIX: user.username
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
                logger.warning(f"Heartbeat query error: {e}")
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Heartbeat loop error: {e}")
        
        time.sleep(30)

def run_worker():
    global HEARTBEAT_RUNNING
    logger.info("=" * 60)
    logger.info("Roleigh QuanTrader Worker Started")
    logger.info(f"Time: {datetime.datetime.now()}")
    logger.info("=" * 60)
    
    # Start heartbeat thread
    heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True, name="heartbeat")
    heartbeat_thread.start()
    logger.info("💓 Heartbeat thread launched")
    
    cycle = 0
    
    while True:
        cycle += 1
        db = SessionLocal()
        
        try:
            active_users = db.query(User).filter(User.bot_running == True).all()
            
            if not active_users:
                if cycle % 6 == 0:
                    logger.info(f"[{datetime.datetime.now()}] No active bots. Waiting...")
                db.close()
                time.sleep(10)
                continue
            
            logger.info(f"\n{'='*40}")
            logger.info(f"[{datetime.datetime.now()}] Cycle #{cycle} - {len(active_users)} active bot(s)")
            logger.info(f"{'='*40}")
            
            for user in active_users:
                username = user.username
                try:
                    engine = get_or_create_engine(user)
                    
                    if not engine.connected:
                        logger.info(f"Connecting {username}...")
                        success, msg = connect_engine(engine, user)
                        if not success:
                            logger.error(f"Connection failed for {username}: {msg}")
                            try:
                                db_err = SessionLocal()
                                from sqlalchemy import text
                                db_err.execute(text("UPDATE users SET bot_status=:status WHERE username=:uname"),
                                           {"status": f"❌ Connection failed: {msg[:80]}", "uname": username})
                                db_err.commit()
                                db_err.close()
                            except Exception:
                                pass
                            continue
                        logger.info(f"✅ Connected {username}")
                    
                    # Load settings from DB (this also saves to file)
                    load_settings_from_db_for_worker(engine, username)
                    # DO NOT call engine.load_settings() here — it would overwrite DB settings with stale file data
                    engine.invalidate_all_caches()
                    
                    # Run cycle
                    engine.run_cycle()
                    
                    # Get status AFTER cycle
                    status_msg = engine.status_message
                    buy_count = sum(1 for s in engine.signals_found if s.get("signal") == "BUY")
                    sell_count = sum(1 for s in engine.signals_found if s.get("signal") == "SELL")
                    scan_mode = "Universe" if engine.settings.get("scan_full_universe", True) else "Watchlist"
                    
                    logger.info(f"✅ {username}: {status_msg}")
                    logger.info(f"   Signals: 🟢{buy_count} 🔴{sell_count} | P&L: ${engine.daily_pnl:+,.2f} | Mode: {scan_mode}")
                    
                    # Update status using a fresh DB session
                    try:
                        db_status = SessionLocal()
                        from sqlalchemy import text
                        detailed_status = (
                            f"✅ Cycle #{engine.cycle_count} | "
                            f"{status_msg[:120]} | "
                            f"🟢{buy_count} 🔴{sell_count} | "
                            f"P&L: ${engine.daily_pnl:+,.2f} | "
                            f"Mode: {scan_mode}"
                        )
                        db_status.execute(text("UPDATE users SET bot_status=:status, last_login=:now WHERE username=:uname"),
                                   {"status": detailed_status[:500],
                                    "now": datetime.datetime.now(),
                                    "uname": username})
                        db_status.commit()
                        db_status.close()
                    except Exception as e:
                        logger.warning(f"DB status update failed for {username}: {e}")
                        try:
                            db_status.rollback()
                            db_status.close()
                        except Exception:
                            pass
                    
                    # Save cycle timestamp
                    try:
                        engine.settings["_last_cycle_time"] = datetime.datetime.now().isoformat()
                        engine.settings["_last_cycle_cycles"] = engine.cycle_count
                        engine.settings["_last_cycle_signals"] = len(engine.signals_found)
                        save_settings_to_db_for_worker(username, engine.settings)
                    except Exception:
                        pass
                    
                except Exception as e:
                    logger.error(f"❌ Cycle error for {username}: {e}")
                    traceback.print_exc()
                    # Update status so UI shows the error
                    try:
                        db_err = SessionLocal()
                        from sqlalchemy import text
                        db_err.execute(text("UPDATE users SET bot_status=:status WHERE username=:uname"),
                                   {"status": f"❌ Error: {str(e)[:200]}", "uname": username})
                        db_err.commit()
                        db_err.close()
                    except Exception:
                        pass
                    try:
                        db.rollback()
                    except Exception:
                        pass
            
            # Stop engines for users who clicked Stop
            try:
                db_check = SessionLocal()
                stopped_users = db_check.query(User).filter(User.bot_running == False).all()
                for user in stopped_users:
                    username = user.username
                    if username in active_engines:
                        logger.info(f"🛑 Stopping engine for {username} (user requested stop)")
                        stop_engine(username)
                    try:
                        from sqlalchemy import text
                        db_check.execute(text("UPDATE users SET bot_status='Stopped' WHERE username=:uname"),
                                   {"uname": username})
                        db_check.commit()
                    except Exception:
                        pass
                db_check.close()
            except Exception as e:
                logger.warning(f"Error checking stopped users: {e}")
            
        except Exception as e:
            logger.error(f"❌ Database error: {e}")
            traceback.print_exc()
        finally:
            try:
                db.close()
            except Exception:
                pass
        
        # Calculate sleep time
        if active_users:
            intervals = []
            for user in active_users:
                username = user.username
                if username in active_engines:
                    interval = active_engines[username].settings.get("scan_interval_min", 8) * 60
                    intervals.append(interval)
            sleep_time = max(60, min(intervals) if intervals else 300)
        else:
            sleep_time = 10
        
        logger.info(f"💤 Cycle #{cycle} complete. Sleeping {sleep_time}s...")
        time.sleep(sleep_time)

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
