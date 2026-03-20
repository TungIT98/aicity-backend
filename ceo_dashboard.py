from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class DashboardData(BaseModel):
    revenue: float = 0
    users: int = 0
    agents_active: int = 0
    leads_total: int = 0
    leads_converted: int = 0

@router.get("/summary")
async def dashboard_summary():
    return {
        "revenue": 0,
        "users": 0,
        "agents_active": 0,
        "leads_total": 0,
        "leads_converted": 0
    }

@router.get("/health")
async def dashboard_health():
    return {"status": "ok"}
