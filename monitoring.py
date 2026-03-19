"""
AI City API Monitoring Module
Real-time performance tracking and alerting
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from collections import defaultdict
import time

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

# ============== In-memory metrics storage ==============

class MetricsStore:
    def __init__(self):
        self.requests = []
        self.errors = []
        self.latencies = defaultdict(list)
        self.request_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.start_time = datetime.utcnow()

    def record_request(self, endpoint: str, method: str, status_code: int, latency_ms: float):
        """Record an API request"""
        now = datetime.utcnow()
        self.requests.append({
            "timestamp": now.isoformat(),
            "endpoint": endpoint,
            "method": method,
            "status_code": status_code,
            "latency_ms": latency_ms,
        })

        key = f"{method} {endpoint}"
        self.request_counts[key] += 1
        self.latencies[key].append(latency_ms)

        if status_code >= 400:
            self.error_counts[key] += 1
            self.errors.append({
                "timestamp": now.isoformat(),
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "latency_ms": latency_ms,
            })

        # Keep only last 10000 requests
        if len(self.requests) > 10000:
            self.requests = self.requests[-5000:]

    def get_stats(self) -> Dict:
        """Get overall statistics"""
        total_requests = len(self.requests)
        if total_requests == 0:
            return {
                "total_requests": 0,
                "error_rate": 0,
                "avg_latency_ms": 0,
                "uptime_seconds": 0,
            }

        errors = sum(1 for r in self.requests if r["status_code"] >= 400)
        total_latency = sum(r["latency_ms"] for r in self.requests)

        uptime = (datetime.utcnow() - self.start_time).total_seconds()

        return {
            "total_requests": total_requests,
            "error_rate": (errors / total_requests) * 100,
            "avg_latency_ms": total_latency / total_requests,
            "uptime_seconds": uptime,
            "requests_per_minute": total_requests / (uptime / 60) if uptime > 0 else 0,
        }

    def get_endpoint_stats(self, endpoint: Optional[str] = None) -> List[Dict]:
        """Get stats per endpoint"""
        if endpoint:
            counts = {endpoint: self.request_counts.get(f"GET {endpoint}", 0)}
            errors = {endpoint: self.error_counts.get(f"GET {endpoint}", 0)}
            latencies = {endpoint: self.latencies.get(f"GET {endpoint}", [])}
        else:
            counts = dict(self.request_counts)
            errors = dict(self.error_counts)
            latencies = dict(self.latencies)

        result = []
        for key in counts:
            lats = latencies.get(key, [])
            result.append({
                "endpoint": key,
                "requests": counts[key],
                "errors": errors.get(key, 0),
                "error_rate": (errors.get(key, 0) / counts[key] * 100) if counts[key] > 0 else 0,
                "avg_latency_ms": sum(lats) / len(lats) if lats else 0,
                "p50_latency_ms": sorted(lats)[len(lats) // 2] if lats else 0,
                "p95_latency_ms": sorted(lats)[int(len(lats) * 0.95)] if lats else 0,
                "p99_latency_ms": sorted(lats)[int(len(lats) * 0.99)] if lats else 0,
            })

        return sorted(result, key=lambda x: x["requests"], reverse=True)

    def get_recent_errors(self, limit: int = 50) -> List[Dict]:
        """Get recent errors"""
        return self.errors[-limit:]

    def clear(self):
        """Clear all metrics"""
        self.requests = []
        self.errors = []
        self.latencies.clear()
        self.request_counts.clear()
        self.error_counts.clear()
        self.start_time = datetime.utcnow()


metrics = MetricsStore()


# ============== Models ==============

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    uptime_seconds: float
    version: str = "1.0.0"


class StatsResponse(BaseModel):
    stats: Dict
    endpoints: List[Dict]
    recent_errors: List[Dict]


class AlertConfig(BaseModel):
    endpoint: Optional[str] = None
    latency_threshold_ms: float = 1000
    error_rate_threshold_percent: float = 5.0


# ============== Middleware ==============

async def monitor_middleware(request: Request, call_next):
    """Middleware to record request metrics"""
    start_time = time.time()

    response = await call_next(request)

    latency_ms = (time.time() - start_time) * 1000

    # Don't record health check endpoints
    if not request.url.path.startswith("/monitoring") and \
       not request.url.path.startswith("/health"):
        metrics.record_request(
            endpoint=request.url.path,
            method=request.method,
            status_code=response.status_code,
            latency_ms=latency_ms,
        )

    return response


# ============== API Endpoints ==============

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        uptime_seconds=(datetime.utcnow() - metrics.start_time).total_seconds(),
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get API statistics"""
    return StatsResponse(
        stats=metrics.get_stats(),
        endpoints=metrics.get_endpoint_stats(),
        recent_errors=metrics.get_recent_errors(),
    )


@router.get("/stats/{endpoint}", response_model=Dict)
async def get_endpoint_stats(endpoint: str):
    """Get stats for specific endpoint"""
    return metrics.get_endpoint_stats(endpoint)


@router.get("/errors", response_model=List[Dict])
async def get_recent_errors(limit: int = 50):
    """Get recent errors"""
    return metrics.get_recent_errors(limit)


@router.post("/clear")
async def clear_metrics():
    """Clear all metrics (admin only)"""
    metrics.clear()
    return {"message": "Metrics cleared"}


@router.get("/latency/{endpoint}")
async def get_endpoint_latency(endpoint: str):
    """Get latency distribution for an endpoint"""
    lats = metrics.latencies.get(f"GET {endpoint}", [])
    if not lats:
        raise HTTPException(status_code=404, detail="No data for endpoint")

    sorted_lats = sorted(lats)
    return {
        "endpoint": endpoint,
        "count": len(lats),
        "min_ms": min(lats),
        "max_ms": max(lats),
        "avg_ms": sum(lats) / len(lats),
        "p50_ms": sorted_lats[len(lats) // 2],
        "p95_ms": sorted_lats[int(len(lats) * 0.95)],
        "p99_ms": sorted_lats[int(len(lats) * 0.99)],
    }
