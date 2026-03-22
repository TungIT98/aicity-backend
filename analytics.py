"""
AI City Analytics API Module
Handles analytics endpoints for Revenue, Leads, Invoices, and Subscriptions.
Uses async SQLAlchemy with Neon PostgreSQL async connection pool.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta

from storage.database import async_session
from sqlalchemy import text

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# ---- Revenue Analytics ----

class RevenueOverview(BaseModel):
    total_transactions: int
    total_revenue: float
    unique_customers: int
    avg_transaction: float
    completed_count: int
    refunded_count: int


class RevenueByMethod(BaseModel):
    payment_method: str
    transaction_count: int
    total_amount: float
    unique_customers: int


class DailyRevenue(BaseModel):
    date: str
    amount: float
    transaction_count: int


@router.get("/revenue/overview", response_model=RevenueOverview)
async def get_revenue_overview(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """Get revenue overview metrics for the period."""
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    try:
        async with async_session() as session:
            result = await session.execute(
                text("""
                    SELECT
                        COUNT(*)                                                       AS total_transactions,
                        COALESCE(SUM(amount), 0)                                      AS total_revenue,
                        COUNT(DISTINCT customer_email)                                  AS unique_customers,
                        COALESCE(AVG(amount), 0)                                       AS avg_transaction,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END)               AS completed,
                        COUNT(CASE WHEN status = 'refunded' THEN 1 END)                AS refunded
                    FROM revenue_transactions
                    WHERE transaction_date BETWEEN :start_date AND :end_date
                """),
                {"start_date": start_date, "end_date": end_date}
            )
            row = result.fetchone()
            return RevenueOverview(
                total_transactions=row[0] or 0,
                total_revenue=float(row[1] or 0),
                unique_customers=row[2] or 0,
                avg_transaction=float(row[3] or 0),
                completed_count=row[4] or 0,
                refunded_count=row[5] or 0,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Revenue overview failed: {str(e)}")


@router.get("/revenue/by-method", response_model=List[RevenueByMethod])
async def get_revenue_by_method(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """Get revenue breakdown by payment method."""
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    try:
        async with async_session() as session:
            result = await session.execute(
                text("""
                    SELECT
                        payment_method,
                        COUNT(*)                                       AS count,
                        COALESCE(SUM(amount), 0)                      AS total,
                        COUNT(DISTINCT customer_email)                  AS customers
                    FROM revenue_transactions
                    WHERE transaction_date BETWEEN :start_date AND :end_date
                    GROUP BY payment_method
                    ORDER BY total DESC
                """),
                {"start_date": start_date, "end_date": end_date}
            )
            rows = result.fetchall()
            return [
                RevenueByMethod(
                    payment_method=r[0] or "unknown",
                    transaction_count=r[1] or 0,
                    total_amount=float(r[2] or 0),
                    unique_customers=r[3] or 0,
                )
                for r in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Revenue by method failed: {str(e)}")


@router.get("/revenue/daily", response_model=List[DailyRevenue])
async def get_daily_revenue(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """Get daily revenue for the period."""
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    try:
        async with async_session() as session:
            result = await session.execute(
                text("""
                    SELECT
                        transaction_date                    AS date,
                        COALESCE(SUM(amount), 0)           AS total,
                        COUNT(*)                            AS count
                    FROM revenue_transactions
                    WHERE transaction_date BETWEEN :start_date AND :end_date
                    AND status = 'completed'
                    GROUP BY transaction_date
                    ORDER BY transaction_date ASC
                """),
                {"start_date": start_date, "end_date": end_date}
            )
            rows = result.fetchall()
            return [
                DailyRevenue(
                    date=str(r[0]),
                    amount=float(r[1] or 0),
                    transaction_count=r[2] or 0,
                )
                for r in rows
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Daily revenue failed: {str(e)}")


# ---- Lead Analytics ----

class LeadOverview(BaseModel):
    total_leads: int
    by_status: dict
    by_source: dict
    leads_7d: int
    leads_30d: int


@router.get("/leads/overview", response_model=LeadOverview)
async def get_leads_overview():
    """Get lead metrics overview."""
    try:
        async with async_session() as session:
            # By status
            status_result = await session.execute(
                text("SELECT status, COUNT(*) FROM leads GROUP BY status ORDER BY COUNT(*) DESC")
            )
            by_status = {r[0]: r[1] for r in status_result.fetchall()}

            # By source
            source_result = await session.execute(
                text("SELECT source, COUNT(*) FROM leads GROUP BY source ORDER BY COUNT(*) DESC")
            )
            by_source = {r[0]: r[1] for r in source_result.fetchall()}

            # 7d and 30d counts
            counts_result = await session.execute(text("""
                SELECT
                    COUNT(*)                                                                      AS total,
                    COUNT(CASE WHEN created_at >= NOW() - INTERVAL '7 days' THEN 1 END)           AS "7d",
                    COUNT(CASE WHEN created_at >= NOW() - INTERVAL '30 days' THEN 1 END)          AS "30d"
                FROM leads
            """))
            counts = counts_result.fetchone()

            return LeadOverview(
                total_leads=counts[0] or 0,
                by_status=by_status,
                by_source=by_source,
                leads_7d=counts[1] or 0,
                leads_30d=counts[2] or 0,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Leads overview failed: {str(e)}")


# ---- Invoice Analytics ----

class InvoiceOverview(BaseModel):
    total_invoices: int
    total_amount: float
    total_vat: float
    by_status: dict
    by_payment_status: dict
    draft_count: int
    issued_count: int


@router.get("/invoices/overview", response_model=InvoiceOverview)
async def get_invoices_overview(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """Get invoice summary metrics."""
    where = ""
    params = {}
    if start_date and end_date:
        where = "WHERE created_at::date BETWEEN :start_date AND :end_date"
        params = {"start_date": start_date, "end_date": end_date}

    try:
        async with async_session() as session:
            result = await session.execute(
                text(f"""
                    SELECT
                        COUNT(*)                                                     AS total,
                        COALESCE(SUM(total), 0)                                     AS total_amount,
                        COALESCE(SUM(vat_amount), 0)                                AS total_vat,
                        COUNT(CASE WHEN status = 'draft' THEN 1 END)                 AS draft,
                        COUNT(CASE WHEN status = 'issued' THEN 1 END)                AS issued
                    FROM invoices {where}
                """),
                params
            )
            row = result.fetchone()

            status_result = await session.execute(
                text(f"SELECT status, COUNT(*) FROM invoices {where} GROUP BY status"),
                params
            )
            by_status = {r[0]: r[1] for r in status_result.fetchall()}

            pmt_result = await session.execute(
                text(f"SELECT payment_status, COUNT(*) FROM invoices {where} GROUP BY payment_status"),
                params
            )
            by_payment_status = {r[0]: r[1] for r in pmt_result.fetchall()}

            return InvoiceOverview(
                total_invoices=row[0] or 0,
                total_amount=float(row[1] or 0),
                total_vat=float(row[2] or 0),
                by_status=by_status,
                by_payment_status=by_payment_status,
                draft_count=row[3] or 0,
                issued_count=row[4] or 0,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invoices overview failed: {str(e)}")


# ---- Subscription Analytics ----

class SubscriptionOverview(BaseModel):
    total_subscriptions: int
    active: int
    expired: int
    cancelled: int
    expiring_soon: int
    by_plan: dict


@router.get("/subscriptions/overview", response_model=SubscriptionOverview)
async def get_subscriptions_overview():
    """Get subscription health overview."""
    try:
        async with async_session() as session:
            result = await session.execute(text("""
                SELECT
                    COUNT(*)                                                                          AS total,
                    COUNT(CASE WHEN status = 'active' THEN 1 END)                                     AS active,
                    COUNT(CASE WHEN status = 'expired' OR expires_at < NOW() THEN 1 END)              AS expired,
                    COUNT(CASE WHEN status = 'cancelled' THEN 1 END)                                  AS cancelled,
                    COUNT(CASE WHEN expires_at BETWEEN NOW() AND NOW() + INTERVAL '7 days'
                           AND status = 'active' THEN 1 END)                                          AS expiring_soon
                FROM subscriptions
            """))
            row = result.fetchone()

            plan_result = await session.execute(
                text("SELECT plan, COUNT(*) FROM subscriptions GROUP BY plan ORDER BY COUNT(*) DESC")
            )
            by_plan = {r[0]: r[1] for r in plan_result.fetchall()}

            return SubscriptionOverview(
                total_subscriptions=row[0] or 0,
                active=row[1] or 0,
                expired=row[2] or 0,
                cancelled=row[3] or 0,
                expiring_soon=row[4] or 0,
                by_plan=by_plan,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Subscriptions overview failed: {str(e)}")


# ---- Payment Analytics ----

class PaymentOverview(BaseModel):
    total_payments: int
    pending: int
    completed: int
    failed: int
    expired_pending: int


@router.get("/payments/overview", response_model=PaymentOverview)
async def get_payments_overview():
    """Get payment processing overview."""
    try:
        async with async_session() as session:
            result = await session.execute(text("""
                SELECT
                    COUNT(*)                                                                      AS total,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END)                                AS pending,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END)                              AS completed,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END)                                 AS failed,
                    COUNT(CASE WHEN expires_at < NOW() AND status = 'pending' THEN 1 END)          AS expired_pending
                FROM payments
            """))
            row = result.fetchone()
            return PaymentOverview(
                total_payments=row[0] or 0,
                pending=row[1] or 0,
                completed=row[2] or 0,
                failed=row[3] or 0,
                expired_pending=row[4] or 0,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Payments overview failed: {str(e)}")
