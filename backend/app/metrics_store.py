"""
metrics_store.py — Store en memoria para métricas de rendimiento.
Captura latencia por endpoint, contadores de requests y estado del sistema.
"""
from collections import deque
from dataclasses import dataclass, field
from time import time
from threading import Lock

# Ventana de requests almacenados (últimos 500)
MAX_REQUESTS = 500

@dataclass
class RequestRecord:
    timestamp: float
    method: str
    path: str
    status_code: int
    duration_ms: float

class MetricsStore:
    def __init__(self):
        self._lock = Lock()
        self._requests: deque[RequestRecord] = deque(maxlen=MAX_REQUESTS)

    def record(self, method: str, path: str, status_code: int, duration_ms: float):
        with self._lock:
            self._requests.append(RequestRecord(
                timestamp=time(),
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
            ))

    def get_recent(self, seconds: int = 300) -> list[RequestRecord]:
        cutoff = time() - seconds
        with self._lock:
            return [r for r in self._requests if r.timestamp >= cutoff]

    def get_summary(self, seconds: int = 60) -> dict:
        recent = self.get_recent(seconds)
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
            # Normalizar paths con IDs dinámicos
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
        """Agrupa requests en buckets de tiempo para la gráfica de línea."""
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


def _normalize_path(path: str) -> str:
    """Reemplaza segmentos que parecen IDs por {id}."""
    import re
    # UUIDs
    path = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '{id}', path)
    # Números puros
    path = re.sub(r'/\d+', '/{id}', path)
    return path


# Instancia global
metrics = MetricsStore()
