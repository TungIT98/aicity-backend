"""
AI City Subscription Management Module
Handles subscription plans, billing, and usage tracking
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import uuid
import json
import psycopg2

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "database": "promptforge",
    "user": "promptforge",
    "password": "promptforge123",
}

# Subscription Plans (from pricing.md)
SUBSCRIPTION_PLANS = {
    "starter": {
        "id": "starter",
        "name": "Starter Plan",
        "price_vnd": 500000,
        "price_display": "500,000 VND",
        "features": {
            "ai_agent_runs_per_day": 5,
            "knowledge_base_docs": 100,
            "support": "email",
            "analytics": False,
            "api_access": False,
        },
        "description": "Perfect for small teams starting with AI"
    },
    "business": {
        "id": "business",
        "name": "Business Plan",
        "price_vnd": 1000000,
        "price_display": "1,000,000 VND",
        "features": {
            "ai_agent_runs_per_day": 50,
            "knowledge_base_docs": 1000,
            "support": "priority",
            "analytics": True,
            "api_access": False,
        },
        "description": "Best for growing businesses"
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Enterprise Plan",
        "price_vnd": 2500000,
        "price_display": "2,500,000 VND",
        "features": {
            "ai_agent_runs_per_day": -1,  # unlimited
            "knowledge_base_docs": -1,  # unlimited
            "support": "dedicated",
            "analytics": True,
            "api_access": True,
            "custom_integrations": True,
        },
        "description": "For established businesses"
    }
}


# ============== Models ==============

class SubscriptionCreate(BaseModel):
    customer_id: str
    customer_email: str
    customer_name: str
    plan_id: str  # starter, business, enterprise
    payment_method: str
    payment_transaction_id: str
    billing_cycle: str = "monthly"  # monthly, quarterly, annual


class SubscriptionUpdate(BaseModel):
    plan_id: Optional[str] = None
    status: Optional[str] = None  # active, cancelled, expired, suspended
    auto_renew: Optional[bool] = None


class UsageRecord(BaseModel):
    date: str
    ai_runs: int = 0
    documents_count: int = 0


class SubscriptionResponse(BaseModel):
    subscription_id: str
    customer_id: str
    customer_email: str
    customer_name: str
    plan_id: str
    plan_name: str
    price_vnd: int
    status: str
    billing_cycle: str
    start_date: str
    end_date: str
    auto_renew: bool
    usage_today: UsageRecord


# ============== Helper Functions ==============

def get_db():
    """Database connection"""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def init_subscriptions_db():
    """Initialize subscriptions table"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY,
            subscription_id VARCHAR(50) UNIQUE NOT NULL,
            customer_id VARCHAR(100) NOT NULL,
            customer_email VARCHAR(255) NOT NULL,
            customer_name VARCHAR(255) NOT NULL,
            plan_id VARCHAR(20) NOT NULL,
            status VARCHAR(20) DEFAULT 'active',
            billing_cycle VARCHAR(20) DEFAULT 'monthly',
            price_vnd INTEGER NOT NULL,
            start_date TIMESTAMP NOT NULL,
            end_date TIMESTAMP NOT NULL,
            auto_renew BOOLEAN DEFAULT True,
            payment_transaction_id VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            metadata JSONB DEFAULT '{}'
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_subscriptions_customer ON subscriptions(customer_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status)
    """)

    # Usage tracking table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscription_usage (
            id SERIAL PRIMARY KEY,
            subscription_id VARCHAR(50) NOT NULL,
            usage_date DATE NOT NULL,
            ai_runs INTEGER DEFAULT 0,
            documents_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(subscription_id, usage_date)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_usage_subscription ON subscription_usage(subscription_id)
    """)

    conn.commit()
    cursor.close()
    conn.close()


def generate_subscription_id():
    """Generate unique subscription ID"""
    return f"SUB-{uuid.uuid4().hex[:10].upper()}"


def calculate_end_date(start_date: datetime, billing_cycle: str) -> datetime:
    """Calculate subscription end date based on billing cycle"""
    if billing_cycle == "monthly":
        return start_date + timedelta(days=30)
    elif billing_cycle == "quarterly":
        return start_date + timedelta(days=90)
    elif billing_cycle == "annual":
        return start_date + timedelta(days=365)
    return start_date + timedelta(days=30)  # default to monthly


def get_usage_today(subscription_id: str) -> UsageRecord:
    """Get today's usage for a subscription"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    today = datetime.now().date().isoformat()

    cursor.execute("""
        SELECT ai_runs, documents_count
        FROM subscription_usage
        WHERE subscription_id = %s AND usage_date = %s
    """, (subscription_id, today))

    result = cursor.fetchone()
    cursor.close()
    conn.close()

    if result:
        return UsageRecord(date=today, ai_runs=result[0], documents_count=result[1])
    return UsageRecord(date=today, ai_runs=0, documents_count=0)


def check_usage_limits(plan_id: str, subscription_id: str) -> dict:
    """Check if subscription has exceeded usage limits"""
    plan = SUBSCRIPTION_PLANS.get(plan_id)
    if not plan:
        return {"allowed": True, "reason": "Unknown plan"}

    usage = get_usage_today(subscription_id)
    daily_limit = plan["features"]["ai_agent_runs_per_day"]

    # -1 means unlimited
    if daily_limit == -1:
        return {"allowed": True, "reason": "Unlimited"}

    if usage.ai_runs >= daily_limit:
        return {
            "allowed": False,
            "reason": f"Daily limit reached ({usage.ai_runs}/{daily_limit})",
            "current": usage.ai_runs,
            "limit": daily_limit
        }

    return {
        "allowed": True,
        "remaining": daily_limit - usage.ai_runs
    }


# ============== API Endpoints ==============

@router.on_event("startup")
async def init_subscriptions():
    """Initialize subscription tables on startup"""
    init_subscriptions_db()


@router.get("/plans")
async def get_subscription_plans():
    """Get available subscription plans"""
    plans = []
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        plans.append({
            "id": plan["id"],
            "name": plan["name"],
            "price_vnd": plan["price_vnd"],
            "price_display": plan["price_display"],
            "features": plan["features"],
            "description": plan["description"]
        })
    return {"plans": plans}


@router.post("/", response_model=SubscriptionResponse)
async def create_subscription(subscription: SubscriptionCreate):
    """Create a new subscription from payment"""
    try:
        # Validate plan
        plan = SUBSCRIPTION_PLANS.get(subscription.plan_id)
        if not plan:
            raise HTTPException(status_code=400, detail="Invalid plan ID")

        # Generate subscription ID
        subscription_id = generate_subscription_id()

        # Calculate dates
        start_date = datetime.now()
        end_date = calculate_end_date(start_date, subscription.billing_cycle)

        # Calculate price based on billing cycle
        price = plan["price_vnd"]
        if subscription.billing_cycle == "quarterly":
            price = price * 3 * 0.95  # 5% discount
        elif subscription.billing_cycle == "annual":
            price = price * 12 * 0.85  # 15% discount
        price = int(price)

        # Save to database
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO subscriptions (
                subscription_id, customer_id, customer_email, customer_name,
                plan_id, status, billing_cycle, price_vnd,
                start_date, end_date, auto_renew, payment_transaction_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, subscription_id, customer_id, customer_email, customer_name,
                      plan_id, status, billing_cycle, price_vnd,
                      start_date, end_date, auto_renew
        """, (
            subscription_id, subscription.customer_id, subscription.customer_email,
            subscription.customer_name, subscription.plan_id, "active",
            subscription.billing_cycle, price, start_date, end_date,
            True, subscription.payment_transaction_id
        ))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        usage = get_usage_today(subscription_id)

        return SubscriptionResponse(
            subscription_id=result[1],
            customer_id=result[2],
            customer_email=result[3],
            customer_name=result[4],
            plan_id=result[5],
            plan_name=plan["name"],
            price_vnd=result[8],
            status=result[6],
            billing_cycle=result[7],
            start_date=str(result[9]),
            end_date=str(result[10]),
            auto_renew=result[11],
            usage_today=usage
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(subscription_id: str):
    """Get subscription details"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT subscription_id, customer_id, customer_email, customer_name,
                   plan_id, status, billing_cycle, price_vnd,
                   start_date, end_date, auto_renew
            FROM subscriptions
            WHERE subscription_id = %s
        """, (subscription_id,))

        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if not result:
            raise HTTPException(status_code=404, detail="Subscription not found")

        plan = SUBSCRIPTION_PLANS.get(result[4])
        usage = get_usage_today(subscription_id)

        return SubscriptionResponse(
            subscription_id=result[0],
            customer_id=result[1],
            customer_email=result[2],
            customer_name=result[3],
            plan_id=result[4],
            plan_name=plan["name"] if plan else "Unknown",
            price_vnd=result[7],
            status=result[5],
            billing_cycle=result[6],
            start_date=str(result[8]),
            end_date=str(result[9]),
            auto_renew=result[10],
            usage_today=usage
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/customer/{customer_id}")
async def get_customer_subscriptions(customer_id: str):
    """Get all subscriptions for a customer"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT subscription_id, customer_id, customer_email, customer_name,
                   plan_id, status, billing_cycle, price_vnd,
                   start_date, end_date, auto_renew
            FROM subscriptions
            WHERE customer_id = %s
            ORDER BY created_at DESC
        """, (customer_id,))

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        subscriptions = []
        for r in results:
            plan = SUBSCRIPTION_PLANS.get(r[4])
            usage = get_usage_today(r[0])
            subscriptions.append(SubscriptionResponse(
                subscription_id=r[0],
                customer_id=r[1],
                customer_email=r[2],
                customer_name=r[3],
                plan_id=r[4],
                plan_name=plan["name"] if plan else "Unknown",
                price_vnd=r[7],
                status=r[5],
                billing_cycle=r[6],
                start_date=str(r[8]),
                end_date=str(r[9]),
                auto_renew=r[10],
                usage_today=usage
            ))

        return {"subscriptions": subscriptions}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{subscription_id}")
async def update_subscription(subscription_id: str, update: SubscriptionUpdate):
    """Update subscription (change plan, status, auto-renew)"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Check if subscription exists
        cursor.execute("""
            SELECT plan_id, status, price_vnd FROM subscriptions
            WHERE subscription_id = %s
        """, (subscription_id,))

        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Subscription not found")

        current_plan_id, current_status, current_price = result

        # Build update query
        updates = []
        values = []

        if update.plan_id is not None:
            new_plan = SUBSCRIPTION_PLANS.get(update.plan_id)
            if not new_plan:
                raise HTTPException(status_code=400, detail="Invalid plan ID")

            updates.append("plan_id = %s")
            values.append(update.plan_id)
            updates.append("price_vnd = %s")
            values.append(new_plan["price_vnd"])

        if update.status is not None:
            if update.status not in ["active", "cancelled", "expired", "suspended"]:
                raise HTTPException(status_code=400, detail="Invalid status")
            updates.append("status = %s")
            values.append(update.status)

        if update.auto_renew is not None:
            updates.append("auto_renew = %s")
            values.append(update.auto_renew)

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = NOW()")
        values.append(subscription_id)

        cursor.execute(f"""
            UPDATE subscriptions SET {', '.join(updates)}
            WHERE subscription_id = %s
            RETURNING subscription_id, status
        """, tuple(values))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return {
            "subscription_id": result[0],
            "status": result[1],
            "message": "Subscription updated"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{subscription_id}/cancel")
async def cancel_subscription(subscription_id: str):
    """Cancel a subscription"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE subscriptions
            SET status = 'cancelled', auto_renew = False, updated_at = NOW()
            WHERE subscription_id = %s AND status = 'active'
            RETURNING subscription_id
        """, (subscription_id,))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not result:
            raise HTTPException(status_code=400, detail="Subscription not found or already cancelled")

        return {
            "subscription_id": result[0],
            "status": "cancelled",
            "message": "Subscription cancelled successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{subscription_id}/usage")
async def record_usage(subscription_id: str, ai_runs: int = 1, documents: int = 0):
    """Record usage for a subscription (called by AI agent execution)"""
    try:
        # Get subscription to check limits
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT plan_id, status FROM subscriptions
            WHERE subscription_id = %s
        """, (subscription_id,))

        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Subscription not found")

        plan_id, status = result

        if status != "active":
            raise HTTPException(status_code=400, detail="Subscription is not active")

        # Check usage limits
        usage_check = check_usage_limits(plan_id, subscription_id)
        if not usage_check.get("allowed"):
            raise HTTPException(
                status_code=403,
                detail=usage_check.get("reason", "Usage limit exceeded")
            )

        # Record usage
        today = datetime.now().date().isoformat()

        cursor.execute("""
            INSERT INTO subscription_usage (subscription_id, usage_date, ai_runs, documents_count)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (subscription_id, usage_date)
            DO UPDATE SET
                ai_runs = subscription_usage.ai_runs + EXCLUDED.ai_runs,
                documents_count = subscription_usage.documents_count + EXCLUDED.documents_count
            RETURNING ai_runs, documents_count
        """, (subscription_id, today, ai_runs, documents))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return {
            "subscription_id": subscription_id,
            "ai_runs_today": result[0],
            "documents_today": result[1],
            "allowed": True
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{subscription_id}/usage/check")
async def check_usage(subscription_id: str):
    """Check current usage and limits"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT plan_id FROM subscriptions
            WHERE subscription_id = %s
        """, (subscription_id,))

        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Subscription not found")

        plan_id = result[0]
        usage = get_usage_today(subscription_id)
        limits = check_usage_limits(plan_id, subscription_id)
        plan = SUBSCRIPTION_PLANS.get(plan_id)

        return {
            "subscription_id": subscription_id,
            "plan": plan["name"] if plan else "Unknown",
            "usage_today": usage,
            "daily_limit": plan["features"]["ai_agent_runs_per_day"] if plan else 0,
            "limits": limits
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_subscriptions(status: Optional[str] = None, limit: int = 50):
    """List all subscriptions"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        if status:
            cursor.execute("""
                SELECT subscription_id, customer_id, customer_email, customer_name,
                       plan_id, status, billing_cycle, price_vnd, start_date, end_date
                FROM subscriptions
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (status, limit))
        else:
            cursor.execute("""
                SELECT subscription_id, customer_id, customer_email, customer_name,
                       plan_id, status, billing_cycle, price_vnd, start_date, end_date
                FROM subscriptions
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        return {
            "subscriptions": [
                {
                    "subscription_id": r[0],
                    "customer_id": r[1],
                    "customer_email": r[2],
                    "customer_name": r[3],
                    "plan_id": r[4],
                    "status": r[5],
                    "billing_cycle": r[6],
                    "price_vnd": r[7],
                    "start_date": str(r[8]),
                    "end_date": str(r[9])
                }
                for r in results
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Webhook Integration ==============

@router.post("/webhooks/payment")
async def payment_webhook(payment_id: str, status: str, transaction_id: str = None):
    """
    Handle payment webhook to create/activate subscription
    Called after successful payment
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Get payment info
        cursor.execute("""
            SELECT order_id, amount, payment_method, customer_id, customer_email
            FROM payments
            WHERE payment_id = %s AND status = 'completed'
        """, (payment_id,))

        payment = cursor.fetchone()
        if not payment:
            return {"error": "Payment not found or not completed"}

        order_id, amount, payment_method, customer_id, customer_email = payment

        # Determine plan based on amount
        plan_id = "starter"  # default
        for pid, plan in SUBSCRIPTION_PLANS.items():
            if plan["price_vnd"] <= amount:
                plan_id = pid  # use the highest plan that fits the budget

        # Create subscription
        subscription_id = generate_subscription_id()
        start_date = datetime.now()
        end_date = calculate_end_date(start_date, "monthly")

        cursor.execute("""
            INSERT INTO subscriptions (
                subscription_id, customer_id, customer_email, customer_name,
                plan_id, status, billing_cycle, price_vnd,
                start_date, end_date, auto_renew, payment_transaction_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            subscription_id, customer_id, customer_email, f"Customer_{order_id[:8]}",
            plan_id, "active", "monthly", amount, start_date, end_date, True, transaction_id
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return {
            "status": "subscription_created",
            "subscription_id": subscription_id,
            "plan_id": plan_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    uvicorn.run(app, host="0.0.0.0", port=8000)