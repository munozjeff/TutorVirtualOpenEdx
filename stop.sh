#!/usr/bin/env bash
# stop.sh — Detiene todos los servicios del LTI Virtual Tutor

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"

echo "Deteniendo servicios..."

# Backend
if [[ -f "$LOG_DIR/backend.pid" ]]; then
    PID=$(cat "$LOG_DIR/backend.pid")
    kill "$PID" 2>/dev/null && echo "  ✔ Backend (PID $PID) detenido" || echo "  ℹ Backend ya estaba detenido"
    rm -f "$LOG_DIR/backend.pid"
fi
pkill -f "uvicorn app.main:app" 2>/dev/null || true

# Frontend
if [[ -f "$LOG_DIR/frontend.pid" ]]; then
    PID=$(cat "$LOG_DIR/frontend.pid")
    kill "$PID" 2>/dev/null && echo "  ✔ Frontend (PID $PID) detenido" || echo "  ℹ Frontend ya estaba detenido"
    rm -f "$LOG_DIR/frontend.pid"
fi
pkill -f "vite" 2>/dev/null || true

# Proxy nginx (Docker)
cd "$SCRIPT_DIR"
docker compose down 2>/dev/null && echo "  ✔ Proxy nginx detenido" || true

echo "Todos los servicios detenidos."
