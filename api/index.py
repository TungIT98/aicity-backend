"""
Vercel Serverless Handler for AI City Backend
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Create FastAPI app
app = FastAPI(title="AI City API", docs_url=None, redoc_url=None, openapi_url=None)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "ok", "message": "AI City API is running", "timestamp": datetime.utcnow().isoformat()}

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "aicity-backend"}

# Import and include routes from main app
try:
    from main import app as main_app

    # Copy all routes from main app including payment gateway
    for route in main_app.routes:
        if hasattr(route, 'path'):
            # Skip docs routes
            if route.path not in ['/docs', '/redoc', '/openapi.json', '/api/docs', '/api/redoc', '/api/openapi.json']:
                app.routes.append(route)

except ImportError as e:
    print(f"Warning: Could not import main app routes: {e}")
    # Fallback: import payment gateway directly
    try:
        from payment_gateway import router as payment_router
        app.include_router(payment_router)
    except ImportError as e2:
        print(f"Warning: Could not import payment gateway: {e2}")

# Vercel handler
handler = app
