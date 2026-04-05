#!/usr/bin/env bash
# =============================================================================
#  setup.sh — LTI Virtual Tutor · Configuración y arranque automático
#
#  Modos disponibles:
#   1) HTTPS local (mkcert) — desarrollo/pruebas, dominio personalizado
#   2) HTTP mismo dominio   — testing HTTP simple, mismo dominio que Open edX
#   3) HTTPS producción     — certificado SSL real (Let's Encrypt, etc.)
# =============================================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

banner() {
    echo ""
    echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}${BOLD}║       LTI Virtual Tutor — Setup & Launch             ║${NC}"
    echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
}

step() { echo -e "\n${BOLD}${GREEN}▶ $1${NC}"; }
info() { echo -e "  ${CYAN}ℹ  $1${NC}"; }
warn() { echo -e "  ${YELLOW}⚠  $1${NC}"; }
ok()   { echo -e "  ${GREEN}✔  $1${NC}"; }
err()  { echo -e "  ${RED}✘  $1${NC}"; exit 1; }

ask() {
    local prompt="$1" default="$2"
    echo -ne "  ${BOLD}$prompt${NC} [${CYAN}$default${NC}]: "
    read -r input
    REPLY="${input:-$default}"
}

ask_secret() {
    local prompt="$1" default="$2"
    echo -ne "  ${BOLD}$prompt${NC} [${CYAN}$default${NC}]: "
    read -rs input; echo ""
    REPLY="${input:-$default}"
}

# ── 0. Banner ─────────────────────────────────────────────────────────────────
banner

# ── 0b. Detectar si ya está configurado ───────────────────────────────────────
ENV_FILE_CHECK="$SCRIPT_DIR/backend/.env"
if [[ -f "$ENV_FILE_CHECK" ]] && grep -q "BASE_URL=" "$ENV_FILE_CHECK" 2>/dev/null; then
    EXISTING_URL=$(grep "^BASE_URL=" "$ENV_FILE_CHECK" | cut -d= -f2-)
    EXISTING_AI=$(grep "^AI_PROVIDER=" "$ENV_FILE_CHECK" | cut -d= -f2-)
    echo -e "  ${GREEN}✔ Configuración existente detectada:${NC}"
    echo -e "  • Tutor URL: ${CYAN}${EXISTING_URL}${NC}"
    echo -e "  • Proveedor IA: ${CYAN}${EXISTING_AI}${NC}"
    echo ""
    echo -e "  ${BOLD}¿Qué deseas hacer?${NC}"
    echo -e "  ${BOLD}1)${NC} Usar config existente — solo (re)instalar deps y levantar servicios"
    echo -e "  ${BOLD}2)${NC} Reconfigurar todo desde cero"
    echo ""
    ask "Elige (1/2)" "1"
    if [[ "$REPLY" == "1" ]]; then
        info "Usando configuración existente. Reinstalando deps y levantando servicios..."
        # Leer puertos del .env existente
        BACKEND_PORT=$(grep "^BACKEND_DEV_PORT=" "$ENV_FILE_CHECK" | cut -d= -f2-)
        FRONTEND_PORT=$(grep "^FRONTEND_DEV_PORT=" "$ENV_FILE_CHECK" | cut -d= -f2-)
        BACKEND_PORT="${BACKEND_PORT:-8000}"
        FRONTEND_PORT="${FRONTEND_PORT:-5173}"
        AI_PROVIDER=$(grep "^AI_PROVIDER=" "$ENV_FILE_CHECK" | cut -d= -f2-)

        # Saltar al paso de dependencias directamente
        mkdir -p "$SCRIPT_DIR/backend/data" "$SCRIPT_DIR/logs"

        step "Verificando dependencias del sistema"
        sudo apt-get update -q 2>/dev/null
        install_if_missing libnss3-tools certutil
        install_if_missing wget wget
        install_if_missing python3-pip pip3
        install_if_missing nodejs node
        if ! command -v docker &>/dev/null; then
            err "Docker no encontrado. Instálalo con: curl -fsSL https://get.docker.com | sudo sh"
        else
            ok "Docker $(docker --version | cut -d' ' -f3 | tr -d ',')"
        fi

        step "Verificando dependencias Python (venv)"
        VENV="$SCRIPT_DIR/backend/venv"
        if [[ ! -d "$VENV" ]]; then
            python3 -m venv "$VENV"
            ok "venv creado"
        else
            ok "venv ya existe"
        fi
        "$VENV/bin/pip" install -q -r "$SCRIPT_DIR/backend/requirements.txt"
        ok "Dependencias Python listas"

        step "Verificando dependencias Node.js"
        if [[ ! -d "$SCRIPT_DIR/frontend/node_modules" ]]; then
            npm install --prefix "$SCRIPT_DIR/frontend" --silent
            ok "node_modules instalado"
        else
            ok "node_modules ya existe"
        fi

        step "Levantando proxy nginx con Docker"
        cd "$SCRIPT_DIR"
        docker compose down --remove-orphans 2>/dev/null || true
        docker compose up -d
        ok "Proxy nginx corriendo"

        step "Lanzando backend FastAPI"
        LOG_DIR="$SCRIPT_DIR/logs"
        pkill -f "uvicorn app.main:app" 2>/dev/null || true
        sleep 1
        cd "$SCRIPT_DIR/backend"
        nohup "$VENV/bin/uvicorn" app.main:app \
            --host 0.0.0.0 --port "$BACKEND_PORT" --reload \
            > "$LOG_DIR/backend.log" 2>&1 &
        echo "$!" > "$LOG_DIR/backend.pid"
        ok "Backend lanzado → logs/backend.log"

        step "Lanzando frontend Vite"
        pkill -f "vite" 2>/dev/null || true
        sleep 1
        cd "$SCRIPT_DIR/frontend"
        nohup npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" \
            > "$LOG_DIR/frontend.log" 2>&1 &
        echo "$!" > "$LOG_DIR/frontend.pid"
        ok "Frontend lanzado → logs/frontend.log"

        sleep 4
        TUTOR_BASE_URL="$EXISTING_URL"
        check_service() {
            local name="$1" url="$2"
            curl -sk --max-time 5 "$url" > /dev/null 2>&1 \
                && ok "$name responde" || warn "$name aún iniciando (puede tardar unos segundos)"
        }
        check_service "Backend"  "http://localhost:$BACKEND_PORT/api/health"
        check_service "Frontend" "http://localhost:$FRONTEND_PORT"
        check_service "Proxy"    "${TUTOR_BASE_URL}/api/health"

        echo ""
        echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${CYAN}${BOLD}║                    ✅  SERVICIOS ACTIVOS                     ║${NC}"
        echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "  ${GREEN}🌐 Tutor:${NC}       ${TUTOR_BASE_URL}"
        echo -e "  ${GREEN}🔧 Admin:${NC}        ${TUTOR_BASE_URL}/?admin=1"
        echo -e "  ${GREEN}📋 API Docs:${NC}     http://localhost:$BACKEND_PORT/docs"
        echo ""
        echo -e "  ${BOLD}Para detener:${NC} $SCRIPT_DIR/stop.sh"
        echo -e "  ${BOLD}Para solo arrancar la próxima vez:${NC} $SCRIPT_DIR/start.sh"
        echo ""
        exit 0
    fi
    echo ""
fi

# ── 1. Selección de modo ──────────────────────────────────────────────────────
step "Modo de instalación"
echo ""
echo -e "  ${BOLD}1)${NC} ${GREEN}HTTPS local (mkcert)${NC}"
echo -e "     Certificado SSL auto-firmado y de confianza local. Dominio"
echo -e "     personalizado (ej: tutor.local.openedx.io). Requiere Docker."
echo -e "     ${YELLOW}Cookie: SameSite=None; Secure — funciona en iframe cross-origin.${NC}"
echo ""
echo -e "  ${BOLD}2)${NC} ${GREEN}HTTP mismo dominio${NC}"
echo -e "     Sin HTTPS. El tutor usa el MISMO dominio que Open edX pero"
echo -e "     distinto puerto (ej: local.openedx.io:8080). Requiere Docker."
echo -e "     ${YELLOW}Cookie: SameSite=Lax — funciona porque comparte dominio con Open edX.${NC}"
echo ""
echo -e "  ${BOLD}3)${NC} ${GREEN}HTTPS producción (certificado real)${NC}"
echo -e "     Certificado SSL real (Let's Encrypt, ZeroSSL, etc.)."
echo -e "     Para servidores con dominio público. Requiere Docker."
echo -e "     ${YELLOW}Cookie: SameSite=None; Secure — funciona en iframe cross-origin.${NC}"
echo ""
ask "Elige modo (1/2/3)" "1"
INSTALL_MODE="$REPLY"

[[ "$INSTALL_MODE" =~ ^[123]$ ]] || err "Modo inválido. Elige 1, 2 o 3."

# ── 2. Configuración común ────────────────────────────────────────────────────
step "Configuración general"
echo "  Presiona Enter para aceptar los valores por defecto."
echo ""

ask "URL base de Open edX (issuer)" "http://local.openedx.io"
OPENEDX_ISSUER="$REPLY"

ask "Puerto del backend (FastAPI)" "8000"
BACKEND_PORT="$REPLY"

ask "Puerto del frontend (Vite dev server)" "5173"
FRONTEND_PORT="$REPLY"

ask "Proveedor IA (gemini / ollama)" "gemini"
AI_PROVIDER="$REPLY"

if [[ "$AI_PROVIDER" == "gemini" ]]; then
    CURRENT_KEY=$(grep "GEMINI_API_KEY=" "$SCRIPT_DIR/backend/.env" 2>/dev/null | cut -d= -f2 || echo "")
    ask_secret "Gemini API Key" "${CURRENT_KEY:-tu-api-key-aqui}"
    GEMINI_API_KEY="$REPLY"
    OLLAMA_BASE_URL="http://localhost:11434"
    OLLAMA_MODEL="llama3"
else
    ask "URL de Ollama" "http://localhost:11434"
    OLLAMA_BASE_URL="$REPLY"
    ask "Modelo Ollama" "llama3"
    OLLAMA_MODEL="$REPLY"
    GEMINI_API_KEY=""
fi

# ── 3. Configuración específica por modo ──────────────────────────────────────
if [[ "$INSTALL_MODE" == "1" ]]; then
    # ── Modo 1: HTTPS local (mkcert) ──────────────────────────────────────────
    echo ""
    step "Configuración HTTPS local (mkcert)"
    ask "Hostname del tutor" "tutor.local.openedx.io"
    TUTOR_HOST="$REPLY"
    ask "Puerto HTTPS" "4443"
    TUTOR_PORT="$REPLY"
    TUTOR_HTTP_PORT="8001"
    TUTOR_SCHEME="https"
    APP_ENV="production"
    NEEDS_MKCERT=true
    NEEDS_SSL_CERT=true
    NEEDS_HOSTS_ENTRY=true
    SSL_CERT_FILE=""
    SSL_KEY_FILE=""

elif [[ "$INSTALL_MODE" == "2" ]]; then
    # ── Modo 2: HTTP mismo dominio ─────────────────────────────────────────────
    echo ""
    step "Configuración HTTP mismo dominio"
    warn "El hostname del tutor DEBE compartir dominio con Open edX para que"
    warn "SameSite=Lax funcione correctamente en el iframe."
    echo ""
    # Extraer dominio base de Open edX issuer
    OPENEDX_DOMAIN=$(echo "$OPENEDX_ISSUER" | sed 's|https\?://||' | cut -d: -f1)
    ask "Hostname del tutor (mismo dominio que Open edX)" "$OPENEDX_DOMAIN"
    TUTOR_HOST="$REPLY"
    ask "Puerto HTTP del tutor" "8080"
    TUTOR_PORT="$REPLY"
    TUTOR_HTTP_PORT="$TUTOR_PORT"
    TUTOR_SCHEME="http"
    APP_ENV="development"
    NEEDS_MKCERT=false
    NEEDS_SSL_CERT=false
    # Solo añadir a /etc/hosts si no es el mismo host que Open edX
    if [[ "$TUTOR_HOST" == "$OPENEDX_DOMAIN" ]]; then
        NEEDS_HOSTS_ENTRY=false
    else
        NEEDS_HOSTS_ENTRY=true
    fi
    SSL_CERT_FILE=""
    SSL_KEY_FILE=""

elif [[ "$INSTALL_MODE" == "3" ]]; then
    # ── Modo 3: HTTPS producción (certificado real) ────────────────────────────
    echo ""
    step "Configuración HTTPS producción"
    ask "Hostname/dominio del tutor" "tutor.midominio.com"
    TUTOR_HOST="$REPLY"
    ask "Puerto HTTPS" "443"
    TUTOR_PORT="$REPLY"
    TUTOR_HTTP_PORT="80"
    TUTOR_SCHEME="https"
    APP_ENV="production"
    NEEDS_MKCERT=false
    NEEDS_SSL_CERT=false
    NEEDS_HOSTS_ENTRY=false

    echo ""
    warn "Proporciona las rutas a tu certificado SSL real."
    ask "Ruta al certificado SSL (.pem/.crt)" "/etc/letsencrypt/live/$TUTOR_HOST/fullchain.pem"
    SSL_CERT_FILE="$REPLY"
    ask "Ruta a la clave privada SSL (.key)" "/etc/letsencrypt/live/$TUTOR_HOST/privkey.pem"
    SSL_KEY_FILE="$REPLY"

    [[ -f "$SSL_CERT_FILE" ]] || err "Certificado no encontrado: $SSL_CERT_FILE"
    [[ -f "$SSL_KEY_FILE" ]]  || err "Clave privada no encontrada: $SSL_KEY_FILE"
fi

# ── Resumen ───────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${BOLD}Resumen de configuración:${NC}"
echo -e "  • Modo:          ${CYAN}$([ "$INSTALL_MODE" == "1" ] && echo "HTTPS local (mkcert)" || { [ "$INSTALL_MODE" == "2" ] && echo "HTTP mismo dominio" || echo "HTTPS producción"; })${NC}"
echo -e "  • Tutor URL:     ${CYAN}${TUTOR_SCHEME}://$TUTOR_HOST:$TUTOR_PORT${NC}"
echo -e "  • Open edX:      ${CYAN}$OPENEDX_ISSUER${NC}"
echo -e "  • Backend:       ${CYAN}http://0.0.0.0:$BACKEND_PORT${NC}"
echo -e "  • Frontend:      ${CYAN}http://0.0.0.0:$FRONTEND_PORT${NC}"
echo -e "  • IA:            ${CYAN}$AI_PROVIDER${NC}"
echo ""
ask "¿Continuar con esta configuración?" "s"
[[ "$REPLY" =~ ^[sS]$ ]] || { echo "Cancelado."; exit 0; }

# ── 4. Dependencias del sistema ───────────────────────────────────────────────
step "Verificando dependencias del sistema"

install_if_missing() {
    local pkg="$1" bin="$2"
    if ! command -v "$bin" &>/dev/null; then
        info "Instalando $pkg..."
        sudo apt-get install -y "$pkg" -q
        ok "$pkg instalado"
    else
        ok "$bin ya disponible"
    fi
}

sudo apt-get update -q 2>/dev/null
install_if_missing libnss3-tools certutil
install_if_missing wget wget
install_if_missing python3-pip pip3
install_if_missing nodejs node

# Docker (necesario para todos los modos — nginx proxy)
if ! command -v docker &>/dev/null; then
    warn "Docker no encontrado. Instalando..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    warn "Docker instalado. Es posible que necesites cerrar sesión y volver a entrar."
    ok "Docker instalado"
else
    ok "Docker $(docker --version | cut -d' ' -f3 | tr -d ',')"
fi

# mkcert (solo modo 1)
if [[ "$NEEDS_MKCERT" == "true" ]]; then
    if ! command -v mkcert &>/dev/null; then
        info "Instalando mkcert..."
        MKCERT_VERSION="v1.4.4"
        ARCH=$(uname -m)
        [[ "$ARCH" == "x86_64" ]] && MKCERT_BIN="mkcert-${MKCERT_VERSION}-linux-amd64"
        [[ "$ARCH" == "aarch64" ]] && MKCERT_BIN="mkcert-${MKCERT_VERSION}-linux-arm64"
        [[ "$ARCH" == "armv7l" ]]  && MKCERT_BIN="mkcert-${MKCERT_VERSION}-linux-arm"
        if [[ -z "${MKCERT_BIN:-}" ]]; then
            err "Arquitectura $ARCH no soportada para mkcert automático. Instálalo manualmente."
        fi
        wget -q "https://github.com/FiloSottile/mkcert/releases/download/${MKCERT_VERSION}/${MKCERT_BIN}" -O /tmp/mkcert
        chmod +x /tmp/mkcert
        sudo mv /tmp/mkcert /usr/local/bin/mkcert
        ok "mkcert instalado"
    else
        ok "mkcert $(mkcert --version 2>/dev/null || echo 'disponible')"
    fi
fi

# ── 5. Instalar CA local de mkcert (solo modo 1) ──────────────────────────────
if [[ "$NEEDS_MKCERT" == "true" ]]; then
    step "Instalando CA local de mkcert"
    mkcert -install
    ok "CA local instalada — el navegador confiará en los certificados generados"
fi

# ── 6. /etc/hosts ─────────────────────────────────────────────────────────────
if [[ "$NEEDS_HOSTS_ENTRY" == "true" ]]; then
    step "Verificando /etc/hosts"
    if grep -q "^127.0.0.1.*$TUTOR_HOST" /etc/hosts; then
        ok "$TUTOR_HOST ya apunta a 127.0.0.1"
    else
        info "Añadiendo $TUTOR_HOST a /etc/hosts..."
        echo "127.0.0.1 $TUTOR_HOST" | sudo tee -a /etc/hosts > /dev/null
        ok "$TUTOR_HOST → 127.0.0.1 añadido"
    fi
fi

# ── 7. Generar/copiar certificados SSL ────────────────────────────────────────
CERTS_DIR="$SCRIPT_DIR/nginx/certs"
mkdir -p "$CERTS_DIR"

if [[ "$INSTALL_MODE" == "1" ]]; then
    step "Generando certificado SSL local (mkcert)"
    CERT_FILE="$CERTS_DIR/$TUTOR_HOST.pem"
    KEY_FILE="$CERTS_DIR/$TUTOR_HOST-key.pem"

    pushd "$CERTS_DIR" > /dev/null
    mkcert "$TUTOR_HOST" localhost 127.0.0.1 2>/dev/null
    popd > /dev/null

    GENERATED_CERT=$(ls "$CERTS_DIR"/*.pem 2>/dev/null | grep -v "\-key" | head -1)
    GENERATED_KEY=$(ls "$CERTS_DIR"/*-key.pem 2>/dev/null | head -1)

    [[ "$GENERATED_CERT" != "$CERT_FILE" && -f "$GENERATED_CERT" ]] && mv "$GENERATED_CERT" "$CERT_FILE"
    [[ "$GENERATED_KEY"  != "$KEY_FILE"  && -f "$GENERATED_KEY"  ]] && mv "$GENERATED_KEY"  "$KEY_FILE"

    ok "Certificado: $CERT_FILE"
    ok "Clave:       $KEY_FILE"

elif [[ "$INSTALL_MODE" == "3" ]]; then
    step "Enlazando certificado SSL de producción"
    CERT_FILE="$CERTS_DIR/$TUTOR_HOST.pem"
    KEY_FILE="$CERTS_DIR/$TUTOR_HOST-key.pem"
    cp "$SSL_CERT_FILE" "$CERT_FILE"
    cp "$SSL_KEY_FILE"  "$KEY_FILE"
    ok "Certificado copiado a $CERTS_DIR"
fi

# ── 8. Generar nginx config ───────────────────────────────────────────────────
step "Generando configuración nginx"
NGINX_CONF="$SCRIPT_DIR/nginx/tutor_proxy.conf"
DOCKER_BRIDGE_IP=$(ip route show | grep docker0 | grep -oP 'src \K[\d.]+' 2>/dev/null || echo "172.17.0.1")
info "IP bridge Docker detectada: $DOCKER_BRIDGE_IP"

if [[ "$INSTALL_MODE" == "1" ]]; then
    # ── Config HTTPS modo 1 (dev — proxy a Vite) ─────────────────────────────
    cat > "$NGINX_CONF" <<NGINX
# ── HTTP → redirige a HTTPS ──────────────────────────────────────────────────
server {
    listen 80;
    server_name $TUTOR_HOST;
    return 301 https://\$host:${TUTOR_PORT}\$request_uri;
}

# ── HTTPS ─────────────────────────────────────────────────────────────────────
server {
    listen 443 ssl;
    server_name $TUTOR_HOST;

    ssl_certificate     /etc/nginx/certs/$TUTOR_HOST.pem;
    ssl_certificate_key /etc/nginx/certs/$TUTOR_HOST-key.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://${DOCKER_BRIDGE_IP}:${FRONTEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /api/ {
        proxy_pass http://${DOCKER_BRIDGE_IP}:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }

    location /lti/ {
        proxy_pass http://${DOCKER_BRIDGE_IP}:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
}
NGINX

elif [[ "$INSTALL_MODE" == "2" ]]; then
    # ── Config HTTP ──────────────────────────────────────────────────────────
    cat > "$NGINX_CONF" <<NGINX
# ── HTTP (mismo dominio que Open edX, distinto puerto) ───────────────────────
server {
    listen 80;
    server_name $TUTOR_HOST;

    # Sin X-Frame-Options: el tutor se carga en el iframe de Open edX
    # SameSite=Lax funciona porque el dominio es el mismo que Open edX

    location / {
        proxy_pass http://${DOCKER_BRIDGE_IP}:${FRONTEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto http;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /api/ {
        proxy_pass http://${DOCKER_BRIDGE_IP}:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto http;
    }

    location /lti/ {
        proxy_pass http://${DOCKER_BRIDGE_IP}:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto http;
    }
}
NGINX

elif [[ "$INSTALL_MODE" == "3" ]]; then
    # ── Config HTTPS modo 3 (producción — archivos estáticos) ────────────────
    cat > "$NGINX_CONF" <<NGINX
# ── HTTP → redirige a HTTPS ──────────────────────────────────────────────────
server {
    listen 80;
    server_name $TUTOR_HOST;
    return 301 https://\$host:${TUTOR_PORT}\$request_uri;
}

# ── HTTPS producción ──────────────────────────────────────────────────────────
server {
    listen 443 ssl;
    server_name $TUTOR_HOST;

    ssl_certificate     /etc/nginx/certs/$TUTOR_HOST.pem;
    ssl_certificate_key /etc/nginx/certs/$TUTOR_HOST-key.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Frontend: archivos estáticos compilados (Vite build)
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://${DOCKER_BRIDGE_IP}:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }

    location /lti/ {
        proxy_pass http://${DOCKER_BRIDGE_IP}:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
}
NGINX
fi

ok "nginx config generada"

# ── 9. Generar docker-compose.yml ─────────────────────────────────────────────
step "Generando docker-compose.yml"

if [[ "$INSTALL_MODE" == "1" ]]; then
    COMPOSE_PORTS="      - \"${TUTOR_HTTP_PORT}:80\"\n      - \"${TUTOR_PORT}:443\""
    COMPOSE_VOLUMES="      - ./nginx/tutor_proxy.conf:/etc/nginx/conf.d/default.conf:ro\n      - ./nginx/certs:/etc/nginx/certs:ro"
elif [[ "$INSTALL_MODE" == "2" ]]; then
    COMPOSE_PORTS="      - \"${TUTOR_PORT}:80\""
    COMPOSE_VOLUMES="      - ./nginx/tutor_proxy.conf:/etc/nginx/conf.d/default.conf:ro"
elif [[ "$INSTALL_MODE" == "3" ]]; then
    COMPOSE_PORTS="      - \"${TUTOR_HTTP_PORT}:80\"\n      - \"${TUTOR_PORT}:443\""
    # Modo 3: nginx sirve frontend/dist como archivos estáticos
    COMPOSE_VOLUMES="      - ./nginx/tutor_proxy.conf:/etc/nginx/conf.d/default.conf:ro\n      - ./nginx/certs:/etc/nginx/certs:ro\n      - ./frontend/dist:/usr/share/nginx/html:ro"
fi

cat > "$SCRIPT_DIR/docker-compose.yml" <<COMPOSE
services:
  proxy:
    image: nginx:alpine
    container_name: tutor_proxy
    ports:
$(printf '%b' "$COMPOSE_PORTS" | sed 's/^/      /')
    volumes:
$(printf '%b' "$COMPOSE_VOLUMES" | sed 's/^/      /')
    restart: unless-stopped
COMPOSE

ok "docker-compose.yml actualizado"

# ── 10. Generar backend/.env ──────────────────────────────────────────────────
step "Escribiendo backend/.env"
ENV_FILE="$SCRIPT_DIR/backend/.env"

SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

TUTOR_BASE_URL="${TUTOR_SCHEME}://${TUTOR_HOST}:${TUTOR_PORT}"

# ALLOWED_ORIGINS
ALLOWED="${TUTOR_BASE_URL},${OPENEDX_ISSUER},http://localhost:${FRONTEND_PORT},http://localhost:${BACKEND_PORT}"
ALLOWED="${ALLOWED},http://apps.local.openedx.io,http://local.openedx.io"

cat > "$ENV_FILE" <<ENV
# ─── Generado por setup.sh — $(date '+%Y-%m-%d %H:%M:%S') ───────────────────
# ─── Modo: $([ "$INSTALL_MODE" == "1" ] && echo "HTTPS local (mkcert)" || { [ "$INSTALL_MODE" == "2" ] && echo "HTTP mismo dominio" || echo "HTTPS producción"; }) ─────────────────────────────────────────────

# ─── Servidor ────────────────────────────────────────────────────────────────
APP_ENV=${APP_ENV}
APP_HOST=0.0.0.0
APP_PORT=${BACKEND_PORT}
BASE_URL=${TUTOR_BASE_URL}

# ─── Seguridad ────────────────────────────────────────────────────────────────
SECRET_KEY=${SECRET_KEY}
SESSION_COOKIE_NAME=lti_session
SESSION_MAX_AGE=86400

# ─── Base de datos ────────────────────────────────────────────────────────────
DATABASE_URL=sqlite+aiosqlite:///./data/tutor.db

# ─── LTI 1.3 ──────────────────────────────────────────────────────────────────
LTI_PRIVATE_KEY_FILE=./data/lti_private.key
LTI_PUBLIC_KEY_FILE=./data/lti_public.pem

# ─── Open edX Platform ───────────────────────────────────────────────────────
OPENEDX_ISSUER=${OPENEDX_ISSUER}
OPENEDX_CLIENT_ID=your-client-id-from-openedx
OPENEDX_AUTH_ENDPOINT=${OPENEDX_ISSUER}/api/lti_consumer/v1/launch/
OPENEDX_TOKEN_ENDPOINT=${OPENEDX_ISSUER}/api/lti_consumer/v1/token/
OPENEDX_JWKS_ENDPOINT=${OPENEDX_ISSUER}/api/lti_consumer/v1/public_keysets/

# ─── Proveedor IA ─────────────────────────────────────────────────────────────
AI_PROVIDER=${AI_PROVIDER}
GEMINI_API_KEY=${GEMINI_API_KEY}
GEMINI_MODEL=gemini-flash-lite-latest
OLLAMA_BASE_URL=${OLLAMA_BASE_URL}
OLLAMA_MODEL=${OLLAMA_MODEL}

# ─── CORS / Frontend ─────────────────────────────────────────────────────────
FRONTEND_URL=${TUTOR_BASE_URL}
ALLOWED_ORIGINS=${ALLOWED}

# ─── Puertos locales de desarrollo (usados por start.sh) ─────────────────────
BACKEND_DEV_PORT=${BACKEND_PORT}
FRONTEND_DEV_PORT=${FRONTEND_PORT}

# ─── Puertos del proxy (usados por deploy.sh / start-prod.sh) ────────────────
PROXY_HTTPS_PORT=${TUTOR_PORT}
PROXY_HTTP_PORT=${TUTOR_HTTP_PORT}
ENV

ok "backend/.env escrito"

# ── 11. Crear directorios necesarios ─────────────────────────────────────────
mkdir -p "$SCRIPT_DIR/backend/data" "$SCRIPT_DIR/logs"
ok "Directorios data/ y logs/ listos"

# ── 12. Instalar dependencias Python ──────────────────────────────────────────
step "Verificando dependencias Python (venv)"
VENV="$SCRIPT_DIR/backend/venv"
if [[ ! -d "$VENV" ]]; then
    info "Creando entorno virtual..."
    python3 -m venv "$VENV"
    ok "venv creado"
else
    ok "venv ya existe"
fi
info "Instalando/actualizando paquetes Python..."
"$VENV/bin/pip" install -q -r "$SCRIPT_DIR/backend/requirements.txt"
ok "Dependencias Python listas"

# ── 12. Instalar dependencias Node y compilar frontend ────────────────────────
step "Verificando dependencias Node.js"
if [[ ! -d "$SCRIPT_DIR/frontend/node_modules" ]]; then
    info "Ejecutando npm install..."
    npm install --prefix "$SCRIPT_DIR/frontend" --silent
    ok "node_modules instalado"
else
    ok "node_modules ya existe"
fi

if [[ "$INSTALL_MODE" == "3" ]]; then
    step "Compilando frontend para producción (npm run build)"
    npm run build --prefix "$SCRIPT_DIR/frontend"
    ok "Frontend compilado en frontend/dist/"
fi

# ── 13. Levantar proxy nginx (Docker) ─────────────────────────────────────────
step "Levantando proxy nginx con Docker"
cd "$SCRIPT_DIR"
docker compose down --remove-orphans 2>/dev/null || true
docker compose up -d
ok "Proxy nginx corriendo"

# ── 14. Lanzar backend ────────────────────────────────────────────────────────
step "Lanzando backend FastAPI"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 1

cd "$SCRIPT_DIR/backend"
if [[ "$INSTALL_MODE" == "3" ]]; then
    # Producción: 2 workers, sin hot-reload
    nohup "$VENV/bin/uvicorn" app.main:app \
        --host 0.0.0.0 \
        --port "$BACKEND_PORT" \
        --workers 2 \
        > "$LOG_DIR/backend.log" 2>&1 &
else
    # Desarrollo: 1 worker con hot-reload
    nohup "$VENV/bin/uvicorn" app.main:app \
        --host 0.0.0.0 \
        --port "$BACKEND_PORT" \
        --reload \
        > "$LOG_DIR/backend.log" 2>&1 &
fi
BACKEND_PID=$!
echo "$BACKEND_PID" > "$LOG_DIR/backend.pid"
ok "Backend PID $BACKEND_PID → log: logs/backend.log"

# ── 15. Lanzar frontend (solo modos 1 y 2 — en modo 3 sirve nginx) ────────────
if [[ "$INSTALL_MODE" != "3" ]]; then
    step "Lanzando frontend Vite (desarrollo)"
    pkill -f "vite" 2>/dev/null || true
    sleep 1

    cd "$SCRIPT_DIR/frontend"
    nohup npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" \
        > "$LOG_DIR/frontend.log" 2>&1 &
    FRONTEND_PID=$!
    echo "$FRONTEND_PID" > "$LOG_DIR/frontend.pid"
    ok "Frontend PID $FRONTEND_PID → log: logs/frontend.log"
else
    ok "Frontend: archivos estáticos servidos por nginx (sin proceso Vite)"
fi

# ── 16. Verificar servicios ───────────────────────────────────────────────────
step "Verificando que los servicios respondan..."
sleep 4

check_service() {
    local name="$1" url="$2"
    if curl -sk --max-time 5 "$url" > /dev/null 2>&1; then
        ok "$name responde en $url"
    else
        warn "$name aún no responde en $url (puede tardar unos segundos más)"
    fi
}

check_service "Backend"  "http://localhost:$BACKEND_PORT/api/health"
[[ "$INSTALL_MODE" != "3" ]] && check_service "Frontend (Vite)" "http://localhost:$FRONTEND_PORT"
check_service "Proxy"    "${TUTOR_BASE_URL}/api/health"
check_service "Tutor"    "${TUTOR_BASE_URL}"

# ── 17. Resumen final ─────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║                    ✅  TODO LISTO                           ║${NC}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BOLD}  Modo:${NC} $([ "$INSTALL_MODE" == "1" ] && echo "HTTPS local (mkcert)" || { [ "$INSTALL_MODE" == "2" ] && echo "HTTP mismo dominio" || echo "HTTPS producción"; })"
echo ""
echo -e "${BOLD}  URLs del Tutor:${NC}"
echo -e "  ${GREEN}🌐 Tutor:${NC}        ${TUTOR_BASE_URL}"
echo -e "  ${GREEN}🔧 Admin panel:${NC}  ${TUTOR_BASE_URL}/?admin=1"
echo -e "  ${GREEN}📋 API Docs:${NC}     http://localhost:$BACKEND_PORT/docs"
echo ""
echo -e "${BOLD}  Registra en Open edX Studio (mismo valor para todos los bloques LTI):${NC}"
echo -e "  ${YELLOW}Tool Launch URL:${NC}      ${TUTOR_BASE_URL}/lti/launch"
echo -e "  ${YELLOW}Login Initiation URL:${NC} ${TUTOR_BASE_URL}/lti/login"
echo -e "  ${YELLOW}Redirect URI:${NC}         ${TUTOR_BASE_URL}/lti/launch"
echo -e "  ${YELLOW}JWKS / Keyset URL:${NC}    ${TUTOR_BASE_URL}/lti/jwks"
echo ""

if [[ "$INSTALL_MODE" == "2" ]]; then
    echo -e "  ${YELLOW}⚠  Modo HTTP:${NC} Las cookies usan SameSite=Lax."
    echo -e "     Funciona porque el dominio del tutor (${TUTOR_HOST}) es"
    echo -e "     el mismo que Open edX. No usar con dominios distintos."
    echo ""
fi

echo -e "${BOLD}  Logs en tiempo real:${NC}"
echo -e "  tail -f $LOG_DIR/backend.log"
echo -e "  tail -f $LOG_DIR/frontend.log"
echo ""
echo -e "${BOLD}  Para detener todos los servicios:${NC}"
echo -e "  $SCRIPT_DIR/stop.sh"
echo ""
