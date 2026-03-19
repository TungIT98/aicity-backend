"""
AI City Backend API
FastAPI server for AI City services

Company: AI City (AI Agent Platform for Vietnamese SMEs)
Documentation: http://localhost:3200/docs
OpenAPI Schema: http://localhost:3200/openapi.json
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from pydantic import BaseModel
from typing import Optional, List
import psycopg2
import requests
import os

app = FastAPI(
    title="AI City API",
    version="1.0.0",
    description="""
## AI City Backend API

AI City is an AI Agent Platform for Vietnamese SMEs.

### Features
- 🔐 **Authentication** - JWT-based user authentication
- 📊 **Analytics** - Real-time analytics with Matomo integration
- 🎯 **Lead Management** - CRM with conversion tracking
- 💳 **Billing & Invoices** - Vietnamese e-invoice support
- 📈 **Revenue Tracking** - Subscription and payment tracking
- 🔍 **RAG Search** - Semantic search with Ollama + Qdrant

### Authentication
All protected endpoints require a Bearer token in the Authorization header:
```
Authorization: Bearer <your_token>
```

### Rate Limits
- Default: 1000 requests/minute per user
- Search: 100 requests/minute

### Support
- Email: support@aicity.vn
- API Version: 1.0.0
    """,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    contact={
        "name": "AI City Support",
        "email": "support@aicity.vn",
        "url": "https://aicity.vn"
    },
    license_info={
        "name": "Proprietary",
        "url": "https://aicity.vn/terms"
    },
    tags_metadata=[
        {
            "name": "Health",
            "description": "Health check and status endpoints",
        },
        {
            "name": "Auth",
            "description": "User authentication and authorization (JWT)",
        },
        {
            "name": "Search",
            "description": "RAG-powered semantic search",
        },
        {
            "name": "Leads",
            "description": "CRM lead management and conversion tracking",
        },
        {
            "name": "Analytics",
            "description": "Dashboard analytics and Matomo integration",
        },
        {
            "name": "Invoices",
            "description": "Vietnamese e-invoice generation (Hóa đơn điện tử)",
        },
        {
            "name": "Payments",
            "description": "Payment gateway integration (VietQR, MoMo, ZaloPay)",
        },
        {
            "name": "Subscriptions",
            "description": "Subscription management and billing",
        },
        {
            "name": "Tracking",
            "description": "User behavior and event tracking",
        },
        {
            "name": "Reports",
            "description": "Automated report generation",
        },
        {
            "name": "Feedback",
            "description": "NPS, CSAT surveys and feedback analytics",
        },
    ]
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5433"),
    "database": os.getenv("DB_NAME", "promptforge"),
    "user": os.getenv("DB_USER", "promptforge"),
    "password": os.getenv("DB_PASSWORD", "promptforge123"),
}

# Qdrant configuration
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Models
class SearchRequest(BaseModel):
    query: str
    limit: int = 5

class SearchResult(BaseModel):
    id: int
    score: float
    title: str
    content: str

class DocumentRequest(BaseModel):
    title: str
    content: str
    metadata: Optional[dict] = {}


def get_db():
    """Database connection"""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def get_embedding(text: str) -> List[float]:
    """Get embedding from Ollama"""
    response = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": "nomic-embed-text", "prompt": text}
    )
    response.raise_for_status()
    return response.json()["embedding"]


@app.get("/")
async def root():
    return {"status": "running", "service": "AI City API"}


@app.get("/health")
async def health():
    # Check Ollama
    ollama_status = "ok"
    try:
        requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
    except:
        ollama_status = "unavailable"

    # Check Qdrant
    qdrant_status = "ok"
    try:
        requests.get(f"{QDRANT_URL}/collections", timeout=2)
    except:
        qdrant_status = "unavailable"

    # Check PostgreSQL
    pg_status = "ok"
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.close()
    except:
        pg_status = "unavailable"

    return {
        "ollama": ollama_status,
        "qdrant": qdrant_status,
        "postgresql": pg_status
    }


@app.post("/search", response_model=List[SearchResult])
async def search(request: SearchRequest):
    """Semantic search using RAG"""
    try:
        embedding = get_embedding(request.query)

        # Search in Qdrant collection
        response = requests.post(
            f"{QDRANT_URL}/collections/ai_city_embeddings/points/search",
            json={
                "vector": embedding,
                "limit": request.limit,
                "with_payload": True
            }
        )

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Search failed")

        results = response.json().get("result", [])
        return [
            SearchResult(
                id=r["id"],
                score=r["score"],
                title=r["payload"].get("title", ""),
                content=r["payload"].get("content", "")
            )
            for r in results
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/documents")
async def add_document(request: DocumentRequest):
    """Add document to RAG store"""
    try:
        embedding = get_embedding(request.content)

        # Insert into Qdrant
        import uuid
        point_id = str(uuid.uuid4()).split("-")[0]
        response = requests.post(
            f"{QDRANT_URL}/collections/ai_city_embeddings/points",
            json={
                "points": [{
                    "id": int(point_id, 16),
                    "vector": embedding,
                    "payload": {
                        "title": request.title,
                        "content": request.content,
                        "metadata": request.metadata
                    }
                }]
            }
        )

        if response.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Failed to add document")

        return {"id": point_id, "status": "added"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections")
async def list_collections():
    """List Qdrant collections"""
    try:
        response = requests.get(f"{QDRANT_URL}/collections")
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections/{collection}/points/count")
async def count_points(collection: str):
    """Count points in collection"""
    try:
        response = requests.get(f"{QDRANT_URL}/collections/{collection}/points/count")
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Analytics configuration
MATOMO_URL = os.getenv("MATOMO_URL", "http://localhost:8080")
MATOMO_API_TOKEN = os.getenv("MATOMO_API_TOKEN", "")
MATOMO_SITE_ID = os.getenv("MATOMO_SITE_ID", "1")

# Lead tracking models
class LeadCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    source: str
    status: str = "new"
    metadata: Optional[dict] = {}

class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict] = None

class LeadResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: Optional[str]
    source: str
    status: str
    metadata: dict
    created_at: str
    updated_at: str


# Analytics endpoints
@app.get("/analytics/overview")
async def get_analytics_overview():
    """Get dashboard overview metrics"""
    try:
        # Get Matomo data
        matomo_data = {}
        if MATOMO_API_TOKEN:
            resp = requests.get(
                f"{MATOMO_URL}/index.php",
                params={
                    "module": "API",
                    "method": "API.get",
                    "idSite": MATOMO_SITE_ID,
                    "period": "day",
                    "date": "today",
                    "format": "json",
                    "token_auth": MATOMO_API_TOKEN,
                },
                timeout=5
            )
            if resp.status_code == 200:
                matomo_data = resp.json()

        # Get lead stats from database
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Count leads by status
        cursor.execute("""
            SELECT status, COUNT(*) FROM leads GROUP BY status
        """)
        lead_stats = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.close()
        conn.close()

        return {
            "matomo": matomo_data,
            "leads": lead_stats,
            "period": "today"
        }
    except Exception as e:
        return {"error": str(e), "matomo": {}, "leads": {}}


@app.get("/analytics/users")
async def get_user_metrics(period: str = "week"):
    """Get user metrics for the specified period"""
    try:
        if not MATOMO_API_TOKEN:
            return {"error": "Matomo not configured"}

        resp = requests.get(
            f"{MATOMO_URL}/index.php",
            params={
                "module": "API",
                "method": "Live.getCounters",
                "idSite": MATOMO_SITE_ID,
                "format": "json",
                "token_auth": MATOMO_API_TOKEN,
            },
            timeout=5
        )

        if resp.status_code == 200:
            data = resp.json()
            return {
                "visitors": data.get("0", {}).get("visitors", 0),
                "actions": data.get("0", {}).get("actions", 0),
                "period": period
            }

        return {"error": "Failed to fetch user metrics"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/analytics/conversions")
async def get_conversion_metrics():
    """Get conversion funnel data"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Get conversion rates from leads
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
    """Get revenue tracking data"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Get revenue from converted leads
        cursor.execute("""
            SELECT COALESCE(SUM(CAST(metadata->>'revenue' AS numeric)), 0) as total
            FROM leads
            WHERE status = 'converted'
        """)
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        return {
            "total_revenue": result[0] or 0,
            "currency": "USD",
            "period": "all_time"
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/analytics/matomo")
async def get_matomo_data(method: str = "VisitsSummary.get", period: str = "day"):
    """Get raw Matomo analytics data"""
    try:
        if not MATOMO_API_TOKEN:
            return {"error": "Matomo not configured"}

        resp = requests.get(
            f"{MATOMO_URL}/index.php",
            params={
                "module": "API",
                "method": method,
                "idSite": MATOMO_SITE_ID,
                "period": period,
                "date": "today",
                "format": "json",
                "token_auth": MATOMO_API_TOKEN,
            },
            timeout=10
        )

        if resp.status_code == 200:
            return resp.json()

        return {"error": f"Matomo API error: {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}


# Lead tracking endpoints
@app.post("/leads", response_model=LeadResponse)
async def create_lead(lead: LeadCreate):
    """Create a new lead"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO leads (name, email, phone, source, status, metadata, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            RETURNING id, name, email, phone, source, status, metadata, created_at, updated_at
        """, (lead.name, lead.email, lead.phone, lead.source, lead.status, str(lead.metadata)))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        # Track funnel progression - new lead = signup started
        if lead.email:
            track_funnel_stage(
                user_id=lead.email,
                stage="signup_start",
                metadata={"source": lead.source, "name": lead.name}
            )
            # Also track as event
            track_event(
                user_id=lead.email,
                category="lead",
                action="create",
                name=lead.source
            )

        return LeadResponse(
            id=result[0],
            name=result[1],
            email=result[2],
            phone=result[3],
            source=result[4],
            status=result[5],
            metadata=result[6],
            created_at=str(result[7]),
            updated_at=str(result[8])
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/leads")
async def list_leads(status: Optional[str] = None, limit: int = 50):
    """List leads with optional status filter"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        if status:
            cursor.execute("""
                SELECT id, name, email, phone, source, status, metadata, created_at, updated_at
                FROM leads WHERE status = %s ORDER BY created_at DESC LIMIT %s
            """, (status, limit))
        else:
            cursor.execute("""
                SELECT id, name, email, phone, source, status, metadata, created_at, updated_at
                FROM leads ORDER BY created_at DESC LIMIT %s
            """, (limit,))

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        return [
            {
                "id": r[0],
                "name": r[1],
                "email": r[2],
                "phone": r[3],
                "source": r[4],
                "status": r[5],
                "metadata": r[6],
                "created_at": str(r[7]),
                "updated_at": str(r[8])
            }
            for r in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/leads/{lead_id}")
async def get_lead(lead_id: int):
    """Get lead details"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, name, email, phone, source, status, metadata, created_at, updated_at
            FROM leads WHERE id = %s
        """, (lead_id,))

        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if not result:
            raise HTTPException(status_code=404, detail="Lead not found")

        return {
            "id": result[0],
            "name": result[1],
            "email": result[2],
            "phone": result[3],
            "source": result[4],
            "status": result[5],
            "metadata": result[6],
            "created_at": str(result[7]),
            "updated_at": str(result[8])
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/leads/{lead_id}")
async def update_lead(lead_id: int, lead: LeadUpdate):
    """Update lead details"""
    try:
        updates = []
        values = []

        if lead.name is not None:
            updates.append("name = %s")
            values.append(lead.name)
        if lead.email is not None:
            updates.append("email = %s")
            values.append(lead.email)
        if lead.phone is not None:
            updates.append("phone = %s")
            values.append(lead.phone)
        if lead.source is not None:
            updates.append("source = %s")
            values.append(lead.source)
        if lead.status is not None:
            updates.append("status = %s")
            values.append(lead.status)
        if lead.metadata is not None:
            updates.append("metadata = %s")
            values.append(str(lead.metadata))

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        values.append(lead_id)

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute(f"""
            UPDATE leads SET {', '.join(updates)}, updated_at = NOW()
            WHERE id = %s
            RETURNING id, name, email, phone, source, status, metadata, created_at, updated_at
        """, tuple(values))

        result = cursor.fetchone()
        conn.commit()

        # Track conversion when lead is converted
        if lead.status == "converted" and result and result[2]:  # email field
            email = result[2]
            revenue = 0
            if result[6]:  # metadata
                try:
                    import json
                    metadata = json.loads(str(result[6])) if isinstance(result[6], str) else result[6]
                    revenue = float(metadata.get("revenue", 0))
                except:
                    pass

            # Track conversion in funnel
            track_funnel_stage(
                user_id=email,
                stage="signup_complete",
                metadata={"revenue": revenue}
            )

            # Track conversion event
            track_event(
                user_id=email,
                category="lead",
                action="converted",
                value=revenue
            )

            # Track revenue if present
            if revenue > 0:
                track_transaction(
                    user_id=email,
                    order_id=f"lead_{lead_id}",
                    total=revenue,
                    items=[{"id": "lead_conversion", "name": "Lead Conversion", "price": revenue, "qty": 1}]
                )

        cursor.close()
        conn.close()

        if not result:
            raise HTTPException(status_code=404, detail="Lead not found")

        return {
            "id": result[0],
            "name": result[1],
            "email": result[2],
            "phone": result[3],
            "source": result[4],
            "status": result[5],
            "metadata": result[6],
            "created_at": str(result[7]),
            "updated_at": str(result[8])
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/leads/analytics/conversion")
async def get_lead_analytics():
    """Get lead conversion analytics"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Get conversion by source
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

        # Get conversion by status
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
        raise HTTPException(status_code=500, detail=str(e))


# Automated reporting endpoints
@app.post("/reports/generate")
async def generate_report(report_type: str = "weekly"):
    """Generate automated report"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Gather analytics data
        report_data = {}

        # Lead stats
        cursor.execute("""
            SELECT status, COUNT(*) FROM leads GROUP BY status
        """)
        report_data["leads_by_status"] = {r[0]: r[1] for r in cursor.fetchall()}

        # Revenue
        cursor.execute("""
            SELECT COALESCE(SUM(CAST(metadata->>'revenue' AS numeric)), 0)
            FROM leads WHERE status = 'converted'
        """)
        report_data["total_revenue"] = cursor.fetchone()[0] or 0

        # Conversion rates
        cursor.execute("""
            SELECT source, COUNT(*),
                   SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END)
            FROM leads GROUP BY source
        """)
        report_data["conversions_by_source"] = [
            {"source": r[0], "total": r[1], "converted": r[2]}
            for r in cursor.fetchall()
        ]

        # Save report
        cursor.execute("""
            INSERT INTO reports (report_type, title, content, period_start, period_end)
            VALUES (%s, %s, %s, CURRENT_DATE - 7, CURRENT_DATE)
            RETURNING id, generated_at
        """, (report_type, f"{report_type.title()} Report - AI City", str(report_data)))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return {
            "id": str(result[0]),
            "generated_at": str(result[1]),
            "type": report_type,
            "data": report_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/reports")
async def list_reports(limit: int = 10):
    """List generated reports"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, report_type, title, generated_at, period_start, period_end
            FROM reports ORDER BY generated_at DESC LIMIT %s
        """, (limit,))

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        return [
            {
                "id": str(r[0]),
                "type": r[1],
                "title": r[2],
                "generated_at": str(r[3]),
                "period_start": str(r[4]) if r[4] else None,
                "period_end": str(r[5]) if r[5] else None
            }
            for r in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/reports/{report_id}")
async def get_report(report_id: str):
    """Get report details"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, report_type, title, content, generated_at, period_start, period_end
            FROM reports WHERE id = %s
        """, (report_id,))

        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if not result:
            raise HTTPException(status_code=404, detail="Report not found")

        return {
            "id": str(result[0]),
            "type": result[1],
            "title": result[2],
            "content": result[3],
            "generated_at": str(result[4]),
            "period_start": str(result[5]) if result[5] else None,
            "period_end": str(result[6]) if result[6] else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Import auth router (JWT authentication)
from auth import router as auth_router
app.include_router(auth_router)

# Import payment gateway router
from payment_gateway import router as payment_router
app.include_router(payment_router)

# Import invoice router
from invoice import router as invoice_router
app.include_router(invoice_router)

# Import subscription router
from subscription import router as subscription_router
app.include_router(subscription_router)

# Import feedback router
from feedback import router as feedback_router
app.include_router(feedback_router)

# Import revenue report router
from revenue_report import router as revenue_report_router
app.include_router(revenue_report_router)

# Import tracking module
import tracking
from tracking import (
    track_page_view,
    track_event,
    track_funnel_stage,
    track_transaction,
    track_feature_used,
    track_button_click,
    track_form_submit,
    track_search,
    track_api_call,
    FUNNEL_STAGES
)

# Tracking API endpoints
class PageViewRequest(BaseModel):
    user_id: Optional[str] = None
    page_url: str = "/"
    page_title: Optional[str] = None
    referrer: Optional[str] = None


class EventRequest(BaseModel):
    user_id: str
    category: str  # feature, button, form, search, api
    action: str
    name: Optional[str] = None
    value: Optional[float] = None


class FunnelRequest(BaseModel):
    user_id: str
    stage: str  # landing, signup_start, signup_complete, etc.
    metadata: Optional[dict] = None


class TransactionRequest(BaseModel):
    user_id: str
    order_id: str
    total: float
    items: Optional[list] = None


class RevenueRequest(BaseModel):
    user_id: str
    amount: float
    subscription_type: Optional[str] = None
    plan: Optional[str] = None


@app.post("/tracking/pageview")
async def api_track_page_view(request: PageViewRequest, x_forwarded_for: Optional[str] = None):
    """Track page view"""
    ip = x_forwarded_for.split(",")[0].strip() if x_forwarded_for else None
    result = track_page_view(
        user_id=request.user_id,
        page_url=request.page_url,
        page_title=request.page_title,
        referrer=request.referrer,
        ip_address=ip
    )
    return {"success": result}


@app.post("/tracking/event")
async def api_track_event(request: EventRequest, x_forwarded_for: Optional[str] = None):
    """Track custom event"""
    ip = x_forwarded_for.split(",")[0].strip() if x_forwarded_for else None
    result = track_event(
        user_id=request.user_id,
        category=request.category,
        action=request.action,
        name=request.name,
        value=request.value,
        ip_address=ip
    )
    return {"success": result}


@app.post("/tracking/feature")
async def api_track_feature(
    user_id: str,
    feature_name: str,
    x_forwarded_for: Optional[str] = None
):
    """Track feature usage"""
    ip = x_forwarded_for.split(",")[0].strip() if x_forwarded_for else None
    result = track_feature_used(user_id, feature_name, ip)
    return {"success": result}


@app.post("/tracking/button")
async def api_track_button(
    user_id: str,
    button_name: str,
    page: str,
    x_forwarded_for: Optional[str] = None
):
    """Track button click"""
    ip = x_forwarded_for.split(",")[0].strip() if x_forwarded_for else None
    result = track_button_click(user_id, button_name, page, ip)
    return {"success": result}


@app.post("/tracking/funnel")
async def api_track_funnel(request: FunnelRequest, x_forwarded_for: Optional[str] = None):
    """Track conversion funnel progression"""
    ip = x_forwarded_for.split(",")[0].strip() if x_forwarded_for else None
    result = track_funnel_stage(request.user_id, request.stage, request.metadata, ip)
    return {"success": result}


@app.get("/tracking/funnel/stages")
async def get_funnel_stages():
    """Get available funnel stages"""
    return {"stages": FUNNEL_STAGES}


@app.post("/tracking/transaction")
async def api_track_transaction(request: TransactionRequest, x_forwarded_for: Optional[str] = None):
    """Track ecommerce transaction"""
    ip = x_forwarded_for.split(",")[0].strip() if x_forwarded_for else None
    result = track_transaction(
        user_id=request.user_id,
        order_id=request.order_id,
        total=request.total,
        items=request.items,
        ip_address=ip
    )
    return {"success": result}


@app.post("/tracking/revenue")
async def api_track_revenue(request: RevenueRequest, x_forwarded_for: Optional[str] = None):
    """Track revenue from subscriptions"""
    ip = x_forwarded_for.split(",")[0].strip() if x_forwarded_for else None

    # Track as transaction
    result = track_transaction(
        user_id=request.user_id,
        order_id=f"sub_{int(datetime.now().timestamp())}",
        total=request.amount,
        items=[{
            "id": request.plan or "subscription",
            "name": f"{request.subscription_type or 'Standard'} Subscription",
            "price": request.amount,
            "qty": 1
        }],
        ip_address=ip
    )

    # Also track as conversion goal
    track_funnel_stage(
        user_id=request.user_id,
        stage="subscription_start",
        metadata={"amount": request.amount},
        ip_address=ip
    )

    return {"success": result}


@app.get("/tracking/status")
async def get_tracking_status():
    """Check tracking configuration"""
    return {
        "enabled": True,
        "matomo_url": MATOMO_URL,
        "site_id": MATOMO_SITE_ID,
        "features": [
            "page_view_tracking",
            "feature_usage",
            "button_clicks",
            "form_submissions",
            "search_tracking",
            "api_tracking",
            "conversion_funnel",
            "revenue_tracking"
        ]
    }


class UserSessionRequest(BaseModel):
    visitor_id: str
    user_id: str


@app.post("/tracking/session")
async def register_user_session(request: UserSessionRequest):
    """Register a user session to link anonymous visitor to authenticated user"""
    # This stores the mapping in Matomo via custom variable
    result = track_event(
        user_id=request.user_id,
        category="session",
        action="register",
        name=request.visitor_id
    )
    # Also track the funnel stage for signup start
    track_funnel_stage(
        user_id=request.user_id,
        stage="signup_complete"
    )
    return {"success": result}


# Enhanced analytics combining Matomo + internal data
@app.get("/analytics/dashboard")
async def get_dashboard_analytics(period: str = "week"):
    """Get comprehensive dashboard analytics"""
    try:
        import json
        from datetime import datetime, timedelta

        # Get Matomo visitor data
        matomo_visitors = {}
        if MATOMO_API_TOKEN:
            try:
                resp = requests.get(
                    f"{MATOMO_URL}/index.php",
                    params={
                        "module": "API",
                        "method": "VisitsSummary.get",
                        "idSite": MATOMO_SITE_ID,
                        "period": period,
                        "date": "today",
                        "format": "json",
                        "token_auth": MATOMO_API_TOKEN,
                    },
                    timeout=5
                )
                if resp.status_code == 200:
                    matomo_visitors = resp.json()
            except:
                pass

        # Get leads data
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Leads by source
        cursor.execute("""
            SELECT source, COUNT(*) as total,
                   SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted
            FROM leads
            GROUP BY source
        """)
        leads_by_source = [
            {"source": r[0], "total": r[1], "converted": r[2], "rate": round(r[2]/r[1]*100, 2) if r[1] > 0 else 0}
            for r in cursor.fetchall()
        ]

        # Leads by status
        cursor.execute("""
            SELECT status, COUNT(*) FROM leads GROUP BY status
        """)
        leads_by_status = {r[0]: r[1] for r in cursor.fetchall()}

        # Revenue from converted leads
        cursor.execute("""
            SELECT COALESCE(SUM(CAST(metadata->>'revenue' AS numeric)), 0)
            FROM leads WHERE status = 'converted'
        """)
        total_revenue = cursor.fetchone()[0] or 0

        cursor.close()
        conn.close()

        # Calculate conversion rate
        total_leads = sum(leads_by_status.values())
        converted_leads = leads_by_status.get("converted", 0)
        conversion_rate = round(converted_leads / total_leads * 100, 2) if total_leads > 0 else 0

        return {
            "period": period,
            "visitors": matomo_visitors,
            "leads": {
                "by_source": leads_by_source,
                "by_status": leads_by_status,
                "total": total_leads,
                "converted": converted_leads,
                "conversion_rate": conversion_rate
            },
            "revenue": {
                "total": total_revenue,
                "currency": "USD"
            },
            "features": {
                "tracking_enabled": True,
                "matomo_configured": bool(MATOMO_API_TOKEN)
            }
        }
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
