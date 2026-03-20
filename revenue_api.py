"""
AI City Revenue API Module
Handles revenue transaction tracking and reporting
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
import psycopg2
import os
import uuid
import random

router = APIRouter(prefix="/api/revenue", tags=["revenue"])

# Database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5433")),
    "database": os.getenv("DB_NAME", "promptforge"),
    "user": os.getenv("DB_USER", "promptforge"),
    "password": os.getenv("DB_PASSWORD", "promptforge123"),
}

# Vietnam location mapping for geo data
VIETNAM_LOCATIONS = {
    "hcm": {"lat": 10.8231, "lng": 106.6297, "name": "Ho Chi Minh City"},
    "hn": {"lat": 21.0285, "lng": 105.8542, "name": "Hanoi"},
    "dn": {"lat": 16.0544, "lng": 108.2022, "name": "Da Nang"},
    "other": {"lat": 16.0544, "lng": 108.2022, "name": "Other"},
}

# International location mapping
INTERNATIONAL_LOCATIONS = {
    "sg": {"lat": 1.3521, "lng": 103.8198, "name": "Singapore"},
    "us": {"lat": 37.0902, "lng": -95.7129, "name": "United States"},
    "uk": {"lat": 55.3781, "lng": -3.4360, "name": "United Kingdom"},
    "au": {"lat": -25.2744, "lng": 133.7751, "name": "Australia"},
    "jp": {"lat": 36.2048, "lng": 138.2529, "name": "Japan"},
}


class VietQRWebhookRequest(BaseModel):
    """Request model for VietQR webhook"""
    payment_id: str
    status: str  # completed, failed
    transaction_id: Optional[str] = None
    amount: Optional[int] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None


class RevenueTransaction(BaseModel):
    """Revenue transaction model"""
    transaction_id: str
    payment_id: Optional[str] = None
    order_id: Optional[str] = None
    amount: int
    currency: str = "VND"
    customer_email: str
    customer_name: Optional[str] = None
    customer_location: Optional[str] = None
    payment_method: str
    transaction_ref: Optional[str] = None
    status: str = "completed"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    transaction_date: date


def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(**DB_CONFIG)


def generate_transaction_id() -> str:
    """Generate unique transaction ID"""
    return f"TXN-{uuid.uuid4().hex[:12].upper()}"


def get_location_from_email(email: str) -> dict:
    """Get geo location from customer email or domain"""
    if not email:
        return INTERNATIONAL_LOCATIONS.get("us", {"lat": 0, "lng": 0, "name": "Unknown"})

    email_lower = email.lower()

    # Check for Vietnam email domains
    vn_domains = ["@gmail.com", "@yahoo.com", "@hotmail.com", "@outlook.com"]
    if any(email.endswith(dom) for dom in vn_domains):
        # Default to Ho Chi Minh for generic VN emails
        return VIETNAM_LOCATIONS.get("hcm", {"lat": 10.8231, "lng": 106.6297, "name": "Vietnam"})

    # Check for specific company domains (can be extended)
    company_domains = {
        "fpt.com.vn": {"lat": 10.8231, "lng": 106.6297, "name": "Ho Chi Minh City"},
        "viettel.com.vn": {"lat": 21.0285, "lng": 105.8542, "name": "Hanoi"},
        "vnpt.com.vn": {"lat": 21.0285, "lng": 105.8542, "name": "Hanoi"},
    }

    for domain, loc in company_domains.items():
        if domain in email_lower:
            return loc

    # Default international
    return INTERNATIONAL_LOCATIONS.get("us", {"lat": 37.0902, "lng": -95.7129, "name": "United States"})


@router.post("/webhook/vietqr")
async def vietqr_revenue_webhook(request: VietQRWebhookRequest):
    """
    Handle VietQR payment success and create revenue transaction.

    This endpoint is called when a VietQR payment is confirmed.
    It records the transaction in the revenue_transactions table.
    """
    if request.status != "completed":
        return {"status": "ignored", "reason": "Payment not completed"}

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get location from email
        location = get_location_from_email(request.customer_email)

        # Generate transaction ID
        transaction_id = generate_transaction_id()

        # Get payment details if payment_id provided
        order_id = None
        amount = request.amount or 0
        if request.payment_id:
            cursor.execute("""
                SELECT order_id, amount, customer_email, customer_name
                FROM payments WHERE payment_id = %s
            """, (request.payment_id,))
            result = cursor.fetchone()
            if result:
                order_id = result[0]
                if not amount:
                    amount = result[1]
                if not request.customer_email:
                    request.customer_email = result[2]
                if not request.customer_name:
                    request.customer_name = result[3]

        # Insert revenue transaction
        cursor.execute("""
            INSERT INTO revenue_transactions (
                transaction_id, payment_id, order_id,
                amount, currency,
                customer_email, customer_name, customer_location,
                payment_method, transaction_ref,
                status, latitude, longitude,
                transaction_date, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            )
            ON CONFLICT (transaction_id) DO NOTHING
        """, (
            transaction_id,
            request.payment_id,
            order_id,
            amount,
            "VND",
            request.customer_email or "unknown@example.com",
            request.customer_name,
            location["name"],
            "vietqr",
            request.transaction_id,
            "completed",
            location["lat"],
            location["lng"],
            date.today()
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return {
            "status": "success",
            "transaction_id": transaction_id,
            "amount": amount,
            "location": location["name"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record transaction: {str(e)}")


@router.get("/globe")
async def get_revenue_for_globe():
    """
    Get revenue data formatted for globe visualization.

    Returns:
        - total_revenue_today: Total revenue today
        - revenue_by_region: Revenue grouped by region with lat/lng
        - revenue_by_agent: Revenue by agent (if applicable)
        - trend: 'up' or 'down' compared to yesterday
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get today's revenue
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM revenue_transactions
            WHERE transaction_date = CURRENT_DATE AND status = 'completed'
        """)
        total_today = cursor.fetchone()[0] or 0

        # Get revenue by region/location
        cursor.execute("""
            SELECT
                COALESCE(customer_location, 'Unknown') as region,
                latitude, longitude,
                COALESCE(SUM(amount), 0) as revenue,
                COUNT(*) as transaction_count
            FROM revenue_transactions
            WHERE status = 'completed'
            GROUP BY customer_location, latitude, longitude
            ORDER BY revenue DESC
        """)
        regions = cursor.fetchall()

        revenue_by_region = []
        for row in regions:
            if row[1] and row[2]:  # Has lat/lng
                revenue_by_region.append({
                    "region": row[0],
                    "lat": float(row[1]),
                    "lng": float(row[2]),
                    "amount": float(row[3]),
                    "transaction_count": row[4]
                })

        # Get trend (compare to yesterday)
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM revenue_transactions
            WHERE transaction_date = CURRENT_DATE - INTERVAL '1 day' AND status = 'completed'
        """)
        yesterday_revenue = cursor.fetchone()[0] or 0

        trend = "up" if total_today >= yesterday_revenue else "down"

        cursor.close()
        conn.close()

        return {
            "total_revenue_today": float(total_today),
            "revenue_by_region": revenue_by_region,
            "trend": trend,
            "yesterday_revenue": float(yesterday_revenue)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get revenue data: {str(e)}")


@router.get("/summary")
async def get_revenue_summary():
    """Get revenue summary metrics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Total revenue all time
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM revenue_transactions WHERE status = 'completed'
        """)
        total_revenue = cursor.fetchone()[0] or 0

        # Revenue this month
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM revenue_transactions
            WHERE status = 'completed'
            AND transaction_date >= DATE_TRUNC('month', CURRENT_DATE)
        """)
        monthly_revenue = cursor.fetchone()[0] or 0

        # Revenue this week
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM revenue_transactions
            WHERE status = 'completed'
            AND transaction_date >= DATE_TRUNC('week', CURRENT_DATE)
        """)
        weekly_revenue = cursor.fetchone()[0] or 0

        # Transaction count
        cursor.execute("""
            SELECT COUNT(*)
            FROM revenue_transactions WHERE status = 'completed'
        """)
        transaction_count = cursor.fetchone()[0] or 0

        # Unique customers
        cursor.execute("""
            SELECT COUNT(DISTINCT customer_email)
            FROM revenue_transactions WHERE status = 'completed'
        """)
        customer_count = cursor.fetchone()[0] or 0

        cursor.close()
        conn.close()

        return {
            "total_revenue": float(total_revenue),
            "monthly_revenue": float(monthly_revenue),
            "weekly_revenue": float(weekly_revenue),
            "transaction_count": transaction_count,
            "customer_count": customer_count,
            "mrr_estimate": float(monthly_revenue)  # Simplified MRR
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get revenue summary: {str(e)}")
