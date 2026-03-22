"""
stress_runner.py — Motor de pruebas de estrés integrado.

Escenarios disponibles:
  - "basic"    : requests sin autenticación (mide capacidad bruta del servidor)
  - "realistic": simula usuarios reales autenticados haciendo consultas a la IA
                 (requiere preparar sesiones de prueba primero)
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Optional
import httpx
import psutil


ALLOWED_ENDPOINTS = [
    "/api/health",
    "/api/chat",
    "/api/config",
    "/lti/jwks",
]

# Pool de preguntas realistas de estudiantes
STUDENT_QUESTIONS = [
    "¿Puedes explicarme el concepto principal de este tema?",
    "No entiendo bien la teoría. ¿Puedes darme un ejemplo práctico?",
    "¿Cuáles son las diferencias entre los conceptos que hemos visto?",
    "¿Puedes resumirme los puntos más importantes?",
    "Tengo dudas sobre cómo aplicar esto en la práctica.",
    "¿Podrías darme un ejercicio de ejemplo resuelto paso a paso?",
    "¿Cuál es la importancia de este tema en el contexto del curso?",
    "¿Hay alguna regla general que deba recordar?",
    "¿Qué errores comunes cometen los estudiantes en este tema?",
    "¿Puedes explicar esto de una manera más sencilla?",
    "¿Cómo se relaciona este tema con lo que vimos la semana pasada?",
    "¿Qué recursos adicionales me recomiendas para profundizar?",
    "¿Puedes darme tres puntos clave para recordar sobre esto?",
    "Explícame la diferencia entre estos dos conceptos con ejemplos.",
    "¿Cuándo debo usar este enfoque y cuándo otro diferente?",
]


@dataclass
class StressConfig:
    endpoint: str = "/api/health"
    method: str = "GET"
    concurrent_users: int = 10
    duration_seconds: int = 30
    ramp_up_seconds: int = 5
    scenario: str = "basic"         # "basic" | "realistic"
    body: Optional[dict] = None
    think_time_ms: int = 500        # pausa entre requests por usuario (ms)


@dataclass
class ResourceSample:
    timestamp: float
    cpu_pct: float
    ram_mb: float
    ram_pct: float
    active_users: int


@dataclass
class StressStats:
    total: int = 0
    success: int = 0
    failed: int = 0
    latencies_ms: list = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    elapsed: float = 0.0
    resource_samples: list = field(default_factory=list)  # list[ResourceSample]

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
            "resources": self._resource_summary(),
        }

    def _resource_summary(self) -> dict:
        samples = self.resource_samples
        if not samples:
            return {}
        cpu_vals = [s.cpu_pct for s in samples]
        ram_vals = [s.ram_mb for s in samples]
        ram_pct_vals = [s.ram_pct for s in samples]
        peak_users = max(s.active_users for s in samples)
        avg_users = round(sum(s.active_users for s in samples) / len(samples), 1)
        avg_cpu = round(sum(cpu_vals) / len(cpu_vals), 1)
        peak_cpu = round(max(cpu_vals), 1)
        avg_ram = round(sum(ram_vals) / len(ram_vals), 1)
        peak_ram = round(max(ram_vals), 1)
        avg_ram_pct = round(sum(ram_pct_vals) / len(ram_pct_vals), 1)
        peak_ram_pct = round(max(ram_pct_vals), 1)
        # Per-session estimations (at peak load)
        peak_cpu_per_session = round(peak_cpu / peak_users, 2) if peak_users else 0
        peak_ram_per_session = round(peak_ram / peak_users, 1) if peak_users else 0
        timeline = [
            {"t": round(s.timestamp - self.start_time, 1), "cpu": s.cpu_pct, "ram_mb": s.ram_mb, "users": s.active_users}
            for s in samples
        ]
        return {
            "avg_cpu_pct": avg_cpu,
            "peak_cpu_pct": peak_cpu,
            "avg_ram_mb": avg_ram,
            "peak_ram_mb": peak_ram,
            "avg_ram_pct": avg_ram_pct,
            "peak_ram_pct": peak_ram_pct,
            "peak_concurrent_users": peak_users,
            "avg_concurrent_users": avg_users,
            "per_session_cpu_pct": peak_cpu_per_session,
            "per_session_ram_mb": peak_ram_per_session,
            "timeline": timeline,
        }


class StressRunner:
    def __init__(self):
        self.status: str = "idle"
        self.config: Optional[StressConfig] = None
        self.stats: StressStats = StressStats()
        self.progress: float = 0.0
        self.active_users: int = 0
        self.current_question: str = ""
        self._stop_event: Optional[asyncio.Event] = None
        self._task: Optional[asyncio.Task] = None
        self._base_url: str = "http://localhost:8000"
        self._test_sessions: list[dict] = []   # tokens de sesiones de prueba
        self._test_session_ids: list[str] = []  # IDs para limpiar después

    def set_base_url(self, url: str):
        self._base_url = url.rstrip("/")

    def set_test_sessions(self, sessions: list[dict], session_ids: list[str]):
        """Almacena los tokens de sesión creados para el escenario realista."""
        self._test_sessions = sessions
        self._test_session_ids = session_ids

    def get_test_session_ids(self) -> list[str]:
        return self._test_session_ids

    async def start(self, config: StressConfig) -> dict:
        if self.status == "running":
            return {"error": "Ya hay una prueba en curso"}

        if config.scenario == "realistic" and not self._test_sessions:
            return {"error": "Debes preparar sesiones de prueba primero"}

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
            "current_question": self.current_question,
            "sessions_ready": len(self._test_sessions),
            "stats": summary,
            "config": {
                "endpoint": self.config.endpoint if self.config else None,
                "scenario": self.config.scenario if self.config else "basic",
                "concurrent_users": self.config.concurrent_users if self.config else 0,
                "duration_seconds": self.config.duration_seconds if self.config else 0,
            } if self.config else {},
        }

    # ── Runner principal ─────────────────────────────────────────────────────

    async def _run(self):
        cfg = self.config
        end_time = time.time() + cfg.duration_seconds
        semaphore = asyncio.Semaphore(cfg.concurrent_users)

        limits = httpx.Limits(max_connections=cfg.concurrent_users + 20, max_keepalive_connections=cfg.concurrent_users)

        # Iniciar sampler de recursos en background
        sampler_task = asyncio.create_task(self._sample_resources(end_time))

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0), limits=limits) as client:
            tasks = set()

            while not self._stop_event.is_set():
                now = time.time()
                if now >= end_time:
                    break

                elapsed = now - self.stats.start_time
                self.progress = min(elapsed / cfg.duration_seconds, 1.0)
                self.stats.elapsed = elapsed

                ramp_pct = min(elapsed / cfg.ramp_up_seconds, 1.0) if cfg.ramp_up_seconds > 0 else 1.0
                target_users = max(1, int(cfg.concurrent_users * ramp_pct))

                while self.active_users < target_users and not self._stop_event.is_set():
                    if cfg.scenario == "realistic":
                        # Asignar sesión round-robin
                        user_idx = self.active_users % len(self._test_sessions)
                        session_token = self._test_sessions[user_idx]["token"]
                        task = asyncio.create_task(
                            self._realistic_user(client, semaphore, session_token, end_time)
                        )
                    else:
                        url = f"{self._base_url}{cfg.endpoint}"
                        task = asyncio.create_task(
                            self._single_request(client, cfg.method, url, cfg.body, semaphore)
                        )
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                    self.active_users += 1

                await asyncio.sleep(0.05)

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        await sampler_task

        self.stats.end_time = time.time()
        self.stats.elapsed = self.stats.end_time - self.stats.start_time
        self.progress = 1.0
        self.active_users = 0
        if self.status == "running":
            self.status = "done"

    async def _sample_resources(self, end_time: float):
        """Muestrea CPU y RAM cada segundo durante la prueba."""
        psutil.cpu_percent()  # primer llamado descartado (siempre 0.0)
        while not self._stop_event.is_set() and time.time() < end_time:
            await asyncio.sleep(1.0)
            try:
                vm = psutil.virtual_memory()
                self.stats.resource_samples.append(ResourceSample(
                    timestamp=time.time(),
                    cpu_pct=psutil.cpu_percent(),
                    ram_mb=round(vm.used / 1024 / 1024, 1),
                    ram_pct=vm.percent,
                    active_users=self.active_users,
                ))
            except Exception:
                pass

    # ── Escenario REALISTA — un usuario completo ─────────────────────────────

    async def _realistic_user(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        session_token: str,
        end_time: float,
    ):
        """
        Simula un estudiante real:
          1. Carga la configuración del tutor
          2. Envía preguntas al chat (IA)
          3. Espera think_time entre mensajes
        """
        cookies = {self._get_cookie_name(): session_token}
        base = self._base_url

        while not self._stop_event.is_set() and time.time() < end_time:
            # Paso 1: GET /api/config
            await self._timed_request(client, "GET", f"{base}/api/config",
                                      cookies=cookies, semaphore=semaphore)

            if self._stop_event.is_set() or time.time() >= end_time:
                break

            # Paso 2: POST /api/chat con pregunta aleatoria
            question = random.choice(STUDENT_QUESTIONS)
            self.current_question = question[:50] + "…"

            await self._timed_request(
                client, "POST", f"{base}/api/chat",
                body={"message": question},
                cookies=cookies,
                semaphore=semaphore,
                headers={"X-Stress-Test": "1"},
            )

            # Think time — pausa entre interacciones del mismo usuario
            think = self.config.think_time_ms / 1000.0
            await asyncio.sleep(think + random.uniform(0, think * 0.5))

        self.active_users = max(0, self.active_users - 1)

    # ── Request individual ────────────────────────────────────────────────────

    async def _timed_request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        body: Optional[dict] = None,
        cookies: Optional[dict] = None,
        headers: Optional[dict] = None,
        semaphore: Optional[asyncio.Semaphore] = None,
    ):
        sem = semaphore or asyncio.Semaphore(1)
        async with sem:
            t0 = time.perf_counter()
            try:
                h = {"X-Stress-Test": "1", **(headers or {})}
                if method == "POST":
                    resp = await client.post(url, json=body or {}, cookies=cookies, headers=h)
                else:
                    resp = await client.get(url, cookies=cookies, headers=h)
                ms = (time.perf_counter() - t0) * 1000
                self.stats.total += 1
                self.stats.latencies_ms.append(ms)
                if resp.status_code < 400:
                    self.stats.success += 1
                else:
                    self.stats.failed += 1
            except Exception:
                ms = (time.perf_counter() - t0) * 1000
                self.stats.total += 1
                self.stats.failed += 1
                self.stats.latencies_ms.append(ms)

    async def _single_request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        body: Optional[dict],
        semaphore: asyncio.Semaphore,
    ):
        await self._timed_request(client, method, url, body=body, semaphore=semaphore)
        self.active_users = max(0, self.active_users - 1)

    def _get_cookie_name(self) -> str:
        try:
            from app.config import get_settings
            return get_settings().session_cookie_name
        except Exception:
            return "lti_session"


# Instancia global
runner = StressRunner()
