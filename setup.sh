#!/usr/bin/env bash
# =============================================================================
#  setup.sh — LTI Virtual Tutor · Configuración y arranque automático
#  Instala dependencias, genera certificados SSL locales (mkcert),
#  configura .env, nginx y lanza todos los servicios.
# =============================================================================
set -e

# ── Colores ───────────────────────────────────────────────────────────────────
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
err()  { echo -e "  ${RED}✘  $1${NC}"; }

ask() {
    # ask "Pregunta" "default" → devuelve respuesta en $REPLY
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

# ── 1. Recolectar configuración ───────────────────────────────────────────────
step "Configuración del tutor"
echo "  Presiona Enter para aceptar los valores por defecto."
echo ""

ask  "Hostname del tutor (en /etc/hosts)" "tutor.local.openedx.io"
TUTOR_HOST="$REPLY"

ask  "Puerto HTTPS del tutor" "4443"
TUTOR_HTTPS_PORT="$REPLY"

ask  "Puerto HTTP del backend (FastAPI)" "8000"
BACKEND_PORT="$REPLY"

ask  "Puerto del frontend (Vite dev server)" "5173"
FRONTEND_PORT="$REPLY"

ask  "URL base de Open edX (issuer)" "http://local.openedx.io"
OPENEDX_ISSUER="$REPLY"

ask  "Proveedor IA (gemini / ollama)" "gemini"
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

echo ""
echo -e "  ${BOLD}Resumen de configuración:${NC}"
echo -e "  • Tutor URL:     ${CYAN}https://$TUTOR_HOST:$TUTOR_HTTPS_PORT${NC}"
echo -e "  • Backend:       ${CYAN}http://0.0.0.0:$BACKEND_PORT${NC}"
echo -e "  • Frontend:      ${CYAN}http://0.0.0.0:$FRONTEND_PORT${NC}"
echo -e "  • Open edX:      ${CYAN}$OPENEDX_ISSUER${NC}"
echo -e "  • IA:            ${CYAN}$AI_PROVIDER${NC}"
echo ""
ask "¿Continuar con esta configuración?" "s"
[[ "$REPLY" =~ ^[sS]$ ]] || { echo "Cancelado."; exit 0; }

# ── 2. Instalar dependencias del sistema ──────────────────────────────────────
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

# Actualizar apt silenciosamente
sudo apt-get update -q 2>/dev/null

install_if_missing libnss3-tools certutil
install_if_missing wget wget
install_if_missing python3-pip pip3
install_if_missing nodejs node

# Docker
if ! command -v docker &>/dev/null; then
    warn "Docker no encontrado. Instalando..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    warn "Docker instalado. Es posible que necesites cerrar sesión y volver a entrar."
    ok "Docker instalado"
else
    ok "Docker $(docker --version | cut -d' ' -f3 | tr -d ',')"
fi

# mkcert
if ! command -v mkcert &>/dev/null; then
    info "Instalando mkcert..."
    MKCERT_VERSION="v1.4.4"
    ARCH=$(uname -m)
    [[ "$ARCH" == "x86_64" ]] && MKCERT_BIN="mkcert-${MKCERT_VERSION}-linux-amd64"
    [[ "$ARCH" == "aarch64" ]] && MKCERT_BIN="mkcert-${MKCERT_VERSION}-linux-arm64"
    [[ "$ARCH" == "armv7l" ]]  && MKCERT_BIN="mkcert-${MKCERT_VERSION}-linux-arm"
    if [[ -z "${MKCERT_BIN:-}" ]]; then
        err "Arquitectura $ARCH no soportada para mkcert automático. Instálalo manualmente."
        exit 1
    fi
    wget -q "https://github.com/FiloSottile/mkcert/releases/download/${MKCERT_VERSION}/${MKCERT_BIN}" -O /tmp/mkcert
    chmod +x /tmp/mkcert
    sudo mv /tmp/mkcert /usr/local/bin/mkcert
    ok "mkcert instalado"
else
    ok "mkcert $(mkcert --version 2>/dev/null || echo 'disponible')"
fi

# ── 3. Instalar CA local de mkcert ────────────────────────────────────────────
step "Instalando CA local de mkcert (autoridad certificadora)"
mkcert -install
ok "CA local instalada — el navegador confiará en los certificados generados"

# ── 4. /etc/hosts ─────────────────────────────────────────────────────────────
step "Verificando /etc/hosts"
if grep -q "^127.0.0.1.*$TUTOR_HOST" /etc/hosts; then
    ok "$TUTOR_HOST ya apunta a 127.0.0.1"
else
    info "Añadiendo $TUTOR_HOST a /etc/hosts..."
    echo "127.0.0.1 $TUTOR_HOST" | sudo tee -a /etc/hosts > /dev/null
    ok "$TUTOR_HOST → 127.0.0.1 añadido"
fi

# ── 5. Generar certificados SSL ───────────────────────────────────────────────
step "Generando certificado SSL local"
CERTS_DIR="$SCRIPT_DIR/nginx/certs"
mkdir -p "$CERTS_DIR"

CERT_FILE="$CERTS_DIR/$TUTOR_HOST.pem"
KEY_FILE="$CERTS_DIR/$TUTOR_HOST-key.pem"

if [[ -f "$CERT_FILE" && -f "$KEY_FILE" ]]; then
    info "Certificados ya existen, regenerando para hostname actualizado..."
fi

# Generar en el directorio de certs
pushd "$CERTS_DIR" > /dev/null
mkcert "$TUTOR_HOST" localhost 127.0.0.1 2>/dev/null
popd > /dev/null

# mkcert genera nombre con "+" si hay múltiples hosts — normalizar
GENERATED_CERT=$(ls "$CERTS_DIR"/*.pem 2>/dev/null | grep -v "\-key" | head -1)
GENERATED_KEY=$(ls "$CERTS_DIR"/*-key.pem 2>/dev/null | head -1)

if [[ "$GENERATED_CERT" != "$CERT_FILE" && -f "$GENERATED_CERT" ]]; then
    mv "$GENERATED_CERT" "$CERT_FILE"
fi
if [[ "$GENERATED_KEY" != "$KEY_FILE" && -f "$GENERATED_KEY" ]]; then
    mv "$GENERATED_KEY" "$KEY_FILE"
fi

ok "Certificado: $CERT_FILE"
ok "Clave:       $KEY_FILE"

# ── 6. Generar nginx config ───────────────────────────────────────────────────
step "Generando configuración nginx"
NGINX_CONF="$SCRIPT_DIR/nginx/tutor_proxy.conf"

# Detectar IP del bridge Docker (172.17.0.1 por defecto)
DOCKER_BRIDGE_IP=$(ip route show | grep docker0 | grep -oP 'src \K[\d.]+' 2>/dev/null || echo "172.17.0.1")
info "IP bridge Docker detectada: $DOCKER_BRIDGE_IP"

cat > "$NGINX_CONF" <<NGINX
# ── HTTP → redirige a HTTPS ──────────────────────────────────────────────────
server {
    listen 80;
    server_name $TUTOR_HOST;
    return 301 https://\$host:${TUTOR_HTTPS_PORT}\$request_uri;
}

# ── HTTPS (LTI en iframe requiere SameSite=None;Secure → necesita HTTPS) ─────
server {
    listen 443 ssl;
    server_name $TUTOR_HOST;

    ssl_certificate     /etc/nginx/certs/$TUTOR_HOST.pem;
    ssl_certificate_key /etc/nginx/certs/$TUTOR_HOST-key.pem;

    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # NO enviar X-Frame-Options: el tutor debe cargarse en iframe de Open edX

    # Frontend (React/Vite)
    location / {
        proxy_pass http://${DOCKER_BRIDGE_IP}:${FRONTEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        # WebSocket HMR para Vite
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Backend API
    location /api/ {
        proxy_pass http://${DOCKER_BRIDGE_IP}:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    # LTI Endpoints
    location /lti/ {
        proxy_pass http://${DOCKER_BRIDGE_IP}:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
NGINX

ok "nginx config generada"

# ── 7. Generar docker-compose.yml ─────────────────────────────────────────────
step "Generando docker-compose.yml"
cat > "$SCRIPT_DIR/docker-compose.yml" <<COMPOSE
services:
  proxy:
    image: nginx:alpine
    container_name: tutor_proxy
    ports:
      - "8001:80"               # HTTP (redirige a HTTPS)
      - "${TUTOR_HTTPS_PORT}:443"  # HTTPS con certificado mkcert local
    volumes:
      - ./nginx/tutor_proxy.conf:/etc/nginx/conf.d/default.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro
    restart: unless-stopped
COMPOSE
ok "docker-compose.yml actualizado"

# ── 8. Generar SECRET_KEY segura ──────────────────────────────────────────────
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# ── 9. Actualizar backend/.env ────────────────────────────────────────────────
step "Escribiendo backend/.env"
ENV_FILE="$SCRIPT_DIR/backend/.env"

# Construir ALLOWED_ORIGINS
ALLOWED="https://$TUTOR_HOST:$TUTOR_HTTPS_PORT,$OPENEDX_ISSUER,http://localhost:$FRONTEND_PORT,http://localhost:$BACKEND_PORT"
# Añadir dominios comunes de Open edX local
ALLOWED="$ALLOWED,http://apps.local.openedx.io,http://local.openedx.io"

cat > "$ENV_FILE" <<ENV
# ─── Generado por setup.sh — $(date '+%Y-%m-%d %H:%M:%S') ───────────────────
# ─── Servidor ────────────────────────────────────────────────────────────────
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=${BACKEND_PORT}
BASE_URL=https://${TUTOR_HOST}:${TUTOR_HTTPS_PORT}

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
FRONTEND_URL=https://${TUTOR_HOST}:${TUTOR_HTTPS_PORT}
ALLOWED_ORIGINS=${ALLOWED}
ENV

ok "backend/.env escrito"

# ── 10. Instalar dependencias Python ──────────────────────────────────────────
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

# ── 11. Instalar dependencias Node ────────────────────────────────────────────
step "Verificando dependencias Node.js"
if [[ ! -d "$SCRIPT_DIR/frontend/node_modules" ]]; then
    info "Ejecutando npm install..."
    npm install --prefix "$SCRIPT_DIR/frontend" --silent
    ok "node_modules instalado"
else
    ok "node_modules ya existe"
fi

# ── 12. Levantar proxy nginx (Docker) ─────────────────────────────────────────
step "Levantando proxy nginx con Docker"
cd "$SCRIPT_DIR"
docker compose down --remove-orphans 2>/dev/null || true
docker compose up -d
ok "Proxy nginx corriendo en puerto $TUTOR_HTTPS_PORT (HTTPS)"

# ── 13. Lanzar backend ────────────────────────────────────────────────────────
step "Lanzando backend FastAPI"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# Matar proceso previo si existe
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 1

cd "$SCRIPT_DIR/backend"
nohup "$VENV/bin/uvicorn" app.main:app \
    --host 0.0.0.0 \
    --port "$BACKEND_PORT" \
    --reload \
    > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$LOG_DIR/backend.pid"
ok "Backend PID $BACKEND_PID → log: logs/backend.log"

# ── 14. Lanzar frontend ───────────────────────────────────────────────────────
step "Lanzando frontend Vite"
pkill -f "vite" 2>/dev/null || true
sleep 1

cd "$SCRIPT_DIR/frontend"
nohup npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" \
    > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$LOG_DIR/frontend.pid"
ok "Frontend PID $FRONTEND_PID → log: logs/frontend.log"

# ── 15. Esperar y verificar servicios ─────────────────────────────────────────
step "Verificando que los servicios respondan..."
sleep 4

check_service() {
    local name="$1" url="$2"
    if curl -sk --max-time 5 "$url" > /dev/null 2>&1; then
        ok "$name responde en $url"
        return 0
    else
        warn "$name aún no responde en $url (puede tardar unos segundos más)"
        return 1
    fi
}

check_service "Backend (health)" "http://localhost:$BACKEND_PORT/api/health"
check_service "Frontend (Vite)"  "http://localhost:$FRONTEND_PORT"
check_service "Proxy HTTPS"      "https://$TUTOR_HOST:$TUTOR_HTTPS_PORT/api/health"

# ── 16. Resumen final ─────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║                    ✅  TODO LISTO                           ║${NC}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BOLD}  URLs del Tutor:${NC}"
echo -e "  ${GREEN}🌐 Tutor HTTPS:${NC}  https://$TUTOR_HOST:$TUTOR_HTTPS_PORT"
echo -e "  ${GREEN}🔧 Admin panel:${NC}  https://$TUTOR_HOST:$TUTOR_HTTPS_PORT/?admin=1"
echo -e "  ${GREEN}📋 API Docs:${NC}     http://localhost:$BACKEND_PORT/docs"
echo ""
echo -e "${BOLD}  Registra en Open edX Studio (mismo valor para todos tus bloques):${NC}"
echo -e "  ${YELLOW}Tool Launch URL:${NC}    https://$TUTOR_HOST:$TUTOR_HTTPS_PORT/lti/launch"
echo -e "  ${YELLOW}Login Initiation URL:${NC} https://$TUTOR_HOST:$TUTOR_HTTPS_PORT/lti/login"
echo -e "  ${YELLOW}Redirect URI:${NC}       https://$TUTOR_HOST:$TUTOR_HTTPS_PORT/lti/launch"
echo -e "  ${YELLOW}JWKS / Keyset URL:${NC}  https://$TUTOR_HOST:$TUTOR_HTTPS_PORT/lti/jwks"
echo ""
echo -e "${BOLD}  Logs en tiempo real:${NC}"
echo -e "  tail -f $LOG_DIR/backend.log"
echo -e "  tail -f $LOG_DIR/frontend.log"
echo ""
echo -e "${BOLD}  Para detener todos los servicios:${NC}"
echo -e "  $SCRIPT_DIR/stop.sh"
echo ""
