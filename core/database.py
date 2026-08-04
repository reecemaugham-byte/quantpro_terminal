import sqlalchemy
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
import datetime
import bcrypt
import os
import json

# --- Database Setup ---
DATABASE_URL = os.environ.get("DATABASE_URL", "")

if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    engine = sqlalchemy.create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
    )
else:
    DATABASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
    os.makedirs(DATABASE_DIR, exist_ok=True)
    sqlite_path = os.path.join(DATABASE_DIR, 'cascadetrade_users.db')
    DATABASE_URL = f"sqlite:///{sqlite_path}"
    engine = sqlalchemy.create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ==========================================
# USER TABLE
# ==========================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    email = Column(String, unique=True, index=True, nullable=True)

    # API Keys (stored encrypted — encryption handled by core/encryption.py)
    alpaca_api_key = Column(String, nullable=True)
    alpaca_secret_key = Column(String, nullable=True)
    finnhub_api_key = Column(String, nullable=True)

    # Discord Webhooks
    discord_webhook_url = Column(String, nullable=True)
    discord_webhook_url_daily = Column(String, nullable=True)
    openai_api_key = Column(String, nullable=True)

    # --- Bucket Allocation Settings ---
    dividend_pct = Column(Float, default=0.35)
    growth_pct = Column(Float, default=0.35)
    penny_pct = Column(Float, default=0.30)
    min_dividend_yield = Column(Float, default=0.03)
    penny_price_threshold = Column(Float, default=5.0)
    profit_skim_pct = Column(Float, default=1.0)  # 1.0 = 100% skim to withdrawal

    # --- Security & Compliance ---
    terms_accepted = Column(Boolean, default=False)
    terms_accepted_date = Column(DateTime, nullable=True)
    login_attempts = Column(Integer, default=0)
    account_locked_until = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)
    last_heartbeat = Column(DateTime, nullable=True)


    # --- Tier System ---
    tier = Column(String, default="starter")
    tier_expires = Column(DateTime, nullable=True)
    
    # --- Trading Mode ---
    trading_mode = Column(String, default="paper")  # "paper" or "live"
    bot_running = Column(Boolean, default=False)  # 24/7 Worker control
    bot_status = Column(String, default="Stopped")  # Worker status message

    # --- Full Settings JSON ---
    settings_json = Column(Text, nullable=True)  # Complete settings dict stored as JSON

    # --- Subscription & Payments (Stripe) ---
    subscription_plan = Column(String, default="starter")      # starter, pro, fund, admin
    subscription_id = Column(String, nullable=True)             # Stripe subscription ID
    subscription_status = Column(String, default="inactive")    # active, past_due, cancelled, inactive
    subscription_start = Column(DateTime, nullable=True)        # When the subscription started
    subscription_end = Column(DateTime, nullable=True)         # When the current billing period ends

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ==========================================
# DIVIDEND PAYMENT TABLE
# ==========================================
class DividendPayment(Base):
    __tablename__ = "dividend_payments"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    symbol = Column(String)
    amount = Column(Float)
    pay_date = Column(String)
    status = Column(String, default="received")
    notes = Column(String, nullable=True)
    recorded_at = Column(DateTime, default=datetime.datetime.utcnow)


# ==========================================
# TRADE LOG TABLE
# ==========================================
class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, index=True)
    timestamp = Column(String(50), nullable=False)
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)
    qty = Column(Float, nullable=True)
    price = Column(Float, nullable=True)
    filled_price = Column(Float, nullable=True)
    filled_qty = Column(Float, nullable=True)
    slippage_cost = Column(Float, nullable=True)
    sec_fee = Column(Float, nullable=True)
    order_id = Column(String(100), nullable=True)
    status = Column(String(20), nullable=True)
    reason = Column(String(500), nullable=True)
    confidence = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    estimated_cost = Column(Float, nullable=True)
    sector = Column(String(50), nullable=True)
    bucket = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# Create all tables
Base.metadata.create_all(bind=engine)


# ==========================================
# MIGRATION: Add new columns if they don't exist
# ==========================================
def migrate_db():
    """Add new columns to existing tables if they don't exist.
    Works with both PostgreSQL and SQLite."""
    is_postgres = 'postgresql' in str(engine.url).lower() or 'postgres' in str(engine.url).lower()
    ts_type = 'TIMESTAMP' if is_postgres else 'DATETIME'

    with engine.connect() as conn:
        # ==========================================
        # CRITICAL: Ensure last_heartbeat exists FIRST
        # (The app crashes if this column is missing)
        # ==========================================
        try:
            if is_postgres:
                conn.execute(sqlalchemy.text(
                    f"ALTER TABLE users ADD COLUMN IF NOT EXISTS last_heartbeat {ts_type}"
                ))
            else:
                conn.execute(sqlalchemy.text(
                    f"ALTER TABLE users ADD COLUMN last_heartbeat {ts_type}"
                ))
            conn.commit()
            print("[MIGRATE] Added last_heartbeat column")
        except Exception:
            conn.rollback()
            # Column already exists, that's fine

        # ==========================================
        # Add all other missing columns
        # ==========================================
        new_columns = [
            ('dividend_pct', 'FLOAT'),
            ('growth_pct', 'FLOAT'),
            ('penny_pct', 'FLOAT'),
            ('min_dividend_yield', 'FLOAT'),
            ('penny_price_threshold', 'FLOAT'),
            ('profit_skim_pct', 'FLOAT'),
            ('terms_accepted', 'BOOLEAN'),
            ('terms_accepted_date', ts_type),
            ('login_attempts', 'INTEGER'),
            ('account_locked_until', ts_type),
            ('last_login', ts_type),
            ('tier', 'VARCHAR'),
            ('tier_expires', ts_type),
            ('subscription_plan', "VARCHAR DEFAULT 'starter'"),
            ('subscription_id', 'VARCHAR'),
            ('subscription_status', "VARCHAR DEFAULT 'inactive'"),
            ('subscription_start', ts_type),
            ('subscription_end', ts_type),
            ('finnhub_api_key', 'VARCHAR'),
            ('trading_mode', "VARCHAR DEFAULT 'paper'"),
            ('bot_running', "BOOLEAN DEFAULT FALSE"),
            ('bot_status', "VARCHAR DEFAULT 'Stopped'"),
            ('settings_json', 'TEXT'),
        ]
        for col_name, col_type in new_columns:
            try:
                if is_postgres:
                    conn.execute(sqlalchemy.text(
                        f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                    ))
                else:
                    conn.execute(sqlalchemy.text(
                        f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"
                    ))
                conn.commit()
            except Exception:
                conn.rollback()
                # Column already exists, that's fine

        # ==========================================
        # TIER NAME MIGRATION (one-time)
        # Only rename if old names still exist
        # ==========================================
        try:
            result = conn.execute(sqlalchemy.text(
                "SELECT COUNT(*) FROM users WHERE tier IN ('starter', 'pro', 'fund')"
            ))
            old_count = result.scalar()
            if old_count and int(old_count) > 0:
                conn.execute(sqlalchemy.text("UPDATE users SET tier = 'free' WHERE tier = 'starter'"))
                conn.execute(sqlalchemy.text("UPDATE users SET tier = 'live_trading' WHERE tier = 'pro'"))
                conn.execute(sqlalchemy.text("UPDATE users SET tier = 'pro_trader' WHERE tier = 'fund'"))
                conn.execute(sqlalchemy.text("UPDATE users SET subscription_plan = 'free' WHERE subscription_plan = 'starter'"))
                conn.execute(sqlalchemy.text("UPDATE users SET subscription_plan = 'live_trading' WHERE subscription_plan = 'pro'"))
                conn.execute(sqlalchemy.text("UPDATE users SET subscription_plan = 'pro_trader' WHERE subscription_plan = 'fund'"))
                conn.commit()
                print("[MIGRATE] Renamed old tier names to new tier names")
        except Exception:
            conn.rollback()
            # Migration already ran or error


# Run migration on import
migrate_db()

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_user(db: SessionLocal, username: str, password: str, terms_accepted: bool = False):
    """Create a new user account with default tier."""
    hashed_pw = hash_password(password)
    db_user = User(
        username=username,
        hashed_password=hashed_pw,
        dividend_pct=0.35,
        growth_pct=0.35,
        penny_pct=0.30,
        min_dividend_yield=0.03,
        penny_price_threshold=5.0,
        profit_skim_pct=1.0,
        terms_accepted=terms_accepted,
        terms_accepted_date=datetime.datetime.utcnow() if terms_accepted else None,
        tier="free",
        trading_mode="paper",
        bot_running=False,
        bot_status="Stopped",
        subscription_plan="free",
        subscription_status="inactive",
        is_active=True,
        created_at=datetime.datetime.utcnow(),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def authenticate_user(db: SessionLocal, username: str, password: str):
    """Authenticate a user with username and password."""
    from core.rate_limit import rate_limiter

    allowed, message = rate_limiter.check_login_allowed(username)
    if not allowed:
        return False

    user = db.query(User).filter(User.username == username).first()
    if not user:
        rate_limiter.record_login_attempt(username, success=False)
        return False

    if not user.is_active:
        rate_limiter.record_login_attempt(username, success=False)
        return False

    if not verify_password(password, user.hashed_password):
        rate_limiter.record_login_attempt(username, success=False)
        return False

    rate_limiter.record_login_attempt(username, success=True)
    user.last_login = datetime.datetime.utcnow()
    db.commit()

    return user


# ==========================================
# TIER MANAGEMENT FUNCTIONS
# ==========================================

def get_user_tier(db: SessionLocal, username: str) -> str:
    """Get the effective tier for a user.

    Checks both the legacy 'tier' column and the Stripe subscription fields.
    If the subscription has expired or is inactive, downgrades to 'starter'.
    Returns 'starter' if not set or expired.
    """
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return "starter"

    # --- Check Stripe subscription status first ---
    if user.subscription_id and user.subscription_status == "active":
        # Active Stripe subscription — use subscription_plan
        # If subscription_end has passed, downgrade
        if user.subscription_end and user.subscription_end < datetime.datetime.utcnow():
            # Subscription period ended — downgrade
            user.tier = "free"
            user.tier_expires = None
            user.subscription_status = "inactive"
            db.commit()
            return "free"
        # Subscription is active and current
        return user.subscription_plan or "free"

    # --- Fall back to legacy tier column ---
    if hasattr(user, 'tier') and user.tier:
        if user.tier_expires and user.tier_expires < datetime.datetime.utcnow():
            # Tier has expired — downgrade to free
            user.tier = "free"
            user.tier_expires = None
            db.commit()
            return "free"
        return user.tier

    return "free"

def set_user_tier(db: SessionLocal, username: str, tier: str, expires: datetime.datetime = None) -> bool:
    """Set a user's tier (legacy method — for admin overrides or manual upgrades)."""
    valid_tiers = ["free", "starter", "live_trading", "pro", "pro_trader", "fund", "admin"]
    if tier not in valid_tiers:
        return False

    user = db.query(User).filter(User.username == username).first()
    if not user:
        return False

    user.tier = tier
    user.tier_expires = expires
    db.commit()
    return True


def update_subscription(db: SessionLocal, username: str, plan: str,
                        subscription_id: str, status: str = "active",
                        start_date: datetime.datetime = None,
                        end_date: datetime.datetime = None) -> bool:
    """Update a user's Stripe subscription details and sync the tier.

    Called by the Stripe webhook handler when a checkout.session.completed
    or customer.subscription.updated event is received.
    """
    valid_plans = ["free", "live_trading", "pro_trader", "admin"]
    if plan not in valid_plans:
        return False

    user = db.query(User).filter(User.username == username).first()
    if not user:
        return False

    user.subscription_plan = plan
    user.subscription_id = subscription_id
    user.subscription_status = status
    user.subscription_start = start_date
    user.subscription_end = end_date

    # Keep legacy tier column in sync
    if status == "active":
        user.tier = plan
        user.tier_expires = end_date
    elif status in ("cancelled", "inactive", "past_due"):
        user.tier = "free"
        user.tier_expires = None

    db.commit()
    return True


def deactivate_subscription(db: SessionLocal, username: str) -> bool:
    """Deactivate a user's subscription — downgrades to free.

    Called when a Stripe subscription is deleted, expires, or payment fails
    after the grace period.
    """
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return False

    user.subscription_status = "inactive"
    user.subscription_plan = "free"
    user.tier = "free"
    user.tier_expires = None

    db.commit()
    return True


def get_user_by_subscription_id(db: SessionLocal, stripe_subscription_id: str):
    """Look up a user by their Stripe subscription ID.

    Used by the webhook handler to find the local user for a Stripe event.
    Returns the User object or None.
    """
    return db.query(User).filter(
        User.subscription_id == stripe_subscription_id
    ).first()


def get_user_by_stripe_customer_id(db: SessionLocal, stripe_customer_id: str):
    """Look up a user by their Stripe customer ID.

    Falls back to email match if no direct customer_id link exists.
    Returns the User object or None.
    """
    # If we add a stripe_customer_id column later, query it here
    # For now, we rely on the subscription_id or email
    return None


def get_all_users_with_tiers(db: SessionLocal) -> list:
    """Get all users with their tier info. For admin panel."""
    users = db.query(User).all()
    result = []
    for u in users:
        result.append({
            "id": u.id,
            "username": u.username,
            "tier": getattr(u, 'tier', 'free') or 'free',
            "tier_expires": str(u.tier_expires) if hasattr(u, 'tier_expires') and u.tier_expires else None,
            "email": u.email,
            "created_at": str(u.created_at) if u.created_at else None,
            "last_login": str(u.last_login) if u.last_login else None,
            "is_active": u.is_active,
            "terms_accepted": u.terms_accepted,
            "alpaca_connected": bool(u.alpaca_api_key),
            "discord_connected": bool(u.discord_webhook_url),
            "openai_connected": bool(u.openai_api_key),
            "subscription_plan": getattr(u, 'subscription_plan', 'free') or 'free',
            "subscription_status": getattr(u, 'subscription_status', 'inactive') or 'inactive',
            "subscription_end": str(u.subscription_end) if hasattr(u, 'subscription_end') and u.subscription_end else None,
        })
    return result

# ==========================================
# TERMS & COMPLIANCE FUNCTIONS
# ==========================================

def accept_terms(db: SessionLocal, username: str) -> bool:
    """Mark that a user has accepted the Terms of Service."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return False

    user.terms_accepted = True
    user.terms_accepted_date = datetime.datetime.utcnow()
    db.commit()
    return True


def has_accepted_terms(db: SessionLocal, username: str) -> bool:
    """Check if a user has accepted the Terms of Service."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return False
    return bool(user.terms_accepted)


def update_last_login(db: SessionLocal, username: str) -> None:
    """Update the last login timestamp for a user."""
    user = db.query(User).filter(User.username == username).first()
    if user:
        user.last_login = datetime.datetime.utcnow()
        db.commit()


# ==========================================
# GDPR FUNCTIONS — Data Portability & Deletion
# ==========================================

def export_user_data(db: SessionLocal, username: str) -> dict:
    """Export all data for a user (GDPR Right to Data Portability)."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return {}

    user_data = {
        "profile": {
            "username": user.username,
            "email": user.email,
            "created_at": str(user.created_at) if user.created_at else None,
            "last_login": str(user.last_login) if user.last_login else None,
            "terms_accepted": user.terms_accepted,
            "terms_accepted_date": str(user.terms_accepted_date) if user.terms_accepted_date else None,
            "tier": getattr(user, 'tier', 'starter') or 'starter',
            "tier_expires": str(user.tier_expires) if hasattr(user, 'tier_expires') and user.tier_expires else None,
        },
        "settings": {
            "dividend_pct": user.dividend_pct,
            "growth_pct": user.growth_pct,
            "penny_pct": user.penny_pct,
            "min_dividend_yield": user.min_dividend_yield,
            "penny_price_threshold": user.penny_price_threshold,
            "profit_skim_pct": user.profit_skim_pct,
        },
        "integrations": {
            "alpaca_connected": bool(user.alpaca_api_key),
            "discord_connected": bool(user.discord_webhook_url),
            "openai_connected": bool(user.openai_api_key),
            "finnhub_connected": bool(getattr(user, 'finnhub_api_key', None)),
        },
        "subscription": {
            "plan": getattr(user, 'subscription_plan', 'starter'),
            "status": getattr(user, 'subscription_status', 'inactive'),
            "start_date": str(user.subscription_start) if hasattr(user, 'subscription_start') and user.subscription_start else None,
            "end_date": str(user.subscription_end) if hasattr(user, 'subscription_end') and user.subscription_end else None,
        },
        "dividend_history": [],
        "trade_history_count": 0,
    }

    dividends = db.query(DividendPayment).filter(
        DividendPayment.username == username
    ).order_by(DividendPayment.recorded_at.desc()).all()

    for div in dividends:
        user_data["dividend_history"].append({
            "symbol": div.symbol,
            "amount": div.amount,
            "pay_date": div.pay_date,
            "status": div.status,
            "recorded_at": str(div.recorded_at) if div.recorded_at else None,
        })

    trade_count = db.query(Trade).filter(Trade.username == username).count()
    user_data["trade_history_count"] = trade_count

    user_data["trading_data"] = {
        "note": "Trading logs, signals, and performance data are stored in data/trading_logs/. "
                "These can be exported separately from the Portfolio tab in the app.",
    }

    return user_data


def export_user_data_json(db: SessionLocal, username: str) -> str:
    """Export user data as a JSON string."""
    data = export_user_data(db, username)
    return json.dumps(data, indent=2)


def delete_user_and_data(db: SessionLocal, username: str) -> bool:
    """Delete a user account and all associated data (GDPR Right to Erasure)."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return False

    db.query(Trade).filter(Trade.username == username).delete()
    db.query(DividendPayment).filter(DividendPayment.username == username).delete()
    db.delete(user)
    db.commit()

    return True


# ==========================================
# DIVIDEND FUNCTIONS
# ==========================================

def record_dividend(db: SessionLocal, username: str, symbol: str, amount: float,
                    pay_date: str = "", status: str = "received", notes: str = ""):
    """Record a dividend payment in the database."""
    div = DividendPayment(
        username=username,
        symbol=symbol,
        amount=amount,
        pay_date=pay_date,
        status=status,
        notes=notes,
    )
    db.add(div)
    db.commit()
    db.refresh(div)
    return div


def get_dividend_history(db: SessionLocal, username: str):
    """Get all dividend payments for a user."""
    return db.query(DividendPayment).filter(
        DividendPayment.username == username
    ).order_by(DividendPayment.recorded_at.desc()).all()


# ==========================================
# TRADE LOG FUNCTIONS
# ==========================================

def save_trade_to_db(username: str, trade_record: dict) -> bool:
    """Save a single trade record to the database."""
    db = SessionLocal()
    try:
        trade = Trade(
            username=username,
            timestamp=trade_record.get("timestamp", ""),
            symbol=trade_record.get("symbol", ""),
            side=trade_record.get("side", ""),
            qty=trade_record.get("qty"),
            price=trade_record.get("price"),
            filled_price=trade_record.get("filled_price"),
            filled_qty=trade_record.get("filled_qty"),
            slippage_cost=trade_record.get("slippage_cost"),
            sec_fee=trade_record.get("sec_fee"),
            order_id=trade_record.get("order_id", ""),
            status=trade_record.get("status", ""),
            reason=trade_record.get("reason", ""),
            confidence=trade_record.get("confidence"),
            stop_loss=trade_record.get("stop_loss"),
            take_profit=trade_record.get("take_profit"),
            estimated_cost=trade_record.get("estimated_cost"),
            sector=trade_record.get("sector", ""),
            bucket=trade_record.get("bucket", ""),
        )
        db.add(trade)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"Error saving trade to DB: {e}")
        return False
    finally:
        db.close()


def load_trades_from_db(username: str, limit: int = 5000) -> list:
    """Load trade records from the database for a given user."""
    db = SessionLocal()
    try:
        trades = db.query(Trade).filter(Trade.username == username).order_by(Trade.id.asc()).limit(limit).all()
        result = []
        for t in trades:
            result.append({
                "timestamp": t.timestamp or "",
                "symbol": t.symbol or "",
                "side": t.side or "",
                "qty": t.qty,
                "price": t.price,
                "filled_price": t.filled_price,
                "filled_qty": t.filled_qty,
                "slippage_cost": t.slippage_cost,
                "sec_fee": t.sec_fee,
                "order_id": t.order_id or "",
                "status": t.status or "",
                "reason": t.reason or "",
                "confidence": t.confidence,
                "stop_loss": t.stop_loss,
                "take_profit": t.take_profit,
                "estimated_cost": t.estimated_cost,
                "sector": t.sector or "",
                "bucket": t.bucket or "",
            })
        return result
    except Exception as e:
        print(f"Error loading trades from DB: {e}")
        return []
    finally:
        db.close()


def clear_trades_from_db(username: str) -> bool:
    """Delete all trade records for a user (for GDPR right to be forgotten)."""
    db = SessionLocal()
    try:
        db.query(Trade).filter(Trade.username == username).delete()
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"Error clearing trades from DB: {e}")
        return False
    finally:
        db.close()


# ==========================================
# FINNHUB API KEY FUNCTIONS
# ==========================================

def save_finnhub_api_key(db: SessionLocal, username: str, api_key: str) -> bool:
    """Save or update a user's Finnhub API key."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return False
    user.finnhub_api_key = api_key
    db.commit()
    return True


def get_finnhub_api_key(db: SessionLocal, username: str) -> str:
    """Get a user's Finnhub API key. Returns empty string if not set."""
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.finnhub_api_key:
        return ""
    return user.finnhub_api_key
