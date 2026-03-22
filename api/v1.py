"""
AI City API v1 Router

All v1 endpoints are prefixed with /v1/.
This module registers all existing routers under the /v1/ prefix for API versioning.

Versioning Strategy: URL-based versioning (/v1/)
- Recommended approach for public REST APIs
- Easy to discover, test, and cache
- Standard practice (Stripe, GitHub, Twilio all use URL versioning)

For details, see: API_VERSIONING.md
"""

from fastapi import APIRouter, FastAPI

# ─── v1 Root Router ────────────────────────────────────────────────────────────

router = APIRouter(prefix="/v1", tags=["v1"])

# ─── v1 App (sub-app for v1 routes) ───────────────────────────────────────────
# Mount all existing routers under /v1/ prefix

_v1_app = FastAPI(
    title="AI City API v1",
    version="1.0.0",
    description="AI City API v1 - all endpoints under /v1/",
    openapi_tags=[
        {"name": "Health", "description": "Health check and status endpoints"},
        {"name": "Auth", "description": "User authentication and authorization (JWT)"},
        {"name": "Search", "description": "RAG-powered semantic search"},
        {"name": "Leads", "description": "CRM lead management and conversion tracking"},
        {"name": "Analytics", "description": "Dashboard analytics and Matomo integration"},
        {"name": "Invoices", "description": "Vietnamese e-invoice generation (Hóa đơn điện tử)"},
        {"name": "Payments", "description": "Payment gateway integration (VietQR, MoMo, ZaloPay)"},
        {"name": "Subscriptions", "description": "Subscription management and billing"},
        {"name": "Tracking", "description": "User behavior and event tracking"},
        {"name": "Reports", "description": "Automated report generation"},
        {"name": "Feedback", "description": "NPS, CSAT surveys and feedback analytics"},
        {"name": "Storage", "description": "File storage and S3-compatible object storage"},
        {"name": "Logging", "description": "ELK-compatible structured logging"},
        {"name": "Globe", "description": "AI City Globe data layer"},
        {"name": "Revenue", "description": "Revenue reporting and analytics"},
        {"name": "CEO Dashboard", "description": "CEO dashboard and executive reporting"},
    ],
)

# Import all existing routers and re-mount under v1
from auth import router as auth_router

# Auth: /api/auth -> /v1/auth
_v1_app.include_router(auth_router)

from payment_gateway import router as payment_router

# Payments: /payments -> /v1/payments
_v1_app.include_router(payment_router)

from invoice import router as invoice_router

_v1_app.include_router(invoice_router)

from subscription import router as subscription_router

_v1_app.include_router(subscription_router)

from feedback import router as feedback_router

_v1_app.include_router(feedback_router)

from revenue_report import router as revenue_report_router

_v1_app.include_router(revenue_report_router)

from revenue_api import router as revenue_api_router

_v1_app.include_router(revenue_api_router)

from ceo_dashboard import router as ceo_dashboard_router

_v1_app.include_router(ceo_dashboard_router)

from analytics import router as analytics_router

_v1_app.include_router(analytics_router)

from globe import router as globe_router

_v1_app.include_router(globe_router)

from api.storage import router as storage_router

_v1_app.include_router(storage_router)

from api.logging_api import router as logging_router

_v1_app.include_router(logging_router)


# ─── Health, Search, Leads, Analytics, Reports, Tracking ─────────────────────
# These are defined in main.py as standalone functions.
# We dynamically import them to avoid circular imports.
import importlib

_main = importlib.import_module("main")

# Health
_v1_app.add_api_route("/health", _main.health, methods=["GET"], tags=["Health"])

# Search & Collections
_v1_app.add_api_route("/search", _main.search, methods=["POST"], tags=["Search"])
_v1_app.add_api_route("/documents", _main.add_document, methods=["POST"], tags=["Search"])
_v1_app.add_api_route("/collections", _main.list_collections, methods=["GET"], tags=["Search"])
_v1_app.add_api_route(
    "/collections/{collection}/points/count",
    _main.count_points,
    methods=["GET"],
    tags=["Search"],
)

# Leads
_v1_app.add_api_route("/leads", _main.create_lead, methods=["POST"], tags=["Leads"])
_v1_app.add_api_route("/leads", _main.list_leads, methods=["GET"], tags=["Leads"])
_v1_app.add_api_route("/leads/{lead_id}", _main.get_lead, methods=["GET"], tags=["Leads"])
_v1_app.add_api_route("/leads/{lead_id}", _main.update_lead, methods=["PATCH"], tags=["Leads"])
_v1_app.add_api_route(
    "/leads/analytics/conversion",
    _main.get_lead_analytics,
    methods=["GET"],
    tags=["Leads"],
)

# Demo booking
_v1_app.add_api_route("/demo", _main.create_demo_booking, methods=["POST"], tags=["Demo"])

# Analytics Dashboard
_v1_app.add_api_route(
    "/analytics/dashboard",
    _main.get_dashboard_analytics,
    methods=["GET"],
    tags=["Analytics"],
)

# Reports
_v1_app.add_api_route("/reports/generate", _main.generate_report, methods=["POST"], tags=["Reports"])
_v1_app.add_api_route("/reports", _main.list_reports, methods=["GET"], tags=["Reports"])
_v1_app.add_api_route("/reports/{report_id}", _main.get_report, methods=["GET"], tags=["Reports"])

# Tracking
_v1_app.add_api_route("/tracking/pageview", _main.api_track_page_view, methods=["POST"], tags=["Tracking"])
_v1_app.add_api_route("/tracking/event", _main.api_track_event, methods=["POST"], tags=["Tracking"])
_v1_app.add_api_route("/tracking/feature", _main.api_track_feature, methods=["POST"], tags=["Tracking"])
_v1_app.add_api_route("/tracking/button", _main.api_track_button, methods=["POST"], tags=["Tracking"])
_v1_app.add_api_route("/tracking/funnel", _main.api_track_funnel, methods=["POST"], tags=["Tracking"])
_v1_app.add_api_route("/tracking/funnel/stages", _main.get_funnel_stages, methods=["GET"], tags=["Tracking"])
_v1_app.add_api_route("/tracking/transaction", _main.api_track_transaction, methods=["POST"], tags=["Tracking"])
_v1_app.add_api_route("/tracking/revenue", _main.api_track_revenue, methods=["POST"], tags=["Tracking"])
_v1_app.add_api_route("/tracking/status", _main.get_tracking_status, methods=["GET"], tags=["Tracking"])
_v1_app.add_api_route("/tracking/session", _main.register_user_session, methods=["POST"], tags=["Tracking"])

# Root
_v1_app.add_api_route("/", _main.root, methods=["GET"], tags=["Root"])


# ─── v1 API Version Info ───────────────────────────────────────────────────────

_v1_app.add_api_route(
    "/",
    lambda: {
        "version": "1.0.0",
        "status": "running",
        "service": "AI City API v1",
        "docs": "/v1/docs",
        "deprecation_notice": "v1 is the current stable version. v2 coming soon.",
    },
    methods=["GET"],
    tags=["Root"],
)

# ─── Agents (v1) ──────────────────────────────────────────────────────────────

_v1_app.add_api_route("/agents", _main.list_agents, methods=["GET"], tags=["Agents"])
_v1_app.add_api_route("/agents/usage", _main.get_agents_usage, methods=["GET"], tags=["Agents"])
