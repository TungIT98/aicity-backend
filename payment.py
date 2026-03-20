"""
AI City Payment Gateway Module
Supports multiple payment providers: Stripe, VietQR, MoMo
Designed for Vietnamese market with international card support
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import uuid
import json
import psycopg2
import os

router = APIRouter(prefix="/payments", tags=["payments"])

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "database": "promptforge",
    "user": "promptforge",
    "password": "promptforge123",
}

# Payment configuration
# Stripe can work without Vietnamese bank details initially
STRIPE_CONFIG = {
    "enabled": True,
    "test_mode": os.getenv("STRIPE_TEST_MODE", "true").lower() == "true",
    "publishable_key": os.getenv("STRIPE_PUBLISHABLE_KEY", ""),
    "secret_key": os.getenv("STRIPE_SECRET_KEY", ""),
    "webhook_secret": os.getenv("STRIPE_WEBHOOK_SECRET", ""),
}

# VietQR configuration (requires bank details from Tùng)
VIETQR_CONFIG = {
    "enabled": False,  # Disabled until Tùng provides bank details
    "bank_name": os.getenv("VIETQR_BANK_NAME", ""),
    "account_number": os.getenv("VIETQR_ACCOUNT_NUMBER", ""),
    "account_name": os.getenv("VIETQR_ACCOUNT_NAME", ""),
}

# MoMo configuration
MOMO_CONFIG = {
    "enabled": False,  # Requires MoMo partner credentials
    "partner_code": os.getenv("MOMO_PARTNER_CODE", ""),
    "api_key": os.getenv("MOMO_API_KEY", ""),
}

# Pricing tiers (VND)
PRICING_TIERS = {
    "starter": {
        "name": "Starter",
        "price_vnd": 299000,
        "price_display": "299K",
        "description": "5 AI runs/day, 100 documents",
        "features": ["5 AI runs/day", "100 document knowledge base", "Email support"]
    },
    "pro": {
        "name": "Pro",
        "price_vnd": 799000,
        "price_display": "799K",
        "description": "50 AI runs/day, 1,000 documents",
        "features": ["50 AI runs/day", "1,000 document knowledge base", "Priority support", "Analytics"]
    },
    "business": {
        "name": "Business",
        "price_vnd": 1999000,
        "price_display": "1.999K",
        "description": "Unlimited AI runs, unlimited documents",
        "features": ["Unlimited AI runs", "Unlimited knowledge base", "Dedicated support", "Custom integrations", "API access"]
    }
}


def get_db():
    """Database connection"""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


# ============== Models ==============

class PaymentCreateRequest(BaseModel):
    """Request to create a payment"""
    plan: str  # starter, pro, business
    customer_email: str
    customer_name: Optional[str] = None
    payment_method: str  # stripe, vietqr, momo
    currency: str = "VND"


class PaymentResponse(BaseModel):
    """Payment response"""
    payment_id: str
    order_id: str
    amount: int
    currency: str
    status: str
    payment_method: str
    customer_email: str
    checkout_url: Optional[str] = None
    qr_code: Optional[str] = None  # For VietQR/MoMo
    expires_at: str
    created_at: str


class PaymentWebhookRequest(BaseModel):
    """Payment webhook from payment provider"""
    payment_id: str
    status: str  # completed, failed, pending, refunded
    transaction_id: Optional[str] = None
    amount: Optional[int] = None


# ============== Pricing API ==============

@router.get("/pricing")
async def get_pricing_tiers():
    """Get available pricing tiers"""
    return {
        "currency": "VND",
        "tiers": PRICING_TIERS,
        "note": "Prices include 10% VAT"
    }


@router.get("/pricing/{plan}")
async def get_plan_details(plan: str):
    """Get details for a specific plan"""
    if plan not in PRICING_TIERS:
        raise HTTPException(status_code=404, detail="Plan not found")

    tier = PRICING_TIERS[plan]
    return {
        "plan": plan,
        **tier,
        "price_vnd": tier["price_vnd"],
        "price_with_vat": int(tier["price_vnd"] * 1.1),
        "available_payment_methods": get_available_payment_methods()
    }


def get_available_payment_methods():
    """Get list of available payment methods"""
    methods = []

    if STRIPE_CONFIG["enabled"] and STRIPE_CONFIG["secret_key"]:
        methods.append({
            "id": "stripe",
            "name": "Credit/Debit Card",
            "description": "Visa, Mastercard, JCB",
            "icon": "💳"
        })

    if VIETQR_CONFIG["enabled"] and VIETQR_CONFIG["bank_name"]:
        methods.append({
            "id": "vietqr",
            "name": "VietQR",
            "description": "Scan QR with any Vietnamese bank app",
            "icon": "📱"
        })

    if MOMO_CONFIG["enabled"] and MOMO_CONFIG["partner_code"]:
        methods.append({
            "id": "momo",
            "name": "MoMo",
            "description": "Pay with MoMo e-wallet",
            "icon": "🅰️"
        })

    # Bank transfer always available as fallback
    methods.append({
        "id": "bank_transfer",
        "name": "Bank Transfer",
        "description": "Direct bank transfer (manual confirmation)",
        "icon": "🏦"
    })

    return methods


# ============== Payment Creation ==============

@router.post("/create", response_model=PaymentResponse)
async def create_payment(request: PaymentCreateRequest):
    """Create a new payment order"""

    # Validate plan
    if request.plan not in PRICING_TIERS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    amount = PRICING_TIERS[request.plan]["price_vnd"]

    # Generate payment ID
    payment_id = f"PAY-{uuid.uuid4().hex[:12].upper()}"
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    # Determine payment method
    payment_method = request.payment_method.lower()

    checkout_url = None
    qr_code = None

    # Create payment based on method
    if payment_method == "stripe":
        checkout_url = await create_stripe_checkout(payment_id, order_id, amount, request.customer_email, request.plan)

    elif payment_method == "vietqr":
        if not VIETQR_CONFIG["enabled"]:
            raise HTTPException(status_code=400, detail="VietQR not available. Please provide bank details.")
        qr_code = await create_vietqr_payment(payment_id, order_id, amount)

    elif payment_method == "momo":
        if not MOMO_CONFIG["enabled"]:
            raise HTTPException(status_code=400, detail="MoMo not available")
        checkout_url = await create_momo_payment(payment_id, order_id, amount, request.customer_email)

    elif payment_method == "bank_transfer":
        # Bank transfer - no immediate checkout
        pass

    else:
        raise HTTPException(status_code=400, detail="Invalid payment method")

    # Calculate expiration (24 hours for most methods)
    expires_at = datetime.now() + timedelta(hours=24)

    # Store in database
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO payments (
            payment_id, order_id, amount, currency, status,
            payment_method, customer_email, customer_name,
            checkout_url, qr_code, expires_at
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s
        )
    """, (
        payment_id, order_id, amount, request.currency, "pending",
        payment_method, request.customer_email, request.customer_name,
        checkout_url, qr_code, expires_at
    ))

    conn.commit()
    cursor.close()
    conn.close()

    return PaymentResponse(
        payment_id=payment_id,
        order_id=order_id,
        amount=amount,
        currency=request.currency,
        status="pending",
        payment_method=payment_method,
        customer_email=request.customer_email,
        checkout_url=checkout_url,
        qr_code=qr_code,
        expires_at=expires_at.isoformat(),
        created_at=datetime.now().isoformat()
    )


async def create_stripe_checkout(payment_id: str, order_id: str, amount: int, email: str, plan: str) -> str:
    """Create Stripe checkout session"""

    if not STRIPE_CONFIG["secret_key"]:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    # For now, return a placeholder URL
    # In production, this would create a Stripe Checkout session
    # The Stripe integration requires: pip install stripe

    plan_name = PRICING_TIERS[plan]["name"]

    # Placeholder checkout URL - in production, use Stripe API
    base_url = os.getenv("APP_BASE_URL", "https://aicity.vn")

    # Return mock checkout for now
    # Real implementation would use stripe.checkout.Session.create()
    return f"{base_url}/checkout/success?payment_id={payment_id}&order_id={order_id}"


async def create_vietqr_payment(payment_id: str, order_id: str, amount: int) -> str:
    """Create VietQR payment (requires bank details from Tùng)"""

    if not all([VIETQR_CONFIG["bank_name"], VIETQR_CONFIG["account_number"], VIETQR_CONFIG["account_name"]]):
        raise HTTPException(status_code=400, detail="VietQR not configured - need bank details from Tùng")

    # Generate VietQR URL
    # In production, use VietQR API or generate QR code
    # For now, return placeholder
    bank = VIETQR_CONFIG["bank_name"]
    account = VIETQR_CONFIG["account_number"]

    # VietQR format: bank://QR?bank={bank}&account={account}&amount={amount}&memo={order_id}
    qr_data = f"bank://QR?bank={bank}&account={account}&amount={amount}&memo={order_id}"

    return qr_data


async def create_momo_payment(payment_id: str, order_id: str, amount: int, email: str) -> str:
    """Create MoMo payment request"""

    if not all([MOMO_CONFIG["partner_code"], MOMO_CONFIG["api_key"]]):
        raise HTTPException(status_code=400, detail="MoMo not configured")

    # MoMo API integration would go here
    # For now, return placeholder
    return f"momo://payment?payment_id={payment_id}&amount={amount}"


# ============== Payment Status ==============

@router.get("/{payment_id}")
async def get_payment(payment_id: str):
    """Get payment details"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT payment_id, order_id, amount, currency, status,
               payment_method, customer_email, customer_name,
               checkout_url, qr_code, expires_at, created_at
        FROM payments WHERE payment_id = %s
    """, (payment_id,))

    result = cursor.fetchone()
    cursor.close()
    conn.close()

    if not result:
        raise HTTPException(status_code=404, detail="Payment not found")

    return {
        "payment_id": result[0],
        "order_id": result[1],
        "amount": result[2],
        "currency": result[3],
        "status": result[4],
        "payment_method": result[5],
        "customer_email": result[6],
        "customer_name": result[7],
        "checkout_url": result[8],
        "qr_code": result[9],
        "expires_at": str(result[10]),
        "created_at": str(result[11])
    }


@router.get("/order/{order_id}")
async def get_payment_by_order(order_id: str):
    """Get payment by order ID"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT payment_id, order_id, amount, currency, status,
               payment_method, customer_email, expires_at, created_at
        FROM payments WHERE order_id = %s ORDER BY created_at DESC LIMIT 1
    """, (order_id,))

    result = cursor.fetchone()
    cursor.close()
    conn.close()

    if not result:
        raise HTTPException(status_code=404, detail="Order not found")

    return {
        "payment_id": result[0],
        "order_id": result[1],
        "amount": result[2],
        "currency": result[3],
        "status": result[4],
        "payment_method": result[5],
        "customer_email": result[6],
        "expires_at": str(result[7]),
        "created_at": str(result[8])
    }


# ============== Webhook Handlers ==============

@router.post("/webhook/stripe")
async def stripe_webhook(payload: dict):
    """Handle Stripe webhook"""

    # In production, verify webhook signature using STRIPE_WEBHOOK_SECRET

    event_type = payload.get("type")
    data = payload.get("data", {}).get("object", {})

    payment_id = data.get("metadata", {}).get("payment_id")

    if not payment_id:
        return {"status": "ignored"}

    if event_type == "checkout.session.completed":
        await confirm_payment(payment_id, "completed", data.get("id"))
    elif event_type == "payment_intent.payment_failed":
        await confirm_payment(payment_id, "failed", data.get("id"))

    return {"status": "processed"}


@router.post("/webhook/vietqr")
async def vietqr_webhook(request: PaymentWebhookRequest):
    """Handle VietQR webhook"""

    await confirm_payment(request.payment_id, request.status, request.transaction_id)

    return {"status": "processed"}


@router.post("/webhook/momo")
async def momo_webhook(request: PaymentWebhookRequest):
    """Handle MoMo webhook"""

    await confirm_payment(request.payment_id, request.status, request.transaction_id)

    return {"status": "processed"}


async def confirm_payment(payment_id: str, status: str, transaction_id: str = None):
    """Confirm payment and update status"""

    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # Update payment status
    cursor.execute("""
        UPDATE payments
        SET status = %s, transaction_id = %s, updated_at = NOW()
        WHERE payment_id = %s
    """, (status, transaction_id, payment_id))

    # If completed, create subscription
    if status == "completed":
        cursor.execute("""
            SELECT customer_email, amount, payment_method
            FROM payments WHERE payment_id = %s
        """, (payment_id,))

        result = cursor.fetchone()
        if result:
            customer_email, amount, payment_method = result

            # Determine plan from amount
            plan = None
            for plan_name, tier in PRICING_TIERS.items():
                if tier["price_vnd"] == amount:
                    plan = plan_name
                    break

            if plan:
                # Create subscription
                subscription_id = f"SUB-{uuid.uuid4().hex[:10].upper()}"
                expires_at = datetime.now() + timedelta(days=30)

                cursor.execute("""
                    INSERT INTO subscriptions (
                        subscription_id, customer_email, plan,
                        status, started_at, expires_at, payment_id
                    ) VALUES (
                        %s, %s, %s,
                        %s, NOW(), %s, %s
                    )
                """, (subscription_id, customer_email, plan, "active", expires_at, payment_id))

            # Create revenue transaction for tracking
            try:
                import uuid as uuid_module
                txn_id = f"TXN-{uuid_module.uuid4().hex[:12].upper()}"

                # Determine location based on email domain
                latitude, longitude = 10.8231, 106.6297  # Default: Ho Chi Minh
                location = "Ho Chi Minh City"
                if customer_email:
                    email_lower = customer_email.lower()
                    if any(d in email_lower for d in ['@gmail', '@yahoo', '@hotmail', '@outlook']):
                        location = "Vietnam"
                        latitude, longitude = 10.8231, 106.6297
                    elif ".vn" in email_lower:
                        location = "Vietnam"
                        latitude, longitude = 21.0285, 105.8542  # Hanoi
                    else:
                        location = "International"
                        latitude, longitude = 37.0902, -95.7129  # US

                cursor.execute("""
                    INSERT INTO revenue_transactions (
                        transaction_id, payment_id, order_id,
                        amount, currency,
                        customer_email, customer_name, customer_location,
                        payment_method, transaction_ref,
                        status, latitude, longitude,
                        transaction_date, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE, NOW()
                    )
                    ON CONFLICT (transaction_id) DO NOTHING
                """, (
                    txn_id, payment_id, payment_id,
                    amount, "VND",
                    customer_email, customer_email.split('@')[0], location,
                    payment_method, transaction_id,
                    "completed", latitude, longitude
                ))
            except Exception as e:
                print(f"Revenue tracking error: {e}")

    conn.commit()
    cursor.close()
    conn.close()


# ============== Payment Methods Status ==============

@router.get("/methods")
async def get_payment_methods_status():
    """Get status of all payment methods"""

    return {
        "stripe": {
            "enabled": STRIPE_CONFIG["enabled"],
            "configured": bool(STRIPE_CONFIG["secret_key"]),
            "test_mode": STRIPE_CONFIG["test_mode"],
            "description": "International cards (Visa, Mastercard, JCB)"
        },
        "vietqr": {
            "enabled": VIETQR_CONFIG["enabled"],
            "configured": all([VIETQR_CONFIG["bank_name"], VIETQR_CONFIG["account_number"], VIETQR_CONFIG["account_name"]]),
            "description": "Vietnamese bank QR payments",
            "note": "Awaiting bank details from Tùng"
        },
        "momo": {
            "enabled": MOMO_CONFIG["enabled"],
            "configured": bool(MOMO_CONFIG["api_key"]),
            "description": "MoMo e-wallet"
        },
        "bank_transfer": {
            "enabled": True,
            "configured": True,
            "description": "Direct bank transfer"
        }
    }


if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    uvicorn.run(app, host="0.0.0.0", port=8000)