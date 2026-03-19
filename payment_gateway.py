"""
Vietnamese Payment Gateway Module
Supports: VietQR, MoMo, ZaloPay
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
import uuid
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta
import psycopg2
import requests

router = APIRouter(prefix="/payments", tags=["payments"])

# Database configuration (imported from main)
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "database": "promptforge",
    "user": "promptforge",
    "password": "promptforge123",
}

# Payment Provider Configuration
# In production, use environment variables
PAYMENT_CONFIG = {
    "vietqr": {
        "enabled": True,
        "partner_id": os.getenv("VIETQR_PARTNER_ID", ""),
        "partner_key": os.getenv("VIETQR_PARTNER_KEY", ""),
        "bank_code": os.getenv("VIETQR_BANK_CODE", "VCB"),
    },
    "momo": {
        "enabled": True,
        "partner_code": os.getenv("MOMO_PARTNER_CODE", ""),
        "api_key": os.getenv("MOMO_API_KEY", ""),
    },
    "zalopay": {
        "enabled": True,
        "app_id": os.getenv("ZALOPAY_APP_ID", ""),
        "key1": os.getenv("ZALOPAY_KEY1", ""),
        "key2": os.getenv("ZALOPAY_KEY2", ""),
    }
}


# ============== Models ==============

class PaymentCreateRequest(BaseModel):
    amount: int  # Amount in VND
    currency: str = "VND"
    payment_method: str  # vietqr, momo, zalopay
    order_id: str
    order_info: str
    customer_id: Optional[str] = None
    customer_email: Optional[str] = None
    callback_url: Optional[str] = None


class PaymentResponse(BaseModel):
    payment_id: str
    order_id: str
    amount: int
    currency: str
    payment_method: str
    status: str
    qr_code: Optional[str] = None
    payment_url: Optional[str] = None
    expired_at: str


class PaymentCallback(BaseModel):
    payment_id: str
    status: str
    amount: int
    transaction_id: Optional[str] = None
    signature: Optional[str] = None


class PaymentStatusResponse(BaseModel):
    payment_id: str
    order_id: str
    amount: int
    currency: str
    payment_method: str
    status: str
    transaction_id: Optional[str] = None
    paid_at: Optional[str] = None


# ============== Helper Functions ==============

def get_db():
    """Database connection"""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def generate_payment_id():
    """Generate unique payment ID"""
    return f"PAY-{uuid.uuid4().hex[:12].upper()}"


def generate_order_id():
    """Generate unique order ID for payment provider"""
    return f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


def generate_hmacsignature(data: str, key: str) -> str:
    """Generate HMAC-SHA256 signature"""
    return hmac.new(
        key.encode(),
        data.encode(),
        hashlib.sha256
    ).hexdigest()


def get_payment_db():
    """Get or create payments table"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # Create payments table if not exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            payment_id VARCHAR(50) UNIQUE NOT NULL,
            order_id VARCHAR(100) NOT NULL,
            amount INTEGER NOT NULL,
            currency VARCHAR(10) DEFAULT 'VND',
            payment_method VARCHAR(20) NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            transaction_id VARCHAR(100),
            qr_code TEXT,
            payment_url TEXT,
            customer_id VARCHAR(100),
            customer_email VARCHAR(255),
            callback_url TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            expired_at TIMESTAMP,
            paid_at TIMESTAMP,
            metadata JSONB DEFAULT '{}'
        )
    """)

    # Create index for faster queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_payments_payment_id ON payments(payment_id)
    """)

    conn.commit()
    cursor.close()
    conn.close()


# ============== Payment Methods ==============

def create_vietqr_payment(payment_id: str, amount: int, order_id: str, order_info: str):
    """
    Create VietQR payment
    In production, this would call the actual bank/PSP API
    For now, generates a placeholder QR code URL
    """
    config = PAYMENT_CONFIG["vietqr"]

    # Generate QR code data (mock implementation)
    # In production, call VietQR API to get actual QR code
    bank_code = config["bank_code"]

    # QR data format for VietQR (simplified)
    qr_data = f"00{bank_code}010211{order_id}{amount:010d}VIETQR"

    # Generate QR code URL (using a QR code generator service)
    qr_code = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={requests.utils.quote(qr_data)}"

    return {
        "qr_code": qr_code,
        "payment_url": None,  # VietQR doesn't need a URL, just QR code
        "instruction": f"Scan QR code with your banking app to pay {amount:,} VND"
    }


def create_momo_payment(payment_id: str, amount: int, order_id: str, order_info: str):
    """
    Create MoMo payment
    In production, this would call MoMo's API
    """
    config = PAYMENT_CONFIG["momo"]

    # Mock payment URL - in production, this would be MoMo's payment endpoint
    payment_url = f"https://momo.vn/payment?orderId={order_id}&amount={amount}"

    return {
        "qr_code": None,
        "payment_url": payment_url,
        "instruction": f"Pay {amount:,} VND via MoMo app"
    }


def create_zalopay_payment(payment_id: str, amount: int, order_id: str, order_info: str):
    """
    Create ZaloPay payment
    In production, this would call ZaloPay's API
    """
    config = PAYMENT_CONFIG["zalopay"]

    # Mock payment URL - in production, this would be ZaloPay's payment endpoint
    payment_url = f"https://zalopay.vn/payment?orderId={order_id}&amount={amount}"

    return {
        "qr_code": None,
        "payment_url": payment_url,
        "instruction": f"Pay {amount:,} VND via ZaloPay app"
    }


# ============== API Endpoints ==============

@router.on_event("startup")
async def init_payments():
    """Initialize payment tables on startup"""
    get_payment_db()


@router.post("/create", response_model=PaymentResponse)
async def create_payment(request: PaymentCreateRequest):
    """Create a new payment"""
    try:
        # Validate payment method
        if request.payment_method not in ["vietqr", "momo", "zalopay"]:
            raise HTTPException(status_code=400, detail="Invalid payment method")

        if not PAYMENT_CONFIG.get(request.payment_method, {}).get("enabled"):
            raise HTTPException(status_code=400, detail="Payment method not available")

        # Generate payment ID and order ID
        payment_id = generate_payment_id()
        provider_order_id = generate_order_id()

        # Set expiration (15 minutes from now)
        expired_at = datetime.now() + timedelta(minutes=15)

        # Create payment based on method
        if request.payment_method == "vietqr":
            payment_data = create_vietqr_payment(payment_id, request.amount, provider_order_id, request.order_info)
        elif request.payment_method == "momo":
            payment_data = create_momo_payment(payment_id, request.amount, provider_order_id, request.order_info)
        elif request.payment_method == "zalopay":
            payment_data = create_zalopay_payment(payment_id, request.amount, provider_order_id, request.order_info)
        else:
            raise HTTPException(status_code=400, detail="Unsupported payment method")

        # Save to database
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO payments (
                payment_id, order_id, amount, currency, payment_method,
                status, qr_code, payment_url, customer_id, customer_email,
                callback_url, expired_at, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING payment_id
        """, (
            payment_id, provider_order_id, request.amount, request.currency,
            request.payment_method, "pending",
            payment_data.get("qr_code"), payment_data.get("payment_url"),
            request.customer_id, request.customer_email, request.callback_url,
            expired_at, json.dumps({"order_info": request.order_info})
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return PaymentResponse(
            payment_id=payment_id,
            order_id=provider_order_id,
            amount=request.amount,
            currency=request.currency,
            payment_method=request.payment_method,
            status="pending",
            qr_code=payment_data.get("qr_code"),
            payment_url=payment_data.get("payment_url")
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{payment_id}/status", response_model=PaymentStatusResponse)
async def get_payment_status(payment_id: str):
    """Get payment status"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT payment_id, order_id, amount, currency, payment_method,
                   status, transaction_id, paid_at
            FROM payments
            WHERE payment_id = %s
        """, (payment_id,))

        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if not result:
            raise HTTPException(status_code=404, detail="Payment not found")

        return PaymentStatusResponse(
            payment_id=result[0],
            order_id=result[1],
            amount=result[2],
            currency=result[3],
            payment_method=result[4],
            status=result[5],
            transaction_id=result[6],
            paid_at=str(result[7]) if result[7] else None
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/callback")
async def payment_callback(callback: PaymentCallback):
    """Handle payment callback from provider"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Update payment status
        cursor.execute("""
            UPDATE payments
            SET status = %s,
                transaction_id = COALESCE(%s, transaction_id),
                paid_at = CASE WHEN %s = 'completed' THEN NOW() ELSE paid_at END
            WHERE payment_id = %s
        """, (callback.status, callback.transaction_id, callback.status, callback.payment_id))

        conn.commit()
        cursor.close()
        conn.close()

        # Trigger invoice webhook if payment completed
        if callback.status == "completed":
            try:
                import requests
                # Call invoice webhook to create invoice
                requests.post(
                    "http://localhost:8000/invoices/webhooks/payment",
                    params={
                        "payment_id": callback.payment_id,
                        "status": "completed",
                        "transaction_id": callback.transaction_id
                    },
                    timeout=5
                )
                # Call subscription webhook to create subscription
                requests.post(
                    "http://localhost:8000/subscriptions/webhooks/payment",
                    params={
                        "payment_id": callback.payment_id,
                        "status": "completed",
                        "transaction_id": callback.transaction_id
                    },
                    timeout=5
                )
            except Exception as e:
                # Log but don't fail the callback
                print(f"Webhook error: {e}")

        return {"status": "ok"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Pricing plans (in VND)
PRICING_PLANS = {
    "starter": {"name": "Starter Plan", "amount": 500000, "period": "monthly"},
    "business": {"name": "Business Plan", "amount": 1000000, "period": "monthly"},
    "enterprise": {"name": "Enterprise Plan", "amount": 2500000, "period": "monthly"},
    "pro": {"name": "Pro Plan", "amount": 1500000, "period": "monthly"},
}


class CheckoutRequest(BaseModel):
    plan_id: str  # starter, business, enterprise, pro
    payment_method: str  # vietqr, momo, zalopay
    customer_id: Optional[str] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None


class CheckoutResponse(BaseModel):
    checkout_id: str
    plan_id: str
    plan_name: str
    amount: int
    currency: str
    payment_method: str
    payment_id: str
    qr_code: Optional[str] = None
    payment_url: Optional[str] = None
    instruction: Optional[str] = None
    expired_at: str


@router.get("/methods")
async def get_payment_methods():
    """Get available payment methods"""
    methods = []
    for method, config in PAYMENT_CONFIG.items():
        if config.get("enabled"):
            methods.append({
                "id": method,
                "name": method.upper(),
                "enabled": True
            })
    return {"payment_methods": methods}


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(request: CheckoutRequest):
    """Create a checkout session for subscription payment"""
    try:
        # Validate plan
        if request.plan_id not in PRICING_PLANS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid plan_id. Available: {', '.join(PRICING_PLANS.keys())}"
            )

        # Validate payment method
        if request.payment_method not in ["vietqr", "momo", "zalopay"]:
            raise HTTPException(status_code=400, detail="Invalid payment method")

        if not PAYMENT_CONFIG.get(request.payment_method, {}).get("enabled"):
            raise HTTPException(status_code=400, detail="Payment method not available")

        # Get plan details
        plan = PRICING_PLANS[request.plan_id]

        # Generate IDs
        checkout_id = f"CHK-{uuid.uuid4().hex[:12].upper()}"
        payment_id = generate_payment_id()
        provider_order_id = generate_order_id()

        # Set expiration (15 minutes)
        expired_at = datetime.now() + timedelta(minutes=15)

        # Create payment based on method
        if request.payment_method == "vietqr":
            payment_data = create_vietqr_payment(
                payment_id, plan["amount"], provider_order_id,
                f"{plan['name']} - {request.customer_name or 'Customer'}"
            )
        elif request.payment_method == "momo":
            payment_data = create_momo_payment(
                payment_id, plan["amount"], provider_order_id,
                f"{plan['name']} - {request.customer_name or 'Customer'}"
            )
        elif request.payment_method == "zalopay":
            payment_data = create_zalopay_payment(
                payment_id, plan["amount"], provider_order_id,
                f"{plan['name']} - {request.customer_name or 'Customer'}"
            )

        # Save to database
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO payments (
                payment_id, order_id, amount, currency, payment_method,
                status, qr_code, payment_url, customer_id, customer_email,
                callback_url, expired_at, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING payment_id
        """, (
            payment_id, provider_order_id, plan["amount"], "VND",
            request.payment_method, "pending",
            payment_data.get("qr_code"), payment_data.get("payment_url"),
            request.customer_id, request.customer_email, None,
            expired_at, json.dumps({
                "checkout_id": checkout_id,
                "plan_id": request.plan_id,
                "plan_name": plan["name"],
                "customer_name": request.customer_name
            })
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return CheckoutResponse(
            checkout_id=checkout_id,
            plan_id=request.plan_id,
            plan_name=plan["name"],
            amount=plan["amount"],
            currency="VND",
            payment_method=request.payment_method,
            payment_id=payment_id,
            qr_code=payment_data.get("qr_code"),
            payment_url=payment_data.get("payment_url"),
            instruction=payment_data.get("instruction"),
            expired_at=expired_at.isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plans")
async def get_pricing_plans():
    """Get available pricing plans"""
    plans = []
    for plan_id, plan in PRICING_PLANS.items():
        plans.append({
            "id": plan_id,
            "name": plan["name"],
            "amount": plan["amount"],
            "currency": "VND",
            "period": plan["period"]
        })
    return {"plans": plans}


@router.get("/")
async def list_payments(limit: int = 50, status: Optional[str] = None):
    """List payments"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        if status:
            cursor.execute("""
                SELECT payment_id, order_id, amount, currency, payment_method,
                       status, transaction_id, created_at, paid_at
                FROM payments
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (status, limit))
        else:
            cursor.execute("""
                SELECT payment_id, order_id, amount, currency, payment_method,
                       status, transaction_id, created_at, paid_at
                FROM payments
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        return {
            "payments": [
                {
                    "payment_id": r[0],
                    "order_id": r[1],
                    "amount": r[2],
                    "currency": r[3],
                    "payment_method": r[4],
                    "status": r[5],
                    "transaction_id": r[6],
                    "created_at": str(r[7]),
                    "paid_at": str(r[8]) if r[8] else None
                }
                for r in results
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Revenue Analytics ==============

@router.get("/analytics/revenue")
async def get_payment_revenue():
    """Get payment revenue analytics"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Total revenue
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as total,
                   COUNT(*) as count
            FROM payments
            WHERE status = 'completed'
        """)
        total_result = cursor.fetchone()

        # Revenue by payment method
        cursor.execute("""
            SELECT payment_method,
                   COALESCE(SUM(amount), 0) as total,
                   COUNT(*) as count
            FROM payments
            WHERE status = 'completed'
            GROUP BY payment_method
        """)
        by_method = [
            {"method": r[0], "total": r[1], "count": r[2]}
            for r in cursor.fetchall()
        ]

        # Daily revenue (last 30 days)
        cursor.execute("""
            SELECT DATE(paid_at) as date,
                   COALESCE(SUM(amount), 0) as total,
                   COUNT(*) as count
            FROM payments
            WHERE status = 'completed'
              AND paid_at >= NOW() - INTERVAL '30 days'
            GROUP BY DATE(paid_at)
            ORDER BY date
        """)
        daily = [
            {"date": str(r[0]), "total": r[1], "count": r[2]}
            for r in cursor.fetchall()
        ]

        cursor.close()
        conn.close()

        return {
            "total_revenue": total_result[0],
            "total_transactions": total_result[1],
            "by_method": by_method,
            "daily": daily,
            "currency": "VND"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    uvicorn.run(app, host="0.0.0.0", port=8000)