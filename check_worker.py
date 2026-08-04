"""Quick health check for the Roleigh QuanTrader Worker."""
import sys

print("=" * 60)
print("Roleigh QuanTrader Worker — Health Check")
print("=" * 60)

errors = []

# 1. Check imports
print("\n[1] Checking imports...")
try:
    from core.database import SessionLocal, User, engine
    print("    ✅ core.database imports OK")
except Exception as e:
    print(f"    ❌ core.database import FAILED: {e}")
    errors.append("database_import")

try:
    from trading_engine import TradingEngine, DIVIDEND_STOCKS, GROWTH_STOCKS, US_LONG_TERM
    print("    ✅ trading_engine imports OK")
except Exception as e:
    print(f"    ❌ trading_engine import FAILED: {e}")
    errors.append("trading_engine_import")

try:
    from utils import safe_decrypt
    print("    ✅ utils imports OK")
except Exception as e:
    print(f"    ❌ utils import FAILED: {e}")
    errors.append("utils_import")

# 2. Check database columns
print("\n[2] Checking database columns...")
try:
    import sqlalchemy
    with engine.connect() as conn:
        result = conn.execute(sqlalchemy.text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='users'"
        )).fetchall()
        columns = [row[0] for row in result]
        
        required = ['last_heartbeat', 'bot_running', 'bot_status', 'settings_json', 
                     'trading_mode', 'alpaca_api_key', 'alpaca_secret_key']
        for col in required:
            if col in columns:
                print(f"    ✅ Column '{col}' exists")
            else:
                print(f"    ❌ Column '{col}' MISSING")
                errors.append(f"missing_column_{col}")
except Exception as e:
    print(f"    ❌ Database check FAILED: {e}")
    errors.append("database_check")

# 3. Check active users
print("\n[3] Checking active users...")
try:
    db = SessionLocal()
    users = db.query(User).filter(User.bot_running == True).all()
    print(f"    Found {len(users)} user(s) with bot_running=True:")
    for u in users:
        print(f"      - {u.username} (status: {u.bot_status})")
        
        # Check API keys
        from core.encryption import is_encrypted
        api_key = u.alpaca_api_key or ""
        secret_key = u.alpaca_secret_key or ""
        print(f"        API key set: {bool(api_key)} (encrypted: {is_encrypted(api_key)})")
        print(f"        Secret key set: {bool(secret_key)} (encrypted: {is_encrypted(secret_key)})")
    db.close()
except Exception as e:
    print(f"    ❌ User check FAILED: {e}")
    errors.append("user_check")

# 4. Test API connection for first active user
print("\n[4] Testing Alpaca connection...")
try:
    db = SessionLocal()
    user = db.query(User).filter(User.bot_running == True).first()
    if user:
        from utils import safe_decrypt
        from core.encryption import is_encrypted
        
        api_key = safe_decrypt(user.alpaca_api_key or "")
        secret_key = safe_decrypt(user.alpaca_secret_key or "")
        trading_mode = getattr(user, 'trading_mode', 'paper') or 'paper'
        
        if not api_key or not secret_key:
            print(f"    ❌ API keys are empty for {user.username}")
            errors.append("empty_api_keys")
        else:
            try:
                import alpaca_trade_api as tradeapi
                base_url = 'https://paper-api.alpaca.markets' if trading_mode == 'paper' else 'https://api.alpaca.markets'
                api = tradeapi.REST(api_key, secret_key, base_url=base_url, api_version='v2')
                account = api.get_account()
                print(f"    ✅ Connected to Alpaca ({trading_mode} mode)")
                print(f"       Account status: {account.status}")
                print(f"       Equity: ${float(account.equity):,.2f}")
                print(f"       Cash: ${float(account.cash):,.2f}")
            except Exception as e:
                print(f"    ❌ Alpaca connection FAILED: {e}")
                errors.append("alpaca_connection")
    else:
        print("    No active users to test")
    db.close()
except Exception as e:
    print(f"    ❌ Connection test FAILED: {e}")
    errors.append("connection_test")

# 5. Summary
print("\n" + "=" * 60)
if errors:
    print(f"❌ ISSUES FOUND ({len(errors)}):")
    for e in errors:
        print(f"   - {e}")
    print("\nRun the migration and check your configuration.")
    sys.exit(1)
else:
    print("✅ ALL CHECKS PASSED — Worker should start successfully.")
    sys.exit(0)
