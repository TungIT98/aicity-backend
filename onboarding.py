"""
AI City Onboarding Module
Interactive onboarding flow with progress tracking
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# ============== Models ==============

class OnboardingStep(BaseModel):
    step_id: str
    name: str
    description: str
    order: int
    status: str  # pending, in_progress, completed
    completed_at: Optional[str] = None


class OnboardingProgress(BaseModel):
    customer_id: str
    total_steps: int
    completed_steps: int
    progress_percentage: float
    current_step: Optional[OnboardingStep]
    started_at: str
    estimated_completion: Optional[str]


class OnboardingAction(BaseModel):
    customer_id: str
    step_id: str
    action: str  # start, complete, skip


# ============== Default Onboarding Steps ==============

DEFAULT_STEPS = [
    {
        "step_id": "welcome",
        "name": "Welcome to AI City",
        "description": "Get started with your account setup",
        "order": 1,
    },
    {
        "step_id": "profile",
        "name": "Configure Your Profile",
        "description": "Set up your company information and preferences",
        "order": 2,
    },
    {
        "step_id": "first_api",
        "name": "Make Your First API Call",
        "description": "Test the AI API with a simple request",
        "order": 3,
    },
    {
        "step_id": "team",
        "name": "Invite Your Team",
        "description": "Collaborate with your team members",
        "order": 4,
    },
    {
        "step_id": "integrations",
        "name": "Connect Integrations",
        "description": "Link your existing tools",
        "order": 5,
    },
    {
        "step_id": "complete",
        "name": "Onboarding Complete",
        "description": "You're ready to succeed with AI City",
        "order": 6,
    },
]

# ============== In-memory storage (replace with DB in production) ==============

onboarding_progress = {}


# ============== API Endpoints ==============

@router.get("/steps", response_model=List[OnboardingStep])
async def get_onboarding_steps():
    """Get all available onboarding steps"""
    return [
        {**step, "status": "available", "completed_at": None}
        for step in DEFAULT_STEPS
    ]


@router.get("/progress/{customer_id}", response_model=OnboardingProgress)
async def get_progress(customer_id: str):
    """Get onboarding progress for a customer"""
    if customer_id not in onboarding_progress:
        # Initialize new onboarding
        onboarding_progress[customer_id] = {
            "started_at": datetime.utcnow().isoformat(),
            "steps": [
                {**step, "status": "pending", "completed_at": None}
                for step in DEFAULT_STEPS
            ],
        }

    progress = onboarding_progress[customer_id]
    steps = progress["steps"]

    completed_count = sum(1 for s in steps if s["status"] == "completed")
    total = len(steps)

    current = next(
        (OnboardingStep(**s) for s in steps if s["status"] in ["pending", "in_progress"]),
        None
    )

    # Estimate completion (1 day per step on average)
    if completed_count < total:
        days_remaining = total - completed_count
        from datetime import timedelta
        estimated = (
            datetime.utcnow() + timedelta(days=days_remaining)
        ).isoformat()
    else:
        estimated = None

    return OnboardingProgress(
        customer_id=customer_id,
        total_steps=total,
        completed_steps=completed_count,
        progress_percentage=(completed_count / total) * 100 if total > 0 else 0,
        current_step=current,
        started_at=progress["started_at"],
        estimated_completion=estimated,
    )


@router.post("/action")
async def take_action(action: OnboardingAction):
    """Take an action on an onboarding step"""
    customer_id = action.customer_id

    if customer_id not in onboarding_progress:
        raise HTTPException(
            status_code=404,
            detail="Onboarding not found. Please start fresh."
        )

    progress = onboarding_progress[customer_id]
    steps = progress["steps"]

    # Find the step
    step = next((s for s in steps if s["step_id"] == action.step_id), None)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    if action.action == "start":
        step["status"] = "in_progress"
        return {
            "message": f"Started: {step['name']}",
            "step": step,
        }

    elif action.action == "complete":
        step["status"] = "completed"
        step["completed_at"] = datetime.utcnow().isoformat()

        # Auto-start next step
        current_order = step["order"]
        next_step = next(
            (s for s in steps if s["order"] == current_order + 1),
            None
        )
        if next_step and next_step["status"] == "pending":
            next_step["status"] = "in_progress"

        return {
            "message": f"Completed: {step['name']}",
            "completed_steps": sum(1 for s in steps if s["status"] == "completed"),
            "total_steps": len(steps),
        }

    elif action.action == "skip":
        step["status"] = "skipped"
        step["completed_at"] = datetime.utcnow().isoformat()

        # Auto-start next step
        current_order = step["order"]
        next_step = next(
            (s for s in steps if s["order"] == current_order + 1),
            None
        )
        if next_step and next_step["status"] == "pending":
            next_step["status"] = "in_progress"

        return {
            "message": f"Skipped: {step['name']}",
            "step": step,
        }

    else:
        raise HTTPException(status_code=400, detail="Invalid action")


@router.post("/start/{customer_id}")
async def start_onboarding(customer_id: str):
    """Start onboarding for a new customer"""
    if customer_id in onboarding_progress:
        return {
            "message": "Onboarding already in progress",
            "progress": await get_progress(customer_id),
        }

    onboarding_progress[customer_id] = {
        "started_at": datetime.utcnow().isoformat(),
        "steps": [
            {**step, "status": "in_progress" if step["order"] == 1 else "pending", "completed_at": None}
            for step in DEFAULT_STEPS
        ],
    }

    return {
        "message": "Onboarding started",
        "progress": await get_progress(customer_id),
    }


@router.post("/reset/{customer_id}")
async def reset_onboarding(customer_id: str):
    """Reset onboarding progress"""
    onboarding_progress[customer_id] = {
        "started_at": datetime.utcnow().isoformat(),
        "steps": [
            {**step, "status": "in_progress" if step["order"] == 1 else "pending", "completed_at": None}
            for step in DEFAULT_STEPS
        ],
    }

    return {
        "message": "Onboarding reset",
        "progress": await get_progress(customer_id),
    }
