# LTI Virtual Tutor — Guía de Instalación y Despliegue

Tutor Virtual con IA integrado en Open edX via LTI 1.3.

---

## Requisitos previos

- **Open edX** instalado y corriendo con [Tutor](https://docs.tutor.edly.io/) (versión Quince o superior)
- **Git**
- **Docker** y **Docker Compose** (v2+)
- **Python 3.10+**
- **Node.js 18+**
- **Clave API de Gemini** — obtener en [Google AI Studio](https://aistudio.google.com/)

---

## Clonar el repositorio

```bash
git clone https://github.com/munozjeff/TutorVirtualOpenEdx.git
cd TutorVirtualOpenEdx
chmod +x setup.sh start.sh stop.sh deploy.sh start-prod.sh
```

---

## Modo 1 — Desarrollo local (recomendado para pruebas)

En este modo el backend y frontend corren como procesos en el host.
El proxy nginx corre en Docker para manejar HTTPS y routing.

### Primera vez

```bash
./setup.sh
```

El script preguntará:

| Pregunta | Valor recomendado |
|---|---|
| Modo de instalación | `1` (HTTPS local con mkcert) |
| URL base de Open edX | `http://local.openedx.io` |
| Puerto del backend | `8000` |
| Puerto del frontend | `5173` |
| Proveedor IA | `gemini` |
| Gemini API Key | tu clave de Google AI Studio |
| Hostname del tutor | `tutor.local.openedx.io` |
| Puerto HTTPS | `4443` |

`setup.sh` realizará automáticamente:
- Instalación de dependencias del sistema (mkcert, Docker, Python, Node)
- Generación de certificados SSL locales
- Creación del archivo `backend/.env`
- Instalación de dependencias Python (`venv`) y Node (`npm install`)
- Arranque del backend, frontend y proxy nginx

Al terminar verás las URLs y los datos para registrar el tutor en Open edX Studio.

### Arranques siguientes

```bash
./start.sh     # arranca todo sin reconfigurar
./stop.sh      # detiene todos los servicios
```

---

## Modo 2 — Producción (todo en Docker)

En este modo todo corre en contenedores Docker. Ideal para servidores o demos permanentes.

### Primera vez

**Paso 1 — Configurar el entorno:**

```bash
./setup.sh
```

Seleccionar modo `3` (HTTPS producción) o `1` (HTTPS local con mkcert).
Esto genera `backend/.env` y los certificados SSL necesarios.

**Paso 2 — Construir y desplegar:**

```bash
./deploy.sh
```

Este script:
- Genera la configuración nginx de producción (`nginx/tutor_prod.conf`)
- Construye las imágenes Docker (backend + frontend)
- Levanta el stack completo

### Arranques siguientes (sin rebuild)

```bash
./start-prod.sh    # levanta el stack existente sin reconstruir imágenes
```

### Detener producción

```bash
docker compose -f docker-compose.prod.yml down
```

### Actualizar tras cambios en el código

```bash
git pull
./deploy.sh        # reconstruye imágenes y reinicia
```

---

## Arquitectura de servicios

### Desarrollo
```
procesos host:
  uvicorn  →  :8000  (backend FastAPI)
  vite     →  :5173  (frontend React)

Docker:
  nginx    →  :4443 (HTTPS) / :8001 (HTTP redirect)
             proxy_pass → backend y frontend en el host
```

### Producción
```
Docker (red interna tutor_net):
  tutor_backend   →  :8000  (uvicorn, 2 workers)
  tutor_frontend  →  :80    (nginx con bundle estático)
  tutor_proxy     →  :4443 (HTTPS) / :8001 (HTTP)
                     proxy_pass → backend y frontend por red Docker
```

---

## Registro del tutor en Open edX

Este paso es **obligatorio** en cada instalación nueva. Solo se hace una vez.

### Paso 1 — Obtener datos de Open edX Studio

1. Abre Open edX Studio → entra a un curso → agrega un bloque **LTI Consumer**
2. Edita el bloque → pestaña **LTI 1.3**
3. Copia el **Client ID** y la **Keyset URL**

### Paso 2 — Registrar en el panel de administración

1. Abre `https://tutor.local.openedx.io:4443/?admin=1`
2. Ve a **Configuración LTI** → sección **Registrar bloque LTI**
3. Pega el **Client ID** y la **Keyset URL** de Open edX
4. Completa el nombre del tutor y el prompt del sistema
5. Guarda la configuración

### Paso 3 — Configurar el bloque LTI en Studio

El panel de administración te mostrará las URLs que debes copiar en Open edX Studio:

| Campo en Studio | URL del tutor |
|---|---|
| Tool Launch URL | `https://tutor.local.openedx.io:4443/lti/launch` |
| Tool Initiate Login URL | `https://tutor.local.openedx.io:4443/lti/login` |
| Registered Redirect URIs | `https://tutor.local.openedx.io:4443/lti/launch` |
| Key Set URL (JWKS) | `https://tutor.local.openedx.io:4443/lti/jwks` |

---

## Archivos generados (no están en git)

Estos archivos se generan automáticamente y **no deben subirse al repositorio**:

| Archivo | Generado por |
|---|---|
| `backend/.env` | `setup.sh` |
| `backend/data/tutor.db` | backend al arrancar |
| `backend/data/lti_private.key` | backend al arrancar |
| `backend/data/lti_public.pem` | backend al arrancar |
| `nginx/certs/` | `setup.sh` (mkcert) |
| `nginx/tutor_proxy.conf` | `setup.sh` |
| `nginx/tutor_prod.conf` | `deploy.sh` |
| `docker-compose.yml` | `setup.sh` |

---

## Migrar datos entre máquinas

Para conservar el historial de chat y configuraciones LTI al cambiar de máquina:

```bash
# Máquina origen — hacer backup
cp backend/data/tutor.db backup_tutor.db

# Máquina destino — después de ./setup.sh
cp backup_tutor.db backend/data/tutor.db
```

---

## Logs y diagnóstico

### Modo desarrollo
```bash
tail -f logs/backend.log
tail -f logs/frontend.log
```

### Modo producción
```bash
docker logs -f tutor_backend
docker logs -f tutor_frontend
docker logs -f tutor_proxy
```

### Health check
```bash
curl http://localhost:8000/api/health
```

---

## Panel de administración

Acceder en: `https://tutor.local.openedx.io:4443/?admin=1`

- **Configuración LTI** — registrar y gestionar instancias del tutor
- **Métricas** — dashboard de rendimiento con:
  - CPU, RAM, disco en tiempo real
  - Historial de picos y evolución de recursos
  - Latencia por endpoint
  - Prueba de estrés (básica y realista con IA)
  - Exportación de datos en CSV para análisis

---

## Proveedor de IA

### Gemini (por defecto)
Obtener API Key en [Google AI Studio](https://aistudio.google.com/).
Plan gratuito soporta ~15 requests/minuto (suficiente para 5-10 usuarios simultáneos).

### Ollama (modelo local)
```bash
# Instalar Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3

# En setup.sh seleccionar: proveedor = ollama
```
Sin límite de requests. Requiere GPU o CPU potente para latencia aceptable.
