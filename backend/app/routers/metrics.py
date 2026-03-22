"""
routers/metrics.py — Endpoints de métricas para el dashboard de administración.
Expone métricas del sistema (CPU, RAM, disco) y métricas de requests (latencia, RPS).
"""
import psutil
import time
from fastapi import APIRouter

from app.metrics_store import metrics

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/system")
def get_system_metrics():
    """Métricas del sistema: CPU, RAM, disco, uptime."""
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu = psutil.cpu_percent(interval=0.2)

    # Conexiones de red activas (aproximación de sesiones concurrentes)
    try:
        connections = len([c for c in psutil.net_connections() if c.status == "ESTABLISHED"])
    except Exception:
        connections = 0

    return {
        "cpu": {
            "percent": cpu,
            "count": psutil.cpu_count(),
        },
        "ram": {
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
        "network": {
            "active_connections": connections,
        },
        "timestamp": time.time(),
    }


@router.get("/requests/summary")
def get_requests_summary(seconds: int = 60):
    """Resumen de requests: total, RPS, latencia promedio, p95, p99, errores."""
    return metrics.get_summary(seconds=seconds)


@router.get("/requests/endpoints")
def get_by_endpoint(seconds: int = 300):
    """Latencia y conteo agrupados por endpoint."""
    return metrics.get_by_endpoint(seconds=seconds)


@router.get("/requests/timeline")
def get_timeline(seconds: int = 300, buckets: int = 30):
    """Serie temporal de requests y latencia para gráficas."""
    return metrics.get_timeline(seconds=seconds, buckets=buckets)


@router.get("/requests/recent")
def get_recent_requests(seconds: int = 60, limit: int = 50):
    """Últimos N requests con detalle."""
    recent = metrics.get_recent(seconds=seconds)
    recent_sorted = sorted(recent, key=lambda r: r.timestamp, reverse=True)[:limit]
    return [
        {
            "timestamp": r.timestamp,
            "method": r.method,
            "path": r.path,
            "status_code": r.status_code,
            "duration_ms": round(r.duration_ms, 1),
        }
        for r in recent_sorted
    ]


@router.get("/dashboard")
def get_dashboard():
    """Endpoint único que devuelve todos los datos del dashboard en una sola llamada."""
    return {
        "system": get_system_metrics(),
        "summary_60s": metrics.get_summary(seconds=60),
        "summary_300s": metrics.get_summary(seconds=300),
        "endpoints": metrics.get_by_endpoint(seconds=300),
        "timeline": metrics.get_timeline(seconds=300, buckets=30),
    }
