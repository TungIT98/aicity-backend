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

# Import auth router
from auth import router as auth_router

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
        conn = psycopg2.connect(**DB_CONFIG)
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
        conn = psycopg2.connect(**DB_CONFIG)
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
        conn = psycopg2.connect(**DB_CONFIG)
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
        conn = psycopg2.connect(**DB_CONFIG)
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
        conn = psycopg2.connect(**DB_CONFIG)
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
        conn = psycopg2.connect(**DB_CONFIG)
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
        conn = psycopg2.connect(**DB_CONFIG)
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
        conn = psycopg2.connect(**DB_CONFIG)
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
        conn = psycopg2.connect(**DB_CONFIG)
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
        conn = psycopg2.connect(**DB_CONFIG)
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

