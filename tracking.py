"""
Matomo Tracking Module
Track user behavior: page views, feature usage, conversions, revenue
"""

import requests
import hashlib
import os
from typing import Optional, Dict, Any
from datetime import datetime

# Matomo configuration
MATOMO_URL = os.getenv("MATOMO_URL", "http://localhost:8080")
MATOMO_SITE_ID = os.getenv("MATOMO_SITE_ID", "1")
MATOMO_TOKEN = os.getenv("MATOMO_TOKEN", "")  # For Tracking API (if needed)


def get_matomo_tracking_url() -> str:
    """Get Matomo tracking endpoint URL"""
    return f"{MATOMO_URL}/matomo.php"


def generate_visitor_id(user_id: Optional[str] = None) -> str:
    """Generate a unique visitor ID for tracking"""
    if user_id:
        # Create consistent ID from user_id
        hash_obj = hashlib.md5(user_id.encode())
        return hash_obj.hexdigest()[:16]
    else:
        # Generate random visitor ID
        import uuid
        return uuid.uuid4().hex[:16]


def track_page_view(
    user_id: Optional[str] = None,
    page_url: str = "/",
    page_title: Optional[str] = None,
    referrer: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
) -> bool:
    """
    Track page view in Matomo

    Args:
        user_id: Unique user identifier
        page_url: Page URL being viewed
        page_title: Page title
        referrer: Referring URL
        ip_address: User's IP address
        user_agent: User's browser agent

    Returns:
        bool: Success status
    """
    try:
        visitor_id = generate_visitor_id(user_id)

        params = {
            "idsite": MATOMO_SITE_ID,
            "rec": "1",
            "url": page_url,
            "urlref": referrer or "",
            "cid": visitor_id,
            "uid": user_id or "",
            "action_name": page_title or "",
            "h": datetime.now().hour,
            "m": datetime.now().minute,
            "s": datetime.now().second,
        }

        if ip_address:
            params["cip"] = ip_address
        if user_agent:
            params["ua"] = user_agent

        response = requests.get(
            get_matomo_tracking_url(),
            params=params,
            timeout=5
        )

        return response.status_code == 200
    except Exception as e:
        print(f"Page view tracking error: {e}")
        return False


def track_event(
    user_id: Optional[str],
    category: str,
    action: str,
    name: Optional[str] = None,
    value: Optional[float] = None,
    ip_address: Optional[str] = None
) -> bool:
    """
    Track custom event in Matomo (for feature usage tracking)

    Args:
        user_id: User identifier
        category: Event category (e.g., 'feature', 'button', 'form')
        action: Event action (e.g., 'click', 'submit', 'use')
        name: Event name (e.g., 'search', 'export')
        value: Optional numeric value
        ip_address: User's IP

    Returns:
        bool: Success status
    """
    try:
        visitor_id = generate_visitor_id(user_id)

        params = {
            "idsite": MATOMO_SITE_ID,
            "rec": "1",
            "e_c": category,
            "e_a": action,
            "cid": visitor_id,
            "uid": user_id or "",
        }

        if name:
            params["e_n"] = name
        if value is not None:
            params["e_v"] = value
        if ip_address:
            params["cip"] = ip_address

        response = requests.get(
            get_matomo_tracking_url(),
            params=params,
            timeout=5
        )

        return response.status_code == 200
    except Exception as e:
        print(f"Event tracking error: {e}")
        return False


def track_conversion(
    user_id: str,
    goal_id: int,
    revenue: float = 0,
    ip_address: Optional[str] = None
) -> bool:
    """
    Track conversion goal in Matomo

    Args:
        user_id: User identifier
        goal_id: Matomo goal ID
        revenue: Revenue amount
        ip_address: User's IP

    Returns:
        bool: Success status
    """
    try:
        visitor_id = generate_visitor_id(user_id)

        params = {
            "idsite": MATOMO_SITE_ID,
            "rec": "1",
            "cid": visitor_id,
            "uid": user_id,
            "idgoal": goal_id,
        }

        if revenue > 0:
            params["revenue"] = revenue

        if ip_address:
            params["cip"] = ip_address

        response = requests.get(
            get_matomo_tracking_url(),
            params=params,
            timeout=5
        )

        return response.status_code == 200
    except Exception as e:
        print(f"Conversion tracking error: {e}")
        return False


def track_transaction(
    user_id: str,
    order_id: str,
    total: float,
    items: Optional[list] = None,
    ip_address: Optional[str] = None
) -> bool:
    """
    Track ecommerce transaction in Matomo

    Args:
        user_id: User identifier
        order_id: Unique order ID
        total: Total transaction amount
        items: List of items (dict with id, name, price, qty)
        ip_address: User's IP

    Returns:
        bool: Success status
    """
    try:
        visitor_id = generate_visitor_id(user_id)

        params = {
            "idsite": MATOMO_SITE_ID,
            "rec": "1",
            "cid": visitor_id,
            "uid": user_id,
            "ec": "order",  # ecommerce
            "eid": order_id,
            "trt": total,  # transaction total
        }

        if items:
            # Add items as JSON in the parameter
            import json
            params["ec_items"] = json.dumps(items)

        if ip_address:
            params["cip"] = ip_address

        response = requests.get(
            get_matomo_tracking_url(),
            params=params,
            timeout=5
        )

        return response.status_code == 200
    except Exception as e:
        print(f"Transaction tracking error: {e}")
        return False


# Conversion funnel stages
FUNNEL_STAGES = {
    "landing": 1,
    "signup_start": 2,
    "signup_complete": 3,
    "onboarding_start": 4,
    "onboarding_complete": 5,
    "first_feature_use": 6,
    "subscription_start": 7,
    "subscription_renewal": 8
}


def track_funnel_stage(
    user_id: str,
    stage: str,
    metadata: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None
) -> bool:
    """
    Track conversion funnel progression

    Args:
        user_id: User identifier
        stage: Funnel stage (see FUNNEL_STAGES)
        metadata: Additional data for this stage
        ip_address: User's IP

    Returns:
        bool: Success status
    """
    if stage not in FUNNEL_STAGES:
        print(f"Unknown funnel stage: {stage}")
        return False

    goal_id = FUNNEL_STAGES[stage]
    revenue = 0

    # Calculate revenue for paid stages
    if stage in ("subscription_start", "subscription_renewal"):
        if metadata and "amount" in metadata:
            revenue = metadata["amount"]

    return track_conversion(
        user_id=user_id,
        goal_id=goal_id,
        revenue=revenue,
        ip_address=ip_address
    )


# Feature tracking helpers
def track_feature_used(user_id: str, feature_name: str, ip_address: Optional[str] = None) -> bool:
    """Track feature usage"""
    return track_event(
        user_id=user_id,
        category="feature",
        action="use",
        name=feature_name,
        ip_address=ip_address
    )


def track_button_click(user_id: str, button_name: str, page: str, ip_address: Optional[str] = None) -> bool:
    """Track button click"""
    return track_event(
        user_id=user_id,
        category="button",
        action="click",
        name=f"{page}:{button_name}",
        ip_address=ip_address
    )


def track_form_submit(user_id: str, form_name: str, success: bool, ip_address: Optional[str] = None) -> bool:
    """Track form submission"""
    return track_event(
        user_id=user_id,
        category="form",
        action="submit" if success else "error",
        name=form_name,
        ip_address=ip_address
    )


def track_search(user_id: str, query: str, results_count: int, ip_address: Optional[str] = None) -> bool:
    """Track search usage"""
    return track_event(
        user_id=user_id,
        category="search",
        action="query",
        name=query[:100],  # Limit length
        value=results_count,
        ip_address=ip_address
    )


def track_api_call(user_id: str, endpoint: str, method: str, status_code: int, duration_ms: int, ip_address: Optional[str] = None) -> bool:
    """Track API usage"""
    return track_event(
        user_id=user_id,
        category="api",
        action=f"{method}:{status_code}",
        name=endpoint,
        value=duration_ms,
        ip_address=ip_address
    )


if __name__ == "__main__":
    # Test tracking
    print("Testing Matomo tracking...")

    # Test page view
    result = track_page_view(
        user_id="test-user-123",
        page_url="/dashboard",
        page_title="Dashboard"
    )
    print(f"Page view: {result}")

    # Test event
    result = track_event(
        user_id="test-user-123",
        category="feature",
        action="use",
        name="search"
    )
    print(f"Event: {result}")

    # Test funnel
    result = track_funnel_stage(
        user_id="test-user-123",
        stage="signup_complete"
    )
    print(f"Funnel: {result}")