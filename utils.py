"""
utils.py — CascadeTrade Terminal
Shared utility functions, constants, and helpers.
Used by app.py and trading_engine.py.
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ==========================================
# LOGGING SETUP
# ==========================================
def setup_logging(name: str = "cascadetrade", level: int = logging.INFO) -> logging.Logger:
    """Create and configure a logger for the app."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger

logger = setup_logging()

# ==========================================
# CONSTANTS
# ==========================================
BUCKET_ICONS = {
    "dividend": "🟢",
    "growth": "🔵",
    "penny": "🔴",
    "withdrawal": "🟡",
    "long_term": "🟢",
}

SECTOR_MAP = {
    "AAPL": "Tech", "MSFT": "Tech", "GOOGL": "Tech", "AMZN": "Tech",
    "NVDA": "Tech", "TSLA": "Auto/Tech", "META": "Tech", "AMD": "Tech",
    "NFLX": "Tech", "PYPL": "Fintech", "SQ": "Fintech", "ROKU": "Tech",
    "ZM": "Tech", "PLTR": "Tech", "COIN": "Fintech", "SOFI": "Fintech",
    "RIVN": "Auto/Tech", "LCID": "Auto/Tech", "NIO": "Auto/Tech",
    "MARA": "Crypto", "RIOT": "Crypto", "BAC": "Financials",
    "C": "Financials", "WFC": "Financials", "GS": "Financials",
    "MS": "Financials", "JPM": "Financials", "CCL": "Travel",
    "NCLH": "Travel", "UAL": "Travel", "AAL": "Travel", "DAL": "Travel",
    "DIS": "Media", "WBD": "Media", "PARA": "Media", "SNAP": "Tech",
    "PINS": "Tech", "SHOP": "Tech", "ETSY": "Tech", "BABA": "China Tech",
    "JD": "China Tech", "PDD": "China Tech", "XOM": "Energy",
    "CVX": "Energy", "FANG": "Energy", "MRNA": "Biotech", "BIIB": "Biotech",
    "F": "Auto", "GM": "Auto", "NKE": "Consumer", "INTC": "Tech",
    "MU": "Tech", "LRCX": "Tech",
    "JNJ": "Healthcare", "PG": "Consumer Staples", "KO": "Consumer Staples",
    "PEP": "Consumer Staples", "V": "Fintech", "MA": "Fintech",
    "UNH": "Healthcare", "HD": "Consumer", "COST": "Consumer",
    "ABBV": "Healthcare", "LLY": "Healthcare", "MRK": "Healthcare",
    "TMO": "Healthcare", "AVGO": "Tech", "TXN": "Tech", "LIN": "Materials",
    "WM": "Industrials", "RTX": "Industrials", "HON": "Industrials",
    "UPS": "Industrials", "CAT": "Industrials", "DE": "Industrials",
    "LOW": "Consumer", "BLK": "Financials", "CME": "Financials",
    "ICE": "Financials", "MMC": "Financials", "AON": "Financials",
    "VZ": "Telecom", "T": "Telecom", "BRK-B": "Financials",
    "WBA": "Consumer", "IBM": "Tech", "CSCO": "Tech", "PFE": "Healthcare",
    "MO": "Consumer Staples", "PM": "Consumer Staples", "BMY": "Healthcare",
    "GILD": "Healthcare", "O": "REITs", "OHI": "REITs", "STAG": "REITs",
    "VICI": "REITs", "AMT": "REITs", "PLD": "REITs", "DLR": "REITs",
    "CRM": "Tech", "ADBE": "Tech", "INTU": "Tech",
    "SNOW": "Tech", "DDOG": "Tech", "NET": "Tech", "ZS": "Tech",
    "CRWD": "Tech", "REGN": "Biotech", "VRTX": "Biotech",
}

US_QUICK_TURNOVER = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META",
    "AMD", "NFLX", "PYPL", "SQ", "ROKU", "ZM", "PLTR", "COIN",
    "SOFI", "RIVN", "LCID", "NIO", "MARA", "RIOT",
    "BAC", "C", "WFC", "GS", "MS", "JPM",
    "CCL", "NCLH", "UAL", "AAL", "DAL",
    "DIS", "WBD", "PARA", "SNAP", "PINS", "SHOP", "ETSY",
    "BABA", "JD", "PDD",
    "XOM", "CVX", "FANG",
    "MRNA", "BIIB",
    "F", "GM", "NKE", "INTC", "MU", "LRCX",
]

US_LONG_TERM = [
    "JNJ", "PG", "KO", "PEP", "V", "MA", "UNH", "HD", "COST",
    "ABBV", "LLY", "MRK", "TMO", "AVGO", "TXN", "AAPL", "MSFT",
    "BRK-B", "VZ", "T", "XOM", "CVX", "SPY", "QQQ",
    "WM", "LIN", "RTX", "HON", "UPS", "CAT", "DE",
    "LOW", "BLK", "CME", "ICE", "MMC", "AON",
]

DIVIDEND_STOCKS = [
    "JNJ", "PG", "KO", "PEP", "VZ", "T", "XOM", "CVX", "ABBV", "MRK",
    "HD", "WMT", "COST", "V", "MA", "UNH", "LLY", "AVGO", "TXN", "LIN",
    "WM", "RTX", "HON", "UPS", "CAT", "DE", "LOW", "BLK", "CME", "ICE",
    "MMC", "AON", "O", "OHI", "STAG", "VICI", "AMT", "PLD", "DLR",
    "EQIX", "PSA", "ESS", "UDR", "INVH", "IBM", "CSCO", "PFE", "MO",
    "PM", "BMY", "GILD", "VFC", "TGT", "CL", "KMB", "ED", "NEE", "DUK",
    "SO", "D", "AEP", "AWK", "WBA", "KR", "MDLZ", "CLX", "CHD",
]

GROWTH_STOCKS = [
    "AMZN", "GOOGL", "META", "TSLA", "NVDA", "NFLX", "PLTR", "COIN",
    "SHOP", "SNAP", "ROKU", "ZM", "SQ", "MARA", "RIOT",
    "CRM", "ADBE", "INTU", "SNOW", "DDOG", "NET", "ZS", "CRWD",
    "MRNA", "BIIB", "REGN", "VRTX",
]

DEFAULT_WATCHLIST = US_QUICK_TURNOVER[:30]

# ==========================================
# ENCRYPTION HELPERS
# ==========================================
def safe_encrypt(value: str) -> str:
    """Encrypt a value if encryption is available, otherwise return as-is."""
    if not value:
        return ""
    try:
        from core.encryption import encrypt_value, is_encrypted
        if is_encrypted(value):
            return value  # Already encrypted
        return encrypt_value(value)
    except ImportError:
        return value
    except Exception:
        return value


def safe_decrypt(value: str) -> str:
    """Decrypt a value if encryption is available, otherwise return as-is."""
    if not value:
        return ""
    try:
        from core.encryption import decrypt_value, is_encrypted
        if is_encrypted(value):
            return decrypt_value(value)
        return value
    except ImportError:
        return value
    except ValueError:
        # Decryption failed — key mismatch or corrupted data
        import logging
        logging.getLogger(__name__).error(
            "Decryption failed — encryption key may have changed. "
            "API keys will need to be re-entered."
        )
        return ""
    except Exception:
        return ""

# ==========================================
# FORMATTING HELPERS
# ==========================================
def format_currency(amount: float, symbol: str = "$") -> str:
    """Format a number as currency with commas."""
    if amount is None:
        return f"{symbol}0.00"
    if abs(amount) >= 1_000_000:
        return f"{symbol}{amount/1_000_000:.1f}M"
    if abs(amount) >= 1_000:
        return f"{symbol}{amount:,.2f}"
    return f"{symbol}{amount:.2f}"


def format_percent(value: float, decimals: int = 1) -> str:
    """Format a decimal as a percentage string."""
    if value is None:
        return "0.0%"
    return f"{value:+.{decimals}f}%"


def format_number(value: float, decimals: int = 0) -> str:
    """Format a number with commas."""
    if value is None:
        return "0"
    return f"{value:,.{decimals}f}"


def format_timestamp(ts: str) -> str:
    """Format an ISO timestamp to a readable string."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts[:19] if ts else "N/A"


def bucket_icon(bucket: str) -> str:
    """Get the icon for a bucket type."""
    return BUCKET_ICONS.get(bucket, "⚪")


def bucket_display_name(bucket: str) -> str:
    """Get a display-friendly bucket name."""
    if bucket == "long_term":
        bucket = "dividend"
    return bucket.title()


# ==========================================
# MARKET HOURS
# ==========================================
US_MARKET_HOLIDAYS = {
    # 2024
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29",
    "2024-05-27", "2024-06-19", "2024-07-04", "2024-09-02",
    "2024-11-28", "2024-12-25",
    # 2025
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01",
    "2025-11-27", "2025-12-25",
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
    "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
    "2026-11-26", "2026-12-25",
}

def is_market_open() -> Dict:
    """Check if the US stock market is currently open."""
    try:
        from zoneinfo import ZoneInfo
        eastern = ZoneInfo("US/Eastern")
        now_et = datetime.now(eastern)
        market_open = dt_time(9, 30)
        market_close = dt_time(16, 0)
        is_weekday = now_et.weekday() < 5
        is_holiday = now_et.strftime("%Y-%m-%d") in US_MARKET_HOLIDAYS
        is_trading_hours = market_open <= now_et.time() <= market_close
        is_open = is_weekday and is_trading_hours and not is_holiday

        if is_weekday and now_et.time() < market_open:
            next_open = datetime.combine(now_et.date(), market_open)
        elif is_weekday and now_et.time() >= market_close:
            next_date = now_et.date() + timedelta(days=1)
            while next_date.weekday() >= 5:
                next_date += timedelta(days=1)
            next_open = datetime.combine(next_date, market_open)
        else:
            next_date = now_et.date() + timedelta(days=1)
            while next_date.weekday() >= 5:
                next_date += timedelta(days=1)
            next_open = datetime.combine(next_date, market_open)

        return {
            "is_open": is_open,
            "current_time_et": now_et.strftime("%I:%M %p"),
            "current_time_uk": now_et.strftime("%H:%M") + " UK",
            "market_open_time": "9:30 AM ET / 2:30 PM UK",
            "market_close_time": "4:00 PM ET / 9:00 PM UK",
            "is_weekday": is_weekday,
            "day_name": now_et.strftime("%A"),
            "next_open": next_open.strftime("%A %I:%M %p ET"),
        }
    except Exception as e:
        return {
            "is_open": False,
            "error": str(e),
            "current_time_et": "Unknown",
            "market_open_time": "9:30 AM ET / 2:30 PM UK",
            "market_close_time": "4:00 PM ET / 9:00 PM UK",
            "next_open": "Unknown",
        }


# ==========================================
# CSV EXPORT
# ==========================================
WATERMARK = "\nSource: Roleigh QuanTrader - Unauthorized reproduction prohibited"


def watermark_csv(csv_string: str) -> str:
    """Add a watermark to exported CSV data."""
    return csv_string + WATERMARK


def df_to_watermarked_csv(df, filename: str = "export.csv") -> Tuple[str, str]:
    """Convert a DataFrame to a watermarked CSV string and return (csv_string, filename)."""
    csv_string = df.to_csv(index=False)
    csv_string = watermark_csv(csv_string)
    return csv_string, filename


# ==========================================
# DISCORD ALERTS
# ==========================================
def send_discord_message(webhook_url: str, message: str) -> bool:
    """Send a message to a Discord webhook."""
    if not webhook_url:
        return False
    try:
        import requests
        payload = {"content": message}
        response = requests.post(webhook_url, json=payload, timeout=10)
        return response.status_code == 204 or response.status_code == 200
    except Exception as e:
        logger.error(f"Discord message failed: {e}")
        return False


def send_discord_file(webhook_url: str, file_data: bytes, filename: str, message: str = "") -> bool:
    """Send a file to a Discord webhook."""
    if not webhook_url:
        return False
    try:
        import requests
        files = {"file": (filename, file_data)}
        payload = {"content": message} if message else {}
        response = requests.post(webhook_url, data=payload, files=files, timeout=30)
        return response.status_code == 204 or response.status_code == 200
    except Exception as e:
        logger.error(f"Discord file upload failed: {e}")
        return False


# ==========================================
# RETRY DECORATOR
# ==========================================
def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Decorator to retry a function on failure with exponential backoff."""
    def decorator(func):
        import time
        def wrapper(*args, **kwargs):
            attempts = 0
            current_delay = delay
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    if attempts >= max_attempts:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise
                    logger.warning(f"{func.__name__} attempt {attempts}/{max_attempts} failed: {e}. Retrying in {current_delay}s...")
                    time.sleep(current_delay)
                    current_delay *= backoff
            return None
        return wrapper
    return decorator


# ==========================================
# TICKER VALIDATION
# ==========================================
def is_valid_ticker(symbol: str) -> bool:
    """Basic validation for a stock ticker symbol."""
    if not symbol or not isinstance(symbol, str):
        return False
    symbol = symbol.strip().upper()
    if len(symbol) > 5:
        return False
    if '.' in symbol and not symbol.endswith('.L'):
        return False
    if '-' in symbol and not symbol.endswith('-USD'):
        return False
    if not symbol.replace('.', '').replace('-', '').replace('$', '').isalpha():
        return False
    return True


def clean_ticker(symbol: str) -> str:
    """Clean and standardize a ticker symbol."""
    if not symbol:
        return ""
    return symbol.strip().upper()


# ==========================================
# SESSION STATE HELPERS
# ==========================================
def init_session_defaults(defaults: dict):
    """Initialize session state with default values if not already set."""
    try:
        import streamlit as st
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value
    except ImportError:
        pass

# ==========================================
# STOCK CLASSIFICATION (lightweight version for utils)
# ==========================================
def classify_stock_simple(symbol: str, price: float = None, div_yield: float = None,
                          penny_threshold: float = 5.0, min_div_yield: float = 0.03) -> str:
    """Classify a stock into dividend/growth/penny based on price and yield.
    This is a lightweight version for use outside the trading engine."""
    symbol = symbol.upper()

    if price is not None and price < penny_threshold:
        return "penny"

    if div_yield is not None and div_yield >= min_div_yield:
        return "dividend"

    if symbol in DIVIDEND_STOCKS:
        return "dividend"
    if symbol in GROWTH_STOCKS or symbol in US_LONG_TERM:
        return "growth"

    if price is not None and price >= penny_threshold:
        return "growth"

    return "penny"


# ==========================================
# SIMPLE CONFIG PERSISTENCE
# ==========================================
CONFIG_DIR = Path("data/config")
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def save_config(key: str, value, username: str = "default"):
    """Save a configuration value to a JSON file."""
    config_file = CONFIG_DIR / f"{username}_config.json"
    config = {}
    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                config = json.load(f)
        except Exception:
            config = {}
    config[key] = value
    try:
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Config save error: {e}")
        return False


def load_config(key: str, default=None, username: str = "default"):
    """Load a configuration value from a JSON file."""
    config_file = CONFIG_DIR / f"{username}_config.json"
    if config_file.exists():
        try:
            with open(config_file, "r") as f:
                config = json.load(f)
            return config.get(key, default)
        except Exception:
            return default
    return default


# ==========================================
# HEALTH CHECK
# ==========================================
def health_check() -> Dict:
    """Run a quick health check on all system components."""
    status = {
        "timestamp": datetime.now().isoformat(),
        "components": {},
        "overall": "healthy",
    }

    # Check yfinance
    try:
        import yfinance
        status["components"]["yfinance"] = "ok"
    except ImportError:
        status["components"]["yfinance"] = "missing"
        status["overall"] = "degraded"

    # Check technical analysis
    try:
        import ta
        status["components"]["ta"] = "ok"
    except ImportError:
        status["components"]["ta"] = "missing"
        status["overall"] = "degraded"

    # Check ML
    try:
        from sklearn.ensemble import RandomForestClassifier
        status["components"]["sklearn"] = "ok"
    except ImportError:
        status["components"]["sklearn"] = "missing"

    # Check core modules
    for module_name in ["core.signals", "core.metrics", "core.dividends",
                        "core.audit", "core.encryption", "core.payments",
                        "core.tiers", "core.ipo_scanner", "core.backtest"]:
        try:
            __import__(module_name)
            status["components"][module_name] = "ok"
        except ImportError:
            status["components"][module_name] = "missing"

    # Check encryption
    try:
        from core.encryption import verify_encryption_working
        if verify_encryption_working():
            status["components"]["encryption"] = "ok"
        else:
            status["components"]["encryption"] = "not_configured"
    except ImportError:
        status["components"]["encryption"] = "missing"

    return status


# ==========================================
# IMPORT SAFELY
# ==========================================
def safe_import(module_name: str, attribute: str = None):
    """Safely import a module or attribute, returning None on failure."""
    try:
        module = __import__(module_name)
        if attribute:
            return getattr(module, attribute)
        return module
    except ImportError:
        return None
    except AttributeError:
        return None
