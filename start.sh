#!/usr/bin/env bash
# =============================================================================
#  start.sh — LTI Virtual Tutor · Arrancar servicios (ya configurado)
#
#  Requisito previo: haber ejecutado setup.sh al menos una vez.
#  Uso:  ./start.sh
# =============================================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/backend/.env"
LOG_DIR="$SCRIPT_DIR/logs"
VENV="$SCRIPT_DIR/backend/venv"

step() { echo -e "\n${BOLD}${GREEN}▶ $1${NC}"; }
info() { echo -e "  ${CYAN}ℹ  $1${NC}"; }
ok()   { echo -e "  ${GREEN}✔  $1${NC}"; }
warn() { echo -e "  ${YELLOW}⚠  $1${NC}"; }
err()  { echo -e "  ${RED}✘  $1${NC}"; exit 1; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║       LTI Virtual Tutor — Arrancar Servicios         ║${NC}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Verificar que existe configuración ────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
    err "No se encontró backend/.env — ejecuta primero: ./setup.sh"
fi

if ! grep -q "BASE_URL=" "$ENV_FILE" 2>/dev/null; then
    err "El archivo .env parece incompleto — ejecuta: ./setup.sh"
fi

# ── Leer configuración del .env ───────────────────────────────────────────────
BACKEND_PORT=$(grep "^BACKEND_DEV_PORT=" "$ENV_FILE" | cut -d= -f2-)
FRONTEND_PORT=$(grep "^FRONTEND_DEV_PORT=" "$ENV_FILE" | cut -d= -f2-)
TUTOR_BASE_URL=$(grep "^BASE_URL=" "$ENV_FILE" | cut -d= -f2-)
AI_PROVIDER=$(grep "^AI_PROVIDER=" "$ENV_FILE" | cut -d= -f2-)

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

echo -e "  ${BOLD}Configuración detectada:${NC}"
echo -e "  • Tutor URL:    ${CYAN}${TUTOR_BASE_URL}${NC}"
echo -e "  • Proveedor IA: ${CYAN}${AI_PROVIDER}${NC}"
echo -e "  • Backend port: ${CYAN}${BACKEND_PORT}${NC}"
echo -e "  • Frontend port:${CYAN}${FRONTEND_PORT}${NC}"

# ── Verificar dependencias mínimas ────────────────────────────────────────────
step "Verificando requisitos"

[[ -d "$VENV" ]] || err "Entorno virtual no encontrado. Ejecuta: ./setup.sh"
ok "venv Python encontrado"

[[ -d "$SCRIPT_DIR/frontend/node_modules" ]] || err "node_modules no encontrado. Ejecuta: ./setup.sh"
ok "node_modules encontrado"

command -v docker &>/dev/null || err "Docker no disponible"
ok "Docker disponible"

# ── Crear directorios necesarios ──────────────────────────────────────────────
mkdir -p "$SCRIPT_DIR/backend/data" "$LOG_DIR"

# ── Detener servicios previos si estaban corriendo ────────────────────────────
step "Limpiando procesos previos"

if [[ -f "$LOG_DIR/backend.pid" ]]; then
    OLD_PID=$(cat "$LOG_DIR/backend.pid")
    kill "$OLD_PID" 2>/dev/null && info "Backend anterior (PID $OLD_PID) detenido" || true
    rm -f "$LOG_DIR/backend.pid"
fi
pkill -f "uvicorn app.main:app" 2>/dev/null && info "Uvicorn detenido" || true

if [[ -f "$LOG_DIR/frontend.pid" ]]; then
    OLD_PID=$(cat "$LOG_DIR/frontend.pid")
    kill "$OLD_PID" 2>/dev/null && info "Frontend anterior (PID $OLD_PID) detenido" || true
    rm -f "$LOG_DIR/frontend.pid"
fi
pkill -f "vite" 2>/dev/null && info "Vite detenido" || true

sleep 1

# ── Levantar proxy nginx (Docker) ─────────────────────────────────────────────
step "Levantando proxy nginx (Docker)"
cd "$SCRIPT_DIR"
docker compose down --remove-orphans 2>/dev/null || true
docker compose up -d
ok "Proxy nginx activo"

# ── Lanzar backend ────────────────────────────────────────────────────────────
step "Lanzando backend FastAPI (puerto $BACKEND_PORT)"
cd "$SCRIPT_DIR/backend"
nohup "$VENV/bin/uvicorn" app.main:app \
    --host 0.0.0.0 \
    --port "$BACKEND_PORT" \
    --reload \
    > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$LOG_DIR/backend.pid"
ok "Backend PID $BACKEND_PID"

# ── Lanzar frontend ───────────────────────────────────────────────────────────
step "Lanzando frontend Vite (puerto $FRONTEND_PORT)"
cd "$SCRIPT_DIR/frontend"
nohup npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" \
    > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$LOG_DIR/frontend.pid"
ok "Frontend PID $FRONTEND_PID"

# ── Verificar que responden ───────────────────────────────────────────────────
step "Verificando servicios (espera 5s)..."
sleep 5

check_service() {
    local name="$1" url="$2"
    if curl -sk --max-time 5 "$url" > /dev/null 2>&1; then
        ok "$name  →  $url"
    else
        warn "$name aún iniciando  →  $url"
    fi
}

check_service "Backend"  "http://localhost:$BACKEND_PORT/api/health"
check_service "Frontend" "http://localhost:$FRONTEND_PORT"
check_service "Proxy"    "${TUTOR_BASE_URL}/api/health"

# ── Resumen final ─────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║                    ✅  SERVICIOS ACTIVOS                     ║${NC}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}🌐 Tutor:${NC}        ${TUTOR_BASE_URL}"
echo -e "  ${GREEN}🔧 Admin panel:${NC}  ${TUTOR_BASE_URL}/?admin=1"
echo -e "  ${GREEN}📋 API Docs:${NC}     http://localhost:$BACKEND_PORT/docs"
echo ""
echo -e "  ${BOLD}Logs en tiempo real:${NC}"
echo -e "  tail -f $LOG_DIR/backend.log"
echo -e "  tail -f $LOG_DIR/frontend.log"
echo ""
echo -e "  ${BOLD}Para detener todos los servicios:${NC}"
echo -e "  $SCRIPT_DIR/stop.sh"
echo ""
