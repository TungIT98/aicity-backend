"""
AI City Backend API
FastAPI server for AI City services

Company: AI City (AI Agent Platform for Vietnamese SMEs)
Documentation: http://localhost:3200/docs
OpenAPI Schema: http://localhost:3200/openapi.json
"""

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import psycopg2
import requests
import os
import json
import logging
import traceback

log = logging.getLogger(__name__)

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
            "name": "Demo",
            "description": "Demo booking form lead capture",
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


@app.get("/live")
async def liveness():
    """Kubernetes liveness probe - is the process alive?"""
    return {"status": "alive", "service": "AI City API"}


@app.get("/ready")
async def readiness():
    """Kubernetes readiness probe - is the service ready to receive traffic?"""
    # Check PostgreSQL is reachable
    try:
        conn = psycopg2.connect(**DB_CONFIG, connect_timeout=3)
        conn.close()
        pg_ready = True
    except:
        pg_ready = False

    if pg_ready:
        return {"status": "ready", "service": "AI City API"}
    else:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "service": "AI City API", "reason": "database_unavailable"}
        )


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


class ReportRequest(BaseModel):
    report_type: str = "weekly"
    period: Optional[str] = None

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


# Demo booking models
class DemoBookingRequest(BaseModel):
    name: str
    company: str
    email: str
    phone: str
    employees: Optional[str] = None
    message: Optional[str] = None
    timestamp: Optional[str] = None


class DemoBookingResponse(BaseModel):
    success: bool
    message: str
    lead_id: int


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


# Lead analytics endpoints
@app.get("/leads/analytics/conversion")
async def get_leads_conversion_analytics():
    """Get lead conversion analytics - /api/leads/analytics/conversion"""
    return await get_lead_analytics()


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


# Demo booking endpoint
DEMO_SALES_EMAIL = "thanhtungtran364@gmail.com"
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")


@app.post("/api/demo", response_model=DemoBookingResponse, tags=["Demo"])
async def create_demo_booking(booking: DemoBookingRequest):
    """Capture demo booking form submissions and notify sales team."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
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
                    log.warning(f"Resend email failed: {resend_resp.status_code} {resend_resp.text}")
            except Exception as email_err:
                log.warning(f"Failed to send demo booking email: {email_err}")

        return DemoBookingResponse(
            success=True,
            message="Demo booking received. Our team will contact you shortly.",
            lead_id=lead_id,
        )
    except Exception as e:
        log.error(f"Demo booking failed: {e}")
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

# Import revenue API router
from revenue_api import router as revenue_api_router
app.include_router(revenue_api_router)

# Import CEO Dashboard router
from ceo_dashboard import router as ceo_dashboard_router
app.include_router(ceo_dashboard_router)

# Import Analytics router (Telesales, Conversion Funnel, ROI)
from analytics import router as analytics_router
app.include_router(analytics_router)

# Import Globe AI City data layer router
from globe import router as globe_router
app.include_router(globe_router)

# Import Storage Infrastructure router (AIC-518)
from api.storage import router as storage_router
app.include_router(storage_router)

# Import Logging API router (AIC-528 - ELK-compatible structured logging)
from api.logging_api import router as logging_router
app.include_router(logging_router)

# Import Agents router (AIC-590)
from agents import router as agents_router, list_agents, get_agent_usage as get_agents_usage
app.include_router(agents_router)

# ─── API Versioning (AIC-538) ────────────────────────────────────────────────────
# Mount v1 sub-app at /v1/ for versioned API access
# See API_VERSIONING.md for versioning strategy details
from api.v1 import _v1_app
app.mount("/v1", _v1_app)

# Rate Limiting Middleware (AIC-526)
from api.rate_limiter import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)


# ─── API Prefix Aliases (AIC-619) ─────────────────────────────────────────────
# Frontend calls /api/leads, /api/search, /api/reports, /api/forecasting, /api/metrics
# These alias to the existing root-level routes for backward compatibility.

@app.post("/api/leads", response_model=LeadResponse, tags=["Leads"])
async def api_create_lead(lead: LeadCreate):
    """Create a new lead - /api/leads (alias for /leads)"""
    return await create_lead(lead)


@app.get("/api/leads", tags=["Leads"])
async def api_list_leads(status: Optional[str] = None, limit: int = 50):
    """List leads - /api/leads (alias for /leads)"""
    return await list_leads(status=status, limit=limit)


@app.get("/api/leads/{lead_id}", tags=["Leads"])
async def api_get_lead(lead_id: int):
    """Get a lead by ID - /api/leads/{id}"""
    return await get_lead(lead_id)


@app.patch("/api/leads/{lead_id}", tags=["Leads"])
async def api_update_lead(lead_id: int, lead: LeadUpdate):
    """Update a lead - /api/leads/{id}"""
    return await update_lead(lead_id, lead)


@app.get("/api/leads/analytics/conversion", tags=["Leads"])
async def api_leads_conversion_analytics():
    """Lead conversion analytics - /api/leads/analytics/conversion"""
    return await get_leads_conversion_analytics()


@app.post("/api/search", response_model=List[SearchResult], tags=["Search"])
async def api_search(request: SearchRequest):
    """Semantic search - /api/search (alias for /search)"""
    return await search(request)


@app.get("/api/reports", tags=["Reports"])
async def api_list_reports(limit: int = 20):
    """List reports - /api/reports (alias for /reports)"""
    return await list_reports(limit=limit)


@app.get("/api/reports/{report_id}", tags=["Reports"])
async def api_get_report(report_id: int):
    """Get a report - /api/reports/{id}"""
    return await get_report(report_id)


@app.post("/api/reports/generate", tags=["Reports"])
async def api_generate_report(report: ReportRequest):
    """Generate a report - /api/reports/generate"""
    return await generate_report(report)


# ─── Forecasting & Metrics (AIC-619) ───────────────────────────────────────────
# Endpoints the frontend expects that didn't exist before.

@app.get("/api/forecasting", tags=["Forecasting"])
async def get_forecasting(period: str = "30d"):
    """Lead/revenue forecasting based on historical trends."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Determine date range
        days = 30 if period == "30d" else 90 if period == "90d" else 7

        # Get lead trends
        cursor.execute(f"""
            SELECT
                DATE_TRUNC('week', created_at) as week,
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'qualified') as qualified,
                COUNT(*) FILTER (WHERE status = 'converted') as converted
            FROM leads
            WHERE created_at >= NOW() - INTERVAL '{days} days'
            GROUP BY DATE_TRUNC('week', created_at)
            ORDER BY week
        """)
        weekly = cursor.fetchall()

        # Get current total leads and conversion rate
        cursor.execute("""
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE status = 'qualified' OR status = 'converted'),
                   COUNT(*) FILTER (WHERE status = 'converted')
            FROM leads
        """)
        total_row = cursor.fetchone()
        total_leads, total_qualified, total_converted = total_row

        conversion_rate = (total_converted / total_leads * 100) if total_leads > 0 else 0

        cursor.close()
        conn.close()

        # Simple linear forecast: extrapolate from last 4 weeks
        if len(weekly) >= 2:
            recent = weekly[-1]
            prev = weekly[-2]
            growth_rate = (recent[1] - prev[1]) / prev[1] if prev[1] > 0 else 0
            projected_leads_30d = int(recent[1] * (1 + growth_rate))
            projected_leads_90d = int(recent[1] * (1 + growth_rate) ** 3)
        else:
            projected_leads_30d = int(total_leads * 0.1)
            projected_leads_90d = int(total_leads * 0.3)

        return {
            "period": period,
            "total_leads": total_leads,
            "total_qualified": total_qualified,
            "total_converted": total_converted,
            "conversion_rate": round(conversion_rate, 2),
            "weekly_trend": [
                {"week": str(w[0].date()), "total": w[1], "qualified": w[2], "converted": w[3]}
                for w in weekly
            ],
            "projections": {
                "leads_30d": max(0, projected_leads_30d),
                "leads_90d": max(0, projected_leads_90d),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics", tags=["Metrics"])
async def get_metrics(type: str = "overview"):
    """Unified metrics endpoint for dashboard widgets."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        if type == "overview":
            cursor.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE type = 'subscription') as subscriptions,
                    COUNT(*) FILTER (WHERE type = 'one_time') as one_time_payments,
                    SUM(amount) FILTER (WHERE status = 'completed') as total_revenue,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending_payments
                FROM payments
            """)
            payments_row = cursor.fetchone()

            cursor.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'new') as new_leads,
                    COUNT(*) FILTER (WHERE status = 'qualified') as qualified_leads,
                    COUNT(*) FILTER (WHERE status = 'contacted') as contacted_leads,
                    COUNT(*) FILTER (WHERE status = 'converted') as converted_leads
                FROM leads
            """)
            leads_row = cursor.fetchone()

            cursor.execute("""
                SELECT COUNT(*) FROM subscriptions WHERE status = 'active'
            """)
            active_subs = cursor.fetchone()[0]

            cursor.close()
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
        elif type == "revenue":
            return await get_revenue_metrics()
        elif type == "users":
            return await get_user_metrics(period="week")
        elif type == "conversions":
            return await get_conversion_metrics()
        else:
            raise HTTPException(status_code=400, detail="Invalid type: use overview, revenue, users, or conversions")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Standardized Exception Handlers (AIC-526) ────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Standardized HTTP exception response format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "type": exc.__class__.__name__,
            },
            "request_id": getattr(request.state, "request_id", None),
        },
        headers=getattr(exc, "headers", None) or {},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Standardized 500 error response - never leaks internals."""
    log.error(f"Unhandled exception: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": 500,
                "message": "Internal server error",
                "type": "InternalServerError",
            },
            "request_id": getattr(request.state, "request_id", None),
        },
    )


# Import Monitoring router (health, stats, alerting)
from monitoring import router as monitoring_router
app.include_router(monitoring_router)

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

        # Get leads data - OPTIMIZED: Combined single query instead of 3 sequential
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Single combined query for leads analytics
        cursor.execute("""
            WITH leads_summary AS (
                SELECT source, status,
                       COUNT(*) as total,
                       SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted
                FROM leads
                GROUP BY source, status
            ),
            status_summary AS (
                SELECT status, COUNT(*) as count
                FROM leads
                GROUP BY status
            ),
            revenue_summary AS (
                SELECT COALESCE(SUM(CAST(metadata->>'revenue' AS numeric)), 0) as total
                FROM leads WHERE status = 'converted'
            )
            SELECT
                json_agg(json_build_object('source', source, 'total', total, 'converted', converted,
                    'rate', CASE WHEN total > 0 THEN ROUND(converted::numeric/total*100, 2) ELSE 0 END)
                    ORDER BY total DESC) as leads_by_source,
                (SELECT json_object_agg(status, count) FROM status_summary) as leads_by_status,
                (SELECT total FROM revenue_summary) as total_revenue
            FROM leads_summary
            WHERE converted > 0 OR total > 0
        """)
        result = cursor.fetchone()
        leads_by_source = result[0] if result and result[0] else []
        leads_by_status = result[1] if result and result[1] else {}
        total_revenue = result[2] if result and result[2] else 0

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
