"""
AI City Agents API Module
Handles agent management endpoints.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta

from storage.database import async_session
from sqlalchemy import text

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ---- Models ----

class AgentInfo(BaseModel):
    agent_id: str
    name: str
    role: str
    status: str
    last_heartbeat: Optional[str] = None
    created_at: Optional[str] = None


class AgentUsage(BaseModel):
    agent_id: str
    name: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    avg_response_time_ms: float
    total_runs: int


class AgentsResponse(BaseModel):
    agents: List[AgentInfo]
    total: int


class AgentUsageResponse(BaseModel):
    usage: List[AgentUsage]
    period_start: str
    period_end: str


# ---- Endpoints ----

@router.get("", response_model=AgentsResponse)
async def list_agents(
    status: Optional[str] = Query(None, description="Filter by status: running, idle, paused"),
):
    """List all agents in the system."""
    try:
        async with async_session() as session:
            query = text("""
                SELECT id, name, role, status, last_heartbeat_at, created_at
                FROM agents
                ORDER BY created_at DESC
            """)
            result = await session.execute(query)
            rows = result.fetchall()

            agents = []
            for r in rows:
                agent = AgentInfo(
                    agent_id=str(r[0]),
                    name=r[1] or "Unknown",
                    role=r[2] or "unknown",
                    status=r[3] or "unknown",
                    last_heartbeat=str(r[4]) if r[4] else None,
                    created_at=str(r[5]) if r[5] else None,
                )
                if status is None or agent.status == status:
                    agents.append(agent)

            return AgentsResponse(agents=agents, total=len(agents))

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list agents: {str(e)}")


@router.get("/usage", response_model=AgentUsageResponse)
async def get_agent_usage(
    period_days: int = Query(30, description="Number of days to look back"),
):
    """Get usage statistics for all agents."""
    try:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=period_days)).strftime("%Y-%m-%d")

        async with async_session() as session:
            result = await session.execute(
                text("""
                    SELECT
                        a.id,
                        a.name,
                        COALESCE(a.role, 'unknown') as role,
                        COALESCE(a.status, 'unknown') as status,
                        COUNT(r.id)                                           AS total_tasks,
                        COUNT(CASE WHEN r.status = 'done' THEN 1 END)         AS completed,
                        COUNT(CASE WHEN r.status = 'failed' THEN 1 END)       AS failed,
                        COALESCE(AVG(EXTRACT(EPOCH FROM (r.finished_at - r.started_at)) * 1000), 0) AS avg_ms,
                        COUNT(DISTINCT r.id)                                  AS total_runs
                    FROM agents a
                    LEFT JOIN runs r ON r.agent_id = a.id
                        AND DATE(r.started_at) BETWEEN :start_date AND :end_date
                    GROUP BY a.id, a.name, a.role, a.status
                    ORDER BY total_tasks DESC
                """),
                {"start_date": start_date, "end_date": end_date}
            )
            rows = result.fetchall()

            usage = [
                AgentUsage(
                    agent_id=str(r[0]),
                    name=r[1] or "Unknown",
                    total_tasks=r[4] or 0,
                    completed_tasks=r[5] or 0,
                    failed_tasks=r[6] or 0,
                    avg_response_time_ms=round(float(r[7] or 0), 2),
                    total_runs=r[8] or 0,
                )
                for r in rows
            ]

            return AgentUsageResponse(
                usage=usage,
                period_start=start_date,
                period_end=end_date,
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get agent usage: {str(e)}")
