"""
routers/metrics.py — Endpoints de métricas para el dashboard de administración.
Expone métricas del sistema, requests, sesiones y control del stress test.
"""
import psutil
import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.metrics_store import metrics
from app.stress_runner import runner, StressConfig, ALLOWED_ENDPOINTS

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


# ── Sistema ──────────────────────────────────────────────────────────────────

@router.get("/system")
def get_system_metrics():
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu = psutil.cpu_percent(interval=0.2)

    try:
        connections = len([c for c in psutil.net_connections() if c.status == "ESTABLISHED"])
    except Exception:
        connections = 0

    return {
        "cpu":  {"percent": cpu, "count": psutil.cpu_count()},
        "ram":  {
            "percent": vm.percent,
            "used_mb": round(vm.used / 1024 / 1024),
            "total_mb": round(vm.total / 1024 / 1024),
            "available_mb": round(vm.available / 1024 / 1024),
        },
        "disk": {
            "percent": disk.percent,
            "used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
            "total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
            "free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
        },
        "network": {"active_connections": connections},
        "timestamp": time.time(),
    }


# ── Requests ─────────────────────────────────────────────────────────────────

@router.get("/requests/summary")
def get_requests_summary(seconds: int = 60):
    return metrics.get_summary(seconds=seconds)


@router.get("/requests/endpoints")
def get_by_endpoint(seconds: int = 300):
    return metrics.get_by_endpoint(seconds=seconds)


@router.get("/requests/timeline")
def get_timeline(seconds: int = 300, buckets: int = 30):
    return metrics.get_timeline(seconds=seconds, buckets=buckets)


@router.get("/requests/recent")
def get_recent_requests(seconds: int = 60, limit: int = 50):
    recent = metrics.get_recent(seconds=seconds)
    recent_sorted = sorted(recent, key=lambda r: r.timestamp, reverse=True)[:limit]
    return [
        {
            "timestamp": r.timestamp,
            "method": r.method,
            "path": r.path,
            "status_code": r.status_code,
            "duration_ms": round(r.duration_ms, 1),
            "is_stress": r.is_stress,
        }
        for r in recent_sorted
    ]


# ── Sesiones ─────────────────────────────────────────────────────────────────

@router.get("/sessions")
def get_sessions():
    """Métricas por sesión de usuario y estimación de recursos por sesión."""
    return metrics.get_session_stats()


# ── Dashboard unificado ───────────────────────────────────────────────────────

@router.get("/dashboard")
def get_dashboard():
    return {
        "system":       get_system_metrics(),
        "summary_60s":  metrics.get_summary(seconds=60),
        "summary_300s": metrics.get_summary(seconds=300),
        "endpoints":    metrics.get_by_endpoint(seconds=300),
        "timeline":     metrics.get_timeline(seconds=300, buckets=30),
        "sessions":     metrics.get_session_stats(),
    }


# ── Stress Test ───────────────────────────────────────────────────────────────

class StressTestRequest(BaseModel):
    endpoint: str = Field(default="/api/health")
    method: str = Field(default="GET")
    concurrent_users: int = Field(default=10, ge=1, le=200)
    duration_seconds: int = Field(default=30, ge=5, le=120)
    ramp_up_seconds: int = Field(default=5, ge=0, le=30)
    body: Optional[dict] = None


@router.post("/stress-test/start")
async def stress_test_start(req: StressTestRequest):
    if runner.status == "running":
        raise HTTPException(status_code=409, detail="Ya hay una prueba en curso")

    if not req.endpoint.startswith("/api/") and req.endpoint not in ALLOWED_ENDPOINTS:
        raise HTTPException(status_code=400, detail=f"Endpoint no permitido: {req.endpoint}")

    config = StressConfig(
        endpoint=req.endpoint,
        method=req.method.upper(),
        concurrent_users=req.concurrent_users,
        duration_seconds=req.duration_seconds,
        ramp_up_seconds=req.ramp_up_seconds,
        body=req.body,
    )
    result = await runner.start(config)
    return result


@router.post("/stress-test/stop")
def stress_test_stop():
    runner.stop()
    return {"status": "stopped"}


@router.get("/stress-test/status")
def stress_test_status():
    return runner.get_state()


@router.get("/stress-test/endpoints")
def stress_test_endpoints():
    """Endpoints disponibles para el stress test."""
    return ALLOWED_ENDPOINTS
