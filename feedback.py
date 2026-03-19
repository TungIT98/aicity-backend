"""
AI City Feedback Collection Module
NPS surveys, customer satisfaction tracking, feedback forms
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import uuid
import json
import psycopg2

router = APIRouter(prefix="/feedback", tags=["feedback"])

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "database": "promptforge",
    "user": "promptforge",
    "password": "promptforge123",
}


# ============== Models ==============

class FeedbackCreate(BaseModel):
    customer_id: Optional[str] = None
    customer_email: Optional[str] = None
    feedback_type: str  # nps, satisfaction, general, bug, feature_request
    rating: Optional[int] = None  # 0-10 for NPS
    category: Optional[str] = None
    title: str
    message: str
    metadata: Optional[dict] = {}


class FeedbackResponse(BaseModel):
    feedback_id: str
    customer_id: Optional[str]
    customer_email: Optional[str]
    feedback_type: str
    rating: Optional[int]
    category: Optional[str]
    title: str
    message: str
    status: str
    created_at: str


class SurveyResponse(BaseModel):
    survey_id: str
    survey_type: str  # nps, csat
    customer_email: Optional[str]
    questions: List[dict]
    response: Optional[dict]
    status: str
    created_at: str


# ============== Helper Functions ==============

def get_db():
    """Database connection"""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def init_feedback_db():
    """Initialize feedback tables"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # Feedback table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id SERIAL PRIMARY KEY,
            feedback_id VARCHAR(50) UNIQUE NOT NULL,
            customer_id VARCHAR(100),
            customer_email VARCHAR(255),
            feedback_type VARCHAR(20) NOT NULL,
            rating INTEGER,
            category VARCHAR(50),
            title VARCHAR(255) NOT NULL,
            message TEXT NOT NULL,
            status VARCHAR(20) DEFAULT 'new',
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_customer ON feedback(customer_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback(feedback_type)
    """)

    # Surveys table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS surveys (
            id SERIAL PRIMARY KEY,
            survey_id VARCHAR(50) UNIQUE NOT NULL,
            survey_type VARCHAR(20) NOT NULL,
            customer_id VARCHAR(100),
            customer_email VARCHAR(255),
            questions JSONB NOT NULL,
            response JSONB,
            status VARCHAR(20) DEFAULT 'pending',
            sent_at TIMESTAMP,
            responded_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_surveys_customer ON surveys(customer_id)
    """)

    conn.commit()
    cursor.close()
    conn.close()


def generate_feedback_id():
    return f"FB-{uuid.uuid4().hex[:10].upper()}"


def generate_survey_id():
    return f"SUR-{uuid.uuid4().hex[:10].upper()}"


def calculate_nps_score(feedbacks: list) -> dict:
    """Calculate NPS score from feedback ratings"""
    if not feedbacks:
        return {"nps": 0, "promoters": 0, "passives": 0, "detractors": 0}

    promoters = sum(1 for f in feedbacks if f.get("rating", 0) >= 9)
    detractors = sum(1 for f in feedbacks if f.get("rating", 0) <= 6)
    passives = len(feedbacks) - promoters - detractors

    nps = ((promoters - detractors) / len(feedbacks)) * 100 if feedbacks else 0

    return {
        "nps": round(nps, 1),
        "promoters": promoters,
        "passives": passives,
        "detractors": detractors,
        "total": len(feedbacks)
    }


# ============== API Endpoints ==============

@router.on_event("startup")
async def init_feedback():
    """Initialize feedback tables on startup"""
    init_feedback_db()


@router.post("/", response_model=FeedbackResponse)
async def create_feedback(feedback: FeedbackCreate):
    """Create new feedback"""
    try:
        feedback_id = generate_feedback_id()

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO feedback (
                feedback_id, customer_id, customer_email, feedback_type,
                rating, category, title, message, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING feedback_id, customer_id, customer_email, feedback_type,
                      rating, category, title, message, status, created_at
        """, (
            feedback_id, feedback.customer_id, feedback.customer_email,
            feedback.feedback_type, feedback.rating, feedback.category,
            feedback.title, feedback.message, json.dumps(feedback.metadata)
        ))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return FeedbackResponse(
            feedback_id=result[0],
            customer_id=result[1],
            customer_email=result[2],
            feedback_type=result[3],
            rating=result[4],
            category=result[5],
            title=result[6],
            message=result[7],
            status=result[8],
            created_at=str(result[9])
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{feedback_id}", response_model=FeedbackResponse)
async def get_feedback(feedback_id: str):
    """Get feedback details"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT feedback_id, customer_id, customer_email, feedback_type,
                   rating, category, title, message, status, created_at
            FROM feedback WHERE feedback_id = %s
        """, (feedback_id,))

        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if not result:
            raise HTTPException(status_code=404, detail="Feedback not found")

        return FeedbackResponse(
            feedback_id=result[0],
            customer_id=result[1],
            customer_email=result[2],
            feedback_type=result[3],
            rating=result[4],
            category=result[5],
            title=result[6],
            message=result[7],
            status=result[8],
            created_at=str(result[9])
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_feedback(
    feedback_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50
):
    """List feedback with optional filters"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        query = """
            SELECT feedback_id, customer_id, customer_email, feedback_type,
                   rating, category, title, message, status, created_at
            FROM feedback WHERE 1=1
        """
        params = []

        if feedback_type:
            query += " AND feedback_type = %s"
            params.append(feedback_type)
        if status:
            query += " AND status = %s"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        conn.close()

        return {
            "feedback": [
                {
                    "feedback_id": r[0],
                    "customer_id": r[1],
                    "customer_email": r[2],
                    "feedback_type": r[3],
                    "rating": r[4],
                    "category": r[5],
                    "title": r[6],
                    "message": r[7],
                    "status": r[8],
                    "created_at": str(r[9])
                }
                for r in results
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/nps")
async def get_nps_analytics():
    """Get NPS analytics"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Get all NPS feedback
        cursor.execute("""
            SELECT customer_id, rating FROM feedback
            WHERE feedback_type = 'nps' AND rating IS NOT NULL
        """)

        feedbacks = [{"customer_id": r[0], "rating": r[1]} for r in cursor.fetchall()]
        nps_data = calculate_nps_score(feedbacks)

        # NPS by period
        cursor.execute("""
            SELECT DATE_TRUNC('week', created_at) as week,
                   COUNT(*) as count,
                   AVG(rating) as avg_rating
            FROM feedback
            WHERE feedback_type = 'nps' AND rating IS NOT NULL
            GROUP BY DATE_TRUNC('week', created_at)
            ORDER BY week
            LIMIT 12
        """)

        weekly = [
            {"week": str(r[0]), "count": r[1], "avg_rating": float(r[2]) if r[2] else 0}
            for r in cursor.fetchall()
        ]

        cursor.close()
        conn.close()

        return {
            "nps": nps_data,
            "weekly": weekly
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/satisfaction")
async def get_satisfaction_analytics():
    """Get customer satisfaction analytics"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Overall satisfaction
        cursor.execute("""
            SELECT AVG(rating), COUNT(*)
            FROM feedback
            WHERE feedback_type IN ('satisfaction', 'nps')
            AND rating IS NOT NULL
        """)

        result = cursor.fetchone()
        avg_rating = float(result[0]) if result[0] else 0
        total = result[1]

        # By category
        cursor.execute("""
            SELECT category, AVG(rating), COUNT(*)
            FROM feedback
            WHERE category IS NOT NULL AND rating IS NOT NULL
            GROUP BY category
        """)

        by_category = [
            {"category": r[0], "avg_rating": float(r[1]), "count": r[2]}
            for r in cursor.fetchall()
        ]

        cursor.close()
        conn.close()

        return {
            "average_satisfaction": round(avg_rating, 2),
            "total_responses": total,
            "by_category": by_category
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Survey Management ==============

@router.post("/surveys/nps")
async def create_nps_survey(customer_email: str, customer_id: str = None):
    """Create NPS survey for a customer"""
    try:
        survey_id = generate_survey_id()

        questions = [
            {
                "id": "nps",
                "type": "nps",
                "question": "How likely are you to recommend AI City to a friend or colleague?",
                "scale": "0-10"
            },
            {
                "id": "reason",
                "type": "text",
                "question": "What is the primary reason for your score?"
            }
        ]

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO surveys (
                survey_id, survey_type, customer_id, customer_email, questions
            ) VALUES (%s, %s, %s, %s, %s)
            RETURNING survey_id, survey_type, customer_email, status, created_at
        """, (survey_id, "nps", customer_id, customer_email, json.dumps(questions)))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return {
            "survey_id": result[0],
            "survey_type": result[1],
            "customer_email": result[2],
            "status": result[3],
            "created_at": str(result[4]),
            "questions": questions,
            "survey_url": f"/feedback/surveys/{survey_id}/respond"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/surveys/{survey_id}/respond")
async def respond_survey(survey_id: str, response: dict):
    """Submit survey response"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE surveys
            SET response = %s, status = 'completed', responded_at = NOW()
            WHERE survey_id = %s AND status = 'pending'
            RETURNING survey_id, status
        """, (json.dumps(response), survey_id))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not result:
            raise HTTPException(status_code=400, detail="Survey not found or already responded")

        # Also create feedback from the response
        if "nps" in response:
            feedback_id = generate_feedback_id()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO feedback (
                    feedback_id, customer_id, customer_email, feedback_type, rating, title, message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                feedback_id, None, None, "nps", response["nps"],
                "NPS Survey Response", response.get("reason", "")
            ))
            conn.commit()
            cursor.close()
            conn.close()

        return {
            "survey_id": result[0],
            "status": result[1],
            "message": "Thank you for your feedback!"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/surveys/{survey_id}")
async def get_survey(survey_id: str):
    """Get survey details"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT survey_id, survey_type, customer_email, questions, response, status, created_at
            FROM surveys WHERE survey_id = %s
        """, (survey_id,))

        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if not result:
            raise HTTPException(status_code=404, detail="Survey not found")

        return {
            "survey_id": result[0],
            "survey_type": result[1],
            "customer_email": result[2],
            "questions": result[3],
            "response": result[4],
            "status": result[5],
            "created_at": str(result[6])
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/surveys")
async def list_surveys(status: Optional[str] = None, limit: int = 50):
    """List surveys"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        if status:
            cursor.execute("""
                SELECT survey_id, survey_type, customer_email, status, created_at
                FROM surveys WHERE status = %s ORDER BY created_at DESC LIMIT %s
            """, (status, limit))
        else:
            cursor.execute("""
                SELECT survey_id, survey_type, customer_email, status, created_at
                FROM surveys ORDER BY created_at DESC LIMIT %s
            """, (limit,))

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        return {
            "surveys": [
                {
                    "survey_id": r[0],
                    "survey_type": r[1],
                    "customer_email": r[2],
                    "status": r[3],
                    "created_at": str(r[4])
                }
                for r in results
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    uvicorn.run(app, host="0.0.0.0", port=8000)