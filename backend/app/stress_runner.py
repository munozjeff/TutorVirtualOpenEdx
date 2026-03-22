"""
stress_runner.py — Motor de pruebas de estrés integrado.
Ejecuta requests HTTP concurrentes contra endpoints internos del servidor
usando asyncio + httpx. Los resultados se capturan automáticamente por el
middleware de métricas, permitiendo observar el impacto en tiempo real.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional
import httpx


# ── Endpoints permitidos (solo internos, por seguridad) ──────────────────────
ALLOWED_ENDPOINTS = [
    "/api/health",
    "/api/chat",
    "/api/config",
    "/lti/jwks",
]


@dataclass
class StressConfig:
    endpoint: str           # ej: /api/health
    method: str             # GET | POST
    concurrent_users: int   # usuarios simultáneos
    duration_seconds: int   # duración total
    ramp_up_seconds: int    # tiempo para llegar a concurrencia máxima
    body: Optional[dict] = None  # body para POST


@dataclass
class StressStats:
    total: int = 0
    success: int = 0
    failed: int = 0
    latencies_ms: list = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    elapsed: float = 0.0

    def summary(self) -> dict:
        lats = sorted(self.latencies_ms)
        n = len(lats)
        elapsed = self.elapsed or 1
        return {
            "total": self.total,
            "success": self.success,
            "failed": self.failed,
            "rps": round(self.total / elapsed, 2),
            "avg_ms": round(sum(lats) / n, 1) if n else 0,
            "p50_ms": round(lats[int(n * 0.50)], 1) if n else 0,
            "p95_ms": round(lats[int(n * 0.95)], 1) if n else 0,
            "p99_ms": round(lats[int(n * 0.99)], 1) if n else 0,
            "min_ms": round(lats[0], 1) if n else 0,
            "max_ms": round(lats[-1], 1) if n else 0,
            "error_rate": round(self.failed / self.total * 100, 1) if self.total else 0,
            "elapsed_s": round(elapsed, 1),
        }


class StressRunner:
    def __init__(self):
        self.status: str = "idle"   # idle | running | done | stopped
        self.config: Optional[StressConfig] = None
        self.stats: StressStats = StressStats()
        self.progress: float = 0.0
        self.active_users: int = 0
        self._stop_event: Optional[asyncio.Event] = None
        self._task: Optional[asyncio.Task] = None
        self._base_url: str = "http://localhost:8000"

    def set_base_url(self, url: str):
        self._base_url = url.rstrip("/")

    async def start(self, config: StressConfig) -> dict:
        if self.status == "running":
            return {"error": "Ya hay una prueba en curso"}

        self.config = config
        self.stats = StressStats(start_time=time.time())
        self.progress = 0.0
        self.active_users = 0
        self._stop_event = asyncio.Event()
        self.status = "running"

        self._task = asyncio.create_task(self._run())
        return {"status": "started"}

    def stop(self):
        if self._stop_event:
            self._stop_event.set()
        self.status = "stopped"

    def get_state(self) -> dict:
        summary = self.stats.summary() if self.stats.total > 0 else {}
        return {
            "status": self.status,
            "progress": round(self.progress, 3),
            "active_users": self.active_users,
            "stats": summary,
            "config": {
                "endpoint": self.config.endpoint if self.config else None,
                "concurrent_users": self.config.concurrent_users if self.config else 0,
                "duration_seconds": self.config.duration_seconds if self.config else 0,
            } if self.config else {},
        }

    async def _run(self):
        cfg = self.config
        end_time = time.time() + cfg.duration_seconds
        semaphore = asyncio.Semaphore(cfg.concurrent_users)

        url = f"{self._base_url}{cfg.endpoint}"
        headers = {"X-Stress-Test": "1"}  # marcador interno

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=cfg.concurrent_users + 10),
        ) as client:
            tasks = set()

            while not self._stop_event.is_set():
                now = time.time()
                if now >= end_time:
                    break

                # Calcular progreso
                elapsed = now - self.stats.start_time
                self.progress = min(elapsed / cfg.duration_seconds, 1.0)
                self.stats.elapsed = elapsed

                # Ramp-up: aumentar usuarios gradualmente
                ramp_pct = min(elapsed / cfg.ramp_up_seconds, 1.0) if cfg.ramp_up_seconds > 0 else 1.0
                target_users = max(1, int(cfg.concurrent_users * ramp_pct))

                # Lanzar nuevas tareas hasta alcanzar usuarios objetivo
                while self.active_users < target_users and not self._stop_event.is_set():
                    task = asyncio.create_task(
                        self._single_request(client, cfg.method, url, cfg.body, headers, semaphore)
                    )
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                    self.active_users += 1

                await asyncio.sleep(0.05)

            # Esperar que terminen los requests en vuelo
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        self.stats.end_time = time.time()
        self.stats.elapsed = self.stats.end_time - self.stats.start_time
        self.progress = 1.0
        self.active_users = 0
        if self.status == "running":
            self.status = "done"

    async def _single_request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        body: Optional[dict],
        headers: dict,
        semaphore: asyncio.Semaphore,
    ):
        self.active_users = max(0, self.active_users)
        async with semaphore:
            t0 = time.perf_counter()
            try:
                if method == "POST":
                    resp = await client.post(url, json=body or {}, headers=headers)
                else:
                    resp = await client.get(url, headers=headers)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                self.stats.total += 1
                self.stats.latencies_ms.append(elapsed_ms)
                if resp.status_code < 400:
                    self.stats.success += 1
                else:
                    self.stats.failed += 1
            except Exception:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                self.stats.total += 1
                self.stats.failed += 1
                self.stats.latencies_ms.append(elapsed_ms)
            finally:
                self.active_users = max(0, self.active_users - 1)


# Instancia global
runner = StressRunner()
