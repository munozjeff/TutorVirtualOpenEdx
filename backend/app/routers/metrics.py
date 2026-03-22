"""
routers/metrics.py — Endpoints de métricas para el dashboard de administración.
Expone métricas del sistema, requests, sesiones y control del stress test.
"""
import csv
import io
import json
import psutil
import time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.metrics_store import metrics, resource_monitor
from app.models import LtiInstance, LtiSession
from app.services.session_service import generate_session_token, compute_isolation_key
from app.stress_runner import runner, StressConfig, ALLOWED_ENDPOINTS, STUDENT_QUESTIONS

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


# ── Historial de recursos ─────────────────────────────────────────────────────

@router.get("/resources/history")
def get_resource_history(seconds: int = 300):
    return {
        "history": resource_monitor.get_history(seconds),
        "peaks":   resource_monitor.get_peaks(seconds),
    }


@router.get("/resources/peaks")
def get_resource_peaks(seconds: int = 300):
    return resource_monitor.get_peaks(seconds)


# ── Exportación / Historial persistido ────────────────────────────────────────

def _read_jsonl(path: str) -> list[dict]:
    """Lee un archivo JSONL y devuelve lista de dicts. Retorna [] si no existe."""
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return []
    records = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    return records


@router.get("/export/resource-history")
def export_resource_history():
    """Descarga el historial completo de recursos del servidor en CSV."""
    records = _read_jsonl("data/resource_history.jsonl")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "datetime", "cpu_pct", "ram_mb", "ram_pct", "disk_pct", "disk_free_gb"])
    for r in records:
        writer.writerow([
            r.get("t"), datetime.fromtimestamp(r.get("t", 0)).strftime("%Y-%m-%d %H:%M:%S"),
            r.get("cpu"), r.get("ram_mb"), r.get("ram_pct"), r.get("disk_pct"), r.get("disk_free_gb"),
        ])
    buf.seek(0)
    filename = f"recursos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(io.BytesIO(buf.getvalue().encode()), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/export/stress-results")
def export_stress_results():
    """Descarga el historial de todas las pruebas de estrés en CSV."""
    records = _read_jsonl("data/stress_results.jsonl")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "timestamp", "datetime", "scenario", "endpoint", "concurrent_users",
        "duration_s", "think_time_ms", "total_req", "rps", "success", "errors",
        "error_rate_pct", "avg_ms", "p50_ms", "p95_ms", "p99_ms", "min_ms", "max_ms",
        "peak_cpu_pct", "avg_cpu_pct", "peak_ram_mb", "avg_ram_mb",
        "per_session_cpu_pct", "per_session_ram_mb",
    ])
    for r in records:
        cfg = r.get("config", {})
        res = r.get("results", {})
        rsc = r.get("resources", {})
        writer.writerow([
            r.get("timestamp"),
            datetime.fromtimestamp(r.get("timestamp", 0)).strftime("%Y-%m-%d %H:%M:%S"),
            cfg.get("scenario"), cfg.get("endpoint"), cfg.get("concurrent_users"),
            res.get("elapsed_s"), cfg.get("think_time_ms"),
            res.get("total"), res.get("rps"), res.get("success"), res.get("failed"),
            res.get("error_rate"), res.get("avg_ms"), res.get("p50_ms"),
            res.get("p95_ms"), res.get("p99_ms"), res.get("min_ms"), res.get("max_ms"),
            rsc.get("peak_cpu_pct"), rsc.get("avg_cpu_pct"),
            rsc.get("peak_ram_mb"), rsc.get("avg_ram_mb"),
            rsc.get("per_session_cpu_pct"), rsc.get("per_session_ram_mb"),
        ])
    buf.seek(0)
    filename = f"stress_tests_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(io.BytesIO(buf.getvalue().encode()), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/stress-test/history")
def get_stress_history():
    """Lista de todas las pruebas de estrés guardadas (sin el timeline detallado)."""
    records = _read_jsonl("data/stress_results.jsonl")
    # Devolver en orden más reciente primero, sin el timeline de recursos (muy grande)
    result = []
    for r in reversed(records):
        rsc = {k: v for k, v in r.get("resources", {}).items() if k != "timeline"}
        result.append({**r, "resources": rsc})
    return result


# ── Dashboard unificado ───────────────────────────────────────────────────────

@router.get("/dashboard")
def get_dashboard():
    return {
        "system":           get_system_metrics(),
        "summary_60s":      metrics.get_summary(seconds=60),
        "summary_300s":     metrics.get_summary(seconds=300),
        "endpoints":        metrics.get_by_endpoint(seconds=300),
        "timeline":         metrics.get_timeline(seconds=300, buckets=30),
        "sessions":         metrics.get_session_stats(),
        "resource_history": resource_monitor.get_history(seconds=300),
        "resource_peaks":   resource_monitor.get_peaks(seconds=300),
    }


# ── Stress Test ───────────────────────────────────────────────────────────────

class StressTestRequest(BaseModel):
    endpoint: str = Field(default="/api/health")
    method: str = Field(default="GET")
    concurrent_users: int = Field(default=10, ge=1, le=200)
    duration_seconds: int = Field(default=30, ge=5, le=120)
    ramp_up_seconds: int = Field(default=5, ge=0, le=30)
    scenario: str = Field(default="basic")   # "basic" | "realistic"
    think_time_ms: int = Field(default=500, ge=0, le=10000)
    body: Optional[dict] = None


@router.post("/stress-test/prepare")
async def stress_test_prepare(
    n: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """
    Crea N sesiones sintéticas de prueba en la BD para el escenario realista.
    Requiere que exista al menos una instancia LTI lanzada desde Open edX.
    """
    # Obtener primera instancia LTI disponible
    result = await db.execute(select(LtiInstance).limit(1))
    instance = result.scalar_one_or_none()

    if not instance:
        raise HTTPException(
            status_code=400,
            detail="No hay instancias LTI disponibles. Lanza el tutor desde Open edX al menos una vez primero.",
        )

    # Limpiar sesiones de prueba anteriores (por user_id, sobrevive reinicios del servidor)
    await db.execute(delete(LtiSession).where(LtiSession.user_id.like("stress_user_%")))
    await db.commit()

    # Crear N sesiones sintéticas
    sessions_out = []
    session_ids = []
    n = min(n, 200)  # máximo 200

    for i in range(n):
        user_id = f"stress_user_{i + 1}"
        isolation_key = compute_isolation_key(
            user_id=user_id,
            resource_link_id=f"stress_test_{instance.resource_link_id}_{i}",
        )
        token = generate_session_token()
        session = LtiSession(
            isolation_key=isolation_key,
            instance_id=instance.id,
            user_id=user_id,
            user_name=f"Estudiante Prueba {i + 1}",
            user_email=f"stress_{i + 1}@test.local",
            user_role="student",
            course_name="[Prueba de Estrés]",
            session_token=token,
        )
        db.add(session)
        await db.flush()
        sessions_out.append({"user_id": user_id, "token": token})
        session_ids.append(session.id)

    await db.commit()
    runner.set_test_sessions(sessions_out, session_ids)

    return {
        "created": n,
        "instance": instance.tutor_name or instance.resource_link_id[:20],
        "questions_pool": len(STUDENT_QUESTIONS),
    }


@router.post("/stress-test/start")
async def stress_test_start(req: StressTestRequest):
    if runner.status == "running":
        raise HTTPException(status_code=409, detail="Ya hay una prueba en curso")

    if req.scenario == "basic" and not req.endpoint.startswith("/api/") and req.endpoint not in ALLOWED_ENDPOINTS:
        raise HTTPException(status_code=400, detail=f"Endpoint no permitido: {req.endpoint}")

    config = StressConfig(
        endpoint=req.endpoint,
        method=req.method.upper(),
        concurrent_users=req.concurrent_users,
        duration_seconds=req.duration_seconds,
        ramp_up_seconds=req.ramp_up_seconds,
        scenario=req.scenario,
        think_time_ms=req.think_time_ms,
        body=req.body,
    )
    result = await runner.start(config)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/stress-test/stop")
def stress_test_stop():
    runner.stop()
    return {"status": "stopped"}


@router.get("/stress-test/status")
def stress_test_status():
    return runner.get_state()


@router.post("/stress-test/cleanup")
async def stress_test_cleanup(db: AsyncSession = Depends(get_db)):
    """Elimina las sesiones sintéticas de prueba de la BD."""
    result = await db.execute(delete(LtiSession).where(LtiSession.user_id.like("stress_user_%")))
    await db.commit()
    runner.set_test_sessions([], [])
    return {"deleted": result.rowcount}


@router.get("/stress-test/endpoints")
def stress_test_endpoints():
    return ALLOWED_ENDPOINTS


@router.get("/stress-test/questions")
def stress_test_questions():
    """Pool de preguntas usadas en el escenario realista."""
    return STUDENT_QUESTIONS
