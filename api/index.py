import os
import sys
import json
import datetime
import urllib.parse

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

# VietQR Bank Transfer Config (Techcombank)
VIETQR_BANK_NAME = os.getenv("VIETQR_BANK_NAME", "Techcombank").strip()
VIETQR_BANK_BIN = os.getenv("VIETQR_BANK_BIN", "970403").strip()
VIETQR_ACCOUNT_NUMBER = os.getenv("VIETQR_ACCOUNT_NUMBER", "1903777779").strip()
VIETQR_ACCOUNT_NAME = os.getenv("VIETQR_ACCOUNT_NAME", "TRAN THANH TUNG").strip()

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
    "starter": {"name": "Starter", "amount": 299000, "credits": 5000, "period": "monthly"},
    "pro": {"name": "Pro", "amount": 799000, "credits": 15000, "period": "monthly"},
    "business": {"name": "Business", "amount": 1999000, "credits": 50000, "period": "monthly"},
}


# ============== VietQR Generation ==============

def normalize_vietnamese(text: str) -> str:
    """Convert Vietnamese diacritics to ASCII for QR code."""
    vietnamese_map = {
        'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
        'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
        'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'î': 'i',
        'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
        'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
        'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
        'đ': 'd',
    }
    return ''.join(vietnamese_map.get(c, c) for c in text)


def calculate_crc16(data: str) -> str:
    """Calculate CRC16 for VietQR string."""
    crc = 0xFFFF
    for byte in data.encode('ascii'):
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0x1021
            else:
                crc >>= 1
    return format(crc, '04X').upper()


def generate_vietqr_string(bank_bin: str, account_number: str, account_name: str, amount: int, purpose: str) -> str:
    """Generate VietQR BPCA format string."""
    fields = [
        ('00', '010212'),
        ('01', '12'),
        ('30', bank_bin),
        ('31', account_number),
        ('32', normalize_vietnamese(account_name).upper()),
        ('33', str(amount)),
        ('60', purpose[:50]),
    ]
    qr_string = ''
    for fid, fval in fields:
        qr_string += fid + str(len(fval)).zfill(2) + fval
    crc = calculate_crc16(qr_string)
    return qr_string + '81' + '04' + crc


def generate_vietqr_data(amount: int, purpose: str = "AI City Payment") -> dict:
    """Generate VietQR data: base64 image + raw QR string."""
    import base64

    qr_str = generate_vietqr_string(
        VIETQR_BANK_BIN,
        VIETQR_ACCOUNT_NUMBER,
        VIETQR_ACCOUNT_NAME,
        amount,
        purpose
    )
    # VietQR.io hosted QR image URL (no server-side generation needed)
    qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&format=png&data={urllib.parse.quote(qr_str)}"
    # VietQR.io direct image (recommended for banking apps)
    deep_link = f"https://img.vietqr.io/image/techcombank-1903777779-compact.png?amount={amount}&addInfo={urllib.parse.quote(purpose)}&accountName={urllib.parse.quote(VIETQR_ACCOUNT_NAME)}"

    return {"qr_code": qr_image_url, "qr_string": qr_str, "deep_link": deep_link}

class HealthResponse(BaseModel):
    ollama: str
    qdrant: str
    postgresql: str

class CheckoutRequest(BaseModel):
    plan_id: str
    payment_method: str = "vietqr"
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
    """Get available payment methods with VietQR bank details."""
    methods = []
    if STRIPE_ENABLED and STRIPE_SECRET_KEY:
        methods.append({"id": "stripe", "name": "Stripe", "description": "Credit/Debit Card (Visa, Mastercard)", "enabled": True})

    # VietQR always available with bank details
    methods.append({
        "id": "vietqr",
        "name": "VietQR",
        "description": "Quét mã QR bằng app ngân hàng Việt Nam",
        "enabled": True,
        "bank_details": {
            "bank_name": VIETQR_BANK_NAME,
            "bank_bin": VIETQR_BANK_BIN,
            "account_number": VIETQR_ACCOUNT_NUMBER,
            "account_name": VIETQR_ACCOUNT_NAME,
        }
    })

    return {
        "payment_methods": methods,
        "stripe_enabled": STRIPE_ENABLED and bool(STRIPE_SECRET_KEY),
        "vietqr_enabled": True
    }


@app.get("/payments/plans")
async def payments_plans():
    """Get subscription plans with VietQR codes."""
    plans = []
    for plan_id, plan in PRICING_PLANS.items():
        amount = plan["amount"]
        purpose = f"AI City {plan['name']}"
        qr_data = generate_vietqr_data(amount, purpose)
        plans.append({
            "id": plan_id,
            "name": plan["name"],
            "amount": amount,
            "amount_formatted": f"{amount:,} VND",
            "credits": plan.get("credits", 0),
            "period": plan.get("period", "monthly"),
            "qr_code": qr_data["qr_code"],
            "qr_string": qr_data["qr_string"],
            "bank_details": {
                "bank_name": VIETQR_BANK_NAME,
                "bank_bin": VIETQR_BANK_BIN,
                "account_number": VIETQR_ACCOUNT_NUMBER,
                "account_name": VIETQR_ACCOUNT_NAME,
            },
            "instructions": [
                "Quét mã QR bằng ứng dụng ngân hàng (Techcombank, Vietcombank, VietinBank...)",
                "Kiểm tra thông tin: " + VIETQR_ACCOUNT_NAME,
                f"Nhập số tiền: {amount:,} VND",
                f"Nội dung: {purpose}",
                "Hoàn tất thanh toán và chờ xác nhận trong 1-5 phút",
            ]
        })
    return {
        "plans": plans,
        "currency": "VND",
        "stripe_enabled": STRIPE_ENABLED and bool(STRIPE_SECRET_KEY),
        "stripe_mode": "live" if (STRIPE_ENABLED and "sk_live" in STRIPE_SECRET_KEY) else "test",
    }

@app.post("/payments/checkout")
async def payments_checkout(req: CheckoutRequest):
    """Create payment checkout session (Stripe or VietQR)"""
    if req.plan_id not in PRICING_PLANS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid plan_id. Available: {', '.join(PRICING_PLANS.keys())}"
        )

    plan = PRICING_PLANS[req.plan_id]
    amount = plan["amount"]
    purpose = f"AI City {plan['name']}"
    method = req.payment_method.lower()

    if method == "stripe":
        if not STRIPE_ENABLED or not STRIPE_SECRET_KEY:
            raise HTTPException(
                status_code=400,
                detail="Stripe is not configured. Use VietQR instead."
            )
        try:
            import stripe
            stripe.api_key = STRIPE_SECRET_KEY
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": "vnd",
                        "product_data": {"name": plan["name"]},
                        "unit_amount": amount,
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
                "payment_method": "stripe",
                "plan_id": req.plan_id,
                "plan_name": plan["name"],
                "amount": amount,
                "currency": "VND",
                "status": "pending"
            }
        except ImportError:
            raise HTTPException(status_code=500, detail="Stripe package not installed")
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    elif method == "vietqr":
        qr_data = generate_vietqr_data(amount, purpose)
        payment_id = f"AIC-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
        return {
            "payment_id": payment_id,
            "payment_method": "vietqr",
            "plan_id": req.plan_id,
            "plan_name": plan["name"],
            "amount": amount,
            "amount_formatted": f"{amount:,} VND",
            "currency": "VND",
            "status": "pending",
            "qr_code": qr_data["qr_code"],
            "qr_string": qr_data["qr_string"],
            "bank_details": {
                "bank_name": VIETQR_BANK_NAME,
                "bank_bin": VIETQR_BANK_BIN,
                "account_number": VIETQR_ACCOUNT_NUMBER,
                "account_name": VIETQR_ACCOUNT_NAME,
            },
            "instructions": [
                "Quet ma QR bang app ngan hang",
                f"Nhap so tien: {amount:,} VND",
                f"Noi dung chuyen khoan: {purpose}",
                "Hoan tat thanh toan",
            ],
            "note": "Thanh toan se duoc xac nhan trong 1-5 phut sau khi chuyen khoan"
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported payment method: {method}")

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
