import os
import sqlalchemy
from sqlalchemy import text

# This reads the database URL from your DigitalOcean environment
DATABASE_URL = os.environ.get("DATABASE_URL", "")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found. Make sure you run this in the App Console.")
    exit(1)

# Fix postgres:// to postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = sqlalchemy.create_engine(DATABASE_URL)

print("Connecting to database...")
print("=" * 50)

def add_column(conn, table, column, col_type):
    """Add a column to a table if it doesn't already exist."""
    try:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"))
        conn.commit()
        print(f"  ✅ Added: {column}")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"  ⏭️  Already exists: {column}")
        else:
            print(f"  ❌ Error: {column} — {e}")

with engine.connect() as conn:
    print("\n1. Adding missing columns to users table...")
    print("-" * 50)

    # Core columns for bot control
    add_column(conn, "users", "trading_mode", "VARCHAR DEFAULT 'paper'")
    add_column(conn, "users", "bot_running", "BOOLEAN DEFAULT FALSE")
    add_column(conn, "users", "bot_status", "VARCHAR DEFAULT 'Stopped'")
    add_column(conn, "users", "settings_json", "TEXT")

    # Auth & account columns
    add_column(conn, "users", "terms_accepted", "BOOLEAN DEFAULT FALSE")
    add_column(conn, "users", "terms_accepted_date", "TIMESTAMP")
    add_column(conn, "users", "login_attempts", "INTEGER DEFAULT 0")
    add_column(conn, "users", "account_locked_until", "TIMESTAMP")
    add_column(conn, "users", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    add_column(conn, "users", "last_login", "TIMESTAMP")
    add_column(conn, "users", "last_heartbeat", "TIMESTAMP")

    # Tier & subscription columns
    add_column(conn, "users", "tier", "VARCHAR DEFAULT 'free'")
    add_column(conn, "users", "tier_expires", "TIMESTAMP")
    add_column(conn, "users", "subscription_plan", "VARCHAR DEFAULT 'free'")
    add_column(conn, "users", "subscription_id", "VARCHAR")
    add_column(conn, "users", "subscription_status", "VARCHAR DEFAULT 'inactive'")
    add_column(conn, "users", "subscription_start", "TIMESTAMP")
    add_column(conn, "users", "subscription_end", "TIMESTAMP")
    add_column(conn, "users", "is_active", "BOOLEAN DEFAULT TRUE")

    # API key columns
    add_column(conn, "users", "finnhub_api_key", "VARCHAR")

    # Trading preference columns
    add_column(conn, "users", "dividend_pct", "FLOAT DEFAULT 0.35")
    add_column(conn, "users", "growth_pct", "FLOAT DEFAULT 0.35")
    add_column(conn, "users", "penny_pct", "FLOAT DEFAULT 0.30")
    add_column(conn, "users", "min_dividend_yield", "FLOAT DEFAULT 0.03")
    add_column(conn, "users", "penny_price_threshold", "FLOAT DEFAULT 5.0")
    add_column(conn, "users", "profit_skim_pct", "FLOAT DEFAULT 1.0")

    print("\n2. Updating tier names...")
    print("-" * 50)
    try:
        conn.execute(text("UPDATE users SET tier = 'free' WHERE tier = 'starter'"))
        conn.execute(text("UPDATE users SET tier = 'live_trading' WHERE tier = 'pro'"))
        conn.execute(text("UPDATE users SET tier = 'pro_trader' WHERE tier = 'fund'"))
        conn.execute(text("UPDATE users SET subscription_plan = 'free' WHERE subscription_plan = 'starter' OR subscription_plan IS NULL"))
        conn.execute(text("UPDATE users SET subscription_plan = 'live_trading' WHERE subscription_plan = 'pro'"))
        conn.execute(text("UPDATE users SET subscription_plan = 'pro_trader' WHERE subscription_plan = 'fund'"))
        conn.commit()
        print("  ✅ Tier names updated")
    except Exception as e:
        print(f"  ❌ Tier update error: {e}")

    print("\n3. Verifying columns...")
    print("-" * 50)
    result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"))
    columns = sorted([row[0] for row in result.fetchall()])
    print(f"  Total columns: {len(columns)}")

    required = [
        "bot_running", "bot_status", "settings_json", "trading_mode",
        "tier", "subscription_plan", "last_login", "last_heartbeat", "created_at",
        "terms_accepted", "finnhub_api_key",
    ]
    for col in required:
        status = "✅" if col in columns else "❌"
        print(f"  {status} {col}")

    print("\n4. Checking user settings_json...")
    print("-" * 50)
    try:
        import json
        users_result = conn.execute(text("SELECT username, bot_running, trading_mode, LENGTH(settings_json) as settings_len, settings_json FROM users")).fetchall()
        for row in users_result:
            username = row[0]
            bot_running = row[1]
            trading_mode = row[2]
            settings_len = row[3] if row[3] else 0
            settings_json = row[4]
            
            if settings_json:
                try:
                    s = json.loads(settings_json)
                    scan_mode = s.get("scan_full_universe", "NOT SET (will use True)")
                    watchlist_count = len(s.get("watchlist", []))
                    universe_count = s.get("universe_scan_count", "NOT SET (will use 300)")
                    print(f"  ✅ {username} | bot={bot_running} | mode={trading_mode} | settings={settings_len} chars | scan_full_universe={scan_mode} | watchlist={watchlist_count} stocks | universe_count={universe_count}")
                except Exception as e:
                    print(f"  ⚠️  {username} | bot={bot_running} | mode={trading_mode} | settings JSON PARSE ERROR: {e}")
            else:
                print(f"  ⚠️  {username} | bot={bot_running} | mode={trading_mode} | NO SETTINGS (will use DEFAULT_SETTINGS: scan_full_universe=True, default watchlist)")
    except Exception as e:
        print(f"  ❌ Error checking settings: {e}")

print("\n" + "=" * 50)
print("Database fix complete! You can close this console.")
print("Now run: python worker.py")
print("=" * 50)

