"""
core/audit.py
Audit trail for all user actions. Records who did what, when, and why.
Essential for compliance, debugging, and dispute resolution.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Use the same database as the main app
import os

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
os.makedirs(DB_DIR, exist_ok=True)
sqlite_path = os.path.join(DB_DIR, 'cascadetrade_users.db')
DATABASE_URL = f"sqlite:///{sqlite_path}"

audit_engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
AuditBase = declarative_base()


class AuditEntry(AuditBase):
    __tablename__ = "audit_trail"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    action = Column(String)  # login, trade, deposit, withdraw, settings_change, etc.
    category = Column(String)  # auth, trading, bucket, settings, data
    symbol = Column(String, nullable=True)
    details = Column(Text)  # JSON string with full details
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


class TradeJournal(AuditBase):
    __tablename__ = "trade_journal"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    trade_id = Column(String, nullable=True)  # Link to trade_log entry
    symbol = Column(String)
    action = Column(String)  # buy, sell, stop_loss, take_profit
    entry_reason = Column(Text)  # WHY did I enter this trade?
    exit_reason = Column(Text, nullable=True)  # WHY did I exit?
    emotion = Column(String, nullable=True)  # confident, anxious, fomo, disciplined
    lesson_learned = Column(Text, nullable=True)  # What did I learn?
    bucket = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    tags = Column(String, nullable=True)  # Comma-separated tags
    timestamp = Column(DateTime, default=datetime.utcnow)


# Create tables
AuditBase.metadata.create_all(bind=audit_engine)
AuditSession = sessionmaker(autocommit=False, autoflush=False, bind=audit_engine)


def log_audit(username: str, action: str, category: str, symbol: str = "",
               details: Dict = None, ip_address: str = "") -> AuditEntry:
    """Log an audit entry."""
    session = AuditSession()
    try:
        entry = AuditEntry(
            username=username,
            action=action,
            category=category,
            symbol=symbol,
            details=json.dumps(details or {}),
            ip_address=ip_address,
            timestamp=datetime.utcnow(),
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry
    except Exception as e:
        session.rollback()
        print(f"Audit log error: {e}")
        return None
    finally:
        session.close()


def get_audit_trail(username: str = None, category: str = None,
                     limit: int = 100) -> List[Dict]:
    """Get audit trail entries, optionally filtered."""
    session = AuditSession()
    try:
        query = session.query(AuditEntry)
        if username:
            query = query.filter(AuditEntry.username == username)
        if category:
            query = query.filter(AuditEntry.category == category)
        query = query.order_by(AuditEntry.timestamp.desc()).limit(limit)
        entries = query.all()
        return [{
            "id": e.id,
            "username": e.username,
            "action": e.action,
            "category": e.category,
            "symbol": e.symbol,
            "details": json.loads(e.details) if e.details else {},
            "ip_address": e.ip_address,
            "timestamp": e.timestamp.isoformat() if e.timestamp else "",
        } for e in entries]
    except Exception as e:
        print(f"Audit query error: {e}")
        return []
    finally:
        session.close()


def save_journal_entry(username: str, trade_id: str = "", symbol: str = "",
                        action: str = "", entry_reason: str = "",
                        exit_reason: str = "", emotion: str = "",
                        lesson_learned: str = "", bucket: str = "",
                        confidence: float = 0, tags: str = "") -> Optional[TradeJournal]:
    """Save a trade journal entry."""
    session = AuditSession()
    try:
        entry = TradeJournal(
            username=username,
            trade_id=trade_id,
            symbol=symbol,
            action=action,
            entry_reason=entry_reason,
            exit_reason=exit_reason,
            emotion=emotion,
            lesson_learned=lesson_learned,
            bucket=bucket,
            confidence=confidence,
            tags=tags,
            timestamp=datetime.utcnow(),
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry
    except Exception as e:
        session.rollback()
        print(f"Journal save error: {e}")
        return None
    finally:
        session.close()


def get_journal_entries(username: str, symbol: str = None,
                         limit: int = 50) -> List[Dict]:
    """Get journal entries for a user."""
    session = AuditSession()
    try:
        query = session.query(TradeJournal).filter(TradeJournal.username == username)
        if symbol:
            query = query.filter(TradeJournal.symbol == symbol)
        query = query.order_by(TradeJournal.timestamp.desc()).limit(limit)
        entries = query.all()
        return [{
            "id": e.id,
            "trade_id": e.trade_id,
            "symbol": e.symbol,
            "action": e.action,
            "entry_reason": e.entry_reason,
            "exit_reason": e.exit_reason,
            "emotion": e.emotion,
            "lesson_learned": e.lesson_learned,
            "bucket": e.bucket,
            "confidence": e.confidence,
            "tags": e.tags,
            "timestamp": e.timestamp.isoformat() if e.timestamp else "",
        } for e in entries]
    except Exception as e:
        print(f"Journal query error: {e}")
        return []
    finally:
        session.close()


# ==========================================
# CONVENIENCE FUNCTIONS FOR TRADING ENGINE
# ==========================================

def log_trade_audit(username: str, trade_details: Dict):
    """Log a trade execution to the audit trail."""
    log_audit(
        username=username,
        action="trade_executed",
        category="trading",
        symbol=trade_details.get("symbol", ""),
        details=trade_details,
    )


def log_deposit_audit(username: str, amount: float, bucket_split: Dict):
    """Log a deposit to the audit trail."""
    log_audit(
        username=username,
        action="deposit",
        category="bucket",
        details={"amount": amount, **bucket_split},
    )


def log_settings_audit(username: str, settings_changed: Dict):
    """Log a settings change to the audit trail."""
    log_audit(
        username=username,
        action="settings_changed",
        category="settings",
        details=settings_changed,
    )


def log_login_audit(username: str, ip_address: str = ""):
    """Log a login to the audit trail."""
    log_audit(
        username=username,
        action="login",
        category="auth",
        ip_address=ip_address,
    )
