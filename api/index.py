import os
import sys
import json
import datetime
import urllib.parse
import hashlib
import hmac
import base64
import time
import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Lazy psycopg2 import to avoid cold start issues
psycopg2 = None

def get_psycopg2():
    global psycopg2
    if psycopg2 is None:
        import psycopg2 as _psycopg2
        psycopg2 = _psycopg2
    return psycopg2

# Import environment before importing main
from fastapi import FastAPI, HTTPException, Depends, status
from starlette.requests import Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Import auth router
from auth import router as auth_router

# Import rate limiting
try:
    from rate_limit import RateLimitMiddleware
    HAS_RATE_LIMIT = True
except ImportError:
    HAS_RATE_LIMIT = False

# Get environment variables
def _get_db_config():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        import urllib.parse
        parsed = urllib.parse.urlparse(db_url)
        return {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 5432,
            "database": parsed.path.lstrip("/") or "neondb",
            "user": parsed.username or "neondb_owner",
            "password": parsed.password or "",
        }
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "database": os.getenv("DB_NAME", "neondb"),
        "user": os.getenv("DB_USER", "neondb_owner"),
        "password": os.getenv("DB_PASSWORD", ""),
    }

DB_CONFIG = _get_db_config()

# Auth / JWT Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "aicity_secret_key_change_in_production_2024")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30
security = HTTPBearer(auto_error=False)

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

# Add rate limiting middleware
if HAS_RATE_LIMIT:
    app.add_middleware(RateLimitMiddleware)

# Include auth router
app.include_router(auth_router)

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


# ============== Auth Models ==============

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None
    role: str = "user"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserResponse"


class UserResponse(BaseModel):
    id: int | str
    email: str
    name: str
    role: str
    created_at: Optional[str] = None
    last_login: Optional[str] = None


class TokenRefresh(BaseModel):
    refresh_token: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


# ============== Auth Utilities ==============

def hash_password(password: str) -> str:
    salt = SECRET_KEY[:16]
    combined = salt + password + SECRET_KEY
    return hashlib.sha256(combined.encode()).hexdigest() + ":" + salt


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        _, salt = stored_hash.split(":")
        combined = salt + password + SECRET_KEY
        computed = hashlib.sha256(combined.encode()).hexdigest() + ":" + salt
        return hmac.compare_digest(computed, stored_hash)
    except Exception:
        return False


def create_token(user_id: int, email: str, role: str, token_type: str = "access") -> str:
    now = int(time.time())
    exp = now + (ACCESS_TOKEN_EXPIRE_MINUTES * 60) if token_type == "access" else now + (REFRESH_TOKEN_EXPIRE_DAYS * 86400)
    payload = {"user_id": user_id, "email": email, "role": role, "type": token_type, "iat": now, "exp": exp}
    header = {"alg": ALGORITHM, "typ": "JWT"}
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = hmac.new(SECRET_KEY.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def decode_token(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise HTTPException(status_code=401, detail="Invalid token format")
        header_b64, payload_b64, signature_b64 = parts
        expected_sig = hmac.new(SECRET_KEY.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode().rstrip("=")
        if not hmac.compare_digest(signature_b64, expected_sig_b64):
            raise HTTPException(status_code=401, detail="Invalid token signature")
        padding = 4 - len(payload_b64) % 4
        if padding < 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if payload.get("exp", 0) < int(time.time()):
            raise HTTPException(status_code=401, detail="Token expired")
        return payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token decode error: {str(e)}")


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})
    token_data = decode_token(credentials.credentials)
    if token_data.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type - access token required")
    return token_data


async def get_current_user_optional(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[dict]:
    if not credentials:
        return None
    try:
        token_data = decode_token(credentials.credentials)
        if token_data.get("type") == "access":
            return token_data
    except HTTPException:
        pass
    return None


def get_auth_db_conn():
    try:
        return get_psycopg2().connect(**DB_CONFIG)
    except get_psycopg2().OperationalError:
        return None


def init_users_table():
    conn = get_auth_db_conn()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                role VARCHAR(50) DEFAULT 'user',
                phone VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        """)
        conn.commit()
        cursor.close()
    except Exception:
        pass
    finally:
        conn.close()


# Initialize users table on startup (non-blocking, deferred)
# init_users_table() is called lazily on first auth endpoint call


class CheckoutRequest(BaseModel):
    plan_id: str
    payment_method: str = "vietqr"
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None


class DemoBookingRequest(BaseModel):
    name: str
    company: str
    email: str
    phone: str
    employees: Optional[str] = None
    message: Optional[str] = None
    timestamp: Optional[str] = None

@app.get("/")
async def root():
    return {"status": "running", "service": "AI City API"}

@app.get("/health", response_model=HealthResponse)
async def health():
    pg_status = "unavailable"
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
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
        conn = get_psycopg2().connect(**DB_CONFIG)
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
async def analytics_overview(current_user: dict = Depends(get_current_user)):
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
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


@app.get("/analytics/revenue")
async def analytics_revenue():
    """Get revenue tracking data from converted leads"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cur = conn.cursor()

        # Get revenue from converted leads using metadata JSONB field
        cur.execute("""
            SELECT COALESCE(SUM(CAST(metadata->>'revenue' AS numeric)), 0) as total
            FROM leads
            WHERE status = 'converted'
        """)
        result = cur.fetchone()

        cur.close()
        conn.close()

        return {
            "total_revenue": float(result[0] or 0),
            "currency": "USD",
            "period": "all_time"
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


# ============== Globe AI City Data Layer ==============

from typing import Optional

class ProvinceResponse(BaseModel):
    id: str
    name: str
    name_vi: Optional[str]
    industry: Optional[dict]
    region: Optional[dict]
    tier: Optional[dict]
    total_companies: int
    total_revenue: float
    node_size: str
    node_color: str
    is_active: bool


@app.get("/globe/industries")
async def globe_industries():
    """List Globe industries"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, code, name, name_vi, icon, color, description FROM globe_industries WHERE is_active = true ORDER BY name")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{"id": str(r[0]), "code": r[1], "name": r[2], "name_vi": r[3], "icon": r[4], "color": r[5], "description": r[6]} for r in rows]
    except Exception as e:
        return {"error": str(e)}


@app.get("/globe/regions")
async def globe_regions():
    """List Globe regions"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, code, name, name_vi, country, latitude, longitude, timezone FROM globe_regions WHERE is_active = true ORDER BY country, name")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{"id": str(r[0]), "code": r[1], "name": r[2], "name_vi": r[3], "country": r[4],
                 "latitude": float(r[5]) if r[5] else None, "longitude": float(r[6]) if r[6] else None, "timezone": r[7]} for r in rows]
    except Exception as e:
        return {"error": str(e)}


@app.get("/globe/tiers")
async def globe_tiers():
    """List Globe tiers"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, code, name, name_vi, description, min_employees, max_employees FROM globe_tiers ORDER BY min_employees")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{"id": str(r[0]), "code": r[1], "name": r[2], "name_vi": r[3], "description": r[4],
                 "min_employees": r[5], "max_employees": r[6]} for r in rows]
    except Exception as e:
        return {"error": str(e)}


@app.get("/globe/provinces")
async def globe_provinces(industry_id: Optional[str] = None, region_id: Optional[str] = None, tier_id: Optional[str] = None, limit: int = 100):
    """List Globe provinces"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = """
            SELECT p.id, p.name, p.name_vi, p.description, p.industry_id, p.region_id, p.tier_id,
                   p.node_size, p.node_color, p.total_companies, p.total_revenue, p.total_leads, p.is_active,
                   i.name as industry_name, r.name as region_name, r.latitude, r.longitude, t.name as tier_name
            FROM globe_provinces p
            LEFT JOIN globe_industries i ON p.industry_id = i.id
            LEFT JOIN globe_regions r ON p.region_id = r.id
            LEFT JOIN globe_tiers t ON p.tier_id = t.id
            WHERE p.is_active = true
        """
        params = []
        if industry_id:
            query += " AND p.industry_id = %s"
            params.append(industry_id)
        if region_id:
            query += " AND p.region_id = %s"
            params.append(region_id)
        if tier_id:
            query += " AND p.tier_id = %s"
            params.append(tier_id)
        query += " ORDER BY p.total_companies DESC LIMIT %s"
        params.append(limit)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{
            "id": str(r[0]), "name": r[1], "name_vi": r[2], "description": r[3],
            "industry_id": str(r[4]) if r[4] else None, "region_id": str(r[5]) if r[5] else None, "tier_id": str(r[6]) if r[6] else None,
            "node_size": r[7], "node_color": r[8], "total_companies": r[9] or 0, "total_revenue": float(r[10] or 0),
            "total_leads": r[11] or 0, "is_active": r[12],
            "industry": {"name": r[13]} if r[13] else None,
            "region": {"name": r[14], "latitude": float(r[15]) if r[15] else None, "longitude": float(r[16]) if r[16] else None} if r[14] else None,
            "tier": {"name": r[17]} if r[17] else None,
        } for r in rows]
    except Exception as e:
        return {"error": str(e)}


@app.get("/globe/provinces/stats")
async def globe_province_stats():
    """Get province statistics"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(total_companies), SUM(total_revenue), SUM(total_leads) FROM globe_provinces WHERE is_active = true")
        row = cursor.fetchone()
        cursor.execute("""
            SELECT i.name, COUNT(p.id), COALESCE(SUM(p.total_companies), 0)
            FROM globe_industries i LEFT JOIN globe_provinces p ON p.industry_id = i.id AND p.is_active = true
            GROUP BY i.id, i.name ORDER BY SUM(p.total_companies) DESC NULLS LAST
        """)
        by_industry = [{"name": r[0], "province_count": r[1], "companies": int(r[2])} for r in cursor.fetchall()]
        cursor.execute("""
            SELECT r.name, COUNT(p.id), COALESCE(SUM(p.total_companies), 0)
            FROM globe_regions r LEFT JOIN globe_provinces p ON p.region_id = r.id AND p.is_active = true
            GROUP BY r.id, r.name ORDER BY SUM(p.total_companies) DESC NULLS LAST
        """)
        by_region = [{"name": r[0], "province_count": r[1], "companies": int(r[2])} for r in cursor.fetchall()]
        cursor.close()
        conn.close()
        return {"total_provinces": row[0] or 0, "total_companies": row[1] or 0,
                "total_revenue": float(row[2] or 0), "total_leads": row[3] or 0,
                "by_industry": by_industry, "by_region": by_region}
    except Exception as e:
        return {"error": str(e)}


@app.get("/globe/chains")
async def globe_chains():
    """List production chains"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, chain_code, name, name_vi, description, stages FROM globe_chains WHERE is_active = true")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{"id": str(r[0]), "chain_code": r[1], "name": r[2], "name_vi": r[3],
                 "description": r[4], "stages": r[5] if isinstance(r[5], list) else []} for r in rows]
    except Exception as e:
        return {"error": str(e)}


@app.get("/globe/chains/pipeline")
async def globe_pipeline_stats():
    """Get pipeline funnel statistics"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT current_stage, COUNT(*), COALESCE(SUM(pipeline_value), 0), COALESCE(AVG(probability), 0)
            FROM globe_chain_instances GROUP BY current_stage ORDER BY MIN(stage_order)
        """)
        rows = cursor.fetchall()
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(actual_value), 0) FROM globe_chain_instances")
        totals = cursor.fetchone()
        cursor.close()
        conn.close()
        return {"by_stage": [{"stage": r[0], "count": r[1], "total_value": float(r[2]),
                              "avg_probability": float(r[3])} for r in rows],
                "totals": {"total_instances": totals[0] or 0, "realized_value": float(totals[1] or 0)}}
    except Exception as e:
        return {"error": str(e)}


@app.get("/globe/discovery/tree")
async def globe_discovery_tree(category: Optional[str] = None):
    """Get discovery tree"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = """
            SELECT id, node_code, category, parent_code, name, name_vi, description, node_type, keywords, icon, color, selection_count
            FROM globe_discovery_nodes WHERE is_active = true
        """
        params = []
        if category:
            query += " AND category = %s"
            params.append(category)
        query += " ORDER BY category, parent_code NULLS FIRST, node_type, name"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        nodes = {str(r[0]): {"id": str(r[0]), "node_code": r[1], "category": r[2], "parent_code": r[3],
                              "name": r[4], "name_vi": r[5], "description": r[6], "node_type": r[7],
                              "keywords": r[8] if isinstance(r[8], list) else [], "icon": r[9],
                              "color": r[10], "selection_count": r[11] or 0, "children": []} for r in rows}
        tree = []
        for node in nodes.values():
            if node["parent_code"]:
                parent = next((n for n in nodes.values() if n["node_code"] == node["parent_code"]), None)
                if parent:
                    parent["children"].append(node)
            else:
                tree.append(node)
        return {"categories": tree} if not category else tree
    except Exception as e:
        return {"error": str(e)}


@app.get("/globe/dashboard")
async def globe_dashboard():
    """Globe overview dashboard"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM globe_industries WHERE is_active = true")
        ind_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM globe_regions WHERE is_active = true")
        reg_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM globe_discovery_nodes WHERE is_active = true")
        node_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM globe_pipelines WHERE is_active = true")
        pipe_count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return {"status": "operational", "counts": {"industries": ind_count, "regions": reg_count,
                "discovery_nodes": node_count, "pipelines": pipe_count}}
    except Exception as e:
        return {"error": str(e)}


@app.get("/globe/status")
async def globe_status():
    """Globe data layer status"""
    return {
        "status": "operational",
        "endpoints": ["/globe/industries", "/globe/regions", "/globe/tiers",
                      "/globe/provinces", "/globe/chains", "/globe/chains/pipeline",
                      "/globe/discovery/tree", "/globe/dashboard", "/globe/seed"],
        "note": "Schema migration (globe_schema.sql) needed to enable full functionality"
    }


@app.post("/globe/seed")
async def globe_seed():
    """Seed provinces: Industry x Region x Tier combinations"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Check if provinces already exist
        cursor.execute("SELECT COUNT(*) FROM globe_provinces")
        existing = cursor.fetchone()[0]
        if existing > 0:
            cursor.close()
            conn.close()
            return {"message": f"Provinces already seeded ({existing} existing)", "seeded": 0}

        # Get all active industries, regions, tiers
        cursor.execute("SELECT id, code, name, color FROM globe_industries WHERE is_active = true")
        industries = cursor.fetchall()
        cursor.execute("SELECT id, code, name, latitude, longitude FROM globe_regions WHERE is_active = true")
        regions = cursor.fetchall()
        cursor.execute("SELECT id, code, name FROM globe_tiers ORDER BY min_employees")
        tiers = cursor.fetchall()

        seeded = 0
        for ind in industries:
            for reg in regions:
                for tier in tiers:
                    size_map = {"startup": "small", "sme": "medium", "enterprise": "large"}
                    node_size = size_map.get(tier[1], "medium")
                    name = f"{ind[2]} - {reg[2]} - {tier[2]}"
                    desc = f"{ind[2]} {reg[2]} market for {tier[2]} companies"
                    cursor.execute("""
                        INSERT INTO globe_provinces
                        (name, name_vi, description, industry_id, region_id, tier_id, node_size, node_color,
                         total_companies, total_revenue, total_leads)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, 0, 0)
                    """, (name, name, desc, ind[0], reg[0], tier[0], node_size, ind[3]))
                    seeded += 1

        conn.commit()
        cursor.close()
        conn.close()
        return {
            "message": f"Seeded {seeded} provinces",
            "seeded": seeded,
            "combinations": f"{len(industries)} industries × {len(regions)} regions × {len(tiers)} tiers"
        }
    except Exception as e:
        return {"error": str(e)}


# ============== Auth Endpoints ==============

@app.post("/api/auth/register", response_model=TokenResponse, summary="Register new user")
async def register(user: UserRegister):
    """Create a new user account and return JWT tokens."""
    init_users_table()  # Ensure users table exists
    conn = get_auth_db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s", (user.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")
        password_hash = hash_password(user.password)
        cursor.execute(
            "INSERT INTO users (email, password_hash, name, role, phone) VALUES (%s, %s, %s, %s, %s) RETURNING id, created_at",
            (user.email, password_hash, user.name, user.role, user.phone)
        )
        user_id, created_at = cursor.fetchone()
        conn.commit()
        access_token = create_token(user_id, user.email, user.role, "access")
        refresh_token = create_token(user_id, user.email, user.role, "refresh")
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse(id=user_id, email=user.email, name=user.name, role=user.role, created_at=str(created_at))
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration error: {str(e)}")
    finally:
        conn.close()


@app.post("/api/auth/login", response_model=TokenResponse, summary="User login")
async def login(user: UserLogin):
    """Authenticate user and return JWT tokens."""
    conn = get_auth_db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, password_hash, name, role, created_at, last_login, is_active FROM users WHERE email = %s", (user.email,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        user_id, email, password_hash, name, role, created_at, last_login, is_active = row
        if not is_active:
            raise HTTPException(status_code=401, detail="Account is deactivated")
        if not verify_password(user.password, password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s", (user_id,))
        conn.commit()
        access_token = create_token(user_id, email, role, "access")
        refresh_token = create_token(user_id, email, role, "refresh")
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse(id=user_id, email=email, name=name, role=role, created_at=str(created_at), last_login=str(last_login) if last_login else None)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login error: {str(e)}")
    finally:
        conn.close()


@app.post("/api/auth/refresh", summary="Refresh access token")
async def refresh_token(request: TokenRefresh):
    """Exchange a valid refresh token for a new access token."""
    try:
        token_data = decode_token(request.refresh_token)
        if token_data.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type - refresh token required")
        return {
            "access_token": create_token(token_data["user_id"], token_data["email"], token_data["role"], "access"),
            "refresh_token": create_token(token_data["user_id"], token_data["email"], token_data["role"], "refresh"),
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token refresh error: {str(e)}")


@app.get("/api/auth/me", response_model=UserResponse, summary="Get current user")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get the authenticated user's profile."""
    conn = get_auth_db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, name, role, created_at, last_login FROM users WHERE id = %s", (current_user["user_id"],))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return UserResponse(id=row[0], email=row[1], name=row[2], role=row[3], created_at=str(row[4]), last_login=str(row[5]) if row[5] else None)
    finally:
        conn.close()


@app.post("/api/auth/logout", summary="Logout user")
async def logout(current_user: dict = Depends(get_current_user)):
    """Logout the current user (client should discard tokens)."""
    return {"message": "Logged out successfully", "user_id": current_user["user_id"]}


@app.post("/api/auth/change-password", summary="Change password")
async def change_password(request: PasswordChange, current_user: dict = Depends(get_current_user)):
    """Change the current user's password."""
    conn = get_auth_db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE id = %s", (current_user["user_id"],))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        if not verify_password(request.current_password, row[0]):
            raise HTTPException(status_code=401, detail="Current password is incorrect")
        new_hash = hash_password(request.new_password)
        cursor.execute("UPDATE users SET password_hash = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (new_hash, current_user["user_id"]))
        conn.commit()
        return {"message": "Password changed successfully"}
    finally:
        conn.close()


@app.post("/api/auth/password-reset-request", summary="Request password reset")
async def password_reset_request(email: str):
    """Request password reset (email integration pending)."""
    return {"message": "If the email exists, a password reset link has been sent", "email": email, "note": "Email integration pending"}


# Demo booking endpoint
DEMO_SALES_EMAIL = "thanhtungtran364@gmail.com"
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")


@app.post("/api/demo")
async def create_demo_booking(booking: DemoBookingRequest):
    """Capture demo booking form submissions and notify sales team."""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cursor = conn.cursor()

        metadata = json.dumps({
            "company": booking.company,
            "employees": booking.employees,
            "message": booking.message,
            "timestamp": booking.timestamp,
        })

        cursor.execute("""
            INSERT INTO leads (name, email, phone, source, status, metadata, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            RETURNING id
        """, (
            booking.name,
            booking.email,
            booking.phone,
            "demo_booking",
            "new",
            metadata,
        ))

        result = cursor.fetchone()
        lead_id = result[0]
        conn.commit()
        cursor.close()
        conn.close()

        # Sanitize user inputs to prevent email header injection (OWASP)
        def sanitize_for_email(value: str) -> str:
            if not value:
                return ""
            return value.replace("\r", "").replace("\n", "")[:200]

        safe_name = sanitize_for_email(booking.name or "")
        safe_company = sanitize_for_email(booking.company or "")

        # Send email notification via Resend
        if RESEND_API_KEY:
            try:
                email_body = f"""New Demo Booking Request

Name: {safe_name}
Company: {safe_company}
Email: {booking.email}
Phone: {booking.phone}
Employees: {booking.employees or "N/A"}
Message: {(booking.message or "").replace("\r", "").replace("\n", " ")[:500]}
Submitted: {booking.timestamp or "N/A"}

---
AI City Backend - Lead ID: {lead_id}
"""
                resend_resp = requests.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {RESEND_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": "AI City <onboarding@resend.dev>",
                        "to": DEMO_SALES_EMAIL,
                        "subject": f"New Demo Booking: {safe_name} from {safe_company}",
                        "text": email_body,
                    },
                    timeout=10,
                )
                if resend_resp.status_code not in (200, 201):
                    pass  # Non-fatal, lead is captured
            except Exception:
                pass  # Non-fatal

        return {
            "success": True,
            "message": "Demo booking received. Our team will contact you shortly.",
            "lead_id": lead_id,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# Agents endpoints (Paperclip API integration)
# =============================================================================

PAPERCLIP_API_URL = os.getenv("PAPERCLIP_API_URL", "https://api.paperclip.ai")


@app.get("/agents")
async def get_agents():
    """Get all agents from Paperclip."""
    try:
        paperclip_key = os.getenv("PAPERCLIP_API_KEY")
        if not paperclip_key:
            return {"error": "Paperclip API not configured", "agents": []}

        resp = requests.get(
            f"{PAPERCLIP_API_URL}/api/companies/{DB_CONFIG.get('company_id', os.getenv('COMPANY_ID', ''))}/agents",
            headers={
                "Authorization": f"Bearer {paperclip_key}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )

        if resp.status_code == 200:
            return {"agents": resp.json()}
        return {"error": f"Paperclip API error: {resp.status_code}", "agents": []}
    except Exception as e:
        return {"error": str(e), "agents": []}


@app.get("/agents/usage")
async def get_agent_usage():
    """Get agent usage statistics from Paperclip."""
    try:
        paperclip_key = os.getenv("PAPERCLIP_API_KEY")
        company_id = os.getenv("COMPANY_ID", "")

        if not paperclip_key or not company_id:
            return {
                "total_runs": 0,
                "total_tokens": 0,
                "active_agents": 0,
                "note": "Paperclip API not configured"
            }

        # Get agents
        agents_resp = requests.get(
            f"{PAPERCLIP_API_URL}/api/companies/{company_id}/agents",
            headers={"Authorization": f"Bearer {paperclip_key}", "Content-Type": "application/json"},
            timeout=10,
        )

        if agents_resp.status_code != 200:
            return {"error": f"Failed to fetch agents: {agents_resp.status_code}"}

        agents = agents_resp.json()
        active_agents = [a for a in agents if a.get("status") == "running"]

        # Get dashboard/run stats
        dash_resp = requests.get(
            f"{PAPERCLIP_API_URL}/api/companies/{company_id}/dashboard",
            headers={"Authorization": f"Bearer {paperclip_key}", "Content-Type": "application/json"},
            timeout=10,
        )

        dashboard = dash_resp.json() if dash_resp.status_code == 200 else {}

        return {
            "total_agents": len(agents),
            "active_agents": len(active_agents),
            "total_runs": dashboard.get("total_runs", 0),
            "runs_today": dashboard.get("runs_today", 0),
            "runs_this_week": dashboard.get("runs_this_week", 0),
        }
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# Analytics endpoints
# =============================================================================

@app.get("/analytics/conversions")
async def get_conversion_metrics():
    """Get conversion funnel data."""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted
            FROM leads
        """)
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        total = result[0] or 0
        converted = result[1] or 0
        rate = (converted / total * 100) if total > 0 else 0

        return {
            "total_leads": total,
            "converted": converted,
            "conversion_rate": round(rate, 2),
            "period": "all_time"
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/analytics/revenue")
async def get_revenue_metrics():
    """Get revenue tracking data."""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Lead revenue from converted leads (revenue stored in metadata JSONB)
        cursor.execute("""
            SELECT COALESCE(SUM(CAST(metadata->>'revenue' AS numeric)), 0) as total
            FROM leads
            WHERE status = 'converted'
        """)
        result = cursor.fetchone()

        # Subscription revenue (fallback to 0 if table/column doesn't exist)
        try:
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM subscriptions
                WHERE status = 'active'
            """)
            sub_result = cursor.fetchone()
            subscription_revenue = float(sub_result[0] or 0) if sub_result else 0
        except Exception:
            subscription_revenue = 0

        cursor.close()
        conn.close()

        return {
            "lead_revenue": float(result[0] or 0),
            "subscription_revenue": subscription_revenue,
            "total_revenue": float(result[0] or 0) + subscription_revenue,
            "period": "all_time"
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/leads/analytics/conversion")
async def get_lead_analytics():
    """Get lead conversion analytics by source and status."""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT source,
                   COUNT(*) as total,
                   SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted
            FROM leads
            GROUP BY source
        """)
        by_source = [
            {"source": r[0], "total": r[1], "converted": r[2], "rate": round(r[2]/r[1]*100, 2) if r[1] > 0 else 0}
            for r in cursor.fetchall()
        ]

        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM leads
            GROUP BY status
        """)
        by_status = [{"status": r[0], "count": r[1]} for r in cursor.fetchall()]

        cursor.close()
        conn.close()

        return {
            "by_source": by_source,
            "by_status": by_status
        }
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# /api/ prefixed aliases (AIC-590 - CEO Priority)
# =============================================================================

@app.get("/api/agents")
async def api_get_agents():
    """Get all agents - /api/agents alias."""
    return await get_agents()


@app.get("/api/agents/usage")
async def api_get_agents_usage():
    """Get agent usage - /api/agents/usage alias."""
    return await get_agent_usage()


@app.get("/api/analytics/conversions")
async def api_get_conversions():
    """Get conversions - /api/analytics/conversions alias."""
    return await get_conversion_metrics()


@app.get("/api/analytics/revenue")
async def api_get_revenue():
    """Get revenue - /api/analytics/revenue alias."""
    return await get_revenue_metrics()


@app.get("/api/leads/analytics/conversion")
async def api_get_lead_analytics():
    """Get lead analytics - /api/leads/analytics/conversion alias."""
    return await get_lead_analytics()


# =============================================================================
# AIC-619: Missing /api/ prefixed routes for frontend
# =============================================================================

class LeadCreateRequest(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    source: str = "api"
    status: str = "new"
    metadata: Optional[dict] = {}


class LeadUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict] = None


class SearchRequestModel(BaseModel):
    query: str
    limit: int = 5


class ReportGenerateRequest(BaseModel):
    report_type: str = "weekly"
    period: Optional[str] = None


# ─── /api/leads ───────────────────────────────────────────────────────────────

@app.post("/api/leads")
async def api_create_lead(lead: LeadCreateRequest):
    """Create a new lead - /api/leads (POST)"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO leads (name, email, phone, source, status, metadata, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            RETURNING id, name, email, phone, source, status, metadata, created_at, updated_at
        """, (lead.name, lead.email, lead.phone, lead.source, lead.status, json.dumps(lead.metadata or {})))
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return {
            "id": row[0], "name": row[1], "email": row[2], "phone": row[3],
            "source": row[4], "status": row[5], "metadata": row[6],
            "created_at": str(row[7]), "updated_at": str(row[8])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/leads")
async def api_list_leads(status: Optional[str] = None, limit: int = 50):
    """List leads - /api/leads (GET)"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT id, name, email, phone, source, status, metadata, created_at, updated_at FROM leads WHERE status = %s ORDER BY created_at DESC LIMIT %s",
                (status, limit)
            )
        else:
            cur.execute("SELECT id, name, email, phone, source, status, metadata, created_at, updated_at FROM leads ORDER BY created_at DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {"id": r[0], "name": r[1], "email": r[2], "phone": r[3],
             "source": r[4], "status": r[5], "metadata": r[6],
             "created_at": str(r[7]), "updated_at": str(r[8])}
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/leads/{lead_id}")
async def api_get_lead(lead_id: int):
    """Get a lead by ID - /api/leads/{id}"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT id, name, email, phone, source, status, metadata, created_at, updated_at FROM leads WHERE id = %s", (lead_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Lead not found")
        return {
            "id": row[0], "name": row[1], "email": row[2], "phone": row[3],
            "source": row[4], "status": row[5], "metadata": row[6],
            "created_at": str(row[7]), "updated_at": str(row[8])
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/leads/{lead_id}")
async def api_update_lead(lead_id: int, lead: LeadUpdateRequest):
    """Update a lead - /api/leads/{id} (PATCH)"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cur = conn.cursor()
        fields = []
        values = []
        if lead.name is not None:
            fields.append("name = %s"); values.append(lead.name)
        if lead.email is not None:
            fields.append("email = %s"); values.append(lead.email)
        if lead.phone is not None:
            fields.append("phone = %s"); values.append(lead.phone)
        if lead.source is not None:
            fields.append("source = %s"); values.append(lead.source)
        if lead.status is not None:
            fields.append("status = %s"); values.append(lead.status)
        if lead.metadata is not None:
            fields.append("metadata = %s"); values.append(json.dumps(lead.metadata))
        if not fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        fields.append("updated_at = NOW()")
        values.append(lead_id)
        query = f"UPDATE leads SET {', '.join(fields)} WHERE id = %s RETURNING id, name, email, phone, source, status, metadata, created_at, updated_at"
        cur.execute(query, values)
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Lead not found")
        return {
            "id": row[0], "name": row[1], "email": row[2], "phone": row[3],
            "source": row[4], "status": row[5], "metadata": row[6],
            "created_at": str(row[7]), "updated_at": str(row[8])
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── /api/search ──────────────────────────────────────────────────────────────

@app.post("/api/search")
async def api_search(req: SearchRequestModel):
    """Semantic search - /api/search (POST)"""
    try:
        OLLAMA_URL_INDEX = os.getenv("OLLAMA_URL", "http://localhost:11434")
        QDRANT_URL_INDEX = os.getenv("QDRANT_URL", "http://localhost:6333")
        # Get embedding from Ollama
        emb_resp = requests.post(
            f"{OLLAMA_URL_INDEX}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": req.query},
            timeout=10
        )
        if emb_resp.status_code != 200:
            return {"error": "Embedding service unavailable", "results": []}
        embedding = emb_resp.json().get("embedding", [])
        if not embedding:
            return {"error": "No embedding returned", "results": []}
        # Search Qdrant
        qdrant_resp = requests.post(
            f"{QDRANT_URL_INDEX}/collections/ai_city_embeddings/points/search",
            json={
                "vector": embedding,
                "limit": req.limit,
                "with_payload": True
            },
            timeout=10
        )
        if qdrant_resp.status_code != 200:
            return {"error": "Vector DB unavailable", "results": []}
        results = qdrant_resp.json()
        return {"results": [{"id": r["id"], "score": r["score"], "payload": r.get("payload", {})} for r in results]}
    except Exception as e:
        return {"error": str(e), "results": []}


# ─── /api/reports ─────────────────────────────────────────────────────────────

@app.get("/api/reports")
async def api_list_reports(limit: int = 20):
    """List reports - /api/reports (GET)"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, description, type, created_at FROM reports
            ORDER BY created_at DESC LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{"id": r[0], "name": r[1], "description": r[2], "type": r[3], "created_at": str(r[4])} for r in rows]
    except Exception as e:
        return {"error": str(e), "reports": []}


@app.post("/api/reports/generate")
async def api_generate_report(req: ReportGenerateRequest):
    """Generate a report - /api/reports/generate (POST)"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cur = conn.cursor()
        # Get lead stats
        cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE status = 'qualified' OR status = 'converted'), COUNT(*) FILTER (WHERE status = 'converted') FROM leads")
        lead_row = cur.fetchone()
        # Get revenue stats
        cur.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'completed'")
        revenue = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'pending'")
        pending = cur.fetchone()[0]
        cur.close()
        conn.close()
        conversion_rate = (lead_row[2] / lead_row[0] * 100) if lead_row[0] > 0 else 0
        report = {
            "name": f"{req.report_type.title()} Report",
            "type": req.report_type,
            "description": f"Generated on {datetime.datetime.utcnow().isoformat()}",
            "data": {
                "total_leads": lead_row[0],
                "qualified_leads": lead_row[1],
                "converted_leads": lead_row[2],
                "conversion_rate": round(conversion_rate, 2),
                "total_revenue": float(revenue),
                "pending_revenue": float(pending)
            }
        }
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── /api/forecasting ────────────────────────────────────────────────────────

@app.get("/api/forecasting")
async def api_forecasting(period: str = "30d"):
    """Lead/revenue forecasting - /api/forecasting (GET)"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cur = conn.cursor()
        days = 30 if period == "30d" else 90 if period == "90d" else 7
        cur.execute(f"""
            SELECT DATE_TRUNC('week', created_at) as week,
                   COUNT(*) as total,
                   COUNT(*) FILTER (WHERE status = 'qualified') as qualified,
                   COUNT(*) FILTER (WHERE status = 'converted') as converted
            FROM leads WHERE created_at >= NOW() - INTERVAL '{days} days'
            GROUP BY DATE_TRUNC('week', created_at) ORDER BY week
        """)
        weekly = cur.fetchall()
        cur.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE status = 'qualified' OR status = 'converted'), COUNT(*) FILTER (WHERE status = 'converted') FROM leads")
        total_row = cur.fetchone()
        cur.close()
        conn.close()
        total_leads, total_qualified, total_converted = total_row
        conversion_rate = (total_converted / total_leads * 100) if total_leads > 0 else 0
        if len(weekly) >= 2:
            recent, prev = weekly[-1], weekly[-2]
            growth_rate = (recent[1] - prev[1]) / prev[1] if prev[1] > 0 else 0
            projected_30d = max(0, int(recent[1] * (1 + growth_rate)))
            projected_90d = max(0, int(recent[1] * (1 + growth_rate) ** 3))
        else:
            projected_30d = max(0, int(total_leads * 0.1))
            projected_90d = max(0, int(total_leads * 0.3))
        return {
            "period": period,
            "total_leads": total_leads,
            "total_qualified": total_qualified,
            "total_converted": total_converted,
            "conversion_rate": round(conversion_rate, 2),
            "weekly_trend": [{"week": str(w[0].date()), "total": w[1], "qualified": w[2], "converted": w[3]} for w in weekly],
            "projections": {"leads_30d": projected_30d, "leads_90d": projected_90d}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── /api/metrics ────────────────────────────────────────────────────────────

@app.get("/api/metrics")
async def api_metrics(type: str = "overview"):
    """Unified metrics endpoint - /api/metrics (GET)"""
    try:
        conn = get_psycopg2().connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FILTER (WHERE type = 'subscription'),
                   COUNT(*) FILTER (WHERE type = 'one_time'),
                   COALESCE(SUM(amount), 0) FILTER (WHERE status = 'completed'),
                   COUNT(*) FILTER (WHERE status = 'pending')
            FROM payments
        """)
        payments_row = cur.fetchone()
        cur.execute("""
            SELECT COUNT(*) FILTER (WHERE status = 'new'),
                   COUNT(*) FILTER (WHERE status = 'qualified'),
                   COUNT(*) FILTER (WHERE status = 'contacted'),
                   COUNT(*) FILTER (WHERE status = 'converted')
            FROM leads
        """)
        leads_row = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'active'")
        active_subs = cur.fetchone()[0]
        cur.close()
        conn.close()
        return {
            "subscriptions": payments_row[0] or 0,
            "one_time_payments": payments_row[1] or 0,
            "total_revenue": float(payments_row[2] or 0),
            "pending_payments": payments_row[3] or 0,
            "leads_new": leads_row[0] or 0,
            "leads_qualified": leads_row[1] or 0,
            "leads_contacted": leads_row[2] or 0,
            "leads_converted": leads_row[3] or 0,
            "active_subscriptions": active_subs or 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

