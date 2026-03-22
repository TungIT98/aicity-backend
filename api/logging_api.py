"""
Structured Logging API - ELK-compatible log storage and querying.
Stores login, access, error, and change logs in Neon PostgreSQL.

Endpoints:
- GET  /api/logs                    - Query logs (with filters)
- GET  /api/logs/login              - Login audit trail
- GET  /api/logs/access             - Access logs
- GET  /api/logs/errors             - Error logs
- GET  /api/logs/changes            - Change audit trail
- POST /api/logs/setup              - Create log storage table
"""
import os
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from starlette.responses import StreamingResponse
import psycopg2
import psycopg2.extras
import json

router = APIRouter(prefix="/api/logs", tags=["Logging"])

# DB config
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5433")),
    "database": os.getenv("DB_NAME", "promptforge"),
    "user": os.getenv("DB_USER", "promptforge"),
    "password": os.getenv("DB_PASSWORD", "promptforge123"),
}

LOG_TABLE = "api_logs"


# ─── Pydantic Models ────────────────────────────────────────────────────────

class LogEntry(BaseModel):
    id: int
    log_type: str
    level: str
    message: str
    metadata: dict
    ip_address: Optional[str]
    user_id: Optional[str]
    request_id: Optional[str]
    created_at: str


class LogQueryResponse(BaseModel):
    logs: list[LogEntry]
    total: int
    page: int
    page_size: int


# ─── DB Helpers ─────────────────────────────────────────────────────────────

def get_logs_connection():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except psycopg2.OperationalError:
        return None


def setup_logs_table():
    """Create api_logs table if not exists."""
    conn = get_logs_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {LOG_TABLE} (
                id SERIAL PRIMARY KEY,
                log_type VARCHAR(50) NOT NULL,
                level VARCHAR(20) NOT NULL,
                message TEXT NOT NULL,
                metadata JSONB DEFAULT '{{}}',
                ip_address VARCHAR(45),
                user_id VARCHAR(255),
                request_id VARCHAR(36),
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS {LOG_TABLE}_type_idx ON {LOG_TABLE}(log_type)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS {LOG_TABLE}_created_idx ON {LOG_TABLE}(created_at DESC)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS {LOG_TABLE}_user_idx ON {LOG_TABLE}(user_id)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS {LOG_TABLE}_metadata_idx ON {LOG_TABLE} USING gin (metadata)
        """)
        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        conn.rollback()
        return False
    finally:
        conn.close()


def query_logs(
    log_type: Optional[str] = None,
    level: Optional[str] = None,
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    """Query logs with filters. Returns (logs, total_count)."""
    conn = get_logs_connection()
    if not conn:
        return [], 0

    try:
        cursor = conn.cursor()

        conditions = []
        params = []

        if log_type:
            conditions.append("log_type = %s")
            params.append(log_type)
        if level:
            conditions.append("level = %s")
            params.append(level)
        if user_id:
            conditions.append("user_id = %s")
            params.append(user_id)
        if ip_address:
            conditions.append("ip_address = %s")
            params.append(ip_address)
        if search:
            conditions.append("message ILIKE %s")
            params.append(f"%{search}%")
        if start_date:
            conditions.append("created_at >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("created_at <= %s")
            params.append(end_date)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Count
        count_sql = f"SELECT COUNT(*) FROM {LOG_TABLE} WHERE {where_clause}"
        cursor.execute(count_sql, params)
        total = cursor.fetchone()[0] or 0

        # Fetch page
        offset = (page - 1) * page_size
        select_sql = f"""
            SELECT id, log_type, level, message, metadata, ip_address, user_id, request_id, created_at
            FROM {LOG_TABLE}
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(select_sql, params + [page_size, offset])
        rows = cursor.fetchall()

        logs = [
            {
                "id": r[0],
                "log_type": r[1],
                "level": r[2],
                "message": r[3],
                "metadata": r[4] if r[4] else {},
                "ip_address": r[5],
                "user_id": r[6],
                "request_id": r[7],
                "created_at": str(r[8]) if r[8] else None,
            }
            for r in rows
        ]

        cursor.close()
        return logs, total
    except Exception as e:
        return [], 0
    finally:
        conn.close()


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=LogQueryResponse)
async def get_logs(
    log_type: Optional[str] = Query(None, description="Filter by type: login, access, error, change"),
    level: Optional[str] = Query(None, description="Filter by level: info, warning, error"),
    user_id: str = Query(None, description="Filter by user ID"),
    ip_address: str = Query(None, description="Filter by IP address"),
    search: str = Query(None, description="Search in message"),
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
):
    """Query logs with filters. Supports login, access, error, and change logs."""
    logs, total = query_logs(
        log_type=log_type,
        level=level,
        user_id=user_id,
        ip_address=ip_address,
        search=search,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return {"logs": logs, "total": total, "page": page, "page_size": page_size}


@router.get("/login", response_model=LogQueryResponse)
async def get_login_logs(
    user_id: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    """Login audit trail - all authentication events."""
    logs, total = query_logs(
        log_type="login",
        user_id=user_id,
        page=page,
        page_size=page_size,
    )
    return {"logs": logs, "total": total, "page": page, "page_size": page_size}


@router.get("/access", response_model=LogQueryResponse)
async def get_access_logs(
    path: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    status_code: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    """API access logs - all HTTP requests."""
    logs, total = query_logs(
        log_type="access",
        page=page,
        page_size=page_size,
    )
    # Filter by path/method/status from metadata
    if path or method or status_code:
        filtered = []
        for log in logs:
            meta = log.get("metadata", {})
            if path and path not in meta.get("url.path", ""):
                continue
            if method and method != meta.get("http.request.method"):
                continue
            if status_code and status_code != meta.get("http.response.status_code"):
                continue
            filtered.append(log)
        return {"logs": filtered, "total": len(filtered), "page": page, "page_size": page_size}
    return {"logs": logs, "total": total, "page": page, "page_size": page_size}


@router.get("/errors", response_model=LogQueryResponse)
async def get_error_logs(
    error_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    """Application error logs."""
    logs, total = query_logs(
        log_type="error",
        page=page,
        page_size=page_size,
    )
    if error_type:
        filtered = [l for l in logs if l.get("metadata", {}).get("error.type") == error_type]
        return {"logs": filtered, "total": len(filtered), "page": page, "page_size": page_size}
    return {"logs": logs, "total": total, "page": page, "page_size": page_size}


@router.get("/changes", response_model=LogQueryResponse)
async def get_change_logs(
    table: Optional[str] = Query(None, description="Filter by table name"),
    operation: Optional[str] = Query(None, description="Filter by operation: insert, update, delete"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    """Change audit trail - data modifications."""
    logs, total = query_logs(
        log_type="change",
        page=page,
        page_size=page_size,
    )
    if table or operation:
        filtered = []
        for log in logs:
            meta = log.get("metadata", {})
            if table and table != meta.get("change.table"):
                continue
            if operation and operation != meta.get("change.operation"):
                continue
            filtered.append(log)
        return {"logs": filtered, "total": len(filtered), "page": page, "page_size": page_size}
    return {"logs": logs, "total": total, "page": page, "page_size": page_size}


@router.post("/setup")
async def setup_logs():
    """Create the api_logs table and indexes."""
    success = setup_logs_table()
    if success:
        return {
            "status": "ok",
            "table": LOG_TABLE,
            "indexes": ["log_type", "created_at", "user_id", "metadata"],
            "note": "Log storage is ready. Structured logging will now persist to PostgreSQL."
        }
    return {"status": "error", "message": "Could not connect to database"}


@router.get("/summary")
async def get_logs_summary():
    """Get log summary statistics."""
    conn = get_logs_connection()
    if not conn:
        raise HTTPException(503, "Database unavailable")

    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT
                log_type,
                level,
                COUNT(*) as count,
                MIN(created_at) as first_log,
                MAX(created_at) as last_log
            FROM {LOG_TABLE}
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY log_type, level
            ORDER BY count DESC
        """)
        rows = cursor.fetchall()

        # Unique users/IPs
        cursor.execute(f"""
            SELECT
                COUNT(DISTINCT user_id) as unique_users,
                COUNT(DISTINCT ip_address) as unique_ips,
                COUNT(*) as total_logs
            FROM {LOG_TABLE}
            WHERE created_at >= NOW() - INTERVAL '7 days'
        """)
        summary = cursor.fetchone()

        cursor.close()
        return {
            "period": "7 days",
            "total_logs": summary[2] or 0,
            "unique_users": summary[0] or 0,
            "unique_ips": summary[1] or 0,
            "by_type": [
                {"log_type": r[0], "level": r[1], "count": r[2],
                 "first": str(r[3]) if r[3] else None,
                 "last": str(r[4]) if r[4] else None}
                for r in rows
            ],
        }
    finally:
        conn.close()


# Initialize table on module load
setup_logs_table()
