"""
AI City Revenue Report Module
Automated weekly revenue reporting
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import psycopg2
import os
from collections import Counter

router = APIRouter(prefix="/reports", tags=["reports"])

# Database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5433"),
    "database": os.getenv("DB_NAME", "promptforge"),
    "user": os.getenv("DB_USER", "promptforge"),
    "password": os.getenv("DB_PASSWORD", "promptforge123"),
}

# Pricing plans for MRR calculation
PRICING_PLANS = {
    "starter": {"price_vnd": 299000, "name": "Starter"},
    "professional": {"price_vnd": 799000, "name": "Professional"},
    "enterprise": {"price_vnd": 2990000, "name": "Enterprise"},
}


class WeeklyRevenueReport(BaseModel):
    report_id: str
    period_start: str
    period_end: str
    generated_at: str
    total_revenue_vnd: int
    new_customers: int
    active_users: int
    mrr_vnd: int
    top_feature: str
    revenue_by_plan: dict


def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(**DB_CONFIG)


def get_week_range():
    """Get the current week range (Monday to Sunday)"""
    today = datetime.utcnow()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.date(), sunday.date()


def calculate_total_revenue(conn, period_start, period_end):
    """Calculate total revenue from paid invoices in period"""
    query = """
        SELECT COALESCE(SUM(total), 0) as revenue
        FROM invoices
        WHERE payment_status = 'paid'
        AND issued_at >= %s
        AND issued_at <= %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (period_start, period_end))
        result = cur.fetchone()
        return int(result[0]) if result[0] else 0


def calculate_new_customers(conn, period_start, period_end):
    """Count new customers acquired in period"""
    query = """
        SELECT COUNT(*) FROM users
        WHERE created_at >= %s AND created_at <= %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (period_start, period_end))
        result = cur.fetchone()
        return result[0] or 0


def calculate_active_users(conn):
    """Count users with active subscriptions (mock - based on plan)"""
    # For now, count users with any subscription record
    # In production, check subscription status in subscriptions table
    query = """
        SELECT COUNT(DISTINCT user_id) FROM api_keys WHERE is_active = true
    """
    with conn.cursor() as cur:
        cur.execute(query)
        result = cur.fetchone()
        return result[0] or 0


def calculate_mrr(conn):
    """Calculate Monthly Recurring Revenue"""
    # For now, estimate based on active users and default plan
    # In production, query actual subscription plans
    active_users = calculate_active_users(conn)
    # Assume 70% starter, 20% professional, 10% enterprise
    mrr = (active_users * 0.7 * 299000) + \
          (active_users * 0.2 * 799000) + \
          (active_users * 0.1 * 2990000)
    return int(mrr)


def get_top_performing_feature(conn, period_start, period_end):
    """Determine top performing feature from API usage"""
    query = """
        SELECT endpoint, COUNT(*) as usage_count
        FROM api_logs
        WHERE created_at >= %s AND created_at <= %s
        GROUP BY endpoint
        ORDER BY usage_count DESC
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(query, (period_start, period_end))
        result = cur.fetchone()
        if result:
            # Map endpoint to feature name
            endpoint = result[0]
            if "/chat" in endpoint or "/completion" in endpoint:
                return "AI Chat/Completion"
            elif "/embedding" in endpoint:
                return "Embeddings"
            elif "/search" in endpoint:
                return "Semantic Search"
            elif "/billing" in endpoint:
                return "Billing"
            else:
                return endpoint.split("/")[-1] or "API Usage"
        return "N/A"


def get_revenue_by_plan(conn, period_start, period_end):
    """Get revenue breakdown by plan"""
    # For now, estimate based on distribution
    # In production, query actual subscription data
    total_rev = calculate_total_revenue(conn, period_start, period_end)
    if total_rev == 0:
        return {"starter": 0, "professional": 0, "enterprise": 0}
    return {
        "starter": int(total_rev * 0.3),
        "professional": int(total_rev * 0.4),
        "enterprise": int(total_rev * 0.3),
    }


def generate_weekly_report(conn=None):
    """Generate weekly revenue report"""
    if conn is None:
        conn = get_db_connection()

    period_start, period_end = get_week_range()

    report = {
        "report_id": f"rev_{datetime.utcnow().strftime('%Y%m%d')}",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "generated_at": datetime.utcnow().isoformat(),
        "total_revenue_vnd": calculate_total_revenue(conn, period_start, period_end),
        "new_customers": calculate_new_customers(conn, period_start, period_end),
        "active_users": calculate_active_users(conn),
        "mrr_vnd": calculate_mrr(conn),
        "top_feature": get_top_performing_feature(conn, period_start, period_end),
        "revenue_by_plan": get_revenue_by_plan(conn, period_start, period_end),
    }

    # Save report to database
    save_report(conn, report)

    return report


def save_report(conn, report):
    """Save report to database"""
    query = """
        INSERT INTO reports (report_type, title, content, period_start, period_end)
        VALUES ('weekly_revenue', %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(query, (
            f"Weekly Revenue Report {report['period_start']} - {report['period_end']}",
            str(report),
            report["period_start"],
            report["period_end"],
        ))
    conn.commit()


@router.get("/revenue/weekly")
async def get_weekly_revenue_report():
    """Get weekly revenue report"""
    conn = get_db_connection()
    try:
        report = generate_weekly_report(conn)
        return report
    finally:
        conn.close()


@router.get("/revenue/latest")
async def get_latest_revenue_report():
    """Get the latest saved revenue report"""
    conn = get_db_connection()
    try:
        query = """
            SELECT content, generated_at FROM reports
            WHERE report_type = 'weekly_revenue'
            ORDER BY generated_at DESC
            LIMIT 1
        """
        with conn.cursor() as cur:
            cur.execute(query)
            result = cur.fetchone()
            if result:
                import json
                return json.loads(result[0].replace("'", '"'))
            return {"message": "No reports available"}
    finally:
        conn.close()


@router.get("/revenue/history")
async def get_revenue_history():
    """Get revenue report history"""
    conn = get_db_connection()
    try:
        query = """
            SELECT id, title, period_start, period_end, generated_at
            FROM reports
            WHERE report_type = 'weekly_revenue'
            ORDER BY generated_at DESC
            LIMIT 12
        """
        with conn.cursor() as cur:
            cur.execute(query)
            results = cur.fetchall()
            return {
                "reports": [
                    {
                        "id": str(r[0]),
                        "title": r[1],
                        "period_start": r[2].isoformat() if r[2] else None,
                        "period_end": r[3].isoformat() if r[3] else None,
                        "generated_at": r[4].isoformat() if r[4] else None,
                    }
                    for r in results
                ]
            }
    finally:
        conn.close()


# Standalone script for cron job
if __name__ == "__main__":
    import json
    report = generate_weekly_report()
    print(json.dumps(report, indent=2))