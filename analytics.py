"""
AI City Analytics API Module
Handles analytics endpoints for Telesales, Conversion Funnel, and ROI tracking
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date, timedelta
import psycopg2
import os

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5433")),
    "database": os.getenv("DB_NAME", "promptforge"),
    "user": os.getenv("DB_USER", "promptforge"),
    "password": os.getenv("DB_PASSWORD", "promptforge123"),
}


def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(**DB_CONFIG)


# ================== TELESALES ANALYTICS ==================

class TelesalesSummaryResponse(BaseModel):
    total_calls: int
    successful_calls: int
    conversion_rate: float
    total_revenue: float
    avg_call_duration: float
    calls_per_agent: dict


class CallLog(BaseModel):
    call_id: str
    customer_name: str
    customer_phone: str
    agent_name: str
    call_duration: int
    status: str
    intent: Optional[str] = None
    revenue: Optional[float] = None
    created_at: datetime


class IntentDistribution(BaseModel):
    intent: str
    count: int
    percentage: float


class AgentPerformance(BaseModel):
    agent_id: str
    agent_name: str
    total_calls: int
    successful_calls: int
    conversion_rate: float
    total_revenue: float
    avg_call_duration: float


@router.get("/telesales/summary", response_model=TelesalesSummaryResponse)
async def get_telesales_summary(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD")
):
    """
    Get key metrics for Telesales dashboard.
    Returns: total_calls, successful_calls, conversion_rate, total_revenue, avg_call_duration, calls_per_agent
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Default to last 30 days if no dates provided
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        # Total calls
        cursor.execute("""
            SELECT COUNT(*) FROM telesales_calls
            WHERE created_at::date BETWEEN %s AND %s
        """, (start_date, end_date))
        total_calls = cursor.fetchone()[0] or 0

        # Successful calls (completed with positive outcome)
        cursor.execute("""
            SELECT COUNT(*) FROM telesales_calls
            WHERE created_at::date BETWEEN %s AND %s
            AND status IN ('completed', 'converted')
        """, (start_date, end_date))
        successful_calls = cursor.fetchone()[0] or 0

        # Conversion rate
        conversion_rate = (successful_calls / total_calls * 100) if total_calls > 0 else 0

        # Total revenue from converted calls
        cursor.execute("""
            SELECT COALESCE(SUM(revenue), 0) FROM telesales_calls
            WHERE created_at::date BETWEEN %s AND %s
            AND revenue IS NOT NULL
        """, (start_date, end_date))
        total_revenue = float(cursor.fetchone()[0] or 0)

        # Average call duration
        cursor.execute("""
            SELECT COALESCE(AVG(call_duration), 0) FROM telesales_calls
            WHERE created_at::date BETWEEN %s AND %s
            AND call_duration IS NOT NULL
        """, (start_date, end_date))
        avg_call_duration = float(cursor.fetchone()[0] or 0)

        # Calls per agent
        cursor.execute("""
            SELECT agent_name, COUNT(*) as call_count
            FROM telesales_calls
            WHERE created_at::date BETWEEN %s AND %s
            GROUP BY agent_name
        """, (start_date, end_date))
        agent_calls = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.close()
        conn.close()

        return TelesalesSummaryResponse(
            total_calls=total_calls,
            successful_calls=successful_calls,
            conversion_rate=round(conversion_rate, 2),
            total_revenue=total_revenue,
            avg_call_duration=round(avg_call_duration, 2),
            calls_per_agent=agent_calls
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get telesales summary: {str(e)}")


@router.get("/telesales/calls", response_model=List[CallLog])
async def get_telesales_calls(
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = 0
):
    """
    Get call logs with filters.
    Query params: agent_id, status, start_date, end_date, limit, offset
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        query = """
            SELECT call_id, customer_name, customer_phone, agent_name,
                   call_duration, status, intent, revenue, created_at
            FROM telesales_calls
            WHERE created_at::date BETWEEN %s AND %s
        """
        params = [start_date, end_date]

        if agent_id:
            query += " AND agent_id = %s"
            params.append(agent_id)
        if status:
            query += " AND status = %s"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        calls = [
            CallLog(
                call_id=row[0],
                customer_name=row[1],
                customer_phone=row[2],
                agent_name=row[3],
                call_duration=row[4],
                status=row[5],
                intent=row[6],
                revenue=float(row[7]) if row[7] else None,
                created_at=row[8]
            )
            for row in rows
        ]

        cursor.close()
        conn.close()
        return calls

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get call logs: {str(e)}")


@router.get("/telesales/intents", response_model=List[IntentDistribution])
async def get_telesales_intents(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Get intent distribution for telesales calls.
    Returns: list of intent, count, percentage
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        # Get total count for percentage calculation
        cursor.execute("""
            SELECT COUNT(*) FROM telesales_calls
            WHERE created_at::date BETWEEN %s AND %s
            AND intent IS NOT NULL
        """, (start_date, end_date))
        total = cursor.fetchone()[0] or 0

        # Get intent distribution
        cursor.execute("""
            SELECT intent, COUNT(*) as count
            FROM telesales_calls
            WHERE created_at::date BETWEEN %s AND %s
            AND intent IS NOT NULL
            GROUP BY intent
            ORDER BY count DESC
        """, (start_date, end_date))

        intents = [
            IntentDistribution(
                intent=row[0],
                count=row[1],
                percentage=round(row[1] / total * 100, 2) if total > 0 else 0
            )
            for row in cursor.fetchall()
        ]

        cursor.close()
        conn.close()
        return intents

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get intent distribution: {str(e)}")


@router.get("/telesales/agents", response_model=List[AgentPerformance])
async def get_telesales_agents(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Get agent performance data for telesales.
    Returns: agent_id, agent_name, total_calls, successful_calls, conversion_rate, total_revenue, avg_call_duration
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            SELECT
                agent_id,
                agent_name,
                COUNT(*) as total_calls,
                SUM(CASE WHEN status IN ('completed', 'converted') THEN 1 ELSE 0 END) as successful_calls,
                COALESCE(SUM(revenue), 0) as total_revenue,
                COALESCE(AVG(call_duration), 0) as avg_duration
            FROM telesales_calls
            WHERE created_at::date BETWEEN %s AND %s
            GROUP BY agent_id, agent_name
            ORDER BY total_revenue DESC
        """, (start_date, end_date))

        agents = []
        for row in cursor.fetchall():
            total_calls = row[2] or 0
            successful_calls = row[3] or 0
            conversion_rate = (successful_calls / total_calls * 100) if total_calls > 0 else 0

            agents.append(AgentPerformance(
                agent_id=row[0],
                agent_name=row[1],
                total_calls=total_calls,
                successful_calls=successful_calls,
                conversion_rate=round(conversion_rate, 2),
                total_revenue=float(row[4]),
                avg_call_duration=round(float(row[5]), 2)
            ))

        cursor.close()
        conn.close()
        return agents

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get agent performance: {str(e)}")


# ================== CONVERSION FUNNEL ==================

class FunnelEventRequest(BaseModel):
    """Request model for funnel events"""
    customer_id: str
    event_type: str  # demo_request, trial_signup, payment, churn
    source: Optional[str] = None
    metadata: Optional[dict] = None


class FunnelOverview(BaseModel):
    total_visitors: int
    demo_requests: int
    trial_signups: int
    paid_customers: int
    conversion_rate: float
    dropoff_rates: dict


class DropoffAnalysis(BaseModel):
    stage: str
    from_count: int
    to_count: int
    dropoff_rate: float


class TimingData(BaseModel):
    stage: str
    avg_days: float
    min_days: int
    max_days: int


@router.post("/funnel/event")
async def log_funnel_event(request: FunnelEventRequest):
    """
    Log funnel events (demo_request, trial_signup, payment, churn).
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO funnel_events (customer_id, event_type, source, metadata, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (request.customer_id, request.event_type, request.source, str(request.metadata) if request.metadata else None))

        conn.commit()
        cursor.close()
        conn.close()

        return {"status": "success", "event_id": f"FE-{datetime.now().strftime('%Y%m%d%H%M%S')}"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to log funnel event: {str(e)}")


@router.get("/funnel/overview", response_model=FunnelOverview)
async def get_funnel_overview(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Get funnel metrics summary.
    Returns: total_visitors, demo_requests, trial_signups, paid_customers, conversion_rate, dropoff_rates
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        # Get counts by event type
        cursor.execute("""
            SELECT event_type, COUNT(DISTINCT customer_id)
            FROM funnel_events
            WHERE created_at::date BETWEEN %s AND %s
            GROUP BY event_type
        """, (start_date, end_date))

        event_counts = {row[0]: row[1] for row in cursor.fetchall()}

        total_visitors = event_counts.get("visit", 0)
        demo_requests = event_counts.get("demo_request", 0)
        trial_signups = event_counts.get("trial_signup", 0)
        paid_customers = event_counts.get("payment", 0)

        # Calculate conversion rate (visitors to paid)
        conversion_rate = (paid_customers / total_visitors * 100) if total_visitors > 0 else 0

        # Calculate dropoff rates
        dropoff_rates = {}
        if total_visitors > 0:
            dropoff_rates["visit_to_demo"] = round((total_visitors - demo_requests) / total_visitors * 100, 2)
        if demo_requests > 0:
            dropoff_rates["demo_to_trial"] = round((demo_requests - trial_signups) / demo_requests * 100, 2)
        if trial_signups > 0:
            dropoff_rates["trial_to_paid"] = round((trial_signups - paid_customers) / trial_signups * 100, 2)

        cursor.close()
        conn.close()

        return FunnelOverview(
            total_visitors=total_visitors,
            demo_requests=demo_requests,
            trial_signups=trial_signups,
            paid_customers=paid_customers,
            conversion_rate=round(conversion_rate, 2),
            dropoff_rates=dropoff_rates
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get funnel overview: {str(e)}")


@router.get("/funnel/dropoff", response_model=List[DropoffAnalysis])
async def get_funnel_dropoff(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Get drop-off analysis between funnel stages.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            SELECT event_type, COUNT(DISTINCT customer_id) as count
            FROM funnel_events
            WHERE created_at::date BETWEEN %s AND %s
            GROUP BY event_type
            ORDER BY
                CASE event_type
                    WHEN 'visit' THEN 1
                    WHEN 'demo_request' THEN 2
                    WHEN 'trial_signup' THEN 3
                    WHEN 'payment' THEN 4
                    ELSE 5
                END
        """, (start_date, end_date))

        rows = cursor.fetchall()
        dropoff_analysis = []

        for i in range(len(rows) - 1):
            from_stage = rows[i][0]
            from_count = rows[i][1]
            to_stage = rows[i + 1][0]
            to_count = rows[i + 1][1]

            dropoff_rate = ((from_count - to_count) / from_count * 100) if from_count > 0 else 0

            dropoff_analysis.append(DropoffAnalysis(
                stage=f"{from_stage} -> {to_stage}",
                from_count=from_count,
                to_count=to_count,
                dropoff_rate=round(dropoff_rate, 2)
            ))

        cursor.close()
        conn.close()
        return dropoff_analysis

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dropoff analysis: {str(e)}")


@router.get("/funnel/timing", response_model=List[TimingData])
async def get_funnel_timing(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Get time-to-conversion data between funnel stages.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if not start_date:
            start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        # Calculate timing between stages
        stages = [
            ("demo_request", "trial_signup"),
            ("trial_signup", "payment")
        ]

        timing_data = []
        for from_stage, to_stage in stages:
            cursor.execute("""
                SELECT
                    COALESCE(AVG(DATE_PART('day', to_date.created_at - from_date.created_at)), 0) as avg_days,
                    COALESCE(MIN(DATE_PART('day', to_date.created_at - from_date.created_at)), 0) as min_days,
                    COALESCE(MAX(DATE_PART('day', to_date.created_at - from_date.created_at)), 0) as max_days
                FROM funnel_events from_date
                JOIN funnel_events to_date
                    ON from_date.customer_id = to_date.customer_id
                    AND to_date.event_type = %s
                WHERE from_date.event_type = %s
                AND from_date.created_at::date BETWEEN %s AND %s
            """, (to_stage, from_stage, start_date, end_date))

            row = cursor.fetchone()
            timing_data.append(TimingData(
                stage=f"{from_stage} -> {to_stage}",
                avg_days=round(float(row[0]), 2) if row[0] else 0,
                min_days=int(row[1]) if row[1] else 0,
                max_days=int(row[2]) if row[2] else 0
            ))

        cursor.close()
        conn.close()
        return timing_data

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get timing data: {str(e)}")


# ================== ROI ANALYTICS ==================

class ROIOverview(BaseModel):
    total_revenue: float
    total_costs: float
    net_margin: float
    margin_percentage: float
    active_agents: int


class AgentROI(BaseModel):
    agent_id: str
    agent_name: str
    revenue: float
    costs: float
    roi_percentage: float
    customer_count: int


class ROILeaderboard(BaseModel):
    rank: int
    agent_id: str
    agent_name: str
    roi_percentage: float
    revenue: float


class ROIAlert(BaseModel):
    agent_id: str
    agent_name: str
    alert_type: str
    message: str
    threshold: float
    current_value: float


@router.get("/roi/overview", response_model=ROIOverview)
async def get_roi_overview(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Get ROI summary: total_revenue, total_costs, net_margin, margin_percentage, active_agents
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        # Total revenue
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) FROM revenue_transactions
            WHERE transaction_date BETWEEN %s AND %s AND status = 'completed'
        """, (start_date, end_date))
        total_revenue = float(cursor.fetchone()[0])

        # Total costs (from agent logs or cost tracking)
        cursor.execute("""
            SELECT COALESCE(SUM(cost), 0) FROM agent_costs
            WHERE cost_date BETWEEN %s AND %s
        """, (start_date, end_date))
        total_costs = float(cursor.fetchone()[0])

        # Net margin
        net_margin = total_revenue - total_costs

        # Margin percentage
        margin_percentage = (net_margin / total_revenue * 100) if total_revenue > 0 else 0

        # Active agents
        cursor.execute("""
            SELECT COUNT(DISTINCT agent_id) FROM agent_usage
            WHERE used_at::date BETWEEN %s AND %s
        """, (start_date, end_date))
        active_agents = cursor.fetchone()[0] or 0

        cursor.close()
        conn.close()

        return ROIOverview(
            total_revenue=total_revenue,
            total_costs=total_costs,
            net_margin=net_margin,
            margin_percentage=round(margin_percentage, 2),
            active_agents=active_agents
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get ROI overview: {str(e)}")


@router.get("/roi/agents", response_model=List[AgentROI])
async def get_roi_by_agents(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Get per-agent ROI metrics.
    Returns: agent_id, agent_name, revenue, costs, roi_percentage, customer_count
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            SELECT
                a.agent_id,
                a.agent_name,
                COALESCE(SUM(r.amount), 0) as revenue,
                COALESCE(SUM(a.cost), 0) as costs,
                COUNT(DISTINCT r.customer_email) as customer_count
            FROM agents a
            LEFT JOIN revenue_transactions r
                ON a.agent_id = r.agent_id
                AND r.transaction_date BETWEEN %s AND %s
                AND r.status = 'completed'
            LEFT JOIN agent_costs ac
                ON a.agent_id = ac.agent_id
                AND ac.cost_date BETWEEN %s AND %s
            GROUP BY a.agent_id, a.agent_name
            ORDER BY revenue DESC
        """, (start_date, end_date, start_date, end_date))

        agents = []
        for row in cursor.fetchall():
            revenue = float(row[2])
            costs = float(row[3])
            roi = ((revenue - costs) / costs * 100) if costs > 0 else 0

            agents.append(AgentROI(
                agent_id=row[0],
                agent_name=row[1],
                revenue=revenue,
                costs=costs,
                roi_percentage=round(roi, 2),
                customer_count=row[4]
            ))

        cursor.close()
        conn.close()
        return agents

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get agent ROI: {str(e)}")


@router.get("/roi/leaderboard", response_model=List[ROILeaderboard])
async def get_roi_leaderboard(
    limit: int = Query(10, le=50),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Get agent rankings by ROI performance.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            SELECT
                a.agent_id,
                a.agent_name,
                COALESCE(SUM(r.amount), 0) as revenue,
                COALESCE(SUM(ac.cost), 0) as costs
            FROM agents a
            LEFT JOIN revenue_transactions r
                ON a.agent_id = r.agent_id
                AND r.transaction_date BETWEEN %s AND %s
                AND r.status = 'completed'
            LEFT JOIN agent_costs ac
                ON a.agent_id = ac.agent_id
                AND ac.cost_date BETWEEN %s AND %s
            GROUP BY a.agent_id, a.agent_name
            HAVING COALESCE(SUM(ac.cost), 0) > 0
            ORDER BY (
                (COALESCE(SUM(r.amount), 0) - COALESCE(SUM(ac.cost), 0)) / COALESCE(SUM(ac.cost), 0)
            ) DESC
            LIMIT %s
        """, (start_date, end_date, start_date, end_date, limit))

        leaderboard = []
        rank = 1
        for row in cursor.fetchall():
            revenue = float(row[2])
            costs = float(row[3])
            roi = ((revenue - costs) / costs * 100) if costs > 0 else 0

            leaderboard.append(ROILeaderboard(
                rank=rank,
                agent_id=row[0],
                agent_name=row[1],
                roi_percentage=round(roi, 2),
                revenue=revenue
            ))
            rank += 1

        cursor.close()
        conn.close()
        return leaderboard

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get ROI leaderboard: {str(e)}")


@router.get("/roi/alerts", response_model=List[ROIAlert])
async def get_roi_alerts(
    cost_threshold: float = Query(1000, description="Alert if costs exceed this amount")
):
    """
    Get cost threshold alerts for agents.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                a.agent_id,
                a.agent_name,
                SUM(ac.cost) as total_costs
            FROM agents a
            JOIN agent_costs ac ON a.agent_id = ac.agent_id
            WHERE ac.cost_date >= DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY a.agent_id, a.agent_name
            HAVING SUM(ac.cost) > %s
        """, (cost_threshold,))

        alerts = []
        for row in cursor.fetchall():
            alerts.append(ROIAlert(
                agent_id=row[0],
                agent_name=row[1],
                alert_type="cost_threshold_exceeded",
                message=f"Agent {row[1]} has exceeded monthly cost threshold",
                threshold=cost_threshold,
                current_value=float(row[2])
            ))

        cursor.close()
        conn.close()
        return alerts

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get ROI alerts: {str(e)}")