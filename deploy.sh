#!/usr/bin/env bash
# =============================================================================
#  deploy.sh — LTI Virtual Tutor · Despliegue en producción (todo en Docker)
#
#  Requisito previo: haber ejecutado setup.sh al menos una vez (genera .env y certs).
#  Uso:  ./deploy.sh [--build]
#
#  Diferencias respecto a desarrollo:
#   - Backend y frontend corren en contenedores Docker
#   - Frontend: bundle estático compilado (Vite build), no dev server
#   - Backend: uvicorn con workers múltiples, sin --reload
#   - nginx usa nombres de contenedor Docker (no IP bridge)
# =============================================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/backend/.env"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.prod.yml"

step() { echo -e "\n${BOLD}${GREEN}▶ $1${NC}"; }
info() { echo -e "  ${CYAN}ℹ  $1${NC}"; }
ok()   { echo -e "  ${GREEN}✔  $1${NC}"; }
warn() { echo -e "  ${YELLOW}⚠  $1${NC}"; }
err()  { echo -e "  ${RED}✘  $1${NC}"; exit 1; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║     LTI Virtual Tutor — Despliegue Producción        ║${NC}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Verificar prerequisitos ───────────────────────────────────────────────────
[[ -f "$ENV_FILE" ]] || err "No se encontró backend/.env — ejecuta primero: ./setup.sh"
grep -q "BASE_URL=" "$ENV_FILE" || err "El .env parece incompleto — ejecuta: ./setup.sh"
command -v docker &>/dev/null || err "Docker no disponible"

# ── Leer configuración del .env ───────────────────────────────────────────────
TUTOR_BASE_URL=$(grep "^BASE_URL=" "$ENV_FILE" | cut -d= -f2-)
TUTOR_HOST=$(echo "$TUTOR_BASE_URL" | sed 's|https\?://||' | cut -d: -f1)
TUTOR_SCHEME=$(echo "$TUTOR_BASE_URL" | cut -d: -f1)
TUTOR_PORT=$(echo "$TUTOR_BASE_URL" | grep -oP ':\K\d+$' || echo "")
AI_PROVIDER=$(grep "^AI_PROVIDER=" "$ENV_FILE" | cut -d= -f2-)
BACKEND_PORT=$(grep "^BACKEND_DEV_PORT=" "$ENV_FILE" | cut -d= -f2- || echo "8000")

# Puerto por defecto si no está en la URL
[[ -z "$TUTOR_PORT" ]] && { [[ "$TUTOR_SCHEME" == "https" ]] && TUTOR_PORT=443 || TUTOR_PORT=80; }

# Determinar si HTTP o HTTPS
if [[ "$TUTOR_SCHEME" == "https" ]]; then
    PROXY_HTTP_PORT=80
    PROXY_HTTPS_PORT="$TUTOR_PORT"
    CERT_FILE="$SCRIPT_DIR/nginx/certs/${TUTOR_HOST}.pem"
    KEY_FILE="$SCRIPT_DIR/nginx/certs/${TUTOR_HOST}-key.pem"
    USE_SSL=true
else
    PROXY_HTTP_PORT="$TUTOR_PORT"
    PROXY_HTTPS_PORT=443
    USE_SSL=false
fi

echo -e "  ${BOLD}Configuración detectada:${NC}"
echo -e "  • Tutor URL:    ${CYAN}${TUTOR_BASE_URL}${NC}"
echo -e "  • Proveedor IA: ${CYAN}${AI_PROVIDER}${NC}"
echo -e "  • SSL:          ${CYAN}${USE_SSL}${NC}"
echo ""

# ── Verificar certificados SSL si aplica ──────────────────────────────────────
if [[ "$USE_SSL" == "true" ]]; then
    [[ -f "$CERT_FILE" ]] || err "Certificado no encontrado: $CERT_FILE\n  Ejecuta ./setup.sh para regenerarlo."
    [[ -f "$KEY_FILE" ]]  || err "Clave privada no encontrada: $KEY_FILE\n  Ejecuta ./setup.sh para regenerarlo."
    ok "Certificados SSL encontrados"
fi

# ── Generar nginx/tutor_prod.conf ─────────────────────────────────────────────
step "Generando configuración nginx de producción"
NGINX_CONF="$SCRIPT_DIR/nginx/tutor_prod.conf"
mkdir -p "$SCRIPT_DIR/nginx"

# En producción nginx habla con contenedores por nombre de servicio Docker
BACKEND_UPSTREAM="backend:8000"
FRONTEND_UPSTREAM="frontend:80"

if [[ "$USE_SSL" == "true" ]]; then
cat > "$NGINX_CONF" <<NGINX
# ── HTTP → redirige a HTTPS ───────────────────────────────────────────────────
server {
    listen 80;
    server_name ${TUTOR_HOST};
    return 301 https://\$host:${TUTOR_PORT}\$request_uri;
}

# ── HTTPS ─────────────────────────────────────────────────────────────────────
server {
    listen 443 ssl;
    server_name ${TUTOR_HOST};

    ssl_certificate     /etc/nginx/certs/${TUTOR_HOST}.pem;
    ssl_certificate_key /etc/nginx/certs/${TUTOR_HOST}-key.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # API y LTI → backend FastAPI
    location /api/ {
        proxy_pass         http://${BACKEND_UPSTREAM};
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-Proto https;
        proxy_read_timeout 120s;
    }

    location /lti/ {
        proxy_pass         http://${BACKEND_UPSTREAM};
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-Proto https;
    }

    # Frontend → bundle estático
    location / {
        proxy_pass         http://${FRONTEND_UPSTREAM};
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-Proto https;
        proxy_http_version 1.1;
    }
}
NGINX
else
cat > "$NGINX_CONF" <<NGINX
# ── HTTP ──────────────────────────────────────────────────────────────────────
server {
    listen 80;
    server_name ${TUTOR_HOST};

    location /api/ {
        proxy_pass         http://${BACKEND_UPSTREAM};
        proxy_set_header   Host      \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_read_timeout 120s;
    }

    location /lti/ {
        proxy_pass         http://${BACKEND_UPSTREAM};
        proxy_set_header   Host      \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
    }

    location / {
        proxy_pass         http://${FRONTEND_UPSTREAM};
        proxy_set_header   Host      \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_http_version 1.1;
    }
}
NGINX
fi

ok "nginx/tutor_prod.conf generado (backend: ${BACKEND_UPSTREAM})"

# ── Exportar variables para docker-compose ────────────────────────────────────
export PROXY_HTTP_PORT
export PROXY_HTTPS_PORT

# ── Detener stack previo si existe ────────────────────────────────────────────
step "Deteniendo stack anterior (si existe)"
cd "$SCRIPT_DIR"
docker compose -f "$COMPOSE_FILE" down --remove-orphans 2>/dev/null && ok "Stack anterior detenido" || true

# ── Construir imágenes ────────────────────────────────────────────────────────
step "Construyendo imágenes Docker"
info "Backend  → Python 3.10 + uvicorn (2 workers)"
info "Frontend → Vite build + nginx estático"
info "Esto puede tardar 2-5 minutos la primera vez..."
echo ""

if [[ "$1" == "--no-cache" ]]; then
    docker compose -f "$COMPOSE_FILE" build --no-cache
else
    docker compose -f "$COMPOSE_FILE" build
fi

ok "Imágenes construidas"

# ── Levantar stack ────────────────────────────────────────────────────────────
step "Levantando stack de producción"
docker compose -f "$COMPOSE_FILE" up -d
ok "Contenedores iniciados"

# ── Esperar que el backend esté listo ─────────────────────────────────────────
step "Esperando que el backend responda..."
MAX_WAIT=60
WAITED=0
until docker compose -f "$COMPOSE_FILE" exec -T backend \
    python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" \
    > /dev/null 2>&1; do
    sleep 3
    WAITED=$((WAITED + 3))
    [[ $WAITED -ge $MAX_WAIT ]] && { warn "Backend tardando más de ${MAX_WAIT}s — revisa: docker logs tutor_backend"; break; }
    info "Esperando backend... ${WAITED}s"
done
ok "Backend listo"

# ── Estado del stack ──────────────────────────────────────────────────────────
step "Estado de los contenedores"
docker compose -f "$COMPOSE_FILE" ps

# ── Resumen final ─────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║              ✅  PRODUCCIÓN ACTIVA                           ║${NC}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}🌐 Tutor:${NC}        ${TUTOR_BASE_URL}"
echo -e "  ${GREEN}🔧 Admin panel:${NC}  ${TUTOR_BASE_URL}/?admin=1"
echo ""
echo -e "  ${BOLD}Logs en tiempo real:${NC}"
echo -e "  docker logs -f tutor_backend"
echo -e "  docker logs -f tutor_frontend"
echo -e "  docker logs -f tutor_proxy"
echo ""
echo -e "  ${BOLD}Gestión del stack:${NC}"
echo -e "  docker compose -f docker-compose.prod.yml ps      # estado"
echo -e "  docker compose -f docker-compose.prod.yml down    # detener"
echo -e "  docker compose -f docker-compose.prod.yml restart backend  # reiniciar backend"
echo ""
echo -e "  ${BOLD}Reconstruir tras cambios:${NC}"
echo -e "  ./deploy.sh"
echo -e "  ./deploy.sh --no-cache   # forzar rebuild completo"
echo ""
