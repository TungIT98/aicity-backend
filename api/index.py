import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import environment before importing main
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import psycopg2

# Get environment variables
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "neondb"),
    "user": os.getenv("DB_USER", "neondb_owner"),
    "password": os.getenv("DB_PASSWORD", ""),
}

app = FastAPI(title="AI City API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class HealthResponse(BaseModel):
    ollama: str
    qdrant: str
    postgresql: str

@app.get("/")
async def root():
    return {"status": "running", "service": "AI City API"}

@app.get("/health", response_model=HealthResponse)
async def health():
    # Check PostgreSQL
    pg_status = "unavailable"
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.close()
        pg_status = "ok"
    except Exception as e:
        pg_status = f"error: {str(e)[:50]}"
    
    return HealthResponse(
        ollama="unavailable",
        qdrant="unavailable", 
        postgresql=pg_status
    )

@app.get("/leads")
async def get_leads(limit: int = 50):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT id, name, email, phone, source, status, metadata, created_at, updated_at FROM leads ORDER BY created_at DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "id": r[0], "name": r[1], "email": r[2], "phone": r[3],
                "source": r[4], "status": r[5], "metadata": r[6],
                "created_at": str(r[7]), "updated_at": str(r[8])
            }
            for r in rows
        ]
    except Exception as e:
        return {"error": str(e)}

@app.get("/analytics/overview")
async def analytics_overview():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        cur.execute("SELECT status, COUNT(*) FROM leads GROUP BY status")
        leads_by_status = {r[0]: r[1] for r in cur.fetchall()}
        
        cur.close()
        conn.close()
        
        return {
            "matomo": {},
            "leads": leads_by_status,
            "period": "today"
        }
    except Exception as e:
        return {"error": str(e)}
