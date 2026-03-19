# AI City API Documentation

## Overview

**Company:** AI City (AI Agent Platform for Vietnamese SMEs)  
**API Version:** 1.0.0

**Base URLs:**
- Development: `http://localhost:3200`
- Production: `https://api.aicity.com`

**Interactive Documentation:**
- Swagger UI: `http://localhost:3200/api/docs` (or `/api/redoc` for ReDoc)
- OpenAPI Schema: `http://localhost:3200/api/openapi.json`

**Total Endpoints:** 68

---

## Authentication

All endpoints under `/api/auth/*` are public. Protected endpoints require a **Bearer token**.

### Getting a Token

1. **Register:** `POST /api/auth/register`
2. **Login:** `POST /api/auth/login`

### Using the Token

Include the access token in the `Authorization` header:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiJ9...
```

### Token Details

| Field | Value |
|-------|-------|
| Type | JWT (HS256) |
| Access Token Expiry | 60 minutes |
| Refresh Token Expiry | 30 days |
| Refresh | `POST /api/auth/refresh` |

### Roles

| Role | Permissions |
|------|------------|
| `admin` | read, write, delete, admin |
| `user` | read, write |
| `guest` | read |

---

## Endpoints

---

### Health & Status

#### GET /health

Check API health status and component connectivity.

**Response:**
```json
{
  "ollama": "ok",
  "qdrant": "ok",
  "postgresql": "ok"
}
```

#### GET /tracking/status

Check tracking configuration.

**Response:**
```json
{
  "enabled": true,
  "matomo_url": "http://localhost:8080",
  "site_id": "1",
  "features": ["page_view_tracking", "feature_usage", ...]
}
```

---

### Authentication API (Router: /api/auth)

#### POST /api/auth/register

Register a new user account.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123",
  "name": "Nguyen Van A",
  "phone": "+84 123 456 789",
  "role": "user"
}
```

**Response (201):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": 1,
    "email": "user@example.com",
    "name": "Nguyen Van A",
    "role": "user",
    "created_at": "2026-03-20T04:00:00"
  }
}
```

#### POST /api/auth/login

Authenticate and get JWT tokens.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": 1,
    "email": "user@example.com",
    "name": "Nguyen Van A",
    "role": "user"
  }
}
```

#### POST /api/auth/refresh

Refresh access token using refresh token.

**Request:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiJ9..."
}
```

**Response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

#### GET /api/auth/me

Get current authenticated user's profile.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "name": "Nguyen Van A",
  "role": "user",
  "created_at": "2026-03-20T04:00:00",
  "last_login": "2026-03-20T04:10:00"
}
```

#### POST /api/auth/logout

Logout current user (client should discard tokens).

**Headers:** `Authorization: Bearer <token>`

**Response (200):**
```json
{
  "message": "Logged out successfully",
  "user_id": 1
}
```

#### POST /api/auth/change-password

Change current user's password.

**Headers:** `Authorization: Bearer <token>`

**Request:**
```json
{
  "current_password": "oldpassword",
  "new_password": "newsecurepassword"
}
```

---

### Search & Documents (RAG)

#### POST /search

Semantic search using RAG pipeline.

**Request:**
```json
{
  "query": "search term",
  "limit": 5
}
```

**Response:**
```json
[
  {
    "id": 1,
    "score": 0.95,
    "title": "Document Title",
    "content": "Document content..."
  }
]
```

#### POST /documents

Add document to RAG store.

**Request:**
```json
{
  "title": "Document Title",
  "content": "Document content...",
  "metadata": {}
}
```

**Response:**
```json
{
  "id": "abc123",
  "status": "added"
}
```

#### GET /collections

List Qdrant collections.

#### GET /collections/{collection}/points/count

Count points in a collection.

---

### Leads API

#### POST /leads

Create a new lead.

**Request:**
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "phone": "+1234567890",
  "source": "website",
  "status": "new",
  "metadata": {}
}
```

**Response:**
```json
{
  "id": 1,
  "name": "John Doe",
  "email": "john@example.com",
  "phone": "+1234567890",
  "source": "website",
  "status": "new",
  "metadata": {},
  "created_at": "2026-03-20T00:00:00",
  "updated_at": "2026-03-20T00:00:00"
}
```

#### GET /leads

List leads with optional status filter.

**Query Parameters:**
- `status` (optional): Filter by status (new, contacted, qualified, converted, lost)
- `limit` (optional): Max results (default 50)

#### GET /leads/{lead_id}

Get lead details.

#### PATCH /leads/{lead_id}

Update lead.

**Request:**
```json
{
  "status": "converted",
  "metadata": {"revenue": 1000}
}
```

#### GET /leads/analytics/conversion

Get lead conversion analytics.

**Response:**
```json
{
  "by_source": [
    {"source": "website", "total": 100, "converted": 20, "rate": 20.0}
  ],
  "by_status": [
    {"status": "new", "count": 50},
    {"status": "converted", "count": 20}
  ]
}
```

---

### Analytics API

#### GET /analytics/overview

Get dashboard overview metrics.

**Response:**
```json
{
  "matomo": {...},
  "leads": {"new": 10, "converted": 5},
  "period": "today"
}
```

#### GET /analytics/users

Get user metrics.

**Query Parameters:**
- `period`: week, month, year (default: week)

#### GET /analytics/conversions

Get conversion funnel data.

**Response:**
```json
{
  "total_leads": 100,
  "converted": 25,
  "conversion_rate": 25.0,
  "period": "all_time"
}
```

#### GET /analytics/revenue

Get revenue tracking data.

**Response:**
```json
{
  "total_revenue": 50000,
  "currency": "USD",
  "period": "all_time"
}
```

#### GET /analytics/matomo

Get raw Matomo analytics data.

**Query Parameters:**
- `method`: Matomo API method (default: VisitsSummary.get)
- `period`: day, week, month, year

#### GET /analytics/dashboard

Get comprehensive dashboard analytics.

**Query Parameters:**
- `period`: week, month, year (default: week)

---

### Reports API

#### POST /reports/generate

Generate automated report.

**Request:**
```json
{
  "report_type": "weekly"
}
```

**Response:**
```json
{
  "id": "123",
  "generated_at": "2026-03-20T00:00:00",
  "type": "weekly",
  "data": {...}
}
```

#### GET /reports

List generated reports.

**Query Parameters:**
- `limit`: Max results (default 10)

#### GET /reports/{report_id}

Get report details.

---

### Tracking API

#### POST /tracking/pageview

Track page view.

**Request:**
```json
{
  "user_id": "user123",
  "page_url": "/pricing",
  "page_title": "Pricing",
  "referrer": "/"
}
```

#### POST /tracking/event

Track custom event.

**Request:**
```json
{
  "user_id": "user123",
  "category": "button",
  "action": "click",
  "name": "signup_button",
  "value": 1.0
}
```

#### POST /tracking/feature

Track feature usage.

**Query Parameters:**
- `user_id`: User identifier
- `feature_name`: Name of the feature

#### POST /tracking/button

Track button click.

**Query Parameters:**
- `user_id`: User identifier
- `button_name`: Name of the button
- `page`: Page where button is located

#### POST /tracking/funnel

Track conversion funnel progression.

**Request:**
```json
{
  "user_id": "user123",
  "stage": "signup_start",
  "metadata": {}
}
```

#### GET /tracking/funnel/stages

Get available funnel stages.

**Response:**
```json
{
  "stages": ["landing", "signup_start", "signup_complete", "subscription_start"]
}
```

#### POST /tracking/transaction

Track ecommerce transaction.

**Request:**
```json
{
  "user_id": "user123",
  "order_id": "order_123",
  "total": 99.99,
  "items": [{"id": "product_1", "name": "Plan", "price": 99.99, "qty": 1}]
}
```

#### POST /tracking/revenue

Track revenue from subscriptions.

**Request:**
```json
{
  "user_id": "user123",
  "amount": 99.99,
  "subscription_type": "premium",
  "plan": "professional"
}
```

#### POST /tracking/session

Register user session (link anonymous visitor to authenticated user).

**Request:**
```json
{
  "visitor_id": "visitor_123",
  "user_id": "user_123"
}
```

---

### Payment API (Router: /api/payment)

#### POST /api/payment/create

Create payment.

**Request:**
```json
{
  "amount": 299000,
  "currency": "VND",
  "payment_method": "vietqr",
  "customer_id": "customer_123",
  "description": "Premium Plan"
}
```

#### GET /api/payment/{payment_id}/status

Get payment status.

#### POST /api/payment/callback

Payment gateway callback webhook.

#### GET /api/payment/methods

Get available payment methods.

#### POST /api/payment/checkout

Create checkout session.

**Request:**
```json
{
  "plan_id": "premium",
  "customer_id": "customer_123"
}
```

#### GET /api/payment/plans

Get available payment plans.

#### GET /api/payment/analytics/revenue

Get payment revenue analytics.

---

### Invoice API (Router: /api/invoices)

#### POST /api/invoices

Create invoice.

**Request:**
```json
{
  "customer_id": "customer_123",
  "amount": 299000,
  "description": "Premium Plan - March 2026",
  "due_date": "2026-03-31"
}
```

#### GET /api/invoices/{invoice_id}

Get invoice details.

#### GET /api/invoices

List invoices.

**Query Parameters:**
- `customer_id` (optional): Filter by customer
- `status` (optional): Filter by status
- `limit`: Max results

#### PATCH /api/invoices/{invoice_id}

Update invoice.

#### POST /api/invoices/{invoice_id}/issue

Mark invoice as issued.

#### POST /api/invoices/{invoice_id}/cancel

Cancel invoice.

#### POST /api/invoices/webhooks/payment

Payment webhook for invoice updates.

#### GET /api/invoices/analytics/revenue

Get invoice revenue analytics.

---

### Subscription API (Router: /api/subscriptions)

#### GET /api/subscriptions/plans

Get available subscription plans.

#### POST /api/subscriptions

Create subscription.

**Request:**
```json
{
  "customer_id": "customer_123",
  "plan_id": "professional",
  "billing_cycle": "monthly"
}
```

#### GET /api/subscriptions/{subscription_id}

Get subscription details.

#### GET /api/subscriptions/customer/{customer_id}

Get customer's subscription.

#### PATCH /api/subscriptions/{subscription_id}

Update subscription.

#### POST /api/subscriptions/{subscription_id}/cancel

Cancel subscription.

#### POST /api/subscriptions/{subscription_id}/usage

Record usage.

#### GET /api/subscriptions/{subscription_id}/usage/check

Check usage limits.

#### GET /api/subscriptions

List all subscriptions.

#### POST /api/subscriptions/webhooks/payment

Payment webhook for subscription updates.

---

### Billing API (Router: /api/billing)

#### GET /api/billing/plans

Get billing plans.

#### GET /api/billing/subscription/{customer_id}

Get customer subscription.

#### POST /api/billing/subscription/upgrade

Upgrade subscription.

**Request:**
```json
{
  "customer_id": "customer_123",
  "new_plan_id": "enterprise"
}
```

#### POST /api/billing/subscription/cancel

Cancel subscription.

#### GET /api/billing/usage/{customer_id}

Get usage records.

#### GET /api/billing/invoices/{customer_id}

Get customer invoices.

#### GET /api/billing/invoice/{invoice_id}

Get invoice details.

#### GET /api/billing/payment-methods/{customer_id}

Get customer payment methods.

#### POST /api/billing/payment-methods

Add payment method.

#### DELETE /api/billing/payment-methods/{payment_method_id}

Remove payment method.

---

### Feedback API (Router: /api/feedback)

#### POST /api/feedback

Submit feedback.

**Request:**
```json
{
  "customer_id": "customer_123",
  "type": "nps",
  "rating": 9,
  "comment": "Great service!"
}
```

#### GET /api/feedback/{feedback_id}

Get feedback details.

#### GET /api/feedback

List feedback.

**Query Parameters:**
- `customer_id` (optional): Filter by customer
- `type` (optional): Filter by type (nps, csat, ces)
- `limit`: Max results

#### GET /api/feedback/analytics/nps

Get NPS analytics.

**Response:**
```json
{
  "nps_score": 45,
  "total_responses": 100,
  "promoters": 60,
  "passives": 30,
  "detractors": 10
}
```

#### GET /api/feedback/analytics/satisfaction

Get satisfaction analytics.

#### POST /api/feedback/surveys/nps

Create NPS survey.

#### POST /api/feedback/surveys/{survey_id}/respond

Respond to survey.

#### GET /api/feedback/surveys/{survey_id}

Get survey details.

#### GET /api/feedback/surveys

List surveys.

---

### Onboarding API (Router: /api/onboarding)

#### GET /api/onboarding/steps

Get onboarding steps.

**Response:**
```json
[
  {
    "step_id": "step_1",
    "title": "Create Account",
    "description": "Sign up for an account",
    "order": 1
  }
]
```

#### GET /api/onboarding/progress/{customer_id}

Get customer onboarding progress.

**Response:**
```json
{
  "customer_id": "customer_123",
  "current_step": 2,
  "completed_steps": [1],
  "started_at": "2026-03-20T00:00:00"
}
```

#### POST /api/onboarding/action

Complete an onboarding action.

**Request:**
```json
{
  "customer_id": "customer_123",
  "step_id": "step_1"
}
```

#### POST /api/onboarding/start/{customer_id}

Start onboarding for customer.

#### POST /api/onboarding/reset/{customer_id}

Reset customer onboarding.

---

### Monitoring API (Router: /api/monitoring)

#### GET /api/monitoring/health

Get monitoring health status.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-03-20T00:00:00",
  "services": {...}
}
```

#### GET /api/monitoring/stats

Get API stats.

**Response:**
```json
{
  "total_requests": 1000,
  "avg_latency_ms": 150,
  "error_rate": 0.01
}
```

#### GET /api/monitoring/stats/{endpoint}

Get stats for specific endpoint.

#### GET /api/monitoring/errors

Get recent errors.

#### POST /api/monitoring/clear

Clear monitoring data.

#### GET /api/monitoring/latency/{endpoint}

Get latency for endpoint.

---

### Revenue Report API (Router: /api/revenue)

#### GET /api/revenue/revenue/weekly

Get weekly revenue report.

#### GET /api/revenue/revenue/latest

Get latest revenue data.

#### GET /api/revenue/revenue/history

Get revenue history.

---

## Error Codes

| Code | Description |
|------|-------------|
| 400 | Bad Request - Invalid input |
| 404 | Not Found - Resource not found |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

## Rate Limits

Currently no rate limits. Future versions may implement rate limiting.

## Webhooks

### Payment Webhooks

Endpoint: POST /api/payment/callback

Payload varies by payment gateway (VietQR, MoMo, ZaloPay).

### Subscription Webhooks

Endpoint: POST /api/subscriptions/webhooks/payment

---

## Example Requests

### cURL Examples

```bash
# Health check
curl -X GET http://localhost:8000/health

# Create lead
curl -X POST http://localhost:8000/leads \
  -H "Content-Type: application/json" \
  -d '{"name": "John Doe", "email": "john@example.com", "source": "website"}'

# Search
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "AI services", "limit": 5}'

# Track event
curl -X POST http://localhost:8000/tracking/event \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user123", "category": "button", "action": "click", "name": "signup"}'
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| DB_HOST | PostgreSQL host | localhost |
| DB_PORT | PostgreSQL port | 5433 |
| DB_NAME | Database name | promptforge |
| DB_USER | Database user | promptforge |
| DB_PASSWORD | Database password | promptforge123 |
| QDRANT_URL | Qdrant URL | http://localhost:6333 |
| OLLAMA_URL | Ollama URL | http://localhost:11434 |
| MATOMO_URL | Matomo URL | http://localhost:8080 |
| MATOMO_API_TOKEN | Matomo API token | - |
| MATOMO_SITE_ID | Matomo site ID | 1 |