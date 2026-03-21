import os
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import environment before importing main
from fastapi import FastAPI, HTTPException
from starlette.requests import Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import psycopg2

# Get environment variables
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "neondb"),
    "user": os.getenv("DB_USER", "neondb_owner"),
    "password": os.getenv("DB_PASSWORD", ""),
}

# Stripe config
STRIPE_ENABLED = os.getenv("STRIPE_ENABLED", "false").lower() == "true"
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

app = FastAPI(title="AI City API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pricing plans (VND)
PRICING_PLANS = {
    "starter": {"name": "Starter Plan", "amount": 299000},
    "business": {"name": "Business Plan", "amount": 999000},
    "pro": {"name": "Pro Plan", "amount": 1490000},
}

class HealthResponse(BaseModel):
    ollama: str
    qdrant: str
    postgresql: str

class CheckoutRequest(BaseModel):
    plan_id: str
    payment_method: str = "stripe"
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None

@app.get("/")
async def root():
    return {"status": "running", "service": "AI City API"}

@app.get("/health", response_model=HealthResponse)
async def health():
    pg_status = "unavailable"
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.close()
        pg_status = "ok"
    except Exception as e:
        pg_status = f"error: {str(e)[:50]}"
    return HealthResponse(
        ollama="unavailable",
        qdrant="unavailable",
        postgresql=pg_status
    )

@app.get("/leads")
async def get_leads(limit: int = 50):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT id, name, email, phone, source, status, metadata, created_at, updated_at FROM leads ORDER BY created_at DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "id": r[0], "name": r[1], "email": r[2], "phone": r[3],
                "source": r[4], "status": r[5], "metadata": r[6],
                "created_at": str(r[7]), "updated_at": str(r[8])
            }
            for r in rows
        ]
    except Exception as e:
        return {"error": str(e)}

@app.get("/analytics/overview")
async def analytics_overview():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT status, COUNT(*) FROM leads GROUP BY status")
        leads_by_status = {r[0]: r[1] for r in cur.fetchall()}
        cur.close()
        conn.close()
        return {
            "matomo": {},
            "leads": leads_by_status,
            "period": "today"
        }
    except Exception as e:
        return {"error": str(e)}

# ============== Payment Endpoints ==============

@app.get("/payments/methods")
async def payments_methods():
    """Get available payment methods"""
    methods = []
    if STRIPE_ENABLED and STRIPE_SECRET_KEY:
        methods.append({"id": "stripe", "name": "Stripe", "enabled": True})
    # Legacy methods (always available)
    methods.extend([
        {"id": "vietqr", "name": "VietQR", "enabled": True},
        {"id": "momo", "name": "MoMo", "enabled": True},
        {"id": "zalopay", "name": "ZaloPay", "enabled": True},
    ])
    return {"payment_methods": methods, "stripe_enabled": STRIPE_ENABLED and bool(STRIPE_SECRET_KEY)}

@app.post("/payments/checkout")
async def payments_checkout(req: CheckoutRequest):
    """Create Stripe checkout session"""
    if not STRIPE_ENABLED or not STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=400,
            detail="Stripe is not configured. Set STRIPE_ENABLED=true and STRIPE_SECRET_KEY."
        )

    if req.plan_id not in PRICING_PLANS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid plan_id. Available: {', '.join(PRICING_PLANS.keys())}"
        )

    plan = PRICING_PLANS[req.plan_id]

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "vnd",
                    "product_data": {"name": plan["name"]},
                    "unit_amount": plan["amount"],
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url="https://aicity.vn/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://aicity.vn/pricing",
            customer_email=req.customer_email or None,
            metadata={"plan_id": req.plan_id, "plan_name": plan["name"]}
        )
        return {
            "checkout_id": session.id,
            "checkout_url": session.url,
            "plan_id": req.plan_id,
            "plan_name": plan["name"],
            "amount": plan["amount"],
            "currency": "VND",
            "status": "pending"
        }
    except ImportError:
        raise HTTPException(status_code=500, detail="Stripe package not installed")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/payments/webhook")
async def payments_webhook(request: Request):
    """Handle Stripe webhook"""
    if not STRIPE_ENABLED:
        raise HTTPException(status_code=400, detail="Stripe not enabled")

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        payload = await request.body()
        sig = request.headers.get("stripe-signature", "")
        try:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            print(f"Payment completed: {session.get('id', 'unknown')}")
        return {"received": True}
    except ImportError:
        raise HTTPException(status_code=500, detail="Stripe not installed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
