"""
AI City Self-Service Billing Module
Customer billing portal and subscription management
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import uuid

router = APIRouter(prefix="/billing", tags=["billing"])

# ============== Constants ==============

PRICING_PLANS = {
    "starter": {
        "name": "Starter",
        "price_vnd": 299000,
        "api_calls_per_month": 10000,
        "features": ["Basic AI", "Email Support", "5 Team Members"],
    },
    "professional": {
        "name": "Professional",
        "price_vnd": 799000,
        "api_calls_per_month": 50000,
        "features": ["Advanced AI", "Priority Support", "20 Team Members", "Analytics"],
    },
    "enterprise": {
        "name": "Enterprise",
        "price_vnd": 2990000,
        "api_calls_per_month": 200000,
        "features": ["Custom AI", "24/7 Support", "Unlimited Team", "Custom Integrations", "SLA"],
    },
}

# ============== Models ==============

class Subscription(BaseModel):
    subscription_id: str
    customer_id: str
    plan: str
    status: str  # active, cancelled, past_due
    current_period_start: str
    current_period_end: str
    cancel_at_period_end: bool


class Invoice(BaseModel):
    invoice_id: str
    customer_id: str
    amount_vnd: int
    status: str  # draft, issued, paid, cancelled
    created_at: str
    paid_at: Optional[str] = None
    items: List[dict]


class PaymentMethod(BaseModel):
    payment_method_id: str
    type: str  # card, bank, ewallet
    last4: str
    is_default: bool
    expiry_month: Optional[int] = None
    expiry_year: Optional[int] = None


class UsageRecord(BaseModel):
    customer_id: str
    plan: str
    api_calls_used: int
    api_calls_limit: int
    percentage_used: float
    period_start: str
    period_end: str


class UpgradeRequest(BaseModel):
    customer_id: str
    new_plan: str


# ============== In-memory storage (replace with DB) ==============

subscriptions = {}
invoices = {}
payment_methods = {}


# ============== API Endpoints ==============

@router.get("/plans")
async def get_plans():
    """Get available pricing plans"""
    return {
        "plans": [
            {
                "id": plan_id,
                **plan,
                "price_vnd_per_month": plan["price_vnd"],
                "price_display": f"{plan['price_vnd']:,} VND",
            }
            for plan_id, plan in PRICING_PLANS.items()
        ]
    }


@router.get("/subscription/{customer_id}", response_model=Subscription)
async def get_subscription(customer_id: str):
    """Get customer subscription details"""
    if customer_id not in subscriptions:
        # Return default starter subscription
        return Subscription(
            subscription_id=f"sub_{uuid.uuid4().hex[:8]}",
            customer_id=customer_id,
            plan="starter",
            status="active",
            current_period_start=datetime.utcnow().replace(day=1).isoformat(),
            current_period_end=(datetime.utcnow().replace(day=1) + timedelta(days=32)).replace(day=1).isoformat(),
            cancel_at_period_end=False,
        )

    return subscriptions[customer_id]


@router.post("/subscription/upgrade")
async def upgrade_subscription(request: UpgradeRequest):
    """Upgrade or downgrade subscription plan"""
    if request.new_plan not in PRICING_PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    customer_id = request.customer_id
    new_plan = PRICING_PLANS[request.new_plan]

    # Calculate prorated amount
    if customer_id in subscriptions:
        old_plan = subscriptions[customer_id].plan
        days_remaining = (
            datetime.fromisoformat(subscriptions[customer_id].current_period_end) -
            datetime.utcnow()
        ).days

        if days_remaining > 0:
            old_price = PRICING_PLANS[old_plan]["price_vnd"]
            daily_rate = old_price / 30
            credit = int(daily_rate * days_remaining)
            charge = new_plan["price_vnd"] - credit

            # Create invoice for upgrade
            invoice_id = f"inv_{uuid.uuid4().hex[:8]}"
            invoices[invoice_id] = Invoice(
                invoice_id=invoice_id,
                customer_id=customer_id,
                amount_vnd=charge,
                status="pending",
                created_at=datetime.utcnow().isoformat(),
                items=[
                    {
                        "description": f"Plan upgrade: {old_plan} -> {request.new_plan}",
                        "amount_vnd": charge,
                    }
                ],
            )
    else:
        # New subscription - create first invoice
        invoice_id = f"inv_{uuid.uuid4().hex[:8]}"
        invoices[invoice_id] = Invoice(
            invoice_id=invoice_id,
            customer_id=customer_id,
            amount_vnd=new_plan["price_vnd"],
            status="pending",
            created_at=datetime.utcnow().isoformat(),
            items=[
                {
                    "description": f"{new_plan['name']} Plan - First Month",
                    "amount_vnd": new_plan["price_vnd"],
                }
            ],
        )

    # Update subscription
    subscriptions[customer_id] = Subscription(
        subscription_id=subscriptions.get(customer_id, {}).subscription_id or f"sub_{uuid.uuid4().hex[:8]}",
        customer_id=customer_id,
        plan=request.new_plan,
        status="active",
        current_period_start=datetime.utcnow().isoformat(),
        current_period_end=(datetime.utcnow() + timedelta(days=30)).isoformat(),
        cancel_at_period_end=False,
    )

    return {
        "message": f"Successfully upgraded to {new_plan['name']}",
        "subscription": subscriptions[customer_id],
        "invoice_id": invoice_id,
    }


@router.post("/subscription/cancel")
async def cancel_subscription(customer_id: str):
    """Cancel subscription (at period end)"""
    if customer_id not in subscriptions:
        raise HTTPException(status_code=404, detail="No active subscription")

    subscriptions[customer_id].cancel_at_period_end = True
    subscriptions[customer_id].status = "cancelling"

    return {
        "message": "Subscription will be cancelled at period end",
        "cancelled_on": subscriptions[customer_id].current_period_end,
    }


@router.get("/usage/{customer_id}", response_model=UsageRecord)
async def get_usage(customer_id: str):
    """Get current usage for customer"""
    sub = await get_subscription(customer_id)

    # Mock usage data (replace with actual DB query)
    plan_info = PRICING_PLANS.get(sub.plan, PRICING_PLANS["starter"])
    limit = plan_info["api_calls_per_month"]

    # Mock: assume 40% usage
    used = int(limit * 0.4)

    return UsageRecord(
        customer_id=customer_id,
        plan=sub.plan,
        api_calls_used=used,
        api_calls_limit=limit,
        percentage_used=(used / limit * 100) if limit > 0 else 0,
        period_start=sub.current_period_start,
        period_end=sub.current_period_end,
    )


@router.get("/invoices/{customer_id}")
async def get_invoices(customer_id: str):
    """Get invoice history for customer"""
    customer_invoices = [
        inv for inv in invoices.values()
        if inv.customer_id == customer_id
    ]
    return {"invoices": customer_invoices}


@router.get("/invoice/{invoice_id}")
async def get_invoice(invoice_id: str):
    """Get specific invoice"""
    if invoice_id not in invoices:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return invoices[invoice_id]


@router.get("/payment-methods/{customer_id}")
async def get_payment_methods(customer_id: str):
    """Get saved payment methods"""
    methods = payment_methods.get(customer_id, [])
    return {"payment_methods": methods}


@router.post("/payment-methods")
async def add_payment_method(
    customer_id: str,
    type: str,
    last4: str,
    is_default: bool = False,
):
    """Add a payment method"""
    method_id = f"pm_{uuid.uuid4().hex[:8]}"

    if customer_id not in payment_methods:
        payment_methods[customer_id] = []

    # If setting as default, unset others
    if is_default:
        for m in payment_methods[customer_id]:
            m["is_default"] = False

    payment_methods[customer_id].append(PaymentMethod(
        payment_method_id=method_id,
        type=type,
        last4=last4,
        is_default=is_default,
    ).model_dump())

    return {
        "message": "Payment method added",
        "payment_method_id": method_id,
    }


@router.delete("/payment-methods/{payment_method_id}")
async def remove_payment_method(customer_id: str, payment_method_id: str):
    """Remove a payment method"""
    if customer_id not in payment_methods:
        raise HTTPException(status_code=404, detail="No payment methods")

    methods = payment_methods[customer_id]
    payment_methods[customer_id] = [
        m for m in methods
        if m["payment_method_id"] != payment_method_id
    ]

    return {"message": "Payment method removed"}
