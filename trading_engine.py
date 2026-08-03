import threading
import json
import csv
import os
import time
import math
import re
from datetime import datetime, timedelta, timezone
from math import sqrt
from typing import Dict, List, Optional, Any, Tuple, Union
from pathlib import Path
from collections import defaultdict
import copy

import pandas as pd
import numpy as np

try:
    import yfinance as yf
    YF_AVAILABLE = True
except Exception:
    YF_AVAILABLE = False

try:
    import alpaca_trade_api as tradeapi
    ALPACA_AVAILABLE = True
except Exception:
    tradeapi = None
    ALPACA_AVAILABLE = False

try:
    import ta
    TA_AVAILABLE = True
except Exception:
    TA_AVAILABLE = False

try:
    from core.signals import generate_all_signals, calculate_combined_score, vix_filter
    ADVANCED_SIGNALS_AVAILABLE = True
except Exception:
    ADVANCED_SIGNALS_AVAILABLE = False

try:
    from core.metrics import (
        calculate_sortino_ratio, calculate_calmar_ratio,
        calculate_omega_ratio, calculate_rolling_returns,
        calculate_drawdown_analysis, calculate_attribution_by_bucket,
        generate_full_report
    )
    ADVANCED_METRICS_AVAILABLE = True
except Exception:
    ADVANCED_METRICS_AVAILABLE = False

try:
    from core.dividends import (
        get_upcoming_ex_dividends, get_dividend_yield as get_div_yield_external,
        get_dividend_history as get_div_history_external,
        get_dividend_growth, calculate_drip, get_dividend_comparison
    )
    DIVIDEND_CALENDAR_AVAILABLE = True
except Exception:
    DIVIDEND_CALENDAR_AVAILABLE = False

try:
    from core.backtest import BacktestEngine
    BACKTEST_AVAILABLE = True
except Exception:
    BACKTEST_AVAILABLE = False

try:
    from core.ipo_scanner import load_known_symbols, save_symbol_snapshot, get_upcoming_ipos
    IPO_SCANNER_AVAILABLE = True
except Exception:
    IPO_SCANNER_AVAILABLE = False

try:
    from core.alerts import send_discord_alert, send_discord_file
    ALERTS_AVAILABLE = True
except Exception:
    ALERTS_AVAILABLE = False

try:
    from core.database import (
        SessionLocal, User, Trade, authenticate_user, create_user,
        record_dividend, get_dividend_history, save_trade_to_db,
        load_trades_from_db, clear_trades_from_db
    )
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False

try:
    from core.audit import log_trade_audit, log_audit
    AUDIT_AVAILABLE = True
except Exception:
    AUDIT_AVAILABLE = False

try:
    from core.encryption import encrypt_value, decrypt_value, is_encrypted
    ENCRYPTION_AVAILABLE = True
except Exception:
    ENCRYPTION_AVAILABLE = False


# ==========================================
# CONSTANTS
# ==========================================
US_QUICK_TURNOVER = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "INTC",
    "NFLX", "PYPL", "ADBE", "CRM", "ORCL", "IBM", "QCOM", "TXN", "AVGO",
    "INTU", "SHOP", "SNOW", "PLTR", "COIN", "SQ", "ROKU", "ZM", "CRWD",
    "DDOG", "NET", "MDB", "OKTA", "ZS", "PANW", "RIVN", "LCID", "NIO",
    "UBER", "ABNB", "RBLX", "SOFI", "HOOD", "UPST", "AFRM", "OPEN", "F",
    "GM", "DIS", "BA", "CAT", "GE", "LMT", "NOC", "RTX", "DE", "UNP", "CSX",
]
US_LONG_TERM = 365  # days — long-term capital gains threshold

DIVIDEND_STOCKS = [
    "AAPL", "MSFT", "JNJ", "PG", "KO", "PEP", "VZ", "T", "XOM", "CVX",
    "ABBV", "LLY", "MRK", "PFE", "MO", "HD", "WMT", "COST", "TGT", "V",
    "UNH", "ABT", "TMO", "AVGO", "TXN", "QCOM", "INTC", "CSCO", "IBM", "ORCL",
    "LIN", "DHR", "RTX", "HON", "UPS", "BA", "CAT", "DE", "MMM", "SPGI",
    "MMC", "AON", "CME", "ICE", "BLK", "SCHW", "PGR", "ALL", "BRK.B", "GLW",
    "O", "OHI", "STAG", "VICI", "MPW", "AGNC", "NLY", "LMT", "NOC", "GD",
    "RTX", "EMR", "ETN", "GIS", "CL", "KMB", "CLX", "EL", "APD", "ECL",
    "FIS", "GPN", "MA", "COF", "CB", "CINF", "MET", "AFL", "PRU", "TRV",
    "AIG", "ALL", "BRO", "CF", "MOS", "NUE", "STLD", "FCX", "F", "GM",
    "COP", "SLB", "EOG", "OXY", "MPC", "VLO", "PSX", "KMI", "WMB", "ET",
    "OKE", "D", "DUK", "SO", "NEE", "AEP", "EXC", "XEL", "SRE", "AWK",
    "WEC", "DTE", "PEG", "ESRX", "CI", "HUM", "CNC", "ELV", "WBA", "RAD",
]

GROWTH_STOCKS = [
    "AMZN", "GOOGL", "GOOG", "META", "NVDA", "TSLA", "NFLX", "AMD", "PYPL",
    "ADBE", "CRM", "SHOP", "SNOW", "PLTR", "COIN", "SQ", "ROKU", "ZM", "CRWD",
    "DDOG", "NET", "MDB", "OKTA", "ZS", "PANW", "RIVN", "LCID", "NIO", "RBLX",
    "U", "PATH", "AI", "SOFI", "HOOD", "AFRM", "UPST", "OPEN", "EXAS", "VEEV",
    "WDAY", "TEAM", "DOCU", "ZI", "BILL", "HUBS", "TWLO", "ESTC", "FSLR",
    "ENPH", "SEDG", "RUN", "BE", "PLUG", "BLNK", "CHPT", "NKLA", "QS", "RMO",
    "UBER", "LYFT", "ABNB", "PINS", "SNAP", "SPOT", "MSTR", "SE", "MELI",
    "WIX", "ETSY", "INTU", "MNST",
]

BUCKET_ICONS = {
    "dividend": "🟢",
    "growth": "🔵",
    "penny": "🔴",
    "withdrawal": "🟡",
    "long_term": "🟢",
}

SECTOR_MAP = {
    "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology", "GOOG": "Technology",
    "META": "Technology", "NVDA": "Technology", "AMD": "Technology", "INTC": "Technology",
    "CSCO": "Technology", "ORCL": "Technology", "IBM": "Technology", "QCOM": "Technology",
    "TXN": "Technology", "AVGO": "Technology", "ADBE": "Technology", "CRM": "Technology",
    "NFLX": "Technology", "PYPL": "Technology", "SNOW": "Technology", "PLTR": "Technology",
    "NET": "Technology", "MDB": "Technology", "OKTA": "Technology", "ZS": "Technology",
    "CRWD": "Technology", "DDOG": "Technology", "SHOP": "Technology", "U": "Technology",
    "PATH": "Technology", "AI": "Technology", "FSLR": "Technology", "ENPH": "Technology",
    "SEDG": "Technology", "RUN": "Technology", "PLUG": "Technology", "BE": "Technology",
    "COIN": "Technology", "SQ": "Technology", "ROKU": "Technology", "ZM": "Technology",
    "PINS": "Technology", "SNAP": "Technology", "SPOT": "Technology", "ABNB": "Consumer Discretionary",
    "UBER": "Technology", "LYFT": "Technology", "HOOD": "Financials", "SOFI": "Financials",
    "AFRM": "Financials", "UPST": "Financials", "DOCU": "Technology", "HUBS": "Technology",
    "TWLO": "Technology", "ESTC": "Technology", "BILL": "Technology", "ZI": "Technology",
    "WDAY": "Technology", "TEAM": "Technology", "VEEV": "Healthcare", "MSTR": "Technology",
    "JNJ": "Healthcare", "UNH": "Healthcare", "ABBV": "Healthcare", "LLY": "Healthcare",
    "MRK": "Healthcare", "PFE": "Healthcare", "TMO": "Healthcare", "ABT": "Healthcare",
    "MRNA": "Healthcare", "EXAS": "Healthcare", "BIIB": "Healthcare", "GILD": "Healthcare",
    "AMGN": "Healthcare", "REGN": "Healthcare", "VRTX": "Healthcare", "ISRG": "Healthcare",
    "IDXX": "Healthcare", "ILMN": "Healthcare", "ALGN": "Healthcare", "DXCM": "Healthcare",
    "CI": "Healthcare", "HUM": "Healthcare", "CNC": "Healthcare", "ELV": "Healthcare",
    "ESRX": "Healthcare", "VTRS": "Healthcare", "BMY": "Healthcare", "CVS": "Healthcare",
    "WBA": "Healthcare", "V": "Financials", "MA": "Financials", "JPM": "Financials",
    "BAC": "Financials", "WFC": "Financials", "GS": "Financials", "MS": "Financials",
    "C": "Financials", "BLK": "Financials", "SCHW": "Financials", "COF": "Financials",
    "CB": "Financials", "CINF": "Financials", "MET": "Financials", "AFL": "Financials",
    "PRU": "Financials", "TRV": "Financials", "AIG": "Financials", "ALL": "Financials",
    "AON": "Financials", "MMC": "Financials", "ICE": "Financials", "CME": "Financials",
    "FIS": "Financials", "GPN": "Financials", "BRO": "Financials", "PG": "Consumer Staples",
    "KO": "Consumer Staples", "PEP": "Consumer Staples", "WMT": "Consumer Staples",
    "COST": "Consumer Staples", "TGT": "Consumer Staples", "CL": "Consumer Staples",
    "KMB": "Consumer Staples", "CLX": "Consumer Staples", "EL": "Consumer Staples",
    "GIS": "Consumer Staples", "MO": "Consumer Staples", "MDLZ": "Consumer Staples",
    "HSY": "Consumer Staples", "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
    "HD": "Consumer Discretionary", "NKE": "Consumer Discretionary", "SBUX": "Consumer Discretionary",
    "LOW": "Consumer Discretionary", "BKNG": "Consumer Discretionary", "RIVN": "Consumer Discretionary",
    "LCID": "Consumer Discretionary", "F": "Consumer Discretionary", "GM": "Consumer Discretionary",
    "RBLX": "Consumer Discretionary", "ETSY": "Consumer Discretionary",
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "SLB": "Energy", "EOG": "Energy",
    "OXY": "Energy", "MPC": "Energy", "VLO": "Energy", "PSX": "Energy", "KMI": "Energy",
    "FANG": "Energy", "HAL": "Energy", "BKR": "Energy", "DVN": "Energy", "MRO": "Energy",
    "WES": "Energy", "ET": "Energy", "OKE": "Energy", "WMB": "Energy",
    "BA": "Industrials", "CAT": "Industrials", "DE": "Industrials", "MMM": "Industrials",
    "GE": "Industrials", "HON": "Industrials", "LMT": "Industrials", "NOC": "Industrials",
    "GD": "Industrials", "RTX": "Industrials", "UNP": "Industrials", "CSX": "Industrials",
    "NSC": "Industrials", "EMR": "Industrials", "ETN": "Industrials", "FTV": "Industrials",
    "PH": "Industrials", "IR": "Industrials", "DOV": "Industrials", "ITW": "Industrials",
    "LIN": "Materials", "APD": "Materials", "ECL": "Materials", "SHW": "Materials",
    "FCX": "Materials", "NUE": "Materials", "STLD": "Materials", "CF": "Materials",
    "MOS": "Materials", "DD": "Materials", "NEE": "Utilities", "DUK": "Utilities",
    "SO": "Utilities", "D": "Utilities", "AEP": "Utilities", "EXC": "Utilities",
    "XEL": "Utilities", "SRE": "Utilities", "AWK": "Utilities", "WEC": "Utilities",
    "DTE": "Utilities", "PEG": "Utilities", "ES": "Utilities",
    "O": "Real Estate", "OHI": "Real Estate", "STAG": "Real Estate", "VICI": "Real Estate",
    "MPW": "Real Estate", "AMT": "Real Estate", "PLD": "Real Estate", "CCI": "Real Estate",
    "EQIX": "Real Estate", "DLR": "Real Estate", "PSA": "Real Estate", "WELL": "Real Estate",
    "VTR": "Real Estate", "UDR": "Real Estate",
    "DIS": "Communication Services", "VZ": "Communication Services", "T": "Communication Services",
    "CMCSA": "Communication Services", "TMUS": "Communication Services", "EA": "Communication Services",
    "TTWO": "Communication Services",
}

# VIX cache is now per-engine instance (moved to __init__)


# Reconnection reset
MAX_CONSECUTIVE_SCAN_FAILURES = 10

DEFAULT_SETTINGS = {
    "max_positions": 20,
    "max_position_pct": 0.08,
    "daily_loss_limit_pct": 0.03,
    "stop_loss_pct": 0.05,
    "take_profit_pct": 0.10,
    "min_confidence": 0.20,
    "scan_interval_min": 8,
    "max_same_sector": 3,
    "min_rvol": 1.0,
    "dividend_pct": 0.35,
    "growth_pct": 0.35,
    "penny_pct": 0.30,
    "profit_skim_pct": 1.0,
    "discord_profit_alerts": True,
    "use_pct_threshold": False,
    "profit_threshold_pct": 0.20,
    "profit_threshold_amount": 20000,
    "auto_extract_profits": True,
    "use_advanced_signals": True,
    "use_vix_filter": True,
    "use_atr_position_sizing": True,
    "use_multi_timeframe": False,
    "discord_privacy_mode": True,
    "watchlist_auto": True,
    "watchlist_auto_count": 100,
    "watchlist_last_built": "",
    "penny_price_threshold": 5.0,
    "min_dividend_yield": 0.03,
    "scan_full_universe": True,
    "universe_scan_count": 300,
    "watchlist": [
        # === MEGA CAP (Tech) ===
        "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA",
        "AVGO", "ORCL", "ADBE", "CRM", "INTU", "NOW", "AMD", "QCOM",
        "TXN", "MU", "LRCX", "AMAT", "KLAC", "MRVL", "PLTR", "COIN",
        "SNOW", "DDOG", "NET", "ZS", "CRWD", "PANW", "OKTA",
        # === MEGA CAP (Non-Tech) ===
        "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW",
        "JNJ", "UNH", "PFE", "MRK", "LLY", "ABBV", "TMO", "ABT", "MRNA", "BIIB",
        "PG", "KO", "PEP", "WMT", "HD", "COST", "NKE", "TGT", "LOW", "SBUX",
        "XOM", "CVX", "COP", "SLB", "EOG", "OXY", "MPC", "VLO",
        "DIS", "NFLX", "CMCSA", "TMUS", "EA", "TTWO",
        # === LARGE CAP ===
        "BA", "CAT", "DE", "MMM", "GE", "HON", "LMT", "NOC", "RTX", "UNP",
        "UPS", "FDX", "GM", "F",
        "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "AWK",
        "O", "OHI", "STAG", "VICI", "AMT", "PLD", "DLR", "EQIX",
        "BRK.B", "SPGI", "MMC", "AON", "ICE", "CME",
        # === MID CAP GROWTH ===
        "SHOP", "SQ", "ROKU", "ZM", "UPST", "RIVN", "LCID", "NIO", "MARA", "RIOT",
        "SOFI", "HOOD", "AFRM", "OPEN", "PATH",
        "ABNB", "UBER", "LYFT", "PINS", "SNAP", "SPOT", "MSTR",
        "WDAY", "TEAM", "DOCU", "BILL", "HUBS", "TWLO", "ESTC",
        "FSLR", "ENPH", "SEDG", "RUN", "BE", "BLNK", "CHPT", "PLUG", "NKLA",
        # === DIVIDEND ARISTOCRATS ===
        "IBM", "CSCO", "INTC", "PFE", "MO", "PM", "BMY", "GILD", "VFC",
        "CL", "KMB", "CLX", "ED", "NEE", "DUK", "SO", "D",
        "T", "VZ", "SHW", "APD", "ECL", "LIN",
        "WBA", "KR", "MDLZ", "GIS", "K", "HSY", "CLX", "CHD",
        # === PENNY / SPECULATIVE (under $10) ===
        "SNDL", "FNKO", "HEAR", "GPRO", "FUBO", "SHVO", "NOK", "BB", "NOK",
        "VALE", "TELL", "MRO", "MUR", "CVE", "SU", "CNQ", "PBR",
        "VALE", "TECK", "FCX", "NUE", "STLD", "CLF", "CF", "MOS",
        "SIRI", "LYG", "BCS", "DB", "SAN", "BBVA",
        "RIG", "DOUG", "PTEN", "HLX", "WTI",
        "AQN", "TELL", "MCEP", "CIG", "VIST",
    ],
    "penny_settings": {
        "stop_loss_pct": 0.05,
        "trailing_stop_pct": 0.03,
        "take_profit_pct": 0.10,
        "max_position_pct": 0.06,
        "rsi_oversold": 30,
        "rsi_overbought": 65,
        "min_confidence": 0.20,
        "penny_price_threshold": 5.0,
    },
    "growth_settings": {
        "stop_loss_pct": 0.06,
        "trailing_stop_pct": 0.04,
        "take_profit_pct": 0.12,
        "max_position_pct": 0.08,
        "rsi_oversold": 30,
        "rsi_overbought": 65,
        "min_confidence": 0.20,
    },
    "dividend_settings": {
        "stop_loss_pct": 0.10,
        "trailing_stop_pct": 0.07,
        "take_profit_pct": 0.20,
        "max_position_pct": 0.08,
        "rsi_oversold": 35,
        "rsi_overbought": 70,
        "min_confidence": 0.15,
        "min_dividend_yield": 0.02,
        "sell_after_ex_dividend": False,
    },
}


class TradingEngine:
    """Main trading engine class — all methods at 4-space indent."""

    def __init__(self):
        self.api = None
        self.connected = False
        self.running = False
        self.username = ""
        self.status_message = "Not connected"
        self.cycle_count = 0
        self.daily_pnl = 0.0
        self.last_equity = 0.0
        self.signals_found = []
        self.trade_log = []
        self.equity_snapshots = []
        self.terms_accepted = False
        self.terms_accepted_date = None
        self.known_symbols = []
        self._thread = None
        self._stop_event = threading.Event()
        self._position_cache = {}
        self._position_cache_time = 0
        self._sector_cache = {}
        self._price_cache = {}
        self._price_cache_time = 0
        self._data_cache = {}
        self._data_cache_time = {}
        self._data_cache_ttl = 300  # 5 minutes

        # Universe scan cache (30 min TTL so we don't re-fetch every cycle)
        self._universe_cache = []
        self._universe_cache_time = 0
        self._universe_cache_ttl = 1800  # 30 minutes
        self._daily_start_equity = 0.0
        self._vix_cache = {"value": 0.0, "timestamp": 0.0, "safe": True, "reason": ""}
        self._vix_cache_ttl = 300  # 5 minutes
        self._trailing_stops = {}
        self._alpaca_api_ref = None
        self.daily_reset_date = None
        self.near_signals = []
        self.signal_history = []
        self.performance_metrics = {}
        self._spy_start_value = 0.0
        self._spy_start_date = None
        self._portfolio_start_value = 0.0
        self.last_ipo_scan_date = None
        self.reconnect_count = 0
        self.consecutive_failures = 0
        self.last_reconnect_time = None
        self.last_successful_cycle = None
        self.MAX_RECONNECT_ATTEMPTS = 5
        self.RECONNECT_BASE_DELAY = 30
        self.MAX_RECONNECT_DELAY = 300

        self.buckets = {
            "dividend": {
                "value": 0.0,
                "positions": 0,
                "total_deposited": 0.0,
                "cash_allocated": 0.0,
                "dividends_earned": 0.0,
                "profits_moved_in": 0.0,
                "total_withdrawn": 0.0,
                "deposit_history": [],
                "extraction_history": [],
                "dividend_history": [],
                "last_deposit_date": None,
            },
            "growth": {
                "value": 0.0,
                "positions": 0,
                "total_deposited": 0.0,
                "cash_allocated": 0.0,
                "profits_moved_in": 0.0,
                "total_withdrawn": 0.0,
                "deposit_history": [],
                "extraction_history": [],
                "last_deposit_date": None,
            },
            "penny": {
                "value": 0.0,
                "positions": 0,
                "total_deposited": 0.0,
                "cash_allocated": 0.0,
                "profits_to_growth": 0.0,
                "total_withdrawn": 0.0,
                "deposit_history": [],
                "extraction_history": [],
                "last_deposit_date": None,
            },
            "withdrawal": {
                "available": 0.0,
                "dividends_received": 0.0,
                "profits_extracted": 0.0,
                "total_withdrawn": 0.0,
                "deposit_history": [],
                "extraction_history": [],
                "dividend_history": [],
                "last_deposit_date": None,
            },
            "original_capital": 0,
            "last_updated": None,
        }

        self.settings = dict(DEFAULT_SETTINGS)
        self.load_settings()
        self._load_trade_log()

    # ==========================================
    # Connection & Lifecycle
    # ==========================================

    def set_username(self, username: str):
        """Set the username for this engine instance."""
        self.username = username
        self.load_settings()
        self._load_trade_log()

    def connect(self, api) -> bool:
        """Connect to Alpaca API and verify the connection."""
        try:
            self.api = api
            account = self.api.get_account()
            if account:
                self.connected = True
                self.status_message = "Connected to Alpaca Paper Trading"
                self.last_equity = float(getattr(account, 'equity', 0))
                self._daily_start_equity = self.last_equity
                self._update_buckets()
                if AUDIT_AVAILABLE and self.username:
                    try:
                        log_audit(self.username, "engine_connect", "Connected to Alpaca")
                    except Exception:
                        pass
                return True
            else:
                self.connected = False
                self.status_message = "Failed to get account from Alpaca"
                return False
        except Exception as e:
            self.connected = False
            self.status_message = f"Connection error: {str(e)}"
            return False

    def start(self):
        """Start the trading bot in a background thread."""
        if self.running:
            self.status_message = "Bot already running"
            return
        if not self.connected:
            self.status_message = "Not connected to Alpaca"
            return
        self.running = True
        self._stop_event.clear()
        self._daily_start_equity = self.last_equity
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.status_message = "Bot running"
        if AUDIT_AVAILABLE and self.username:
            try:
                log_audit(self.username, "bot_start", "Trading bot started")
            except Exception:
                pass

    def stop(self):
        """Stop the trading bot."""
        self.running = False
        self._stop_event.set()
        self.status_message = "Bot stopped"
        self._save_trade_log()
        if AUDIT_AVAILABLE and self.username:
            try:
                log_audit(self.username, "bot_stop", "Trading bot stopped")
            except Exception:
                pass

    def _run_loop(self):
        """Main trading loop running in background thread."""
        while self.running and not self._stop_event.is_set():
            try:
                market = self.is_market_open()
                if market.get("is_open", False):
                    self.run_cycle()
                    self.consecutive_failures = 0
                    self.last_successful_cycle = datetime.utcnow().isoformat()
                else:
                    self.status_message = f"Market closed. {market.get('day_name', '')}"
            except Exception as e:
                self.status_message = f"Cycle error: {str(e)}"
                self.consecutive_failures += 1
                # Try to reconnect if connection seems lost
                if self.consecutive_failures >= 3:
                    try:
                        account = self.get_account_info()
                        if "error" in account:
                            self.status_message = f"Connection lost. Attempting reconnect ({self.consecutive_failures} failures)..."
                            if self._reconnect():
                                self.status_message = "Reconnected successfully."
                            elif self.consecutive_failures >= self.MAX_RECONNECT_ATTEMPTS:
                                self.running = False
                                self.status_message = "Max reconnection attempts reached. Bot stopped."
                    except Exception:
                        pass
            interval = self.settings.get("scan_interval_min", 8) * 60
            self._stop_event.wait(timeout=interval)

    # ==========================================
    # Settings (load_settings is SEPARATE from save_settings)
    # ==========================================

    def save_settings(self):
        """Save current settings to a JSON file."""
        try:
            settings_dir = Path.home() / ".cascadetrade"
            settings_dir.mkdir(parents=True, exist_ok=True)
            settings_file = settings_dir / f"settings_{self.username or 'default'}.json"
            with open(settings_file, "w") as f:
                json.dump(self.settings, f, indent=2, default=str)
            if AUDIT_AVAILABLE and self.username:
                try:
                    log_audit(self.username, "settings_save", "Settings saved")
                except Exception:
                    pass
        except Exception as e:
            print(f"Error saving settings: {e}")

    def load_settings(self):
        """Load settings from a JSON file. Separate method, NOT nested inside save_settings."""
        try:
            settings_dir = Path.home() / ".cascadetrade"
            settings_file = settings_dir / f"settings_{self.username or 'default'}.json"
            if settings_file.exists():
                with open(settings_file, "r") as f:
                    loaded = json.load(f)
                merged = dict(DEFAULT_SETTINGS)
                self._deep_merge(merged, loaded)
                self.settings = merged
            else:
                self.settings = dict(DEFAULT_SETTINGS)
        except Exception as e:
            print(f"Error loading settings: {e}")
            self.settings = dict(DEFAULT_SETTINGS)

    def _deep_merge(self, base: dict, override: dict):
        """Deep merge override dict into base dict, preserving nested keys."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def reset_settings(self):
        """Reset all settings to safe defaults."""
        self.settings = dict(DEFAULT_SETTINGS)
        self._trailing_stops = {}
        self.save_settings()

    # ==========================================
    # Trade Log Persistence
    # ==========================================

    def _load_trade_log(self):
        """Load trade log and equity snapshots from file."""
        try:
            trade_dir = Path.home() / ".cascadetrade"
            trade_dir.mkdir(parents=True, exist_ok=True)
            trade_file = trade_dir / f"trades_{self.username or 'default'}.json"
            if trade_file.exists():
                with open(trade_file, "r") as f:
                    data = json.load(f)
                self.trade_log = data.get("trade_log", [])
                self.equity_snapshots = data.get("equity_snapshots", [])
                self.cycle_count = data.get("cycle_count", 0)
                self.daily_pnl = data.get("daily_pnl", 0.0)
                saved_buckets = data.get("buckets", {})
                if saved_buckets:
                    for key in ["dividend", "growth", "penny", "withdrawal"]:
                        if key in saved_buckets:
                            self.buckets[key].update(saved_buckets[key])
                    if "original_capital" in saved_buckets:
                        self.buckets["original_capital"] = saved_buckets["original_capital"]
                    if "last_updated" in saved_buckets:
                        self.buckets["last_updated"] = saved_buckets["last_updated"]
                original_capital = data.get("original_capital", 0)
                if original_capital > 0:
                    self.buckets["original_capital"] = original_capital
                # Restore trailing stops from saved data
                saved_trailing_stops = data.get("trailing_stops", {})
                if saved_trailing_stops:
                    self._trailing_stops = saved_trailing_stops
            else:
                self.trade_log = []
                self.equity_snapshots = []
        except Exception as e:
            print(f"Error loading trade log: {e}")
            self.trade_log = []
            self.equity_snapshots = []

    def _save_trade_log(self):
        """Save trade log and equity snapshots to file."""
        try:
            trade_dir = Path.home() / ".cascadetrade"
            trade_dir.mkdir(parents=True, exist_ok=True)
            trade_file = trade_dir / f"trades_{self.username or 'default'}.json"
            data = {
                "trade_log": self.trade_log,
                "equity_snapshots": self.equity_snapshots,
                "cycle_count": self.cycle_count,
                "daily_pnl": self.daily_pnl,
                "buckets": self.buckets,
                "original_capital": self.buckets.get("original_capital", 0),
                "last_updated": datetime.utcnow().isoformat(),
                "trailing_stops": self._trailing_stops,
            }
            with open(trade_file, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving trade log: {e}")

    # ==========================================
    # Market Status
    # ==========================================

    def is_market_open(self) -> Dict:
        """Check if the US stock market is currently open."""
        try:
            if not self.connected or not self.api:
                return {"is_open": False, "current_time_et": "N/A", "day_name": "N/A"}
            
            try:
                clock = self.api.get_clock()
            except Exception as e:
                # Connection might be stale — try reconnecting once
                self._log_error("market_clock", f"get_clock failed: {e}")
                try:
                    if self._alpaca_api_ref:
                        self.api = self._alpaca_api_ref
                        clock = self.api.get_clock()
                    else:
                        raise e
                except Exception:
                    clock = None
            
            if clock is None:
                # Fallback: use time-based check
                try:
                    from zoneinfo import ZoneInfo
                    eastern = ZoneInfo("US/Eastern")
                    now_et = datetime.now(eastern)
                    market_open_time = dt_time(9, 30)
                    market_close_time = dt_time(16, 0)
                    is_weekday = now_et.weekday() < 5
                    is_holiday = now_et.strftime("%Y-%m-%d") in US_MARKET_HOLIDAYS
                    is_trading_hours = market_open_time <= now_et.time() <= market_close_time
                    is_open = is_weekday and is_trading_hours and not is_holiday
                    return {
                        "is_open": is_open,
                        "current_time_et": now_et.strftime("%I:%M %p"),
                        "day_name": now_et.strftime("%A"),
                    }
                except Exception:
                    return {"is_open": False, "current_time_et": "N/A", "day_name": "N/A"}
            
            is_open = getattr(clock, 'is_open', False)
            timestamp = getattr(clock, 'timestamp', datetime.utcnow())
            next_open = getattr(clock, 'next_open', None)
            next_close = getattr(clock, 'next_close', None)

            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                except Exception:
                    timestamp = datetime.utcnow()

            current_time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            day_name = timestamp.strftime("%A")

            result = {
                "is_open": is_open,
                "current_time_et": current_time_str,
                "day_name": day_name,
            }
            if next_open:
                result["next_open"] = str(next_open) if next_open else None
            if next_close:
                result["next_close"] = str(next_close) if next_close else None
            return result
        except Exception as e:
            return {"is_open": False, "current_time_et": str(e), "day_name": "Unknown"}

    def check_vix(self) -> Dict:
        """Check VIX level with 5-minute caching to avoid hammering Yahoo."""
        
        # Return cached result if fresh
        now = time.time()
        if (now - self._vix_cache["timestamp"]) < self._vix_cache_ttl and self._vix_cache["timestamp"] > 0:
            return {
                "safe_to_trade": self._vix_cache["safe"],
                "vix_value": self._vix_cache["value"],
                "reason": self._vix_cache["reason"],
            }
        
        try:
            if not YF_AVAILABLE:
                result = {"safe_to_trade": True, "vix_value": 0, "reason": "yfinance not available — VIX filter disabled"}
                self._vix_cache = {"value": 0, "timestamp": now, "safe": True, "reason": result["reason"]}
                return result
            
            vix_data = yf.Ticker("^VIX").history(period="5d")
            if vix_data.empty:
                if self._vix_cache["timestamp"] > 0:
                    return {
                        "safe_to_trade": self._vix_cache["safe"],
                        "vix_value": self._vix_cache["value"],
                        "reason": f"VIX data unavailable, using last known: {self._vix_cache['value']:.1f}",
                    }
                result = {"safe_to_trade": True, "vix_value": 0, "reason": "VIX data unavailable — filter disabled"}
                self._vix_cache = {"value": 0, "timestamp": now, "safe": True, "reason": result["reason"]}
                return result
            
            vix_value = float(vix_data['Close'].iloc[-1])
            vix_threshold = 28.0
            
            if self.settings.get("use_vix_filter", True) and vix_value > vix_threshold:
                result = {
                    "safe_to_trade": False,
                    "vix_value": vix_value,
                    "reason": f"VIX is {vix_value:.1f} (above {vix_threshold:.0f}). Buying paused — market volatile.",
                }
            else:
                result = {
                    "safe_to_trade": True,
                    "vix_value": vix_value,
                    "reason": f"VIX is {vix_value:.1f} — safe to trade.",
                }
            
            self._vix_cache = {
                "value": vix_value,
                "timestamp": now,
                "safe": result["safe_to_trade"],
                "reason": result["reason"],
            }
            return result
            
        except Exception as e:
            if self._vix_cache["timestamp"] > 0:
                return {
                    "safe_to_trade": self._vix_cache["safe"],
                    "vix_value": self._vix_cache["value"],
                    "reason": f"VIX check error, using cache: {self._vix_cache['value']:.1f}",
                }
            result = {"safe_to_trade": True, "vix_value": 0, "reason": f"VIX check error — filter disabled: {e}"}
            self._vix_cache = {"value": 0, "timestamp": now, "safe": True, "reason": result["reason"]}
            return result


    # ==========================================
    # Account & Position Info
    # ==========================================

    def get_account_info(self) -> Dict:
        """Get current account information from Alpaca."""
        try:
            if not self.connected or not self.api:
                return {"error": "not_connected"}
            account = self.api.get_account()
            return {
                "portfolio_value": float(getattr(account, 'portfolio_value', 0)),
                "cash": float(getattr(account, 'cash', 0)),
                "equity": float(getattr(account, 'equity', 0)),
                "buying_power": float(getattr(account, 'buying_power', 0)),
                "last_equity": float(getattr(account, 'last_equity', 0)),
                "status": getattr(account, 'status', 'unknown'),
                "pattern_day_trader": getattr(account, 'pattern_day_trader', False),
                "trading_blocked": getattr(account, 'trading_blocked', False),
                "transfers_blocked": getattr(account, 'transfers_blocked', False),
                "account_blocked": getattr(account, 'account_blocked', False),
                "shorting_enabled": getattr(account, 'shorting_enabled', False),
                "initial_margin": float(getattr(account, 'initial_margin', 0)),
                "maintenance_margin": float(getattr(account, 'maintenance_margin', 0)),
                "long_market_value": float(getattr(account, 'long_market_value', 0)),
                "short_market_value": float(getattr(account, 'short_market_value', 0)),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_positions(self) -> List[Dict]:
        """Get all current positions from Alpaca with caching."""
        try:
            now = time.time()
            if now - self._position_cache_time < 30 and self._position_cache:
                return list(self._position_cache.values())

            if not self.connected or not self.api:
                return []

            positions = self.api.list_positions()
            result = []
            for p in positions:
                symbol = getattr(p, 'symbol', '')
                bucket = self.assign_bucket(symbol)
                pos_dict = {
                    "symbol": symbol,
                    "qty": float(getattr(p, 'qty', 0)),
                    "avg_entry_price": float(getattr(p, 'avg_entry_price', 0)),
                    "current_price": float(getattr(p, 'current_price', 0)),
                    "market_value": float(getattr(p, 'market_value', 0)),
                    "unrealized_pl": float(getattr(p, 'unrealized_pl', 0)),
                    "unrealized_plpc": float(getattr(p, 'unrealized_plpc', 0)),
                    "side": getattr(p, 'side', 'long'),
                    "bucket": bucket,
                    "asset_class": getattr(p, 'asset_class', 'us_equity'),
                    "change_today": float(getattr(p, 'change_today', 0)),
                    "cost_basis": float(getattr(p, 'cost_basis', 0)),
                }
                result.append(pos_dict)
                self._position_cache[symbol] = pos_dict

            self._position_cache_time = now
            return result
        except Exception:
            return []

    def _update_buckets(self):
        """Update bucket values based on current positions."""
        try:
            positions = self.get_positions()
            div_value = 0.0
            gro_value = 0.0
            pen_value = 0.0
            div_count = 0
            gro_count = 0
            pen_count = 0

            for p in positions:
                bucket = p.get("bucket", "growth")
                mv = p.get("market_value", 0)
                if bucket in ("dividend", "long_term"):
                    div_value += mv
                    div_count += 1
                elif bucket == "penny":
                    pen_value += mv
                    pen_count += 1
                else:
                    gro_value += mv
                    gro_count += 1

            account = self.get_account_info()
            if "error" not in account:
                total_equity = account.get("equity", 0)
            else:
                total_equity = 0

            self.buckets["dividend"]["value"] = div_value
            self.buckets["dividend"]["positions"] = div_count
            self.buckets["dividend"]["cash_allocated"] = self.buckets["dividend"].get("cash_allocated", div_value)
            self.buckets["growth"]["value"] = gro_value
            self.buckets["growth"]["positions"] = gro_count
            self.buckets["growth"]["cash_allocated"] = self.buckets["growth"].get("cash_allocated", gro_value)
            self.buckets["penny"]["value"] = pen_value
            self.buckets["penny"]["positions"] = pen_count
            self.buckets["penny"]["cash_allocated"] = self.buckets["penny"].get("cash_allocated", pen_value)
            self.buckets["withdrawal"]["available"] = self.buckets["withdrawal"].get("available", 0)
            self.buckets["last_updated"] = datetime.utcnow().isoformat()

            # Set original capital if not yet set
            if self.buckets.get("original_capital", 0) == 0 and total_equity > 0:
                self.buckets["original_capital"] = total_equity
                self.buckets["dividend"]["total_deposited"] = total_equity * self.settings.get("dividend_pct", 0.35)
                self.buckets["growth"]["total_deposited"] = total_equity * self.settings.get("growth_pct", 0.35)
                self.buckets["penny"]["total_deposited"] = total_equity * self.settings.get("penny_pct", 0.30)
                self._portfolio_start_value = total_equity

            self._save_trade_log()
        except Exception as e:
            print(f"Error updating buckets: {e}")

    def get_bucket_overview(self) -> Dict:
        """Return a dict summarizing the state of each bucket."""
        try:
            self._update_buckets()
        except Exception:
            pass

        div = self.buckets.get("dividend", {})
        gro = self.buckets.get("growth", {})
        pen = self.buckets.get("penny", {})
        wit = self.buckets.get("withdrawal", {})

        div_value = div.get("value", 0)
        gro_value = gro.get("value", 0)
        pen_value = pen.get("value", 0)
        wit_value = wit.get("available", 0)

        total_value = div_value + gro_value + pen_value + wit_value
        original_capital = self.buckets.get("original_capital", total_value if total_value > 0 else 100000)
        total_profit = total_value - original_capital
        profit_pct = (total_profit / original_capital * 100) if original_capital > 0 else 0

        return {
            "dividend": {
                "value": div_value,
                "positions": div.get("positions", 0),
                "total_deposited": div.get("total_deposited", 0),
                "dividends_earned": div.get("dividends_earned", 0),
                "profits_moved_in": div.get("profits_moved_in", 0),
            },
            "growth": {
                "value": gro_value,
                "positions": gro.get("positions", 0),
                "total_deposited": gro.get("total_deposited", 0),
                "profits_moved_in": gro.get("profits_moved_in", 0),
            },
            "penny": {
                "value": pen_value,
                "positions": pen.get("positions", 0),
                "total_deposited": pen.get("total_deposited", 0),
                "profits_to_growth": pen.get("profits_to_growth", 0),
            },
            "withdrawal": {
                "available": wit_value,
                "dividends_received": wit.get("dividends_received", 0),
                "profits_extracted": wit.get("profits_extracted", 0),
            },
            "total_profit": total_profit,
            "profit_pct": profit_pct,
            "original_capital": original_capital,
        }

    # ==========================================
    # Stock Classification
    # ==========================================

    def classify_stock(self, symbol: str) -> str:
        """Classify a stock into dividend, growth, or penny bucket."""
        symbol = symbol.upper().strip()
        if symbol in DIVIDEND_STOCKS:
            return "dividend"
        if symbol in GROWTH_STOCKS:
            return "growth"
        try:
            if YF_AVAILABLE:
                ticker = yf.Ticker(symbol)
                info = ticker.info or {}
                price = info.get("currentPrice", info.get("regularMarketPrice", info.get("previousClose", 0)))
                if not price or price == 0:
                    hist = ticker.history(period="5d")
                    if not hist.empty:
                        price = float(hist['Close'].iloc[-1])
                    else:
                        price = 0
                div_yield = info.get("dividendYield", 0) or 0
                if div_yield > 1:
                    div_yield = div_yield / 100
                penny_threshold = self.settings.get("penny_settings", {}).get(
                    "penny_price_threshold", self.settings.get("penny_price_threshold", 5.0))
                min_div_yield = self.settings.get("dividend_settings", {}).get(
                    "min_dividend_yield", self.settings.get("min_dividend_yield", 0.03))
                if price > 0 and price < penny_threshold:
                    return "penny"
                if div_yield and div_yield >= min_div_yield:
                    return "dividend"
                if price > 0:
                    return "growth"
        except Exception:
            pass
        return "growth"

    def assign_bucket(self, symbol: str) -> str:
        """Assign a bucket to a stock (normalizes long_term to dividend)."""
        result = self.classify_stock(symbol)
        if result == "long_term":
            result = "dividend"
        return result

    def debug_bucket(self, symbol: str) -> Dict:
        """Debug bucket classification for a symbol."""
        symbol = symbol.upper().strip()
        result = {
            "symbol": symbol,
            "in_dividend_list": symbol in DIVIDEND_STOCKS,
            "in_growth_list": symbol in GROWTH_STOCKS,
            "final_bucket": self.classify_stock(symbol),
            "penny_threshold": self.settings.get("penny_settings", {}).get(
                "penny_price_threshold", self.settings.get("penny_price_threshold", 5.0)),
            "min_dividend_yield": self.settings.get("dividend_settings", {}).get(
                "min_dividend_yield", self.settings.get("min_dividend_yield", 0.03)),
        }
        try:
            if YF_AVAILABLE:
                ticker = yf.Ticker(symbol)
                info = ticker.info or {}
                price = info.get("currentPrice", info.get("regularMarketPrice", 0))
                div_yield = info.get("dividendYield", 0) or 0
                if div_yield > 1:
                    div_yield = div_yield / 100
                market_cap = info.get("marketCap", 0) or 0
                sector = info.get("sector", "Unknown")
                result["price"] = price
                result["dividend_yield"] = div_yield
                result["market_cap"] = market_cap
                result["sector"] = sector
        except Exception as e:
            result["error"] = str(e)
        return result

    def _get_sector(self, symbol: str) -> str:
        """Get the sector for a symbol, with caching. Uses symbol→sector SECTOR_MAP."""
        symbol = symbol.upper().strip()
        if symbol in self._sector_cache:
            return self._sector_cache[symbol]
        # Direct lookup in symbol→sector map
        sector = SECTOR_MAP.get(symbol, None)
        if sector:
            self._sector_cache[symbol] = sector
            return sector
        # Fallback to yfinance
        try:
            if YF_AVAILABLE:
                ticker = yf.Ticker(symbol)
                info = ticker.info or {}
                sector = info.get("sector", "Unknown")
                self._sector_cache[symbol] = sector
                return sector
        except Exception:
            pass
        self._sector_cache[symbol] = "Unknown"
        return "Unknown"

    def _get_bucket_settings(self, bucket: str) -> Dict:
        """Get the settings dict for a specific bucket."""
        if bucket == "penny":
            return self.settings.get("penny_settings", DEFAULT_SETTINGS["penny_settings"])
        elif bucket in ("dividend", "long_term"):
            return self.settings.get("dividend_settings", DEFAULT_SETTINGS["dividend_settings"])
        else:
            return self.settings.get("growth_settings", DEFAULT_SETTINGS["growth_settings"])

    def _get_current_price(self, symbol: str) -> float:
        """Get the current price for a symbol. Uses Alpaca first, then yfinance fallback."""
        symbol = symbol.upper().strip()
        now = time.time()
        
        # Check cache (2 min TTL)
        if symbol in self._price_cache and (now - self._price_cache_time) < 120:
            return self._price_cache.get(symbol, 0)

        price = 0.0

        # ===== PRIMARY: Alpaca quote =====
        if self.connected and self.api:
            try:
                quote = self.api.get_latest_quote(symbol)
                if quote:
                    bid = float(getattr(quote, 'bid_price', 0) or getattr(quote, 'bid', 0) or 0)
                    ask = float(getattr(quote, 'ask_price', 0) or getattr(quote, 'ask', 0) or 0)
                    if bid > 0 and ask > 0:
                        price = (bid + ask) / 2
                    elif ask > 0:
                        price = ask
                    elif bid > 0:
                        price = bid
            except Exception:
                pass

            # Fallback: try latest trade
            if price <= 0:
                try:
                    trade = self.api.get_latest_trade(symbol)
                    if trade:
                        price = float(getattr(trade, 'price', 0) or 0)
                except Exception:
                    pass

        # ===== FALLBACK: yfinance =====
        if price <= 0 and YF_AVAILABLE:
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info or {}
                price = info.get("currentPrice", info.get("regularMarketPrice", info.get("previousClose", 0)))
                if not price or price == 0:
                    hist = ticker.history(period="5d")
                    if not hist.empty:
                        price = float(hist['Close'].iloc[-1])
            except Exception:
                pass

        if price > 0:
            self._price_cache[symbol] = float(price)
            self._price_cache_time = now
        else:
            self._price_cache[symbol] = 0

        return float(price) if price > 0 else 0
    # ==========================================
    # Scanning & Signals (scan_signals and evaluate_risk are SEPARATE methods)
    # ==========================================

    def scan_signals(self) -> List[Dict]:
        """Scan for signals and return them. Calls scan_all() internally."""
        self.scan_all()
        # Also record signals in history
        for sig in self.signals_found:
            self.record_signal(sig)
        return self.signals_found

    def scan_all(self):
        """Scan the watchlist for buy/sell signals."""
        self.signals_found = []

        if not self.connected or not self.api:
            self.status_message = "Not connected — cannot scan"
            return

        vix_result = {"safe_to_trade": True, "vix_value": 0, "reason": ""}
        if self.settings.get("use_vix_filter", True):
            vix_result = self.check_vix()
            if not vix_result.get("safe_to_trade", True):
                # When VIX is high, only block BUY signals — still allow SELL signals
                # This ensures we don't miss stop-losses and take-profits in volatile markets
                self._log_error("vix_filter", f"VIX {vix_result.get('vix_value', 0):.1f} — BUY signals only allowed for non-penny buckets")
                # Don't return — instead we'll filter signals below

        # Always define watchlist (needed as fallback)
        watchlist = self.settings.get("watchlist", [])

        # Decide which stocks to scan
        use_universe = self.settings.get("scan_full_universe", True)
        scan_slice = []
        scan_source = "none"

        if use_universe and self.connected and self.api:
            # Check universe cache first (30-min TTL)
            now = time.time()
            if (self._universe_cache and 
                (now - self._universe_cache_time) < self._universe_cache_ttl):
                scan_slice = self._universe_cache
                scan_source = "cached_universe"
                cache_age_min = int((now - self._universe_cache_time) / 60)
                self.status_message = f"Scanning {len(scan_slice)} stocks (cached universe, {cache_age_min}min old)"
                print(f"[SCAN] Using cached universe: {len(scan_slice)} stocks (age: {cache_age_min}min)")
            else:
                # Fetch fresh universe from Alpaca
                universe_size = self.settings.get("universe_scan_count", 300)
                print(f"[SCAN] Building universe scan for top {universe_size} stocks...")
                fresh_universe = self.scan_market_universe(top_n=universe_size)
                
                if fresh_universe:
                    # Universe scan succeeded — cache it
                    scan_slice = fresh_universe
                    self._universe_cache = fresh_universe
                    self._universe_cache_time = now
                    scan_source = "fresh_universe"
                    self.status_message = f"Scanning {len(scan_slice)} stocks from universe"
                    print(f"[SCAN] Universe scan complete: {len(scan_slice)} stocks")
                else:
                    # Universe scan FAILED — fall back to watchlist with clear warning
                    if not watchlist:
                        self.status_message = "⚠️ Universe scan failed AND no watchlist configured"
                        print(f"[SCAN] ⚠️ Universe scan failed AND no watchlist configured — nothing to scan")
                        return
                    scan_slice = list(watchlist)
                    scan_source = "watchlist_fallback"
                    self.status_message = f"⚠️ Universe scan failed, using watchlist ({len(watchlist)} stocks)"
                    print(f"[SCAN] ⚠️ Universe scan failed, falling back to watchlist ({len(watchlist)} stocks)")
        else:
            # Watchlist mode (user chose watchlist, or not connected)
            if not watchlist:
                self.status_message = "No watchlist configured"
                return
            max_per_cycle = 50
            if self.running and len(watchlist) > max_per_cycle:
                cycle_offset = (self.cycle_count * max_per_cycle) % len(watchlist)
                scan_slice = watchlist[cycle_offset:cycle_offset + max_per_cycle]
                scan_source = "watchlist_staggered"
                self.status_message = f"Scanning {len(scan_slice)}/{len(watchlist)} stocks (cycle {self.cycle_count})"
            else:
                scan_slice = list(watchlist)
                scan_source = "watchlist"

        if not scan_slice:
            self.status_message = "No stocks to scan"
            return

        print(f"[SCAN] Source: {scan_source}, Stocks: {len(scan_slice)}")

        # Universe scan results are already set above — do NOT override them here
        # Watchlist staggering only applies when universe scanning is disabled


        batch_data = self._batch_fetch_data(scan_slice)

        for symbol in scan_slice:
            try:
                df = batch_data.get(symbol)
                if df is None or df.empty or len(df) < 20:
                    continue

                close = float(df['close'].iloc[-1])
                volume = float(df['volume'].iloc[-1])
                avg_vol = float(df['volume'].rolling(20).mean().iloc[-1])
                rvol = volume / avg_vol if avg_vol > 0 else 0

                if close <= 0 or np.isnan(close):
                    continue

                # Calculate RSI
                rsi_val = 50.0
                if TA_AVAILABLE:
                    try:
                        rsi_series = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
                        rsi_val = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0
                    except Exception:
                        rsi_val = 50.0

                # Calculate ATR
                atr_val = 0.0
                if TA_AVAILABLE and self.settings.get("use_atr_position_sizing", True):
                    try:
                        atr_series = ta.volatility.AverageTrueRange(
                            df['high'], df['low'], df['close'], window=14
                        ).average_true_range()
                        atr_val = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 0.0
                    except Exception:
                        atr_val = 0.0

                # Get bucket and settings
                bucket = self.classify_stock(symbol)
                bucket_settings = self._get_bucket_settings(bucket)
                rsi_oversold = bucket_settings.get("rsi_oversold", 30)
                rsi_overbought = bucket_settings.get("rsi_overbought", 70)
                min_confidence = bucket_settings.get("min_confidence", 0.25)
                min_rvol = self.settings.get("min_rvol", 1.5)

                # Build confidence and signal
                confidence = 0.0
                reason_parts = []
                signal = "HOLD"

                # RSI signal
                if rsi_val < rsi_oversold:
                    confidence += 0.35
                    reason_parts.append(f"RSI {rsi_val:.0f} < {rsi_oversold} (oversold)")
                elif rsi_val > rsi_overbought:
                    confidence += 0.30
                    reason_parts.append(f"RSI {rsi_val:.0f} > {rsi_overbought} (overbought)")

                # Volume signal
                if rvol >= min_rvol:
                    confidence += 0.20
                    reason_parts.append(f"RVOL {rvol:.1f}")

                # Advanced signals
                if self.settings.get("use_advanced_signals", True) and TA_AVAILABLE:
                    # MACD
                    try:
                        macd_indicator = ta.trend.MACD(df['close'])
                        macd_line = macd_indicator.macd()
                        macd_signal_line = macd_indicator.macd_signal()
                        macd_hist = macd_indicator.macd_diff()
                        if not pd.isna(macd_line.iloc[-1]) and not pd.isna(macd_signal_line.iloc[-1]):
                            if macd_line.iloc[-1] > macd_signal_line.iloc[-1]:
                                confidence += 0.15
                                reason_parts.append("MACD bullish crossover")
                            elif macd_line.iloc[-1] < macd_signal_line.iloc[-1]:
                                confidence += 0.10
                                reason_parts.append("MACD bearish crossover")
                            # MACD histogram momentum
                            if len(macd_hist) >= 2 and not pd.isna(macd_hist.iloc[-1]) and not pd.isna(macd_hist.iloc[-2]):
                                if macd_hist.iloc[-1] > macd_hist.iloc[-2] and macd_hist.iloc[-1] > 0:
                                    confidence += 0.05
                                    reason_parts.append("MACD histogram expanding")
                    except Exception:
                        pass

                    # Bollinger Bands
                    try:
                        bb_indicator = ta.volatility.BollingerBands(df['close'])
                        bb_high = bb_indicator.bollinger_hband()
                        bb_low = bb_indicator.bollinger_lband()
                        bb_mid = bb_indicator.bollinger_mavg()
                        if not pd.isna(bb_high.iloc[-1]) and not pd.isna(bb_low.iloc[-1]):
                            if close < bb_low.iloc[-1]:
                                confidence += 0.10
                                reason_parts.append("Below lower Bollinger Band")
                            elif close > bb_high.iloc[-1]:
                                confidence += 0.10
                                reason_parts.append("Above upper Bollinger Band")
                    except Exception:
                        pass

                    # SMA crossovers
                    try:
                        sma_50 = df['close'].rolling(50).mean()
                        sma_200 = df['close'].rolling(200).mean()
                        if len(sma_50) >= 2 and len(sma_200) >= 2:
                            if not pd.isna(sma_50.iloc[-1]) and not pd.isna(sma_200.iloc[-1]):
                                if sma_50.iloc[-1] > sma_200.iloc[-1]:
                                    confidence += 0.10
                                    reason_parts.append("Golden Cross (SMA50 > SMA200)")
                                elif sma_50.iloc[-1] < sma_200.iloc[-1]:
                                    confidence += 0.05
                                    reason_parts.append("Death Cross (SMA50 < SMA200)")
                    except Exception:
                        pass

                # Determine signal direction
                # VIX filter: during high VIX, only allow SELL signals and penny buys
                vix_blocking_buys = (self.settings.get("use_vix_filter", True) and 
                                     not vix_result.get("safe_to_trade", True))
                
                if rsi_val < rsi_oversold and confidence >= min_confidence:
                    if vix_blocking_buys and bucket != "penny":
                        # High VIX: only allow penny buys (they move independently)
                        signal = "HOLD"
                        reason_parts.append("VIX high — buy paused (penny exempt)")
                    else:
                        signal = "BUY"
                elif rsi_val > rsi_overbought and confidence >= min_confidence:
                    signal = "SELL"
                elif confidence >= 0.15:
                    signal = "HOLD"

                self.signals_found.append({
                    "symbol": symbol,
                    "signal": signal,
                    "price": close,
                    "rsi": round(rsi_val, 1),
                    "rvol": round(rvol, 2),
                    "atr": round(atr_val, 2),
                    "confidence": round(min(confidence, 1.0), 2),
                    "bucket": bucket,
                    "reason": " | ".join(reason_parts) if reason_parts else "No strong signal",
                })

            except Exception:
                continue

        buy_count = sum(1 for s in self.signals_found if s.get("signal") == "BUY")
        sell_count = sum(1 for s in self.signals_found if s.get("signal") == "SELL")
        hold_count = len(self.signals_found) - buy_count - sell_count
        self.status_message = (
            f"Scan #{self.cycle_count}: {len(scan_slice)} scanned, "
            f"{buy_count} BUY / {sell_count} SELL / "
            f"{len(self.signals_found) - buy_count - sell_count} HOLD"
        )
        print(f"[SCAN] {self.status_message}")

    def evaluate_risk(self, symbol: str, signal_data: Dict) -> Dict:
        """Evaluate if a trade meets risk criteria. Logs every rejection reason."""
        result = {
            "approved": False,
            "symbol": symbol,
            "reasons": [],
            "bucket": signal_data.get("bucket", "growth"),
            "confidence": signal_data.get("confidence", 0),
        }

        try:
            positions = self.get_positions()

            # Check max positions
            max_positions = self.settings.get("max_positions", 10)
            if len(positions) >= max_positions:
                result["reasons"].append(f"Max positions reached ({len(positions)}/{max_positions})")
                return result

            # Check if already in position
            existing_symbols = [p["symbol"] for p in positions]
            if symbol in existing_symbols and signal_data.get("signal") == "BUY":
                # Allow adding up to max_positions / 2 of the same stock
                same_count = sum(1 for p in positions if p["symbol"] == symbol)
                max_same = max(2, self.settings.get("max_positions", 10) // 3)
                if same_count >= max_same:
                    result["reasons"].append(f"Already holding {max_same} of {symbol}")
                    return result
                # else: allow adding to position

            # Check confidence
            confidence = signal_data.get("confidence", 0)
            bucket = signal_data.get("bucket", "growth")
            bucket_settings = self._get_bucket_settings(bucket)
            min_confidence = bucket_settings.get("min_confidence",
                            self.settings.get("min_confidence", 0.25))
            if confidence < min_confidence:
                result["reasons"].append(f"Confidence {confidence:.0%} below {min_confidence:.0%} minimum")
                return result

            # Check max position %
            account = self.get_account_info()
            if "error" not in account:
                equity = account.get("equity", 0)
                buying_power = account.get("buying_power", 0)
                max_pos_pct = bucket_settings.get("max_position_pct",
                                self.settings.get("max_position_pct", 0.08))
                price = signal_data.get("price", 0)

                if price > 0 and equity > 0:
                    # ATR position sizing
                    if self.settings.get("use_atr_position_sizing", True) and signal_data.get("atr", 0) > 0:
                        atr = signal_data.get("atr", 0)
                        risk_per_share = atr * 2
                        stop_loss_pct = bucket_settings.get("stop_loss_pct",
                                      self.settings.get("stop_loss_pct", 0.05))
                        if risk_per_share > 0 and stop_loss_pct > 0:
                            risk_amount = equity * stop_loss_pct
                            qty_atr = max(1, int(risk_amount / risk_per_share))
                            max_value_atr = qty_atr * price
                            if max_value_atr / equity > max_pos_pct:
                                qty_atr = int(equity * max_pos_pct / price)
                        else:
                            qty_atr = 1
                    else:
                        qty_atr = 1

                    position_value = qty_atr * price
                    if position_value / equity > max_pos_pct:
                        result["reasons"].append(f"Position exceeds {max_pos_pct:.0%} max allocation")
                        return result

                    # Check buying power
                    if signal_data.get("signal") == "BUY" and position_value > buying_power:
                        result["reasons"].append(f"Insufficient buying power (${buying_power:,.0f})")
                        return result

            # Check daily loss limit
            daily_loss_limit = self.settings.get("daily_loss_limit_pct", 0.03)
            if self.daily_pnl < 0 and "error" not in account and account.get("equity", 0) > 0:
                daily_loss_pct = abs(self.daily_pnl) / account["equity"]
                if daily_loss_pct > daily_loss_limit:
                    result["reasons"].append(f"Daily loss limit reached ({daily_loss_pct:.1%} > {daily_loss_limit:.0%})")
                    return result

            # Check sector limit
            max_same_sector = self.settings.get("max_same_sector", 3)
            target_sector = self._get_sector(symbol)
            sector_count = sum(1 for p in positions if self._get_sector(p["symbol"]) == target_sector)
            if sector_count >= max_same_sector:
                result["reasons"].append(f"Max same sector ({sector_count}/{max_same_sector} in {target_sector})")
                return result

            # VIX filter check — penny stocks exempt during high VIX
            if self.settings.get("use_vix_filter", True):
                vix_result = self.check_vix()
                if not vix_result.get("safe_to_trade", True) and bucket != "penny":
                    result["reasons"].append(vix_result.get("reason", "VIX filter active"))
                    return result

            # All checks passed
            result["approved"] = True
            return result

        except Exception as e:
            result["reasons"].append(f"Risk evaluation error: {e}")
            self._log_error("evaluate_risk", str(e), symbol)
            return result

    # ==========================================
    # Batch Data Fetching
    # ==========================================

    def _batch_fetch_data(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """Fetch historical data using Alpaca API first, fall back to yfinance."""
        result = {}
        failed_symbols = []
        now = time.time()
        cache_hits = 0
        fetch_count = 0

        # Check cache first
        for symbol in list(symbols):
            if symbol in self._data_cache and symbol in self._data_cache_time:
                cache_age = now - self._data_cache_time[symbol]
                if cache_age < self._data_cache_ttl:
                    result[symbol] = self._data_cache[symbol]
                    cache_hits += 1

        if len(result) == len(symbols):
            return result

        symbols_to_fetch = [s for s in symbols if s not in result]

        # ===== PRIMARY: Alpaca API =====
        if self.connected and self.api:
            try:
                from alpaca_trade_api.rest import TimeFrame
                
                end_dt = datetime.utcnow()
                start_dt = end_dt - timedelta(days=90)
                
                chunk_size = 50
                for i in range(0, len(symbols_to_fetch), chunk_size):
                    chunk = symbols_to_fetch[i:i + chunk_size]
                    
                    try:
                        bars_df = self.api.get_bars(
                            symbol_or_symbols=chunk,
                            timeframe=TimeFrame.Day,
                            start=start_dt.strftime("%Y-%m-%d"),
                            end=end_dt.strftime("%Y-%m-%d"),
                            adjustment='raw'
                        )
                        
                        if bars_df is not None and not bars_df.empty:
                            # Handle multi-symbol DataFrame (has MultiIndex)
                            if isinstance(bars_df.index, pd.MultiIndex):
                                for symbol in chunk:
                                    try:
                                        if symbol in bars_df.index.get_level_values(0):
                                            sym_df = bars_df.loc[symbol].copy()
                                            sym_df.columns = [c.lower() for c in sym_df.columns]
                                            for drop_col in ['trade_count', 'vwap']:
                                                if drop_col in sym_df.columns:
                                                    sym_df = sym_df.drop(columns=[drop_col])
                                            sym_df.dropna(subset=['close'], inplace=True)
                                            if not sym_df.empty and len(sym_df) >= 20:
                                                result[symbol] = sym_df
                                                self._data_cache[symbol] = sym_df
                                                self._data_cache_time[symbol] = now
                                                fetch_count += 1
                                    except Exception:
                                        failed_symbols.append(symbol)
                            else:
                                # Single symbol response
                                if len(chunk) == 1:
                                    sym_df = bars_df.copy()
                                    sym_df.columns = [c.lower() for c in sym_df.columns]
                                    for drop_col in ['trade_count', 'vwap']:
                                        if drop_col in sym_df.columns:
                                            sym_df = sym_df.drop(columns=[drop_col])
                                    sym_df.dropna(subset=['close'], inplace=True)
                                    if not sym_df.empty and len(sym_df) >= 20:
                                        result[chunk[0]] = sym_df
                                        self._data_cache[chunk[0]] = sym_df
                                        self._data_cache_time[chunk[0]] = now
                                        fetch_count += 1
                    except Exception as e:
                        self._log_error("alpaca_bars_chunk", str(e))
                        failed_symbols.extend(chunk)
                        
            except ImportError:
                # TimeFrame not available, fall through to yfinance
                pass
            except Exception as e:
                self._log_error("alpaca_data_fetch", str(e))

        # ===== FALLBACK: yfinance for remaining symbols =====
        remaining = [s for s in symbols_to_fetch if s not in result]
        
        if remaining and YF_AVAILABLE:
            chunk_size = 50
            for i in range(0, len(remaining), chunk_size):
                chunk = remaining[i:i + chunk_size]
                try:
                    if len(chunk) > 1:
                        ticker_string = " ".join(chunk)
                        batch_df = yf.download(ticker_string, period="3mo", group_by="ticker",
                                               threads=True, progress=False)
                        for symbol in chunk:
                            try:
                                if isinstance(batch_df.columns, pd.MultiIndex):
                                    sym_df = batch_df[symbol].copy()
                                else:
                                    sym_df = batch_df.copy()
                                sym_df.columns = [str(col).lower().replace(' ', '_') for col in sym_df.columns]
                                if 'adj_close' in sym_df.columns:
                                    sym_df = sym_df.drop(columns=['adj_close'])
                                if 'close' in sym_df.columns:
                                    sym_df.dropna(subset=['close'], inplace=True)
                                if not sym_df.empty and len(sym_df) >= 20:
                                    result[symbol] = sym_df
                                    self._data_cache[symbol] = sym_df
                                    self._data_cache_time[symbol] = now
                                    fetch_count += 1
                            except Exception:
                                failed_symbols.append(symbol)
                except Exception:
                    failed_symbols.extend(chunk)

            # Retry failed symbols individually
            still_failed = [s for s in remaining if s not in result]
            if still_failed and len(still_failed) <= 20:
                for symbol in still_failed:
                    if symbol not in result:
                        try:
                            df = yf.Ticker(symbol).history(period="3mo")
                            if df is not None and not df.empty and len(df) >= 20:
                                df.columns = [c.lower() for c in df.columns]
                                if 'adj_close' in df.columns:
                                    df = df.drop(columns=['adj_close'])
                                result[symbol] = df
                                self._data_cache[symbol] = df
                                self._data_cache_time[symbol] = now
                                fetch_count += 1
                        except Exception:
                            pass

        # Log summary
        total_requested = len(symbols)
        total_fetched = len(result)
        if total_fetched < total_requested * 0.5:
            self._log_error("data_fetch_warning", 
                f"Only fetched {total_fetched}/{total_requested} symbols. "
                f"Cache: {cache_hits}, Alpaca/YF: {fetch_count}, Failed: {len(failed_symbols)}")

        # Clean old cache entries (keep only last 500 stocks)
        if len(self._data_cache) > 500:
            oldest_keys = sorted(self._data_cache_time, key=self._data_cache_time.get)[:100]
            for key in oldest_keys:
                self._data_cache.pop(key, None)
                self._data_cache_time.pop(key, None)

        return result

    # ==========================================
    # Order Placement & Position Management
    # ==========================================

    def place_order(self, symbol: str, side: str, qty: float = None,
                    order_type: str = "market", limit_price: float = None,
                    bucket: str = None, confidence: float = 0.0,
                    reason: str = "") -> Dict:
        """Place an order on Alpaca with position sizing."""
        try:
            if not self.connected or not self.api:
                return {"status": "error", "message": "Not connected to Alpaca"}

            if not bucket:
                bucket = self.classify_stock(symbol)

            bucket_settings = self._get_bucket_settings(bucket)
            account = self.get_account_info()
            if "error" in account:
                return {"status": "error", "message": f"Cannot get account info: {account['error']}"}

            equity = account.get("equity", 0)
            buying_power = account.get("buying_power", 0)
            price = 0

            # Get price
            price = self._get_current_price(symbol) if side == "buy" else 0
            if side == "buy" and price <= 0:
                try:
                    ticker = yf.Ticker(symbol)
                    info = ticker.info or {}
                    price = info.get("currentPrice", info.get("regularMarketPrice", 0))
                    if not price:
                        hist = ticker.history(period="5d")
                        if not hist.empty:
                            price = float(hist['Close'].iloc[-1])
                except Exception:
                    pass
            if price <= 0:
                return {"status": "error", "message": f"Cannot get price for {symbol}"}

            # Calculate quantity
            if qty is None or qty <= 0:
                max_pos_pct = bucket_settings.get("max_position_pct",
                                self.settings.get("max_position_pct", 0.08))
                max_position_value = equity * max_pos_pct

                # ATR position sizing
                if self.settings.get("use_atr_position_sizing", True):
                    try:
                        ticker_data = yf.Ticker(symbol).history(period="3mo")
                        if not ticker_data.empty and TA_AVAILABLE and len(ticker_data) >= 14:
                            atr_series = ta.volatility.AverageTrueRange(
                                ticker_data['High'], ticker_data['Low'], ticker_data['Close'],
                                window=14
                            ).average_true_range()
                            atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 0
                            stop_loss_pct = bucket_settings.get("stop_loss_pct",
                                          self.settings.get("stop_loss_pct", 0.05))
                            if atr > 0 and stop_loss_pct > 0:
                                risk_per_share = atr * 2
                                risk_amount = equity * stop_loss_pct
                                qty_atr = max(1, int(risk_amount / risk_per_share))
                                position_value_atr = qty_atr * price
                                if position_value_atr <= max_position_value and qty_atr * price <= buying_power:
                                    qty = qty_atr
                    except Exception:
                        pass

                if qty is None or qty <= 0:
                    qty = max(1, int(max_position_value / price))

                # Ensure we don't exceed buying power
                if side == "buy" and qty * price > buying_power:
                    qty = max(1, int(buying_power / price))
                    if qty * price > buying_power:
                        return {"status": "error", "message": f"Insufficient buying power for {symbol}"}

            # Submit order
            if order_type == "limit" and limit_price:
                order = self.api.submit_order(
                    symbol=symbol, qty=qty, side=side, type="limit",
                    time_in_force="day", limit_price=limit_price,
                )
            else:
                order = self.api.submit_order(
                    symbol=symbol, qty=qty, side=side, type="market",
                    time_in_force="day",
                )

            # Get filled price (may be 0 for market orders initially)
            filled_price = float(getattr(order, 'filled_avg_price', 0) or 0)
            if filled_price <= 0:
                filled_price = price

            # Log the trade
            trade_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "price": filled_price,
                "bucket": bucket,
                "confidence": confidence,
                "reason": reason,
                "order_id": getattr(order, 'id', ''),
                "order_status": getattr(order, 'status', 'unknown'),
            }
            self.trade_log.append(trade_entry)
            self._save_trade_log()

            if AUDIT_AVAILABLE and self.username:
                try:
                    log_trade_audit(self.username, symbol, side, qty, filled_price, bucket, confidence, reason)
                except Exception:
                    pass

            bucket_icon = BUCKET_ICONS.get(bucket, "⚪")
            self.send_alert(
                f"{'🟢' if side == 'buy' else '🔴'} **{side.upper()}** {qty} shares of **{symbol}** "
                f"at ${filled_price:.2f} ({bucket_icon} {bucket.title()}) | Confidence: {confidence:.0%}"
            )

            return {"status": "success", "order_id": getattr(order, 'id', ''), "qty": qty, "price": filled_price}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def close_position(self, symbol: str, reason: str = "") -> Dict:
        """Close a position by selling all shares of a symbol."""
        try:
            if not self.connected or not self.api:
                return {"status": "error", "message": "Not connected to Alpaca"}

            positions = self.get_positions()
            position = None
            for p in positions:
                if p["symbol"] == symbol:
                    position = p
                    break

            if not position:
                return {"status": "error", "message": f"No position found for {symbol}"}

            qty = position["qty"]
            bucket = position.get("bucket", self.classify_stock(symbol))
            entry_price = position.get("avg_entry_price", 0)
            current_price = position.get("current_price", 0)
            pl = position.get("unrealized_pl", 0)
            pl_pct = position.get("unrealized_plpc", 0)
            market_value = position.get("market_value", 0)

            # Submit sell order
            order = self.api.submit_order(
                symbol=symbol, qty=qty, side="sell",
                type="market", time_in_force="day",
            )

            # Handle profit skimming
            skim_pct = self.settings.get("profit_skim_pct", 1.0)
            if pl > 0 and skim_pct > 0:
                profit_to_withdraw = pl * skim_pct
                self.buckets["withdrawal"]["available"] = self.buckets["withdrawal"].get("available", 0) + profit_to_withdraw
                self.buckets["withdrawal"]["profits_extracted"] = self.buckets["withdrawal"].get("profits_extracted", 0) + profit_to_withdraw

                # Remaining profit goes back to bucket
                remaining_profit = pl * (1 - skim_pct)
                if bucket in self.buckets:
                    self.buckets[bucket]["profits_moved_in"] = self.buckets[bucket].get("profits_moved_in", 0) + remaining_profit

            # Check and remove trailing stop
            if symbol in self._trailing_stops:
                del self._trailing_stops[symbol]

            # Log the trade
            trade_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "symbol": symbol,
                "side": "sell",
                "qty": qty,
                "price": current_price if current_price > 0 else entry_price,
                "bucket": bucket,
                "confidence": 0,
                "reason": reason or f"Close position (P&L: {pl_pct:+.2%})",
                "order_id": getattr(order, 'id', ''),
                "order_status": getattr(order, 'status', 'unknown'),
                "pl": pl,
                "pl_pct": pl_pct,
                "market_value": market_value,
                "entry_price": entry_price,
            }
            self.trade_log.append(trade_entry)
            self._save_trade_log()

            bucket_icon = BUCKET_ICONS.get(bucket, "⚪")
            self.send_alert(
                f"🔴 **SELL** {qty} shares of **{symbol}** ({bucket_icon} {bucket.title()}) | "
                f"P&L: ${pl:+,.2f} ({pl_pct:+.2%}) | Reason: {reason or 'Stop/Target hit'}"
            )

            # Profit/Loss alert for Discord
            if self.settings.get("discord_profit_alerts", True):
                if pl > 0:
                    self.send_alert(
                        f"💰 **PROFIT** | **{symbol}** sold for **${pl:+,.2f}** profit ({pl_pct:+.2%}) | "
                        f"Entry ${entry_price:.2f} → Exit ${current_price:.2f} | {bucket_icon} {bucket.title()}"
                    )
                elif pl < 0:
                    self.send_alert(
                        f"📉 **LOSS** | **{symbol}** sold at **${pl:+,.2f}** loss ({pl_pct:+.2%}) | "
                        f"Entry ${entry_price:.2f} → Exit ${current_price:.2f} | {bucket_icon} {bucket.title()}"
                    )

            return {
                "status": "success",
                "symbol": symbol,
                "qty": qty,
                "pl": pl,
                "pl_pct": pl_pct,
                "pl_dollar": pl,
                "market_value": market_value,
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def check_stops(self) -> List[Dict]:
        """Check stop losses, take profits, and trailing stops on all positions."""
        results = []

        try:
            if not self.connected or not self.api:
                return results

            positions = self.get_positions()
            for p in positions:
                symbol = p["symbol"]
                bucket = p.get("bucket", self.classify_stock(symbol))
                bucket_settings = self._get_bucket_settings(bucket)

                entry_price = p.get("avg_entry_price", 0)
                current_price = p.get("current_price", 0)
                pl_pct = p.get("unrealized_plpc", 0)
                pl_dollar = p.get("unrealized_pl", 0)
                market_value = p.get("market_value", 0)

                if entry_price <= 0 or current_price <= 0:
                    continue

                # Get thresholds
                stop_loss_pct = bucket_settings.get("stop_loss_pct",
                                self.settings.get("stop_loss_pct", 0.05))
                take_profit_pct = bucket_settings.get("take_profit_pct",
                                 self.settings.get("take_profit_pct", 0.10))
                trailing_stop_pct = bucket_settings.get("trailing_stop_pct",
                                  self.settings.get("trailing_stop_pct", 0.04))

                # Check stop loss
                if pl_pct <= -stop_loss_pct:
                    close_result = self.close_position(symbol,
                        reason=f"Stop loss hit: {pl_pct:+.2%} (threshold: -{stop_loss_pct:.0%})")
                    results.append({
                        "symbol": symbol,
                        "action": "stop_loss",
                        "pl_pct": pl_pct,
                        "pl_dollar": pl_dollar,
                        "threshold": -stop_loss_pct,
                        "bucket": bucket,
                        "result": close_result,
                    })
                    continue

                # Check take profit
                if pl_pct >= take_profit_pct:
                    close_result = self.close_position(symbol,
                        reason=f"Take profit hit: {pl_pct:+.2%} (target: {take_profit_pct:.0%})")
                    results.append({
                        "symbol": symbol,
                        "action": "take_profit",
                        "pl_pct": pl_pct,
                        "pl_dollar": pl_dollar,
                        "threshold": take_profit_pct,
                        "bucket": bucket,
                        "result": close_result,
                    })
                    continue

                # Trailing stop logic
                if symbol in self._trailing_stops:
                    high_water = self._trailing_stops[symbol].get("high_water", entry_price)
                    if current_price > high_water:
                        self._trailing_stops[symbol]["high_water"] = current_price
                        high_water = current_price
                    drop_from_high = (high_water - current_price) / high_water if high_water > 0 else 0
                    if drop_from_high >= trailing_stop_pct and pl_pct > 0:
                        close_result = self.close_position(symbol,
                            reason=f"Trailing stop hit: dropped {drop_from_high:.2%} from high (${high_water:.2f})")
                        results.append({
                            "symbol": symbol,
                            "action": "trailing_stop",
                            "pl_pct": pl_pct,
                            "pl_dollar": pl_dollar,
                            "threshold": trailing_stop_pct,
                            "bucket": bucket,
                            "result": close_result,
                        })
                        continue
                else:
                    # Initialize trailing stop
                    self._trailing_stops[symbol] = {
                        "high_water": current_price,
                        "entry_price": entry_price,
                    }

        except Exception as e:
            print(f"Error checking stops: {e}")

        return results

    # ==========================================
    # Trading Cycle
    # ==========================================

    def run_cycle(self):
        """Run one complete trading cycle with detailed logging."""
        try:
            self.cycle_count += 1
            self.consecutive_failures = 0  # Reset on successful cycle start
            self.status_message = f"Running cycle {self.cycle_count}..."

            # Check and reset daily counters
            self._check_and_reset_daily()

            # Check market open
            market = self.is_market_open()
            if not market.get("is_open", False):
                self.status_message = f"Market closed ({market.get('day_name', '')}). Cycle {self.cycle_count} skipped."
                return

            # Check VIX filter — only block BUYS, not sells/stops
            vix_result = {"safe_to_trade": True, "vix_value": 0, "reason": ""}
            if self.settings.get("use_vix_filter", True):
                vix_result = self.check_vix()
                # VIX filter only blocks new buys, NOT stop-losses or take-profits
                # Penny stocks often move independently of VIX
                if not vix_result.get("safe_to_trade", True):
                    self.status_message = f"VIX {vix_result.get('vix_value', 0):.1f}: Buys paused, stops still active"
                    # Don't return — still process sells and stops below

            # Always define watchlist (needed as fallback)
            watchlist = self.settings.get("watchlist", [])

            # Reset daily P&L at start of day
            today = datetime.utcnow().strftime("%Y-%m-%d")
            last_cycle_date = self.trade_log[-1].get("timestamp", "")[:10] if self.trade_log else ""
            if last_cycle_date != today:
                account = self.get_account_info()
                if "error" not in account:
                    self._daily_start_equity = account.get("equity", 0)
                    self.daily_pnl = 0.0

            # Scan for signals and record them
            self.scan_all()
            for sig in self.signals_found:
                self.record_signal(sig)
            buy_count = sum(1 for s in self.signals_found if s.get("signal") == "BUY")
            sell_count = sum(1 for s in self.signals_found if s.get("signal") == "SELL")

            # Process BUY signals
            trades_made = 0
            signals_blocked = []
            for signal in self.signals_found:
                if signal["signal"] == "BUY":
                    # Bucket allocation check
                    bucket = signal.get("bucket", "growth")
                    if bucket == "long_term":
                        bucket = "dividend"
                    
                    bucket_pct_key = f"{bucket}_pct"
                    bucket_pct = self.settings.get(bucket_pct_key, 0)
                    
                    if bucket_pct <= 0:
                        signals_blocked.append(f"{signal['symbol']}: {bucket} allocation 0%")
                        continue
                    
                    risk = self.evaluate_risk(signal["symbol"], signal)
                    if risk["approved"]:
                        order_result = self.place_order(
                            symbol=signal["symbol"],
                            side="buy",
                            bucket=signal.get("bucket"),
                            confidence=signal.get("confidence", 0),
                            reason=signal.get("reason", ""),
                        )
                        if order_result.get("status") == "success":
                            trades_made += 1
                    else:
                        signals_blocked.append(f"{signal['symbol']}: {', '.join(risk.get('reasons', ['Unknown']))}")

            # Check stops and take profits
            stop_results = self.check_stops()

            # Check for dividends
            try:
                div_result = self.check_dividends()
                if div_result.get("dividends_found", 0) > 0:
                    for d in div_result.get("details", []):
                        self.buckets["withdrawal"]["available"] = self.buckets["withdrawal"].get("available", 0) + d.get("amount", 0)
                        self.buckets["withdrawal"]["dividends_received"] = self.buckets["withdrawal"].get("dividends_received", 0) + d.get("amount", 0)
            except Exception as e:
                self._log_error("dividends", str(e))
            
            # Check sell after ex-dividend
            try:
                sell_div_result = self.check_sell_after_dividend()
                if sell_div_result:
                    for result in sell_div_result:
                        if result.get("close_result", {}).get("status") == "success":
                            self.buckets["withdrawal"]["available"] = self.buckets["withdrawal"].get("available", 0) + result.get("dividend_income", 0)
                            self.buckets["withdrawal"]["dividends_received"] = self.buckets["withdrawal"].get("dividends_received", 0) + result.get("dividend_income", 0)
            except Exception as e:
                self._log_error("sell_after_dividend", str(e))

            # Check profit extraction
            if self.settings.get("auto_extract_profits", True):
                try:
                    self.extract_profits()
                except Exception:
                    pass

            # Update buckets
            self._update_buckets()

            # Record equity snapshot
            try:
                self.record_equity_snapshot()
            except Exception:
                pass

            # Update P&L
            try:
                account = self.get_account_info()
                if "error" not in account:
                    current_equity = account.get("equity", 0)
                    self.daily_pnl = current_equity - self._daily_start_equity
                    self.last_equity = current_equity
            except Exception:
                pass

            self._save_trade_log()
            
            # Build detailed status message
            blocked_msg = ""
            if signals_blocked:
                blocked_msg = f" | Blocked: {len(signals_blocked)}"
                # Show first reason in status so you can see WHY
                if signals_blocked:
                    blocked_msg += f" WHY: {signals_blocked[0]}"
                for b in signals_blocked[:5]:
                    self._log_error("signal_blocked", b)

            
            self.status_message = (
                f"Cycle {self.cycle_count} complete. "
                f"Signals: {buy_count}B/{sell_count}S | "
                f"Trades: {trades_made} | Stops: {len(stop_results)}"
                f"{blocked_msg}"
            )
            self.last_successful_cycle = datetime.utcnow().isoformat()

        except Exception as e:
            self.consecutive_failures += 1
            self.status_message = f"Cycle error: {str(e)}"
            self._log_error("run_cycle", str(e))

    # ==========================================
    # Sell Everything / Move / Redistribute
    # ==========================================

    def sell_everything(self) -> Dict:
        """Sell all open positions and move proceeds to withdrawal pot."""
        try:
            if not self.connected or not self.api:
                return {"status": "error", "message": "Not connected to Alpaca"}

            positions = self.get_positions()
            if not positions:
                return {"status": "no_positions", "message": "No open positions to sell."}

            positions_sold = []
            total_value = 0.0
            errors = []

            for p in positions:
                symbol = p["symbol"]
                bucket = p.get("bucket", self.classify_stock(symbol))
                qty = p["qty"]
                market_value = p.get("market_value", 0)
                pl_pct = p.get("unrealized_plpc", 0)
                pl_dollar = p.get("unrealized_pl", 0)
                current_price = p.get("current_price", 0)

                try:
                    order = self.api.submit_order(
                        symbol=symbol, qty=qty, side="sell",
                        type="market", time_in_force="day",
                    )
                    positions_sold.append({
                        "symbol": symbol,
                        "bucket": bucket,
                        "qty": qty,
                        "market_value": market_value,
                        "pl_pct": pl_pct,
                        "pl_dollar": pl_dollar,
                        "current_price": current_price,
                    })
                    total_value += market_value

                    # Handle profit skimming on sell
                    skim_pct = self.settings.get("profit_skim_pct", 1.0)
                    pl_dollar = p.get("unrealized_pl", 0)
                    if pl_dollar > 0 and skim_pct > 0:
                        profit_to_withdraw = pl_dollar * skim_pct
                        self.buckets["withdrawal"]["available"] = self.buckets["withdrawal"].get("available", 0) + profit_to_withdraw
                        self.buckets["withdrawal"]["profits_extracted"] = self.buckets["withdrawal"].get("profits_extracted", 0) + profit_to_withdraw

                    # Log the trade
                    trade_entry = {
                        "timestamp": datetime.utcnow().isoformat(),
                        "symbol": symbol,
                        "side": "sell",
                        "qty": qty,
                        "price": current_price,
                        "bucket": bucket,
                        "confidence": 0,
                        "reason": "Sell everything",
                        "pl": pl_dollar,
                        "pl_pct": pl_pct,
                        "market_value": market_value,
                    }
                    self.trade_log.append(trade_entry)

                    # Remove trailing stop
                    if symbol in self._trailing_stops:
                        del self._trailing_stops[symbol]

                except Exception as e:
                    errors.append(f"{symbol}: {str(e)}")
                    positions_sold.append({
                        "symbol": symbol,
                        "bucket": bucket,
                        "market_value": market_value,
                        "pl_pct": pl_pct,
                        "error": str(e),
                    })

            # Move all proceeds to withdrawal pot
            if total_value > 0:
                self.buckets["withdrawal"]["available"] = self.buckets["withdrawal"].get("available", 0) + total_value
            self._save_trade_log()

            self.send_alert(
                f"🛑 **SELL EVERYTHING** — Sold {len(positions_sold)} positions worth ${total_value:,.2f}. "
                f"Proceeds moved to 🟡 Withdrawal Pot."
            )

            # Send individual profit/loss alerts for each position sold
            if self.settings.get("discord_profit_alerts", True):
                for p in positions_sold:
                    p_pl = p.get("pl_dollar", 0)
                    p_symbol = p.get("symbol", "")
                    p_bucket = p.get("bucket", "growth")
                    p_bucket_icon = BUCKET_ICONS.get(p_bucket, "⚪")
                    if p_pl > 0:
                        self.send_alert(
                            f"💰 **PROFIT** | **{p_symbol}** sold for **${p_pl:+,.2f}** profit | {p_bucket_icon} {p_bucket.title()}"
                        )
                    elif p_pl < 0:
                        self.send_alert(
                            f"📉 **LOSS** | **{p_symbol}** sold at **${p_pl:+,.2f}** loss | {p_bucket_icon} {p_bucket.title()}"
                        )

            msg = f"Sold {len(positions_sold)} positions worth ${total_value:,.2f}. Proceeds moved to Withdrawal Pot."

            if errors:
                msg += f" Errors: {len(errors)}"

            return {
                "status": "sold",
                "message": msg,
                "positions_sold": positions_sold,
                "total_value": total_value,
                "errors": errors,
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def move_from_withdrawal(self, amount: float, bucket: str) -> Dict:
        """Move money from the withdrawal pot to a trading bucket."""
        try:
            available = self.buckets["withdrawal"].get("available", 0)
            if amount <= 0:
                return {"status": "error", "message": "Amount must be positive."}
            if amount > available:
                return {"status": "error", "message": f"Amount ${amount:,.2f} exceeds available ${available:,.2f} in Withdrawal Pot."}

            # Normalize bucket name
            if bucket == "long_term":
                bucket = "dividend"

            if bucket not in ["dividend", "growth", "penny"]:
                return {"status": "error", "message": f"Invalid bucket: {bucket}"}

            self.buckets["withdrawal"]["available"] -= amount
            self.buckets[bucket]["total_deposited"] = self.buckets[bucket].get("total_deposited", 0) + amount
            self._save_trade_log()

            bucket_icon = BUCKET_ICONS.get(bucket, "⚪")
            self.send_alert(
                f"💸 Moved ${amount:,.2f} from 🟡 Withdrawal to {bucket_icon} {bucket.title()} Pot."
            )

            if AUDIT_AVAILABLE and self.username:
                try:
                    log_audit(self.username, "move_from_withdrawal",
                             f"Moved ${amount:.2f} to {bucket}")
                except Exception:
                    pass

            return {
                "status": "success",
                "message": f"Moved ${amount:,.2f} from Withdrawal Pot to {bucket.title()} Pot.",
                "amount": amount,
                "bucket": bucket,
                "withdrawal_remaining": self.buckets["withdrawal"]["available"],
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def redistribute_from_withdrawal(self) -> Dict:
        """Redistribute the entire withdrawal pot across trading buckets based on allocation percentages."""
        try:
            available = self.buckets["withdrawal"].get("available", 0)
            if available <= 0:
                return {"status": "error", "message": "No money in Withdrawal Pot to redistribute."}

            div_pct = self.settings.get("dividend_pct", 0.35)
            gro_pct = self.settings.get("growth_pct", 0.35)
            pen_pct = self.settings.get("penny_pct", 0.30)

            total_pct = div_pct + gro_pct + pen_pct
            if total_pct <= 0:
                return {"status": "error", "message": "Allocation percentages must add up to more than 0."}

            # Normalize
            div_pct /= total_pct
            gro_pct /= total_pct
            pen_pct /= total_pct

            div_amount = available * div_pct
            gro_amount = available * gro_pct
            pen_amount = available * pen_pct

            self.buckets["withdrawal"]["available"] = 0
            self.buckets["dividend"]["total_deposited"] = self.buckets["dividend"].get("total_deposited", 0) + div_amount
            self.buckets["growth"]["total_deposited"] = self.buckets["growth"].get("total_deposited", 0) + gro_amount
            self.buckets["penny"]["total_deposited"] = self.buckets["penny"].get("total_deposited", 0) + pen_amount
            self._save_trade_log()

            self.send_alert(
                f"🔄 **Redistributed** ${available:,.2f} from Withdrawal Pot → "
                f"🟢 Dividend ${div_amount:,.2f} | 🔵 Growth ${gro_amount:,.2f} | 🔴 Penny ${pen_amount:,.2f}"
            )

            if AUDIT_AVAILABLE and self.username:
                try:
                    log_audit(self.username, "redistribute_from_withdrawal",
                             f"Redistributed ${available:.2f}")
                except Exception:
                    pass

            return {
                "status": "success",
                "message": f"Redistributed ${available:,.2f}: 🟢 Dividend ${div_amount:,.2f}, 🔵 Growth ${gro_amount:,.2f}, 🔴 Penny ${pen_amount:,.2f}",
                "dividend_amount": div_amount,
                "growth_amount": gro_amount,
                "penny_amount": pen_amount,
                "total_redistributed": available,
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}
    # ==========================================
    # Profit Extraction
    # ==========================================

    def extract_profits(self) -> Dict:
        """Extract profits above threshold and move to withdrawal pot."""
        try:
            account = self.get_account_info()
            if "error" in account:
                return {"status": "error", "message": f"Cannot get account info: {account['error']}"}

            equity = account.get("equity", 0)
            original_capital = self.buckets.get("original_capital", equity)

            if original_capital <= 0:
                return {"status": "error", "message": "Original capital not set."}

            total_profit = equity - original_capital
            profit_pct = total_profit / original_capital if original_capital > 0 else 0

            use_pct = self.settings.get("use_pct_threshold", False)
            threshold_pct = self.settings.get("profit_threshold_pct", 0.20)
            threshold_amount = self.settings.get("profit_threshold_amount", 20000)

            # Check threshold
            if use_pct:
                if profit_pct < threshold_pct:
                    return {
                        "status": "below_threshold",
                        "message": f"Profit {profit_pct:+.1%} is below {threshold_pct:.0%} threshold. Current profit: ${total_profit:+,.2f}",
                    }
            else:
                if total_profit < threshold_amount:
                    return {
                        "status": "below_threshold",
                        "message": f"Profit ${total_profit:,.2f} is below ${threshold_amount:,.0f} threshold.",
                    }

            # Find most profitable positions
            positions = self.get_positions()
            if not positions:
                return {"status": "below_threshold", "message": "No positions to extract profit from."}

            profitable = sorted(
                [p for p in positions if p.get("unrealized_plpc", 0) > 0],
                key=lambda x: x.get("unrealized_plpc", 0),
                reverse=True,
            )

            if not profitable:
                return {"status": "below_threshold", "message": "No profitable positions to extract."}

            # Sell the most profitable position
            best = profitable[0]
            symbol = best["symbol"]
            pl = best.get("unrealized_pl", 0)
            pl_pct = best.get("unrealized_plpc", 0)

            close_result = self.close_position(symbol, reason=f"Profit extraction: {pl_pct:+.2%}")

            if close_result.get("status") == "success":
                skim_pct = self.settings.get("profit_skim_pct", 1.0)
                profit_to_withdraw = pl * skim_pct if pl > 0 else 0

                self.buckets["withdrawal"]["available"] = self.buckets["withdrawal"].get("available", 0) + profit_to_withdraw
                self.buckets["withdrawal"]["profits_extracted"] = self.buckets["withdrawal"].get("profits_extracted", 0) + profit_to_withdraw
                self._update_buckets()
                self._save_trade_log()

                bucket = best.get("bucket", self.classify_stock(symbol))
                bucket_icon = BUCKET_ICONS.get(bucket, "⚪")
                self.send_alert(
                    f"⚡ **Profit Extraction** — Sold {bucket_icon} **{symbol}** ({bucket.title()}) "
                    f"P&L: ${pl:+,.2f} ({pl_pct:+.2%}). Skimmed ${profit_to_withdraw:,.2f} to 🟡 Withdrawal Pot."
                )

                if AUDIT_AVAILABLE and self.username:
                    try:
                        log_audit(self.username, "profit_extraction",
                                 f"Extracted ${profit_to_withdraw:.2f} from {symbol}")
                    except Exception:
                        pass

                return {
                    "status": "extracted",
                    "message": f"Extracted ${profit_to_withdraw:,.2f} profit from {symbol} ({bucket.title()}) to Withdrawal Pot.",
                    "symbol": symbol,
                    "bucket": bucket,
                    "pl": pl,
                    "pl_pct": pl_pct,
                    "amount_withdrawn": profit_to_withdraw,
                }
            else:
                return {"status": "error", "message": f"Failed to close {symbol}: {close_result.get('message', 'Unknown')}"}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ==========================================
    # Dividend Methods
    # ==========================================

    def check_dividends(self) -> Dict:
        """Check for dividend payments received on current positions."""
        try:
            if not self.connected or not self.api:
                return {"status": "error", "message": "Not connected to Alpaca"}

            positions = self.get_positions()
            dividends_found = 0.0
            details = []

            for p in positions:
                symbol = p["symbol"]
                qty = p["qty"]
                try:
                    if YF_AVAILABLE:
                        ticker = yf.Ticker(symbol)
                        info = ticker.info or {}
                        div_yield = info.get("dividendYield", 0) or 0
                        if div_yield > 1:
                            div_yield = div_yield / 100
                        if div_yield > 0:
                            hist = ticker.history(period="1y")
                            if not hist.empty and 'Dividends' in hist.columns:
                                recent_divs = hist['Dividends'][hist['Dividends'] > 0]
                                if not recent_divs.empty:
                                    last_div_date = recent_divs.index[-1]
                                    last_div_amount = float(recent_divs.iloc[-1])
                                    days_since = (datetime.utcnow() - last_div_date.to_pydatetime().replace(tzinfo=None)).days

                                    if days_since <= 7:
                                        bucket = self.classify_stock(symbol)
                                        total_div = last_div_amount * qty
                                        dividends_found += total_div
                                        details.append({
                                            "symbol": symbol,
                                            "amount": round(total_div, 2),
                                            "per_share": round(last_div_amount, 4),
                                            "date": str(last_div_date.date()),
                                            "bucket": bucket,
                                            "yield": round(div_yield * 100, 2),
                                            "shares": qty,
                                        })
                except Exception:
                    continue

            # Update withdrawal bucket with dividends
            if dividends_found > 0:
                self.buckets["withdrawal"]["available"] = self.buckets["withdrawal"].get("available", 0) + dividends_found
                self.buckets["withdrawal"]["dividends_received"] = self.buckets["withdrawal"].get("dividends_received", 0) + dividends_found
                self._save_trade_log()

                # Log dividend trade entries
                for d in details:
                    self.trade_log.append({
                        "timestamp": datetime.utcnow().isoformat(),
                        "symbol": d["symbol"],
                        "side": "dividend",
                        "qty": d.get("shares", 0),
                        "price": d.get("per_share", 0),
                        "bucket": d.get("bucket", "dividend"),
                        "confidence": 1.0,
                        "reason": f"Dividend payment: ${d['amount']:.2f}",
                        "pl": d.get("amount", 0),
                        "pl_pct": 0,
                    })

                if DB_AVAILABLE and self.username:
                    try:
                        db = SessionLocal()
                        for d in details:
                            try:
                                record_dividend(db, self.username, d["symbol"], d["amount"], d["date"])
                            except Exception:
                                pass
                        db.close()
                    except Exception:
                        pass

            return {
                "status": "success",
                "dividends_found": round(dividends_found, 2),
                "details": details,
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def check_sell_after_dividend(self) -> List[Dict]:
        """Check if any dividend positions have passed their ex-dividend date
        and should be sold (if sell_after_ex_dividend is enabled)."""
        try:
            if not self.connected or not self.api:
                return []

            sell_enabled = self.settings.get("dividend_settings", {}).get("sell_after_ex_dividend", False)
            if not sell_enabled:
                return []

            positions = self.get_positions()
            results = []
            today = datetime.utcnow()

            for p in positions:
                symbol = p["symbol"]
                bucket = p.get("bucket", self.classify_stock(symbol))

                # Only sell dividend positions
                if bucket not in ("dividend", "long_term"):
                    continue

                qty = p.get("qty", 0)
                current_price = p.get("current_price", 0)
                avg_entry_price = p.get("avg_entry_price", 0)
                pl = p.get("unrealized_pl", 0)
                pl_pct = p.get("unrealized_plpc", 0)
                market_value = p.get("market_value", 0)

                try:
                    if YF_AVAILABLE:
                        ticker = yf.Ticker(symbol)
                        info = ticker.info or {}

                        div_yield = info.get('dividendYield', 0) or 0
                        div_rate = info.get('dividendRate', 0) or 0
                        ex_date_raw = info.get('exDividendDate', None)

                        if not div_yield or div_yield <= 0:
                            continue

                        if not ex_date_raw:
                            continue

                        # Parse ex-dividend date
                        ex_date = None
                        try:
                            if isinstance(ex_date_raw, (int, float)):
                                ex_date = datetime.fromtimestamp(ex_date_raw)
                            else:
                                ex_date = pd.to_datetime(ex_date_raw).to_pydatetime()
                        except Exception:
                            continue

                        # If ex-date is in the past, estimate next one
                        if ex_date < today:
                            ex_date = ex_date + timedelta(days=91)
                            while ex_date < today:
                                ex_date += timedelta(days=91)

                        # Calculate days since the last ex-dividend date
                        # We want to sell 1 day AFTER the ex-dividend date to ensure we qualify
                        last_ex_date = ex_date - timedelta(days=91)
                        if last_ex_date < today:
                            # We're between ex-dates, check if we recently passed one
                            # If ex_date is more than 91 days away, we may have just passed the last one
                            days_since_ex = (today - last_ex_date).days
                        else:
                            days_since_ex = 999

                        # If we're within 2 days after the ex-dividend date, sell
                        # (gives 1 day buffer to ensure we qualify for the dividend)
                        if 0 <= days_since_ex <= 2:
                            per_share_div = div_rate / 4 if div_rate > 0 else (div_yield * current_price) / 4
                            total_div_income = per_share_div * qty

                            close_result = self.close_position(symbol,
                                reason=f"Dividend capture: ex-dividend date passed, captured ${total_div_income:.2f} dividend income")

                            bucket_icon = BUCKET_ICONS.get(bucket, "⚪")
                            if close_result.get("status") == "success":
                                self.send_alert(
                                    f"🎯 **DIVIDEND CAPTURED** | Sold **{symbol}** ({bucket_icon} {bucket.title()}) "
                                    f"after ex-dividend date | Captured ~${total_div_income:.2f} dividend income | "
                                    f"P&L: ${pl:+,.2f} ({pl_pct:+.2%})"
                                )

                            results.append({
                                "symbol": symbol,
                                "action": "sold_after_dividend",
                                "ex_date": ex_date.strftime("%Y-%m-%d") if ex_date else "Unknown",
                                "days_since_ex": days_since_ex,
                                "dividend_income": round(total_div_income, 2),
                                "pl": pl,
                                "pl_pct": pl_pct,
                                "close_result": close_result,
                            })

                except Exception:
                    continue

            return results

        except Exception as e:
            return []

    def get_upcoming_dividends(self, days_ahead: int = 60) -> List[Dict]:
        """Get upcoming ex-dividend dates for watchlist stocks."""
        results = []
        try:
            if DIVIDEND_CALENDAR_AVAILABLE:
                try:
                    upcoming = get_upcoming_ex_dividends(days_ahead=days_ahead)
                    if upcoming:
                        return upcoming
                except Exception:
                    pass

            # Fallback: use yfinance
            watchlist = self.settings.get("watchlist", [])
            for symbol in watchlist:
                try:
                    if YF_AVAILABLE:
                        ticker = yf.Ticker(symbol)
                        info = ticker.info or {}
                        div_yield = info.get("dividendYield", 0) or 0
                        if div_yield > 1:
                            div_yield = div_yield / 100
                        if div_yield > 0:
                            ex_date_raw = info.get("exDividendDate", None)
                            if ex_date_raw:
                                try:
                                    if isinstance(ex_date_raw, (int, float)):
                                        ex_date = datetime.fromtimestamp(ex_date_raw).strftime("%Y-%m-%d")
                                    else:
                                        ex_date = str(ex_date_raw)[:10]
                                except Exception:
                                    ex_date = str(ex_date_raw)[:10]
                            else:
                                ex_date = "N/A"
                            results.append({
                                "symbol": symbol,
                                "ex_date": ex_date,
                                "dividend_yield": round(div_yield * 100, 2),
                                "bucket": self.classify_stock(symbol),
                            })
                except Exception:
                    continue

            results.sort(key=lambda x: x.get("dividend_yield", 0), reverse=True)
            return results

        except Exception:
            return results

    def get_dividend_history(self) -> List[Dict]:
        """Get dividend payment history."""
        try:
            if DIVIDEND_CALENDAR_AVAILABLE:
                try:
                    external = get_div_history_external(self.username)
                    if external:
                        return external
                except Exception:
                    pass

            # Fallback: from trade log
            div_trades = []
            for t in self.trade_log:
                if t.get("side") == "dividend" or "dividend" in t.get("reason", "").lower():
                    div_trades.append(t)
            return div_trades

        except Exception:
            return []

    def get_dividend_stock_comparison(self) -> List[Dict]:
        """Compare dividend stocks in the watchlist."""
        results = []
        try:
            watchlist = self.settings.get("watchlist", [])
            for symbol in watchlist:
                try:
                    if YF_AVAILABLE:
                        ticker = yf.Ticker(symbol)
                        info = ticker.info or {}
                        div_yield = info.get("dividendYield", 0) or 0
                        if div_yield > 1:
                            div_yield = div_yield / 100
                        if div_yield > 0:
                            payout_ratio = info.get("payoutRatio", 0) or 0
                            price = info.get("currentPrice", info.get("regularMarketPrice", 0))
                            market_cap = info.get("marketCap", 0) or 0
                            five_year_avg_yield = info.get("fiveYearAvgDividendYield", 0) or 0

                            # Get dividend growth
                            div_growth_rate = 0
                            try:
                                hist = ticker.history(period="5y")
                                if not hist.empty and 'Dividends' in hist.columns:
                                    annual_divs = hist['Dividends'][hist['Dividends'] > 0].resample('Y').sum()
                                    if len(annual_divs) >= 2:
                                        first_div = annual_divs.iloc[0]
                                        last_div = annual_divs.iloc[-1]
                                        years = len(annual_divs) - 1
                                        if first_div > 0 and years > 0:
                                            div_growth_rate = ((last_div / first_div) ** (1 / years) - 1) * 100
                            except Exception:
                                pass

                            results.append({
                                "symbol": symbol,
                                "dividend_yield_pct": round(div_yield * 100, 2),
                                "payout_ratio_pct": round(payout_ratio * 100, 1),
                                "price": price,
                                "market_cap": market_cap,
                                "five_year_avg_yield": five_year_avg_yield,
                                "div_growth_rate": round(div_growth_rate, 2),
                                "bucket": self.classify_stock(symbol),
                            })
                except Exception:
                    continue

            results.sort(key=lambda x: x.get("dividend_yield_pct", 0), reverse=True)
            return results

        except Exception:
            return results
        
    def get_position_dividend_income(self) -> List[Dict]:
        """Get upcoming dividend income for stocks currently held in the portfolio.
        Shows estimated income, ex-dates, and whether to sell after ex-date."""
        try:
            positions = self.get_positions()
            if not positions:
                return []

            results = []
            today = datetime.utcnow()

            for p in positions:
                symbol = p["symbol"]
                qty = p.get("qty", 0)
                market_value = p.get("market_value", 0)
                avg_entry_price = p.get("avg_entry_price", 0)
                current_price = p.get("current_price", 0)
                bucket = p.get("bucket", self.classify_stock(symbol))

                try:
                    if YF_AVAILABLE:
                        ticker = yf.Ticker(symbol)
                        info = ticker.info or {}

                        div_yield = info.get('dividendYield', 0) or 0
                        div_rate = info.get('dividendRate', 0) or 0
                        ex_date_raw = info.get('exDividendDate', None)
                        payout_ratio = info.get('payoutRatio', 0) or 0

                        if not div_yield or div_yield <= 0:
                            continue

                        # Fix: yfinance sometimes returns yield as percentage instead of decimal
                        if div_yield > 1:
                            div_yield = div_yield / 100

                        # Calculate estimated annual income
                        annual_income = div_yield * market_value if market_value > 0 else 0
                        quarterly_income = annual_income / 4
                        per_share_quarterly = div_rate / 4 if div_rate > 0 else (div_yield * current_price) / 4

                        # Parse ex-dividend date
                        ex_date = None
                        days_until = None
                        if ex_date_raw:
                            try:
                                if isinstance(ex_date_raw, (int, float)):
                                    ex_date = datetime.fromtimestamp(ex_date_raw)
                                else:
                                    ex_date = pd.to_datetime(ex_date_raw).to_pydatetime()

                                # If ex-date is in the past, estimate next one (~3 months)
                                if ex_date < today:
                                    ex_date = ex_date + timedelta(days=91)
                                    while ex_date < today:
                                        ex_date += timedelta(days=91)

                                days_until = (ex_date - today).days
                            except Exception:
                                ex_date = None

                        # Determine if we should hold or sell
                        sell_after_div = self.settings.get("dividend_settings", {}).get("sell_after_ex_dividend", False)
                        hold_reason = "Hold for dividend income"
                        if sell_after_div and ex_date and days_until is not None:
                            if days_until <= 0:
                                hold_reason = "Ex-dividend date passed — eligible for dividend"
                            else:
                                hold_reason = f"Hold until ex-dividend date ({days_until} days away)"

                        results.append({
                            "symbol": symbol,
                            "bucket": bucket,
                            "qty": qty,
                            "current_price": current_price,
                            "market_value": market_value,
                            "avg_entry_price": avg_entry_price,
                            "dividend_yield_pct": round(div_yield * 100, 2),
                            "dividend_rate": round(div_rate, 4) if div_rate else 0,
                            "per_share_quarterly": round(per_share_quarterly, 4) if per_share_quarterly else 0,
                            "estimated_annual_income": round(annual_income, 2),
                            "estimated_quarterly_income": round(quarterly_income, 2),
                            "payout_ratio_pct": round(payout_ratio * 100, 1) if payout_ratio else 0,
                            "ex_date": ex_date.strftime("%Y-%m-%d") if ex_date else "Unknown",
                            "days_until_ex": days_until if days_until is not None else None,
                            "hold_recommendation": hold_reason,
                        })

                except Exception:
                    continue

            # Sort by days until ex-dividend (soonest first)
            results.sort(key=lambda x: x.get("days_until_ex") if x.get("days_until_ex") is not None else 999)
            return results

        except Exception as e:
            return []

    def calculate_drip_for_position(self, symbol: str, shares: int) -> Dict:
        """Calculate DRIP projection for a position."""
        try:
            if not YF_AVAILABLE:
                return {"error": "yfinance not available"}

            ticker = yf.Ticker(symbol)
            info = ticker.info or {}

            price = info.get("currentPrice", info.get("regularMarketPrice", 0))
            div_yield = info.get("dividendYield", 0) or 0
            if div_yield > 1:
                div_yield = div_yield / 100

            if not price or price <= 0:
                hist = ticker.history(period="5d")
                if not hist.empty:
                    price = float(hist['Close'].iloc[-1])

            if not price or price <= 0:
                return {"error": f"Cannot get price for {symbol}"}

            initial_value = price * shares
            annual_projections = []
            years = 10
            total_dividends = 0.0
            current_shares = float(shares)
            current_value = initial_value
            div_rate = div_yield if div_yield > 0 else 0.02

            for year in range(1, years + 1):
                annual_div = current_value * div_rate
                total_dividends += annual_div
                shares_from_drip = annual_div / price if price > 0 else 0
                current_shares += shares_from_drip
                current_value = current_shares * price * (1 + 0.03)  # Assume 3% price appreciation

                annual_projections.append({
                    "year": year,
                    "total_shares": round(current_shares, 2),
                    "total_value": round(current_value, 2),
                    "annual_dividend": round(annual_div, 2),
                    "total_dividends_received": round(total_dividends, 2),
                    "yield_on_cost": round(div_rate * 100, 2),
                })

            return {
                "symbol": symbol,
                "dividend_yield": round(div_yield * 100, 2) if div_yield else round(div_rate * 100, 2),
                "initial_value": round(initial_value, 2),
                "final_value": round(current_value, 2),
                "total_dividends": round(total_dividends, 2),
                "total_return_pct": round((current_value - initial_value) / initial_value * 100, 2) if initial_value > 0 else 0,
                "annual_projections": annual_projections,
            }

        except Exception as e:
            return {"error": str(e)}

    # ==========================================
    # Performance Calculation
    # ==========================================

    def calculate_performance(self) -> Dict:
        """Calculate comprehensive performance metrics including diamond-standard metrics."""
        try:
            if not self.trade_log and not self.equity_snapshots:
                return {
                    "total_return_pct": 0, "win_rate": 0, "sharpe_ratio": 0,
                    "sortino_ratio": 0, "calmar_ratio": 0, "omega_ratio": 0,
                    "max_drawdown_pct": 0, "best_day_pct": 0, "worst_day_pct": 0,
                    "total_trades": 0, "by_bucket": {},
                }

            # Calculate basic metrics from trade log
            sell_trades = [t for t in self.trade_log if t.get("side") == "sell"]
            total_trades = len(sell_trades)
            winning_trades = len([t for t in sell_trades if t.get("pl", 0) > 0])
            losing_trades = len([t for t in sell_trades if t.get("pl", 0) < 0])
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

            # Account-based return
            account = self.get_account_info()
            if "error" not in account:
                current_equity = account.get("equity", 0)
            else:
                current_equity = self.buckets.get("original_capital", 100000)

            original_capital = self.buckets.get("original_capital", current_equity)
            total_return_pct = ((current_equity - original_capital) / original_capital * 100) if original_capital > 0 else 0

            # Daily returns for risk metrics
            daily_returns = []
            if self.equity_snapshots and len(self.equity_snapshots) > 1:
                for i in range(1, len(self.equity_snapshots)):
                    prev_val = self.equity_snapshots[i-1].get("portfolio_value", 0)
                    curr_val = self.equity_snapshots[i].get("portfolio_value", 0)
                    if prev_val > 0 and curr_val > 0:
                        daily_returns.append((curr_val - prev_val) / prev_val)

            # Calculate risk metrics
            sharpe_ratio = 0.0
            sortino_ratio = 0.0
            max_drawdown_pct = 0.0
            best_day_pct = 0.0
            worst_day_pct = 0.0
            calmar_ratio = 0.0
            omega_ratio = 0.0

            if daily_returns:
                returns_arr = np.array(daily_returns)
                avg_return = np.mean(returns_arr)
                std_return = np.std(returns_arr)

                if std_return > 0:
                    sharpe_ratio = float((avg_return / std_return) * sqrt(252))

                # Sortino
                downside_returns = returns_arr[returns_arr < 0]
                downside_std = np.std(downside_returns) if len(downside_returns) > 0 else std_return
                if downside_std > 0:
                    sortino_ratio = float((avg_return / downside_std) * sqrt(252))

                # Max drawdown
                cumulative = np.cumprod(1 + returns_arr)
                peak = np.maximum.accumulate(cumulative)
                drawdown = (cumulative - peak) / peak
                max_drawdown_pct = float(abs(np.min(drawdown)) * 100) if len(drawdown) > 0 else 0

                # Best/worst day
                best_day_pct = float(np.max(returns_arr) * 100) if len(returns_arr) > 0 else 0
                worst_day_pct = float(np.min(returns_arr) * 100) if len(returns_arr) > 0 else 0

                # Calmar
                annual_return = avg_return * 252
                calmar_ratio = float(annual_return / (max_drawdown_pct / 100)) if max_drawdown_pct > 0 else 0

                # Omega
                threshold = 0
                gains = returns_arr[returns_arr > threshold]
                losses = np.abs(returns_arr[returns_arr < threshold])
                if len(losses) > 0 and np.sum(losses) > 0:
                    omega_ratio = float(np.sum(gains) / np.sum(losses))
                elif len(gains) > 0:
                    omega_ratio = float('inf')

            # Per-bucket metrics
            by_bucket = {}
            for bucket_name in ["dividend", "growth", "penny"]:
                bucket_trades = [t for t in sell_trades if t.get("bucket", "growth") == bucket_name]
                bucket_wins = len([t for t in bucket_trades if t.get("pl", 0) > 0])
                bucket_total = len(bucket_trades)
                bucket_pl = sum(t.get("pl", 0) for t in bucket_trades)
                bucket_return_pct = sum(t.get("pl_pct", 0) for t in bucket_trades)

                by_bucket[bucket_name] = {
                    "trades": bucket_total,
                    "wins": bucket_wins,
                    "losses": bucket_total - bucket_wins,
                    "win_rate": (bucket_wins / bucket_total * 100) if bucket_total > 0 else 0,
                    "return_pct": round(bucket_return_pct, 2),
                    "total_pl": round(bucket_pl, 2),
                }

            # Use advanced metrics if available
            if ADVANCED_METRICS_AVAILABLE and len(daily_returns) > 5:
                try:
                    advanced = generate_full_report(daily_returns, self.trade_log)
                    if isinstance(advanced, dict):
                        sortino_ratio = advanced.get("sortino_ratio", sortino_ratio)
                        calmar_ratio = advanced.get("calmar_ratio", calmar_ratio)
                        omega_ratio = advanced.get("omega_ratio", omega_ratio)
                except Exception:
                    pass

            return {
                "total_return_pct": round(total_return_pct, 2),
                "win_rate": round(win_rate, 1),
                "sharpe_ratio": round(sharpe_ratio, 3),
                "sortino_ratio": round(sortino_ratio, 3),
                "calmar_ratio": round(calmar_ratio, 3),
                "omega_ratio": round(omega_ratio, 3),
                "max_drawdown_pct": round(max_drawdown_pct, 2),
                "best_day_pct": round(best_day_pct, 2),
                "worst_day_pct": round(worst_day_pct, 2),
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "by_bucket": by_bucket,
                "current_equity": current_equity,
                "original_capital": original_capital,
                "total_profit": current_equity - original_capital,
            }

        except Exception as e:
            return {
                "total_return_pct": 0, "win_rate": 0, "sharpe_ratio": 0,
                "sortino_ratio": 0, "calmar_ratio": 0, "omega_ratio": 0,
                "max_drawdown_pct": 0, "best_day_pct": 0, "worst_day_pct": 0,
                "total_trades": 0, "by_bucket": {}, "error": str(e),
            }

    # ==========================================
    # Equity Snapshots
    # ==========================================

    def record_equity_snapshot(self):
        """Record current equity and bucket values as a snapshot."""
        try:
            account = self.get_account_info()
            if "error" in account:
                return

            equity = account.get("equity", 0)
            cash = account.get("cash", 0)

            # Get SPY return for comparison
            spy_return_pct = 0.0
            spy_price = 0.0
            try:
                if YF_AVAILABLE:
                    spy_data = yf.Ticker("SPY").history(period="1d")
                    if not spy_data.empty:
                        spy_open = float(spy_data['Open'].iloc[-1])
                        spy_close = float(spy_data['Close'].iloc[-1])
                        spy_return_pct = ((spy_close - spy_open) / spy_open * 100) if spy_open > 0 else 0
                        spy_price = spy_close
            except Exception:
                pass

            original_capital = self.buckets.get("original_capital", equity)
            portfolio_return_pct = ((equity - original_capital) / original_capital * 100) if original_capital > 0 else 0

            positions = self.get_positions()
            div_value = sum(p.get("market_value", 0) for p in positions if p.get("bucket") in ["dividend", "long_term"])
            gro_value = sum(p.get("market_value", 0) for p in positions if p.get("bucket") == "growth")
            pen_value = sum(p.get("market_value", 0) for p in positions if p.get("bucket") == "penny")

            # Calculate total dividends and profits for the day
            today = datetime.utcnow().strftime("%Y-%m-%d")
            today_trades = [t for t in self.trade_log if t.get("timestamp", "")[:10] == today]
            today_profit = sum(t.get("pl", 0) for t in today_trades if t.get("side") == "sell")
            today_dividends = sum(t.get("pl", 0) for t in today_trades if t.get("side") == "dividend")

            snapshot = {
                "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "portfolio_value": equity,
                "portfolio_return_pct": round(portfolio_return_pct, 2),
                "spy_return_pct": round(spy_return_pct, 2),
                "spy_price": spy_price,
                "dividend_value": div_value,
                "growth_value": gro_value,
                "penny_value": pen_value,
                "withdrawal_available": self.buckets["withdrawal"].get("available", 0),
                "withdrawal_value": self.buckets["withdrawal"].get("available", 0),
                "total_profit": equity - original_capital,
                "cash": cash,
                "positions_count": len(positions),
                "today_profit": round(today_profit, 2),
                "today_dividends": round(today_dividends, 2),
            }

            # Avoid duplicate snapshots on same date (but allow multiple per day for manual snapshots)
            existing_dates = [s.get("date", "")[:10] for s in self.equity_snapshots[-5:]]
            # Only skip if we already have a snapshot from the same hour
            current_hour = datetime.utcnow().strftime("%Y-%m-%d %H")
            recent_hours = [s.get("date", "")[:13] for s in self.equity_snapshots[-5:]]
            if current_hour not in recent_hours:
                self.equity_snapshots.append(snapshot)

            # Keep snapshots manageable (max 365 days)
            if len(self.equity_snapshots) > 3650:
                self.equity_snapshots = self.equity_snapshots[-3650:]

            self._save_trade_log()

        except Exception as e:
            print(f"Error recording snapshot: {e}")

    # ==========================================
    # Export & CSV
    # ==========================================

    def export_to_csv(self):
        """Export trade log, equity snapshots, and bucket data to CSV files."""
        try:
            export_dir = Path.home() / ".cascadetrade" / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)
            today_str = datetime.now().strftime("%Y-%m-%d")

            # Export trade log
            if self.trade_log:
                trade_file = export_dir / f"trades_{today_str}.csv"
                with open(trade_file, "w", newline="", encoding="utf-8") as f:
                    if self.trade_log:
                        all_keys = set()
                        for t in self.trade_log:
                            all_keys.update(t.keys())
                        fieldnames = sorted(all_keys)
                        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                        writer.writeheader()
                        writer.writerows(self.trade_log)

            # Export equity snapshots
            if self.equity_snapshots:
                snap_file = export_dir / f"equity_{today_str}.csv"
                with open(snap_file, "w", newline="", encoding="utf-8") as f:
                    if self.equity_snapshots:
                        all_keys = set()
                        for s in self.equity_snapshots:
                            all_keys.update(s.keys())
                        fieldnames = sorted(all_keys)
                        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                        writer.writeheader()
                        writer.writerows(self.equity_snapshots)

            # Export bucket summary
            bucket_file = export_dir / f"buckets_{today_str}.csv"
            with open(bucket_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Bucket", "Key", "Value"])
                for bucket_name in ["dividend", "growth", "penny", "withdrawal"]:
                    for key, value in self.buckets.get(bucket_name, {}).items():
                        writer.writerow([bucket_name, key, value])

            return True

        except Exception as e:
            print(f"Error exporting to CSV: {e}")
            return False

    # ==========================================
    # Status & Alerts
    # ==========================================

    def get_status(self) -> Dict:
        """Return the current status of the engine. All properties at correct indent level."""
        try:
            account = self.get_account_info()
            if "error" not in account:
                portfolio_value = account.get("portfolio_value", 0)
                equity = account.get("equity", 0)
                cash = account.get("cash", 0)
                buying_power = account.get("buying_power", 0)
            else:
                portfolio_value = 0
                equity = 0
                cash = 0
                buying_power = 0

            positions = self.get_positions() if self.connected else []
            signals_buy = sum(1 for s in self.signals_found if s.get("signal") == "BUY")
            signals_sell = sum(1 for s in self.signals_found if s.get("signal") == "SELL")

            return {
                "connected": self.connected,
                "running": self.running,
                "status_message": self.status_message,
                "cycle_count": self.cycle_count,
                "daily_pnl": self.daily_pnl,
                "portfolio_value": portfolio_value,
                "equity": equity,
                "cash": cash,
                "buying_power": buying_power,
                "num_positions": len(positions),
                "num_signals": len(self.signals_found),
                "num_buy_signals": signals_buy,
                "num_sell_signals": signals_sell,
                "num_trades": len(self.trade_log),
                "username": self.username,
                "last_scan": self.signals_found[0].get("symbol", "N/A") if self.signals_found else "N/A",
                "watchlist_size": len(self.settings.get("watchlist", [])),
                "vix_filter": self.settings.get("use_vix_filter", True),
                "advanced_signals": self.settings.get("use_advanced_signals", True),
                "atr_sizing": self.settings.get("use_atr_position_sizing", True),
                "profit_skim_pct": self.settings.get("profit_skim_pct", 1.0),
                "auto_extract": self.settings.get("auto_extract_profits", True),
            }
        except Exception as e:
            return {
                "connected": self.connected,
                "running": self.running,
                "status_message": f"Status error: {e}",
                "cycle_count": self.cycle_count,
                "daily_pnl": self.daily_pnl,
                "portfolio_value": 0,
                "equity": 0,
                "cash": 0,
                "buying_power": 0,
                "num_positions": 0,
                "num_signals": 0,
                "num_buy_signals": 0,
                "num_sell_signals": 0,
                "num_trades": len(self.trade_log),
                "username": self.username,
                "last_scan": "N/A",
                "watchlist_size": len(self.settings.get("watchlist", [])),
                "vix_filter": self.settings.get("use_vix_filter", True),
                "advanced_signals": self.settings.get("use_advanced_signals", True),
                "atr_sizing": self.settings.get("use_atr_position_sizing", True),
                "profit_skim_pct": self.settings.get("profit_skim_pct", 1.0),
                "auto_extract": self.settings.get("auto_extract_profits", True),
            }

    def get_worker_status(self) -> Dict:
        """Return detailed worker status for UI display."""
        try:
            status = self.get_status()
            status["last_cycle_time"] = self.last_successful_cycle or "Never"
            status["consecutive_failures"] = self.consecutive_failures
            status["scan_mode"] = "Universe" if self.settings.get("scan_full_universe", True) else "Watchlist"
            status["universe_count"] = self.settings.get("universe_scan_count", 300)
            status["watchlist_count"] = len(self.settings.get("watchlist", []))
            status["universe_cache_size"] = len(self._universe_cache) if hasattr(self, '_universe_cache') else 0
            status["universe_cache_age_min"] = round((time.time() - getattr(self, '_universe_cache_time', 0)) / 60, 1) if getattr(self, '_universe_cache_time', 0) > 0 else 0
            if self._daily_start_equity > 0:
                status["daily_pnl_pct"] = round((self.daily_pnl / self._daily_start_equity) * 100, 2)
            else:
                status["daily_pnl_pct"] = 0
            return status
        except Exception as e:
            return {"connected": self.connected, "running": self.running, "error": str(e)}

    def send_alert(self, message: str):
        """Send a Discord alert with privacy mode support."""
        try:
            if ALERTS_AVAILABLE:
                webhook_url = ""
                if DB_AVAILABLE and self.username:
                    try:
                        db = SessionLocal()
                        user = db.query(User).filter(User.username == self.username).first()
                        if user:
                            webhook_url = getattr(user, 'discord_webhook_url', '') or ''
                        db.close()
                    except Exception:
                        pass

                if webhook_url:
                    if self.settings.get("discord_privacy_mode", True):
                        # Strip dollar amounts for privacy
                        message = re.sub(r'\$[\d,]+\.?\d*', '$XX.XX', message)
                    send_discord_alert(webhook_url, message)
        except Exception:
            pass

    # ==========================================
    # Auto Watchlist Builder
    # ==========================================

    def auto_build_watchlist(self, top_n: int = 100, min_price: float = 5.0,
                             max_price: float = 500.0) -> List[str]:
        """Build an automatic watchlist. Tries Alpaca snapshots first, then bars, then yfinance."""
        try:
            if not self.connected or not self.api:
                self.status_message = "Not connected — cannot build watchlist"
                self._log_error("auto_watchlist", "Not connected to Alpaca")
                return self.settings.get("watchlist", [])

            print(f"[WATCHLIST] Starting build: target={top_n}, min=${min_price}, max=${max_price}")
            self.status_message = f"Building watchlist: scanning up to {top_n * 5} Alpaca stocks..."

            symbol_data = {}

            # === STEP 1: Get tradable symbols from Alpaca ===
            tradable = []
            try:
                assets = self.api.list_assets(status="active")
                exchanges = ["NASDAQ", "NYSE", "ARCA", "AMEX", "BATS"]
                for asset in assets:
                    sym = getattr(asset, 'symbol', '')
                    if not sym or len(sym) > 5:
                        continue
                    if getattr(asset, 'exchange', '') not in exchanges:
                        continue
                    if not getattr(asset, 'tradable', False):
                        continue
                    tradable.append(sym)
                print(f"[WATCHLIST] Found {len(tradable)} tradable US symbols from Alpaca")
                self.status_message = f"Found {len(tradable)} tradable stocks, getting prices..."
            except Exception as e:
                print(f"[WATCHLIST] list_assets failed: {e}")
                self._log_error("list_assets", str(e))
                # Try reconnecting once
                try:
                    if self._alpaca_api_ref:
                        self.api = self._alpaca_api_ref
                        assets = self.api.list_assets(status="active")
                        exchanges = ["NASDAQ", "NYSE", "ARCA", "AMEX", "BATS"]
                        for asset in assets:
                            sym = getattr(asset, 'symbol', '')
                            if not sym or len(sym) > 5:
                                continue
                            if getattr(asset, 'exchange', '') not in exchanges:
                                continue
                            if not getattr(asset, 'tradable', False):
                                continue
                            tradable.append(sym)
                        print(f"[WATCHLIST] Reconnected! Found {len(tradable)} tradable symbols")
                        self.status_message = f"Reconnected. Found {len(tradable)} stocks, getting prices..."
                except Exception as e2:
                    print(f"[WATCHLIST] Reconnection also failed: {e2}")

            if not tradable:
                print("[WATCHLIST] No tradable symbols from Alpaca, using default list")
                self._log_error("watchlist_no_assets", "No tradable symbols from Alpaca")

            # === STEP 2: Try Alpaca snapshots (fastest) ===
            if tradable:
                print(f"[WATCHLIST] Trying snapshots for top {min(len(tradable), top_n * 5)} symbols...")
                batch_size = 200
                symbols_to_try = tradable[:top_n * 5]
                
                for i in range(0, len(symbols_to_try), batch_size):
                    batch = symbols_to_try[i:i + batch_size]
                    try:
                        snapshots = None
                        try:
                            snapshots = self.api.get_snapshots(batch)
                        except (AttributeError, TypeError):
                            try:
                                snapshots = self.api.get_snapshot(batch)
                            except (AttributeError, TypeError):
                                pass
                        except Exception as e:
                            print(f"[WATCHLIST] Snapshot batch error: {e}")
                        
                        if snapshots and isinstance(snapshots, dict):
                            for sym, snap in snapshots.items():
                                try:
                                    daily_bar = getattr(snap, 'daily_bar', None) or getattr(snap, 'dailyBar', None)
                                    prev_bar = getattr(snap, 'prev_daily_bar', None) or getattr(snap, 'prevDailyBar', None)
                                    latest_trade = getattr(snap, 'latest_trade', None) or getattr(snap, 'latestTrade', None)
                                    latest_quote = getattr(snap, 'latest_quote', None) or getattr(snap, 'latestQuote', None)
                                    
                                    price = 0.0
                                    volume = 0.0
                                    
                                    if latest_trade:
                                        price = float(getattr(latest_trade, 'price', 0) or 0)
                                    if price <= 0 and latest_quote:
                                        bid = float(getattr(latest_quote, 'bid_price', 0) or getattr(latest_quote, 'bid', 0) or 0)
                                        ask = float(getattr(latest_quote, 'ask_price', 0) or getattr(latest_quote, 'ask', 0) or 0)
                                        if bid > 0 and ask > 0:
                                            price = (bid + ask) / 2
                                        elif ask > 0:
                                            price = ask
                                        elif bid > 0:
                                            price = bid
                                    if price <= 0 and daily_bar:
                                        price = float(getattr(daily_bar, 'close', 0) or 0)
                                    if price <= 0 and prev_bar:
                                        price = float(getattr(prev_bar, 'close', 0) or 0)
                                    
                                    if daily_bar:
                                        volume = float(getattr(daily_bar, 'volume', 0) or 0)
                                    if volume <= 0 and prev_bar:
                                        volume = float(getattr(prev_bar, 'volume', 0) or 0)
                                    
                                    if min_price <= price <= max_price and volume > 0:
                                        symbol_data[sym] = {"price": price, "volume": volume}
                                except Exception:
                                    continue
                            print(f"[WATCHLIST] Snapshot batch {i // batch_size + 1}: got {len(symbol_data)} stocks so far")
                    except Exception as e:
                        print(f"[WATCHLIST] Snapshot batch {i // batch_size + 1} failed: {e}")
                
                print(f"[WATCHLIST] After snapshots: {len(symbol_data)} stocks with data")

            # === STEP 3: Try Alpaca bars (slower but more reliable) ===
            if len(symbol_data) < 50 and tradable:
                print(f"[WATCHLIST] Only {len(symbol_data)} from snapshots, trying bars for top symbols...")
                try:
                    from alpaca_trade_api.rest import TimeFrame
                    end_dt = datetime.utcnow()
                    start_dt = end_dt - timedelta(days=5)
                    
                    # Focus on popular stocks first
                    popular = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM",
                               "JNJ", "V", "PG", "KO", "PEP", "WMT", "HD", "UNH", "ABBV", "LLY",
                               "BAC", "CSCO", "INTC", "VZ", "T", "XOM", "CVX", "PFE", "MRK",
                               "DIS", "NFLX", "AMD", "BA", "CAT", "GE", "F", "GM", "NKE", "COST",
                               "NEE", "DUK", "SO", "D", "O", "OHI", "STAG", "VICI", "AMT", "PLD",
                               "BRK.B", "SPGI", "MMC", "AON", "ICE", "CME"]
                    bars_symbols = [s for s in popular if s not in symbol_data]
                    bars_symbols += [s for s in tradable[:200] if s not in symbol_data and s not in bars_symbols]
                    bars_symbols = bars_symbols[:200]
                    
                    chunk_size = 50
                    for i in range(0, len(bars_symbols), chunk_size):
                        chunk = bars_symbols[i:i + chunk_size]
                        try:
                            bars_df = self.api.get_bars(
                                symbol_or_symbols=chunk,
                                timeframe=TimeFrame.Day,
                                start=start_dt.strftime("%Y-%m-%d"),
                                end=end_dt.strftime("%Y-%m-%d"),
                                adjustment='raw'
                            )
                            if bars_df is not None and not bars_df.empty:
                                if isinstance(bars_df.index, pd.MultiIndex):
                                    for sym in chunk:
                                        try:
                                            if sym in bars_df.index.get_level_values(0):
                                                sym_df = bars_df.loc[sym]
                                                if not sym_df.empty and len(sym_df) >= 2:
                                                    price = float(sym_df['close'].iloc[-1])
                                                    volume = float(sym_df['volume'].mean())
                                                    if min_price <= price <= max_price and volume > 0:
                                                        if sym not in symbol_data:
                                                            symbol_data[sym] = {"price": price, "volume": volume}
                                        except Exception:
                                            continue
                                elif len(chunk) == 1 and not bars_df.empty:
                                    price = float(bars_df['close'].iloc[-1])
                                    volume = float(bars_df['volume'].mean())
                                    if min_price <= price <= max_price and volume > 0:
                                        symbol_data[chunk[0]] = {"price": price, "volume": volume}
                            time.sleep(0.2)
                        except Exception as e:
                            print(f"[WATCHLIST] Bars chunk error: {e}")
                            continue
                    
                    print(f"[WATCHLIST] After bars: {len(symbol_data)} stocks total")
                    self.status_message = f"Got {len(symbol_data)} stocks from Alpaca bars..."
                except Exception as e:
                    print(f"[WATCHLIST] Bars attempt failed: {e}")

            # === STEP 4: yfinance fallback ===
            if len(symbol_data) < 50 and YF_AVAILABLE:
                print(f"[WATCHLIST] Only {len(symbol_data)} from Alpaca, trying yfinance for top stocks...")
                self.status_message = f"Alpaca returned {len(symbol_data)} stocks, supplementing with yfinance..."
                
                yf_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM",
                              "JNJ", "V", "PG", "KO", "PEP", "WMT", "HD", "UNH", "ABBV", "LLY",
                              "BAC", "GS", "MS", "C", "WFC", "BLK", "SCHW", "XOM", "CVX", "COP",
                              "PFE", "MRK", "TMO", "ABT", "AVGO", "TXN", "QCOM", "INTC", "CSCO",
                              "ORCL", "IBM", "CRM", "ADBE", "NFLX", "AMD", "BA", "CAT", "DE",
                              "LMT", "NOC", "RTX", "HON", "UPS", "FDX", "GM", "F", "NKE", "COST",
                              "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "AWK", "WEC",
                              "O", "OHI", "STAG", "VICI", "AMT", "PLD", "DLR", "EQIX", "PSA",
                              "DIS", "CMCSA", "TMUS", "VZ", "T", "EA", "TTWO", "MO", "PM",
                              "IBM", "CSCO", "INTC", "VFC", "CL", "KMB", "CLX", "ED", "LIN",
                              "SHW", "APD", "ECL", "WMB", "ET", "OKE", "DD", "NUE", "STLD",
                              "SBUX", "LOW", "TGT", "DG", "DLTR", "ROST", "TJX", "MCD", "YUM",
                              "ISRG", "REGN", "VRTX", "GILD", "BIIB", "MRNA", "AMGN", "ILMN",
                              "NOW", "WDAY", "TEAM", "DOCU", "ZS", "CRWD", "DDOG", "NET", "MDB",
                              "PLTR", "COIN", "SQ", "ROKU", "ZM", "SNAP", "PINS", "UBER", "ABNB",
                              "SHOP", "SE", "MELI", "MSTR", "SNOW", "AFRM", "SOFI", "RIVN", "LCID",
                              "NIO", "MARA", "RIOT", "BABA", "JD", "PDD", "FSLR", "ENPH", "SEDG",
                              "RUN", "BE", "PLUG", "BLNK", "CHPT", "NKLA", "QS", "RMO", "SNDL",
                              "GPRO", "FUBO", "HEAR", "NOK", "BB", "VALE", "TELL", "MRO", "CVE",
                              "SIRI", "LYG", "BCS", "DB", "SAN", "RIG", "HLX", "WTI", "AQN", "TECK"]
                
                yf_count = 0
                for sym in yf_symbols:
                    if sym in symbol_data:
                        continue
                    try:
                        ticker = yf.Ticker(sym)
                        info = ticker.info or {}
                        price = info.get("currentPrice", info.get("regularMarketPrice", info.get("previousClose", 0)))
                        if not price or price == 0:
                            hist = ticker.history(period="5d")
                            if not hist.empty:
                                price = float(hist['Close'].iloc[-1])
                                volume = float(hist['Volume'].mean())
                            else:
                                volume = 0
                        else:
                            volume = info.get("averageVolume", 0) or 0
                        
                        if price and min_price <= price <= max_price and volume > 0:
                            symbol_data[sym] = {"price": price, "volume": volume}
                            yf_count += 1
                    except Exception:
                        continue
                
                print(f"[WATCHLIST] yfinance added {yf_count} stocks. Total: {len(symbol_data)}")

            # === STEP 5: If still no data, use DEFAULT_WATCHLIST ===
            if not symbol_data:
                print("[WATCHLIST] ⚠️ No data from ANY source. Using default watchlist.")
                self.status_message = f"⚠️ Could not get stock data from Alpaca or yfinance. Using default watchlist ({len(DEFAULT_SETTINGS['watchlist'])} stocks). Try reconnecting to Alpaca."
                self._log_error("watchlist_no_data", "No price data from Alpaca or yfinance")
                
                # Use default watchlist with prices from yfinance as fallback
                for sym in DEFAULT_SETTINGS["watchlist"]:
                    symbol_data[sym] = {"price": 100.0, "volume": 1000000}  # Placeholder data
                result = list(symbol_data.keys())[:top_n]
                self.settings["watchlist"] = result
                self.settings["watchlist_auto"] = True
                self.settings["watchlist_auto_count"] = top_n
                self.settings["watchlist_last_built"] = datetime.utcnow().isoformat()
                self.save_settings()
                return result

            # === STEP 6: Sort and build bucket-aware list ===
            sorted_symbols = sorted(
                symbol_data.keys(),
                key=lambda s: symbol_data[s].get("volume", 0),
                reverse=True
            )

            penny_threshold = self.settings.get("penny_settings", {}).get("penny_price_threshold", 5.0)
            div_pct = self.settings.get("dividend_pct", 0.35)
            gro_pct = self.settings.get("growth_pct", 0.35)
            pen_pct = self.settings.get("penny_pct", 0.30)

            # Categorize
            penny_stocks = [s for s in sorted_symbols if symbol_data[s].get("price", 999) < penny_threshold]
            dividend_stocks = [s for s in sorted_symbols if s in DIVIDEND_STOCKS]
            growth_stocks = [s for s in sorted_symbols if s not in DIVIDEND_STOCKS and symbol_data[s].get("price", 0) >= penny_threshold]

            # Allocate slots
            div_slots = max(20, int(top_n * div_pct))
            gro_slots = max(40, int(top_n * gro_pct))
            pen_slots = max(20, int(top_n * pen_pct))

            result = []
            seen = set()

            # Must-have stocks
            must_have = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM",
                         "JNJ", "V", "PG", "KO", "PEP", "WMT", "HD", "UNH", "ABBV", "LLY"]
            for sym in must_have:
                if sym not in seen and sym in symbol_data:
                    result.append(sym)
                    seen.add(sym)

            # Fill dividend stocks
            for sym in dividend_stocks:
                if sym not in seen and len([s for s in result if s in DIVIDEND_STOCKS]) < div_slots:
                    result.append(sym)
                    seen.add(sym)

            # Fill growth stocks
            for sym in growth_stocks:
                if sym not in seen and len([s for s in result if s not in DIVIDEND_STOCKS and symbol_data.get(s, {}).get("price", 0) >= penny_threshold]) < gro_slots:
                    result.append(sym)
                    seen.add(sym)

            # Fill penny stocks
            for sym in penny_stocks:
                if sym not in seen and len([s for s in result if symbol_data.get(s, {}).get("price", 999) < penny_threshold]) < pen_slots:
                    result.append(sym)
                    seen.add(sym)

            # Fill remaining by volume
            for sym in sorted_symbols:
                if sym not in seen:
                    result.append(sym)
                    seen.add(sym)
                if len(result) >= top_n:
                    break

            print(f"[WATCHLIST] ✅ Built watchlist: {len(result)} stocks from {len(symbol_data)} candidates")
            print(f"[WATCHLIST] Breakdown: {len([s for s in result if s in DIVIDEND_STOCKS])} dividend, "
                  f"{len([s for s in result if s not in DIVIDEND_STOCKS and symbol_data.get(s, {}).get('price', 0) >= penny_threshold])} growth, "
                  f"{len([s for s in result if symbol_data.get(s, {}).get('price', 999) < penny_threshold])} penny")
            print(f"[WATCHLIST] Data sources: Alpaca snapshots={len([s for s in result if s in [k for k in symbol_data]])} stocks with data")

            if result:
                self.settings["watchlist"] = result
                self.settings["watchlist_auto"] = True
                self.settings["watchlist_auto_count"] = top_n
                self.settings["watchlist_last_built"] = datetime.utcnow().isoformat()
                self.save_settings()
                self.status_message = f"✅ Built watchlist with {len(result)} stocks"
                self._log_error("watchlist_built", 
                    f"Built {len(result)} stocks from {len(symbol_data)} candidates. "
                    f"Alpaca: {len(tradable)} assets, Data: {len(symbol_data)} stocks with prices")

            return result

        except Exception as e:
            print(f"[WATCHLIST] FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            self.status_message = f"⚠️ Watchlist build error: {str(e)[:200]}"
            self._log_error("auto_watchlist", str(e))
            return self.settings.get("watchlist", [])

    def scan_market_universe(self, top_n: int = 500, min_price: float = 5.0, max_price: float = 500.0) -> list:
        """Scan the entire Alpaca universe and return the top stocks by volume.
        Uses snapshots for speed, falls back to bars if needed."""
        try:
            if not self.connected or not self.api:
                self.status_message = "Not connected — cannot scan universe"
                return self.settings.get("watchlist", [])

            print(f"[UNIVERSE] Starting universe scan for top {top_n} stocks...")

            # Step 1: Get all tradable assets
            try:
                assets = self.api.list_assets(status="active")
            except Exception as e:
                print(f"[UNIVERSE] Error listing assets: {e}")
                return self.settings.get("watchlist", [])

            exchanges = ["NASDAQ", "NYSE", "ARCA", "AMEX", "BATS"]
            tradable = []
            for asset in assets:
                sym = getattr(asset, 'symbol', '')
                if not sym or len(sym) > 5:
                    continue
                if getattr(asset, 'exchange', '') not in exchanges:
                    continue
                if not getattr(asset, 'tradable', False):
                    continue
                tradable.append(sym)

            print(f"[UNIVERSE] Found {len(tradable)} tradable symbols")

            # Step 2: Use snapshots (fast) — same approach as auto_build_watchlist
            symbol_data = {}
            batch_size = 200

            for i in range(0, min(len(tradable), top_n * 5), batch_size):
                batch = tradable[i:i + batch_size]
                try:
                    snapshots = None
                    try:
                        snapshots = self.api.get_snapshots(batch)
                    except (AttributeError, TypeError):
                        try:
                            snapshots = self.api.get_snapshot(batch)
                        except (AttributeError, TypeError):
                            pass

                    if snapshots and isinstance(snapshots, dict):
                        for sym, snap in snapshots.items():
                            try:
                                daily_bar = getattr(snap, 'daily_bar', None) or getattr(snap, 'dailyBar', None)
                                prev_bar = getattr(snap, 'prev_daily_bar', None) or getattr(snap, 'prevDailyBar', None)
                                latest_trade = getattr(snap, 'latest_trade', None) or getattr(snap, 'latestTrade', None)
                                latest_quote = getattr(snap, 'latest_quote', None) or getattr(snap, 'latestQuote', None)

                                price = 0.0
                                volume = 0.0

                                if latest_trade:
                                    price = float(getattr(latest_trade, 'price', 0) or 0)
                                if price <= 0 and latest_quote:
                                    bid = float(getattr(latest_quote, 'bid_price', 0) or getattr(latest_quote, 'bid', 0) or 0)
                                    ask = float(getattr(latest_quote, 'ask_price', 0) or getattr(latest_quote, 'ask', 0) or 0)
                                    if bid > 0 and ask > 0:
                                        price = (bid + ask) / 2
                                    elif ask > 0:
                                        price = ask
                                    elif bid > 0:
                                        price = bid
                                if price <= 0 and daily_bar:
                                    price = float(getattr(daily_bar, 'close', 0) or 0)
                                if price <= 0 and prev_bar:
                                    price = float(getattr(prev_bar, 'close', 0) or 0)

                                if daily_bar:
                                    volume = float(getattr(daily_bar, 'volume', 0) or 0)
                                if volume <= 0 and prev_bar:
                                    volume = float(getattr(prev_bar, 'volume', 0) or 0)

                                if min_price <= price <= max_price and volume > 0:
                                    symbol_data[sym] = {"price": price, "volume": volume}
                            except Exception:
                                continue

                    print(f"[UNIVERSE] Snapshot batch: {len(symbol_data)} stocks so far")
                    time.sleep(0.1)  # Rate limit

                except Exception as e:
                    print(f"[UNIVERSE] Snapshot batch error: {e}")
                    continue

            # Step 3: Fall back to bars if snapshots didn't give enough data
            if len(symbol_data) < 50:
                print(f"[UNIVERSE] Only {len(symbol_data)} from snapshots, trying bars...")
                try:
                    from alpaca_trade_api.rest import TimeFrame
                    end_dt = datetime.utcnow()
                    start_dt = end_dt - timedelta(days=5)

                    chunk_size = 50
                    symbols_to_process = [s for s in tradable[:top_n * 3] if s not in symbol_data]

                    for i in range(0, len(symbols_to_process), chunk_size):
                        chunk = symbols_to_process[i:i + chunk_size]
                        try:
                            bars_df = self.api.get_bars(
                                symbol_or_symbols=chunk,
                                timeframe=TimeFrame.Day,
                                start=start_dt.strftime("%Y-%m-%d"),
                                end=end_dt.strftime("%Y-%m-%d"),
                                adjustment='raw'
                            )

                            if bars_df is not None and not bars_df.empty:
                                if isinstance(bars_df.index, pd.MultiIndex):
                                    for sym in chunk:
                                        try:
                                            if sym in bars_df.index.get_level_values(0):
                                                sym_df = bars_df.loc[sym]
                                                if not sym_df.empty and len(sym_df) >= 2:
                                                    price = float(sym_df['close'].iloc[-1])
                                                    volume = float(sym_df['volume'].mean())
                                                    if min_price <= price <= max_price and volume > 0:
                                                        if sym not in symbol_data:
                                                            symbol_data[sym] = {"price": price, "volume": volume}
                                        except Exception:
                                            continue
                                elif len(chunk) == 1 and not bars_df.empty:
                                    price = float(bars_df['close'].iloc[-1])
                                    volume = float(bars_df['volume'].mean())
                                    if min_price <= price <= max_price and volume > 0:
                                        if chunk[0] not in symbol_data:
                                            symbol_data[chunk[0]] = {"price": price, "volume": volume}

                            time.sleep(0.15)  # Rate limit
                        except Exception:
                            continue

                except Exception as e:
                    print(f"[UNIVERSE] Bars fallback error: {e}")

            print(f"[UNIVERSE] Total stocks with data: {len(symbol_data)}")

            if not symbol_data:
                print("[UNIVERSE] ⚠️ FAILED to get any price data from Alpaca! Returning empty — will fall back to watchlist with clear warning.")
                self._log_error("universe_scan_failed", f"Got 0 stocks from {len(tradable)} tradable symbols. API may be rate-limited or down.")
                self.status_message = "⚠️ Universe scan failed — API rate limited or disconnected"
                # Return EMPTY list, NOT the watchlist.
                # scan_all() will handle the fallback with a clear warning message.
                return []


            # Step 4: Sort by volume and build bucket-aware list
            sorted_symbols = sorted(
                symbol_data.keys(),
                key=lambda s: symbol_data[s].get("volume", 0),
                reverse=True
            )

            penny_threshold = self.settings.get("penny_settings", {}).get("penny_price_threshold", 5.0)

            # Categorize
            penny_stocks = [s for s in sorted_symbols if symbol_data[s].get("price", 999) < penny_threshold]
            dividend_stocks = [s for s in sorted_symbols if s in DIVIDEND_STOCKS]
            growth_stocks = [s for s in sorted_symbols if s not in DIVIDEND_STOCKS and symbol_data[s].get("price", 0) >= penny_threshold]

            # Build result proportional to bucket allocation
            result = []
            seen = set()

            # Must-have stocks
            must_have = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM",
                         "JNJ", "V", "PG", "KO", "PEP", "WMT", "HD", "UNH", "ABBV", "LLY"]
            for sym in must_have:
                if sym not in seen and sym in symbol_data:
                    result.append(sym)
                    seen.add(sym)

            div_pct = self.settings.get("dividend_pct", 0.35)
            gro_pct = self.settings.get("growth_pct", 0.35)
            pen_pct = self.settings.get("penny_pct", 0.30)

            div_slots = max(20, int(top_n * div_pct))
            gro_slots = max(40, int(top_n * gro_pct))
            pen_slots = max(20, int(top_n * pen_pct))

            # Fill penny stocks
            for sym in penny_stocks:
                if sym not in seen and len([s for s in result if symbol_data.get(s, {}).get("price", 999) < penny_threshold]) < pen_slots:
                    result.append(sym)
                    seen.add(sym)

            # Fill dividend stocks
            for sym in dividend_stocks:
                if sym not in seen and len([s for s in result if s in DIVIDEND_STOCKS]) < div_slots:
                    result.append(sym)
                    seen.add(sym)

            # Fill growth stocks
            for sym in growth_stocks:
                if sym not in seen and len([s for s in result if s not in DIVIDEND_STOCKS and symbol_data.get(s, {}).get("price", 0) >= penny_threshold]) < gro_slots:
                    result.append(sym)
                    seen.add(sym)

            # Fill remaining with high-volume stocks
            for sym in sorted_symbols:
                if sym not in seen:
                    result.append(sym)
                    seen.add(sym)
                if len(result) >= top_n:
                    break

            print(f"[UNIVERSE] Returning {len(result)} stocks (target was {top_n})")
            return result

        except Exception as e:
            print(f"[UNIVERSE] Fatal error: {e}")
            import traceback
            traceback.print_exc()
            self._log_error("universe_scan", str(e))
            return self.settings.get("watchlist", [])

    # ==========================================
    # IPO & New Listings Scanner
    # ==========================================

    def scan_new_listings(self) -> Dict:
        """Scan for new tradable symbols on Alpaca."""
        try:
            if not self.connected or not self.api:
                return {"status": "error", "message": "Not connected to Alpaca", "new_symbols": []}

            if IPO_SCANNER_AVAILABLE:
                known = load_known_symbols()
                if not known:
                    save_symbol_snapshot(self.api)
                    known = load_known_symbols()

                assets = self.api.list_assets(status="active")
                current_symbols = set(a.symbol for a in assets if getattr(a, 'tradable', False))

                new_symbols = list(current_symbols - set(known))

                if new_symbols:
                    save_symbol_snapshot(self.api)
                    self.known_symbols = list(current_symbols)

                return {
                    "status": "success",
                    "new_symbols": new_symbols[:50],
                    "total_current": len(current_symbols),
                    "total_known": len(known),
                }
            else:
                # Fallback without IPO scanner module
                try:
                    assets = self.api.list_assets(status="active")
                    current_symbols = set(a.symbol for a in assets if getattr(a, 'tradable', False))
                    if not self.known_symbols:
                        self.known_symbols = list(current_symbols)
                        return {
                            "status": "success",
                            "new_symbols": [],
                            "total_current": len(current_symbols),
                            "message": "Baseline saved. Run again to detect new listings.",
                        }

                    old_symbols = set(self.known_symbols)
                    new_symbols = list(current_symbols - old_symbols)

                    if new_symbols:
                        self.known_symbols = list(current_symbols)

                    return {
                        "status": "success",
                        "new_symbols": new_symbols[:50],
                        "total_current": len(current_symbols),
                    }
                except Exception as e:
                    return {"status": "error", "message": str(e), "new_symbols": []}

        except Exception as e:
            return {"status": "error", "message": str(e), "new_symbols": []}

    # ==========================================
    # Backtesting
    # ==========================================

    def run_backtest(self, symbols: List[str], start_date: str, end_date: str,
                     strategy: str = "combined") -> Dict:
        """Run a backtest on the given symbols using the backtest engine."""
        try:
            if not BACKTEST_AVAILABLE:
                # Fallback: simple internal backtest
                return self._simple_backtest(symbols, start_date, end_date, strategy)

            engine = BacktestEngine()
            result = engine.run(
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                strategy=strategy,
                settings=self.settings,
            )
            return result

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _simple_backtest(self, symbols: List[str], start_date: str, end_date: str,
                         strategy: str = "combined") -> Dict:
        """Simple internal backtest fallback when BacktestEngine is not available."""
        try:
            if not YF_AVAILABLE:
                return {"status": "error", "message": "yfinance not available for backtesting"}

            all_trades = []
            equity_curve = []
            capital = 100000
            equity = capital

            for symbol in symbols:
                try:
                    ticker = yf.Ticker(symbol)
                    df = ticker.history(start=start_date, end=end_date)
                    if df.empty or len(df) < 50:
                        continue

                    df.columns = [c.lower() for c in df.columns]
                    if 'adj_close' in df.columns:
                        df = df.drop(columns=['adj_close'])

                    # Calculate indicators
                    rsi = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
                    df['rsi'] = rsi

                    bucket = self.classify_stock(symbol)
                    bucket_settings = self._get_bucket_settings(bucket)
                    rsi_oversold = bucket_settings.get("rsi_oversold", 30)
                    rsi_overbought = bucket_settings.get("rsi_overbought", 70)

                    position = 0
                    entry_price = 0
                    entry_date = ""

                    for i in range(50, len(df)):
                        row = df.iloc[i]
                        rsi_val = row.get('rsi', 50)

                        if np.isnan(rsi_val):
                            continue

                        # Buy signal
                        if position == 0 and rsi_val < rsi_oversold:
                            entry_price = row['close']
                            entry_date = row.name.strftime("%Y-%m-%d") if hasattr(row.name, 'strftime') else str(row.name)[:10]
                            shares = int(capital * 0.08 / entry_price) if entry_price > 0 else 0
                            position = shares
                        # Sell signal
                        elif position > 0 and rsi_val > rsi_overbought:
                            exit_price = row['close']
                            exit_date = row.name.strftime("%Y-%m-%d") if hasattr(row.name, 'strftime') else str(row.name)[:10]
                            pnl = (exit_price - entry_price) * position
                            pnl_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0
                            equity += pnl

                            all_trades.append({
                                "symbol": symbol,
                                "bucket": bucket,
                                "entry_date": entry_date,
                                "exit_date": exit_date,
                                "entry_price": round(entry_price, 2),
                                "exit_price": round(exit_price, 2),
                                "shares": position,
                                "pnl": round(pnl, 2),
                                "pnl_pct": round(pnl_pct * 100, 2),
                                "reason": f"RSI {rsi_val:.0f}",
                            })
                            position = 0
                            entry_price = 0

                        # Equity curve point
                        current_value = equity + (position * row['close'] if position > 0 else 0)
                        equity_curve.append({
                            "date": row.name.strftime("%Y-%m-%d") if hasattr(row.name, 'strftime') else str(row.name)[:10],
                            "equity": round(current_value, 2),
                            "cash": round(equity - (position * row['close'] if position > 0 else 0), 2),
                            "positions_value": round(position * row['close'] if position > 0 else 0, 2),
                        })

                except Exception:
                    continue

            if not all_trades:
                return {"status": "error", "message": "No trades generated during backtest period"}

            # Calculate metrics
            winning_trades = [t for t in all_trades if t.get("pnl", 0) > 0]
            losing_trades = [t for t in all_trades if t.get("pnl", 0) < 0]
            total_pnl = sum(t.get("pnl", 0) for t in all_trades)
            win_rate = len(winning_trades) / len(all_trades) * 100 if all_trades else 0

            # Bucket P&L
            bucket_pnl = {}
            for t in all_trades:
                b = t.get("bucket", "growth")
                bucket_pnl[b] = bucket_pnl.get(b, 0) + t.get("pnl", 0)

            total_return_pct = ((equity - capital) / capital * 100) if capital > 0 else 0

            # Max drawdown from equity curve
            max_drawdown_pct = 0
            if equity_curve:
                values = [e["equity"] for e in equity_curve]
                peak = values[0]
                for v in values:
                    if v > peak:
                        peak = v
                    dd = (peak - v) / peak * 100 if peak > 0 else 0
                    if dd > max_drawdown_pct:
                        max_drawdown_pct = dd

            return {
                "status": "complete",
                "symbols_tested": len(symbols),
                "trades": all_trades,
                "metrics": {
                    "total_return_pct": round(total_return_pct, 2),
                    "win_rate": round(win_rate, 1),
                    "max_drawdown_pct": round(max_drawdown_pct, 2),
                    "profit_factor": round(abs(sum(t["pnl"] for t in winning_trades)) / abs(sum(t["pnl"] for t in losing_trades)), 2) if losing_trades and sum(t["pnl"] for t in losing_trades) != 0 else 0,
                    "sharpe_ratio": 0,
                    "sortino_ratio": 0,
                    "calmar_ratio": 0,
                    "omega_ratio": 0,
                    "total_trades": len(all_trades),
                    "winning_trades": len(winning_trades),
                    "losing_trades": len(losing_trades),
                },
                "bucket_pnl": bucket_pnl,
                "equity_curve": equity_curve,
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ==========================================
    # Trade Notes / Journal
    # ==========================================

    def save_trade_note(self, username: str, symbol: str, action: str,
                        entry_reason: str = "", emotion: str = "",
                        lesson_learned: str = "") -> bool:
        """Save a trade journal entry."""
        try:
            if AUDIT_AVAILABLE:
                from core.audit import save_journal_entry
                save_journal_entry(username, symbol, action, entry_reason, emotion, lesson_learned)
                return True
            else:
                self.trade_log.append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "symbol": symbol,
                    "side": "journal",
                    "action": action,
                    "qty": 0,
                    "price": 0,
                    "bucket": self.classify_stock(symbol),
                    "confidence": 0,
                    "reason": entry_reason,
                    "emotion": emotion,
                    "lesson_learned": lesson_learned,
                    "username": username,
                })
                self._save_trade_log()
                return True
        except Exception as e:
            print(f"Error saving trade note: {e}")
            return False

    def _reconnect(self) -> bool:
        """Attempt to reconnect to Alpaca with exponential backoff."""
        if self.reconnect_count >= self.MAX_RECONNECT_ATTEMPTS:
            self.status_message = f"Max reconnect attempts ({self.MAX_RECONNECT_ATTEMPTS}) reached. Stopping bot."
            self.running = False
            self._log_error("reconnect_max", f"Max reconnect attempts reached after {self.consecutive_failures} consecutive failures")
            return False

        delay = min(self.RECONNECT_BASE_DELAY * (2 ** self.reconnect_count), self.MAX_RECONNECT_DELAY)
        self.reconnect_count += 1
        self.status_message = f"Reconnecting... attempt {self.reconnect_count}/{self.MAX_RECONNECT_ATTEMPTS} (wait {delay}s)"
        self._log_error("reconnect_attempt", f"Attempt {self.reconnect_count}, waiting {delay}s")

        import time as _time
        _time.sleep(delay)

        try:
            if self._alpaca_api_ref:
                account = self._alpaca_api_ref.get_account()
                if account:
                    self.connected = True
                    self.reconnect_count = 0  # Reset on successful reconnect
                    self.consecutive_failures = 0  # Reset failure counter
                    self.status_message = "Reconnected successfully."
                    self._log_error("reconnect_success", "Reconnected to Alpaca")
                    return True
        except Exception as e:
            self.consecutive_failures += 1
            self.last_reconnect_time = datetime.utcnow().isoformat()
            self._log_error("reconnect_fail", str(e))

        return False

    def _check_and_reset_daily(self):
        """Reset daily counters if a new US trading day has started."""
        try:
            from zoneinfo import ZoneInfo
            eastern = ZoneInfo("US/Eastern")
            today_et = datetime.now(eastern).strftime("%Y-%m-%d")
        except Exception:
            today_et = datetime.utcnow().strftime("%Y-%m-%d")
        
        if self.daily_reset_date != today_et:
            self.daily_pnl = 0.0
            self.daily_reset_date = today_et
            account = self.get_account_info()
            if "error" not in account:
                self._daily_start_equity = account.get("equity", 0)
                self._portfolio_start_value = account.get("equity", 0)

    def _log_error(self, error_type: str, error_msg: str, symbol: str = ""):
        """Log an error with context."""
        import traceback
        tb = traceback.format_exc()
        error_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": error_type,
            "message": str(error_msg),
            "symbol": symbol,
            "traceback": tb,
        }
        print(f"[{error_type}] {symbol}: {error_msg}")
        if AUDIT_AVAILABLE and self.username:
            try:
                log_audit(self.username, f"error_{error_type}", f"{symbol}: {error_msg}")
            except Exception:
                pass

    def get_open_orders(self) -> List[Dict]:
        """Get all open orders from Alpaca."""
        try:
            if not self.connected or not self.api:
                return []
            orders = self.api.list_orders(status="open")
            result = []
            for o in orders:
                result.append({
                    "id": getattr(o, 'id', ''),
                    "symbol": getattr(o, 'symbol', ''),
                    "qty": float(getattr(o, 'qty', 0)),
                    "side": getattr(o, 'side', ''),
                    "type": getattr(o, 'type', ''),
                    "limit_price": float(getattr(o, 'limit_price', 0) or 0),
                    "stop_price": float(getattr(o, 'stop_price', 0) or 0),
                    "time_in_force": getattr(o, 'time_in_force', ''),
                    "submitted_at": str(getattr(o, 'submitted_at', '')),
                    "status": getattr(o, 'status', ''),
                })
            return result
        except Exception:
            return []

    def scan_advanced(self) -> List[Dict]:
        """Scan using advanced signals if available, otherwise falls back to basic scan."""
        self.signals_found = []
        self.near_signals = []

        if not self.connected or not self.api:
            self.status_message = "Not connected — cannot scan"
            return self.signals_found

        if self.settings.get("use_vix_filter", True):
            vix_result = self.check_vix()
            if not vix_result.get("safe_to_trade", True):
                self.status_message = vix_result.get("reason", "VIX filter active")
                return self.signals_found

        watchlist = self.settings.get("watchlist", [])
        if not watchlist:
            self.status_message = "No watchlist configured"
            return self.signals_found

        if ADVANCED_SIGNALS_AVAILABLE and self.settings.get("use_advanced_signals", True):
            try:
                for symbol in watchlist:
                    try:
                        signal_result = generate_all_signals(symbol)
                        if signal_result and isinstance(signal_result, dict):
                            combined_score = calculate_combined_score(signal_result)
                            bucket = self.classify_stock(symbol)
                            bucket_settings = self._get_bucket_settings(bucket)
                            min_confidence = bucket_settings.get("min_confidence",
                                            self.settings.get("min_confidence", 0.25))

                            if combined_score >= min_confidence:
                                signal_direction = "BUY"
                                for indicator, data in signal_result.items():
                                    if isinstance(data, dict) and data.get("signal") == "SELL":
                                        signal_direction = "SELL"
                                        break

                                price = self._get_current_price(symbol)
                                self.signals_found.append({
                                    "symbol": symbol,
                                    "signal": signal_direction,
                                    "price": price,
                                    "confidence": combined_score,
                                    "bucket": bucket,
                                    "reason": f"Advanced signals combined score: {combined_score:.0%}",
                                    "indicators": signal_result,
                                })
                            elif combined_score >= min_confidence * 0.7:
                                price = self._get_current_price(symbol)
                                self.near_signals.append({
                                    "symbol": symbol,
                                    "signal": "NEAR",
                                    "price": price,
                                    "confidence": combined_score,
                                    "bucket": bucket,
                                    "reason": f"Near signal ({combined_score:.0%})",
                                })
                    except Exception:
                        continue

                self.status_message = f"Advanced scan: {len(self.signals_found)} signals, {len(self.near_signals)} near-signals"
                return self.signals_found
            except Exception:
                pass

        # Fallback to basic scan
        self.scan_all()
        return self.signals_found

    def record_signal(self, signal_data: Dict):
        """Record a signal in the signal history."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "symbol": signal_data.get("symbol", ""),
            "signal": signal_data.get("signal", ""),
            "confidence": signal_data.get("confidence", 0),
            "bucket": signal_data.get("bucket", ""),
            "price": signal_data.get("price", 0),
            "reason": signal_data.get("reason", ""),
        }
        self.signal_history.append(entry)
        # Keep last 500 signals
        if len(self.signal_history) > 500:
            self.signal_history = self.signal_history[-500:]

    def _get_tier(self) -> str:
        """Get the user's subscription tier."""
        try:
            if DB_AVAILABLE and self.username:
                db = SessionLocal()
                user = db.query(User).filter(User.username == self.username).first()
                db.close()
                if user and hasattr(user, 'tier'):
                    return user.tier or "starter"
            return "starter"
        except Exception:
            return "starter"

    def get_available_trading_cash(self, bucket: str = None) -> float:
        """Calculate available trading cash for a specific bucket or total."""
        try:
            account = self.get_account_info()
            if "error" in account:
                return 0.0

            total_equity = account.get("equity", 0)
            cash = account.get("cash", 0)

            if bucket:
                bucket_pct = self.settings.get(f"{bucket}_pct", 0)
                return cash * bucket_pct
            else:
                return cash
        except Exception:
            return 0.0

    def move_profits(self, from_bucket: str, to_bucket: str, amount: float) -> Dict:
        """Move profits from one bucket to another."""
        try:
            if from_bucket not in self.buckets or to_bucket not in self.buckets:
                return {"status": "error", "message": f"Invalid bucket: {from_bucket} or {to_bucket}"}

            if from_bucket == "withdrawal":
                return self.move_from_withdrawal(amount, to_bucket)

            available_profit = self.buckets[from_bucket].get("value", 0) - self.buckets[from_bucket].get("total_deposited", 0)
            if amount <= 0:
                return {"status": "error", "message": "Amount must be positive."}
            if amount > available_profit:
                return {"status": "error", "message": f"Amount ${amount:,.2f} exceeds available profit ${available_profit:,.2f} in {from_bucket.title()}."}

            self.buckets[from_bucket]["total_withdrawn"] = self.buckets[from_bucket].get("total_withdrawn", 0) + amount
            self.buckets[to_bucket]["profits_moved_in"] = self.buckets[to_bucket].get("profits_moved_in", 0) + amount
            self._save_trade_log()

            from_icon = BUCKET_ICONS.get(from_bucket, "⚪")
            to_icon = BUCKET_ICONS.get(to_bucket, "⚪")
            self.send_alert(
                f"📊 Moved ${amount:,.2f} from {from_icon} {from_bucket.title()} to {to_icon} {to_bucket.title()}."
            )

            return {
                "status": "success",
                "message": f"Moved ${amount:,.2f} from {from_bucket.title()} to {to_bucket.title()}.",
                "amount": amount,
                "from_bucket": from_bucket,
                "to_bucket": to_bucket,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _calculate_bucket_profits(self) -> Dict:
        """Calculate profits for each bucket based on positions."""
        try:
            positions = self.get_positions()
            result = {}
            for bucket_name in ["dividend", "growth", "penny"]:
                bucket_positions = [p for p in positions if p.get("bucket") == bucket_name or
                                   (bucket_name == "dividend" and p.get("bucket") == "long_term")]
                total_value = sum(p.get("market_value", 0) for p in bucket_positions)
                total_cost = sum(p.get("avg_entry_price", 0) * p.get("qty", 0) for p in bucket_positions)
                total_pl = sum(p.get("unrealized_pl", 0) for p in bucket_positions)
                result[bucket_name] = {
                    "positions": len(bucket_positions),
                    "total_value": total_value,
                    "total_cost": total_cost,
                    "total_pl": total_pl,
                    "total_pl_pct": (total_pl / total_cost * 100) if total_cost > 0 else 0,
                    "deposited": self.buckets[bucket_name].get("total_deposited", 0),
                    "profit_vs_deposited": ((total_value - self.buckets[bucket_name].get("total_deposited", 0))
                                           / self.buckets[bucket_name].get("total_deposited", 1) * 100)
                                           if self.buckets[bucket_name].get("total_deposited", 0) > 0 else 0,
                }
            return result
        except Exception as e:
            return {"error": str(e)}

    def _apply_profit_skimming(self, symbol: str, pl: float, pl_pct: float, bucket: str):
        """Apply profit skimming rules when a position is closed with profit."""
        try:
            skim_pct = self.settings.get("profit_skim_pct", 1.0)
            if pl > 0 and skim_pct > 0:
                profit_to_withdraw = pl * skim_pct
                self.buckets["withdrawal"]["available"] = self.buckets["withdrawal"].get("available", 0) + profit_to_withdraw
                self.buckets["withdrawal"]["profits_extracted"] = self.buckets["withdrawal"].get("profits_extracted", 0) + profit_to_withdraw

                # Remaining profit goes back to the bucket
                remaining_profit = pl * (1 - skim_pct)
                if bucket in self.buckets:
                    self.buckets[bucket]["profits_moved_in"] = self.buckets[bucket].get("profits_moved_in", 0) + remaining_profit

                # Record in extraction history
                self.buckets["withdrawal"]["extraction_history"].append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "symbol": symbol,
                    "total_profit": pl,
                    "skimmed": profit_to_withdraw,
                    "reinvested": remaining_profit,
                    "skim_pct": skim_pct,
                })
        except Exception as e:
            self._log_error("profit_skimming", str(e), symbol)

    def connect_encrypted(self, api_key: str, secret_key: str, live_mode: bool = False) -> bool:
        """Connect to Alpaca using encrypted API keys.
        
        Args:
            api_key: Encrypted or plain API key
            secret_key: Encrypted or plain secret key
            live_mode: If True, connect to live trading URL. If False, connect to paper trading URL.
        """
        try:
            if ENCRYPTION_AVAILABLE:
                try:
                    api_key = decrypt_value(api_key) if is_encrypted(api_key) else api_key
                    secret_key = decrypt_value(secret_key) if is_encrypted(secret_key) else secret_key
                except Exception:
                    pass

            # Switch URL based on trading mode
            if live_mode:
                base_url = 'https://api.alpaca.markets'
            else:
                base_url = 'https://paper-api.alpaca.markets'

            if not ALPACA_AVAILABLE or tradeapi is None:
                self.status_message = "alpaca_trade_api not installed"
                return False

            api = tradeapi.REST(api_key, secret_key, base_url=base_url, api_version='v2')
            success = self.connect(api)
            
            if success:
                # Store reference for reconnection
                self._alpaca_api_ref = api
                self._alpaca_api_key = api_key
                self._alpaca_secret_key = secret_key
                self._alpaca_live_mode = live_mode
                self.reconnect_count = 0
                self.consecutive_failures = 0
            
            return success
        except Exception as e:
            self.status_message = f"Encrypted connection error: {str(e)}"
            self._log_error("connect_encrypted", str(e))
            return False

    def deposit_money(self, amount: float, bucket: str) -> Dict:
        """Record a manual deposit into a specific bucket."""
        try:
            if bucket not in ["dividend", "growth", "penny", "withdrawal"]:
                return {"status": "error", "message": f"Invalid bucket: {bucket}"}
            if amount <= 0:
                return {"status": "error", "message": "Amount must be positive."}

            self.buckets[bucket]["total_deposited"] = self.buckets[bucket].get("total_deposited", 0) + amount
            self.buckets[bucket]["deposit_history"].append({
                "timestamp": datetime.utcnow().isoformat(),
                "amount": amount,
                "type": "deposit",
            })

            if self.buckets.get("original_capital", 0) == 0:
                account = self.get_account_info()
                if "error" not in account:
                    self.buckets["original_capital"] = account.get("equity", 0)

            self._save_trade_log()

            bucket_icon = BUCKET_ICONS.get(bucket, "⚪")
            self.send_alert(f"💰 Deposited ${amount:,.2f} into {bucket_icon} {bucket.title()} Pot.")

            return {
                "status": "success",
                "message": f"Deposited ${amount:,.2f} into {bucket.title()} Pot.",
                "amount": amount,
                "bucket": bucket,
                "bucket_total_deposited": self.buckets[bucket]["total_deposited"],
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def invalidate_bucket_cache(self):
        """Invalidate the position cache so next call fetches fresh data."""
        self._position_cache = {}
        self._position_cache_time = 0
        self._price_cache = {}
        self._price_cache_time = 0
        self._sector_cache = {}

def invalidate_all_caches(self):
    """Invalidate price/position caches. Does NOT clear universe cache."""
    self._position_cache = {}
    self._position_cache_time = 0
    self._price_cache = {}
    self._price_cache_time = 0
    self._sector_cache = {}
    self._data_cache = {}
    self._data_cache_time = {}

def invalidate_universe_cache(self):
    """Force-clear the universe cache (use when user explicitly requests a refresh)."""
    self._universe_cache = []
    self._universe_cache_time = 0


    def auto_add_new_to_watchlist(self, new_symbols: List[str]) -> Dict:
        """Automatically add newly discovered symbols to the watchlist."""
        try:
            if not new_symbols:
                return {"status": "success", "message": "No new symbols to add.", "added": 0}

            watchlist = self.settings.get("watchlist", [])
            added = 0
            for symbol in new_symbols:
                symbol = symbol.upper().strip()
                if symbol and symbol not in watchlist:
                    # Quick check it's a real stock
                    bucket = self.classify_stock(symbol)
                    watchlist.append(symbol)
                    added += 1

            if added > 0:
                self.settings["watchlist"] = watchlist
                self.save_settings()
                self.send_alert(f"📋 Auto-added {added} new symbols to watchlist: {', '.join(new_symbols[:10])}")

            return {
                "status": "success",
                "message": f"Added {added} new symbols to watchlist.",
                "added": added,
                "total_watchlist": len(watchlist),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
