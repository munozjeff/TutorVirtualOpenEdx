#!/usr/bin/env bash
# =============================================================================
#  start-prod.sh — LTI Virtual Tutor · Arrancar producción (sin rebuild)
#
#  Requisito previo: haber ejecutado ./deploy.sh al menos una vez.
#  Uso:  ./start-prod.sh
# =============================================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/backend/.env"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.prod.yml"

ok()  { echo -e "  ${GREEN}✔  $1${NC}"; }
warn(){ echo -e "  ${YELLOW}⚠  $1${NC}"; }
err() { echo -e "  ${RED}✘  $1${NC}"; exit 1; }
step(){ echo -e "\n${BOLD}${GREEN}▶ $1${NC}"; }
info(){ echo -e "  ${CYAN}ℹ  $1${NC}"; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║   LTI Virtual Tutor — Arrancar Producción            ║${NC}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Verificar prerequisitos ───────────────────────────────────────────────────
[[ -f "$ENV_FILE" ]]         || err "No se encontró backend/.env — ejecuta: ./setup.sh"
[[ -f "$COMPOSE_FILE" ]]     || err "No se encontró docker-compose.prod.yml"
[[ -f "$SCRIPT_DIR/nginx/tutor_prod.conf" ]] || err "No se encontró nginx/tutor_prod.conf — ejecuta: ./deploy.sh primero"
command -v docker &>/dev/null || err "Docker no disponible"

# Verificar que las imágenes existen
BACKEND_IMAGE=$(docker compose -f "$COMPOSE_FILE" config --images 2>/dev/null | grep backend || true)
if ! docker images --format '{{.Repository}}' | grep -q "tutor"; then
    warn "No se encontraron imágenes construidas."
    echo ""
    echo -e "  Ejecuta primero: ${CYAN}./deploy.sh${NC}"
    exit 1
fi

# ── Leer config del .env ──────────────────────────────────────────────────────
TUTOR_BASE_URL=$(grep "^BASE_URL=" "$ENV_FILE" | cut -d= -f2-)
AI_PROVIDER=$(grep "^AI_PROVIDER=" "$ENV_FILE" | cut -d= -f2-)
TUTOR_SCHEME=$(echo "$TUTOR_BASE_URL" | cut -d: -f1)
TUTOR_PORT=$(echo "$TUTOR_BASE_URL" | grep -oP ':\K\d+$' || echo "")
[[ -z "$TUTOR_PORT" ]] && { [[ "$TUTOR_SCHEME" == "https" ]] && TUTOR_PORT=443 || TUTOR_PORT=80; }

[[ "$TUTOR_SCHEME" == "https" ]] && PROXY_HTTP_PORT=80 PROXY_HTTPS_PORT="$TUTOR_PORT" \
                                 || PROXY_HTTP_PORT="$TUTOR_PORT" PROXY_HTTPS_PORT=443
export PROXY_HTTP_PORT PROXY_HTTPS_PORT

echo -e "  ${BOLD}Configuración:${NC}"
echo -e "  • Tutor URL:    ${CYAN}${TUTOR_BASE_URL}${NC}"
echo -e "  • Proveedor IA: ${CYAN}${AI_PROVIDER}${NC}"

# ── Detener contenedores previos si están corriendo ───────────────────────────
step "Verificando contenedores previos"
RUNNING=$(docker compose -f "$COMPOSE_FILE" ps --status running --quiet 2>/dev/null | wc -l)
if [[ "$RUNNING" -gt 0 ]]; then
    info "Deteniendo contenedores activos..."
    docker compose -f "$COMPOSE_FILE" down --remove-orphans
fi
ok "Limpio"

# ── Levantar stack ────────────────────────────────────────────────────────────
step "Levantando stack de producción"
docker compose -f "$COMPOSE_FILE" up -d
ok "Contenedores iniciados"

# ── Esperar backend ───────────────────────────────────────────────────────────
step "Esperando que el backend responda..."
MAX_WAIT=60
WAITED=0
until docker compose -f "$COMPOSE_FILE" exec -T backend \
    python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" \
    > /dev/null 2>&1; do
    sleep 3; WAITED=$((WAITED + 3))
    [[ $WAITED -ge $MAX_WAIT ]] && { warn "Backend tardando — revisa: docker logs tutor_backend"; break; }
    info "Esperando... ${WAITED}s"
done
ok "Backend listo"

# ── Estado ────────────────────────────────────────────────────────────────────
step "Estado del stack"
docker compose -f "$COMPOSE_FILE" ps

# ── Resumen ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║              ✅  PRODUCCIÓN ACTIVA                           ║${NC}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}🌐 Tutor:${NC}        ${TUTOR_BASE_URL}"
echo -e "  ${GREEN}🔧 Admin panel:${NC}  ${TUTOR_BASE_URL}/?admin=1"
echo ""
echo -e "  ${BOLD}Logs:${NC}"
echo -e "  docker logs -f tutor_backend"
echo -e "  docker logs -f tutor_frontend"
echo -e "  docker logs -f tutor_proxy"
echo ""
echo -e "  ${BOLD}Para detener:${NC}"
echo -e "  docker compose -f docker-compose.prod.yml down"
echo ""
