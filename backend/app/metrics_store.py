"""
metrics_store.py — Store en memoria para métricas de rendimiento.
Captura latencia por endpoint, contadores de requests, estado del sistema
y métricas por sesión de usuario.
"""
from collections import deque
from dataclasses import dataclass, field
from time import time
from threading import Lock

# Ventana de requests almacenados (últimos 1000)
MAX_REQUESTS = 1000
# Sesiones inactivas después de N segundos se consideran expiradas
SESSION_TIMEOUT = 300


@dataclass
class RequestRecord:
    timestamp: float
    method: str
    path: str
    status_code: int
    duration_ms: float
    session_id: str = ""      # ID de sesión del usuario
    is_stress: bool = False   # generado por el stress test


@dataclass
class SessionStats:
    session_id: str
    first_seen: float
    last_seen: float
    request_count: int = 0
    total_latency_ms: float = 0.0
    errors: int = 0

    @property
    def avg_latency_ms(self) -> float:
        return round(self.total_latency_ms / self.request_count, 1) if self.request_count else 0.0

    @property
    def active_seconds(self) -> float:
        return round(self.last_seen - self.first_seen, 1)


class MetricsStore:
    def __init__(self):
        self._lock = Lock()
        self._requests: deque[RequestRecord] = deque(maxlen=MAX_REQUESTS)
        self._sessions: dict[str, SessionStats] = {}

    def record(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        session_id: str = "",
        is_stress: bool = False,
    ):
        now = time()
        with self._lock:
            self._requests.append(RequestRecord(
                timestamp=now,
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                session_id=session_id,
                is_stress=is_stress,
            ))

            # Actualizar stats de sesión
            if session_id:
                if session_id not in self._sessions:
                    self._sessions[session_id] = SessionStats(
                        session_id=session_id,
                        first_seen=now,
                        last_seen=now,
                    )
                s = self._sessions[session_id]
                s.last_seen = now
                s.request_count += 1
                s.total_latency_ms += duration_ms
                if status_code >= 400:
                    s.errors += 1

    def get_recent(self, seconds: int = 300, exclude_stress: bool = False) -> list[RequestRecord]:
        cutoff = time() - seconds
        with self._lock:
            return [
                r for r in self._requests
                if r.timestamp >= cutoff and (not exclude_stress or not r.is_stress)
            ]

    def get_summary(self, seconds: int = 60, exclude_stress: bool = False) -> dict:
        recent = self.get_recent(seconds, exclude_stress=exclude_stress)
        if not recent:
            return {
                "total": 0, "rps": 0.0,
                "avg_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0,
                "errors": 0, "error_rate": 0.0,
            }

        durations = sorted(r.duration_ms for r in recent)
        errors = sum(1 for r in recent if r.status_code >= 400)
        n = len(durations)
        window = min(seconds, (time() - recent[0].timestamp) or 1)

        return {
            "total": n,
            "rps": round(n / window, 2),
            "avg_ms": round(sum(durations) / n, 1),
            "p95_ms": round(durations[int(n * 0.95)], 1),
            "p99_ms": round(durations[int(n * 0.99)], 1),
            "errors": errors,
            "error_rate": round(errors / n * 100, 1),
        }

    def get_by_endpoint(self, seconds: int = 300) -> list[dict]:
        recent = self.get_recent(seconds)
        grouped: dict[str, list[float]] = {}
        errors: dict[str, int] = {}

        for r in recent:
            path = _normalize_path(r.path)
            grouped.setdefault(path, []).append(r.duration_ms)
            if r.status_code >= 400:
                errors[path] = errors.get(path, 0) + 1

        result = []
        for path, durations in grouped.items():
            durations_sorted = sorted(durations)
            n = len(durations_sorted)
            result.append({
                "endpoint": path,
                "count": n,
                "avg_ms": round(sum(durations) / n, 1),
                "p95_ms": round(durations_sorted[int(n * 0.95)], 1),
                "min_ms": round(durations_sorted[0], 1),
                "max_ms": round(durations_sorted[-1], 1),
                "errors": errors.get(path, 0),
            })

        return sorted(result, key=lambda x: x["count"], reverse=True)

    def get_timeline(self, seconds: int = 300, buckets: int = 30) -> list[dict]:
        now = time()
        bucket_size = seconds / buckets
        recent = self.get_recent(seconds)

        result = []
        for i in range(buckets):
            bucket_start = now - seconds + i * bucket_size
            bucket_end = bucket_start + bucket_size
            bucket_reqs = [r for r in recent if bucket_start <= r.timestamp < bucket_end]

            avg_ms = 0.0
            if bucket_reqs:
                avg_ms = sum(r.duration_ms for r in bucket_reqs) / len(bucket_reqs)

            result.append({
                "t": round(bucket_start),
                "count": len(bucket_reqs),
                "avg_ms": round(avg_ms, 1),
            })

        return result

    # ── Métricas por sesión ──────────────────────────────────────────────────

    def get_session_stats(self) -> dict:
        """Devuelve métricas por sesión y promedios de recursos por usuario."""
        import psutil
        now = time()

        with self._lock:
            # Limpiar sesiones inactivas
            active_cutoff = now - SESSION_TIMEOUT
            active_sessions = {
                sid: s for sid, s in self._sessions.items()
                if s.last_seen >= active_cutoff
            }

            # Sesiones activas en los últimos 5 minutos
            recent_cutoff = now - 300
            recent_sessions = {
                sid: s for sid, s in active_sessions.items()
                if s.last_seen >= recent_cutoff
            }

            sessions_list = sorted(
                active_sessions.values(),
                key=lambda s: s.last_seen,
                reverse=True,
            )[:20]  # máximo 20 en la tabla

        n_active = len(recent_sessions)

        # Recursos del sistema
        vm = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        disk = psutil.disk_usage("/")

        # Estimación de recursos por sesión (basado en sesiones activas)
        per_session = {}
        if n_active > 0:
            per_session = {
                "cpu_pct": round(cpu / n_active, 2),
                "ram_mb": round(vm.used / 1024 / 1024 / n_active, 1),
                "disk_mb": round(disk.used / 1024 / 1024 / n_active, 1),
            }
        else:
            per_session = {"cpu_pct": 0, "ram_mb": 0, "disk_mb": 0}

        # Promedios globales de sesión
        all_req_counts = [s.request_count for s in active_sessions.values()]
        all_latencies = [s.avg_latency_ms for s in active_sessions.values() if s.request_count > 0]

        avg_requests_per_session = round(sum(all_req_counts) / len(all_req_counts), 1) if all_req_counts else 0
        avg_latency_per_session = round(sum(all_latencies) / len(all_latencies), 1) if all_latencies else 0
        avg_duration_per_session = round(
            sum(s.active_seconds for s in active_sessions.values()) / len(active_sessions), 1
        ) if active_sessions else 0

        return {
            "total_sessions": len(active_sessions),
            "active_sessions_5min": n_active,
            "avg_requests_per_session": avg_requests_per_session,
            "avg_latency_per_session_ms": avg_latency_per_session,
            "avg_duration_per_session_s": avg_duration_per_session,
            "per_session_resources": per_session,
            "sessions": [
                {
                    "id": s.session_id[:12] + "…",
                    "requests": s.request_count,
                    "avg_latency_ms": s.avg_latency_ms,
                    "errors": s.errors,
                    "duration_s": s.active_seconds,
                    "last_seen_ago_s": round(now - s.last_seen, 0),
                }
                for s in sessions_list
            ],
        }


def _normalize_path(path: str) -> str:
    import re
    path = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '{id}', path)
    path = re.sub(r'/\d+', '/{id}', path)
    return path


# Instancia global
metrics = MetricsStore()
