"""
Structured Logging Service for AI City API.
ELK-compatible JSON logging: Login, Access, Error, Change Logs.

Architecture:
- Structured JSON logs written to stdout (Vercel captures them)
- Logs stored in Neon PostgreSQL for querying
- JSON format compatible with Logstash/Filebeat ingestion
- Kibana-compatible dashboards via API endpoints

Log Types:
- login: Authentication events (login, logout, register, failed attempts)
- access: API request/response logs
- error: Application errors and exceptions
- change: Data modification audit trail
"""

import os
import json
import logging
import uuid
import sys
from datetime import datetime, timezone
from typing import Optional, Any
from enum import Enum
from contextvars import ContextVar
import traceback

# ─── Log Types ────────────────────────────────────────────────────────────────

class LogType(str, Enum):
    LOGIN = "login"       # Authentication events
    ACCESS = "access"     # API access logs
    ERROR = "error"       # Application errors
    CHANGE = "change"     # Data modification audit trail


# ─── Context for request-scoped logging ──────────────────────────────────────

request_ctx: ContextVar[dict] = ContextVar("request_ctx", default={})


def set_request_context(
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    path: Optional[str] = None,
    method: Optional[str] = None,
):
    """Set request-scoped context for logging."""
    ctx = {
        "request_id": request_id or str(uuid.uuid4()),
        "user_id": user_id,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "path": path,
        "method": method,
    }
    request_ctx.set(ctx)
    return ctx


def get_request_context() -> dict:
    """Get current request context."""
    return request_ctx.get({})


# ─── ELK-Compatible Log Format ───────────────────────────────────────────────

def format_log_entry(
    level: str,
    message: str,
    log_type: LogType,
    extra: Optional[dict] = None,
    error: Optional[Exception] = None,
) -> dict:
    """
    Format a log entry in ELK-compatible JSON format.
    Compatible with Logstash json filter and Kibana.
    """
    ctx = get_request_context()

    entry = {
        # Standard ELK fields
        "@timestamp": datetime.now(timezone.utc).isoformat(),
        "log.level": level.upper(),
        "message": message,

        # ECS (Elastic Common Schema) fields
        "ecs.version": "8.0.0",
        "event.kind": "event",
        "event.category": log_type.value,
        "event.type": _get_event_type(log_type, level),

        # AI City specific
        "service.name": "aicity-backend",
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("ENVIRONMENT", "production"),

        # Request context
        "trace.id": ctx.get("request_id"),
        "client.ip": ctx.get("ip_address"),
        "user_agent.original": ctx.get("user_agent"),

        # Log metadata
        "log_type": log_type.value,
        "log.logger": "aicity",
    }

    # Add user info
    if ctx.get("user_id"):
        entry["user.id"] = str(ctx.get("user_id"))

    # Add HTTP context
    if ctx.get("path"):
        entry["url.path"] = ctx.get("path")
        entry["http.request.method"] = ctx.get("method")

    # Add extra fields
    if extra:
        entry.update(extra)

    # Add error details
    if error:
        entry["error.type"] = type(error).__name__
        entry["error.message"] = str(error)
        entry["error.stack_trace"] = traceback.format_exc()

    return entry


def _get_event_type(log_type: LogType, level: str) -> str:
    """Map log type + level to ECS event type."""
    if log_type == LogType.LOGIN:
        return "session"
    elif log_type == LogType.ACCESS:
        return "access"
    elif log_type == LogType.ERROR:
        return "error"
    elif log_type == LogType.CHANGE:
        return "change"
    return "info"


# ─── Structured Logger ────────────────────────────────────────────────────────

class StructuredLogger:
    """
    ELK-compatible structured logger for AI City.

    Outputs JSON to stdout (Vercel-compatible) and stores in PostgreSQL.
    """

    def __init__(self, name: str = "aicity"):
        self.name = name
        self.logger = logging.getLogger(name)
        self._setup_console_handler()

    def _setup_console_handler(self):
        """Add JSON handler for stdout (Vercel log capture)."""
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(JsonFormatter())
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def _emit(self, level: str, message: str, log_type: LogType, extra: Optional[dict] = None, error: Optional[Exception] = None):
        """Emit a structured log entry."""
        entry = format_log_entry(level, message, log_type, extra, error)

        # Log to stdout (Vercel captures this)
        if level == "error":
            self.logger.error(json.dumps(entry))
        elif level == "warning":
            self.logger.warning(json.dumps(entry))
        else:
            self.logger.info(json.dumps(entry))

        # Store in PostgreSQL asynchronously
        self._store_in_db(entry)

    def _store_in_db(self, entry: dict):
        """Store log entry in Neon PostgreSQL."""
        try:
            import psycopg2
            from psycopg2.extras import Json

            DB_CONFIG = {
                "host": os.getenv("DB_HOST", "localhost"),
                "port": int(os.getenv("DB_PORT", "5433")),
                "database": os.getenv("DB_NAME", "promptforge"),
                "user": os.getenv("DB_USER", "promptforge"),
                "password": os.getenv("DB_PASSWORD", "promptforge123"),
            }

            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_logs (log_type, level, message, metadata, ip_address, user_id, request_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                entry.get("log_type"),
                entry.get("log.level"),
                entry.get("message"),
                Json({k: v for k, v in entry.items() if k not in (
                    "log_type", "log.level", "message", "ip_address", "user_id", "request_id"
                )}),
                entry.get("client.ip"),
                entry.get("user.id"),
                entry.get("trace.id"),
            ))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception:
            pass  # Never block on DB logging failures

    # Convenience methods

    def login(self, action: str, email: Optional[str] = None, success: bool = True, extra: Optional[dict] = None):
        """Log authentication event."""
        self._emit(
            level="info" if success else "warning",
            message=f"Login {action}: {'success' if success else 'failed'}",
            log_type=LogType.LOGIN,
            extra={
                "auth.action": action,
                "auth.email": email,
                "auth.success": success,
                **(extra or {}),
            },
        )

    def access(self, path: str, method: str, status_code: int, duration_ms: Optional[float] = None, extra: Optional[dict] = None):
        """Log API access."""
        level = "error" if status_code >= 500 else "warning" if status_code >= 400 else "info"
        self._emit(
            level=level,
            message=f"{method} {path} -> {status_code}",
            log_type=LogType.ACCESS,
            extra={
                "http.request.method": method,
                "url.path": path,
                "http.response.status_code": status_code,
                "http.response.duration_ms": duration_ms,
                **(extra or {}),
            },
        )

    def error(self, message: str, error: Optional[Exception] = None, extra: Optional[dict] = None):
        """Log application error."""
        self._emit(
            level="error",
            message=message,
            log_type=LogType.ERROR,
            error=error,
            extra=extra,
        )

    def change(self, table: str, operation: str, record_id: Any, old_value: Optional[dict] = None, new_value: Optional[dict] = None, extra: Optional[dict] = None):
        """Log data modification (audit trail)."""
        self._emit(
            level="info",
            message=f"{operation.title()} on {table} (id={record_id})",
            log_type=LogType.CHANGE,
            extra={
                "change.table": table,
                "change.operation": operation,
                "change.record_id": str(record_id),
                "change.old_value": old_value,
                "change.new_value": new_value,
                **(extra or {}),
            },
        )

    def info(self, message: str, extra: Optional[dict] = None):
        """Log info message."""
        self._emit("info", message, LogType.ACCESS, extra)


# ─── JSON Formatter ────────────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """Format log records as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            return json.dumps(record.getMessage())
        except Exception:
            return record.getMessage()


# ─── Global logger instance ────────────────────────────────────────────────────

structured_logger = StructuredLogger("aicity")
