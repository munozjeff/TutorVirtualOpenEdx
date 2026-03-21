# Tutor Virtual LTI

Aplicación LTI 1.3 de Tutor Virtual para Open edX — backend en **FastAPI (Python)** y frontend en **React + Vite**.

---

## 🗂 Estructura del Proyecto

```
TutorVirtualLti/
├── backend/          # FastAPI + LTI 1.3 + AI
├── frontend/         # React + Vite
└── docker-compose.yml
```

---

## 🚀 Inicio Rápido (Desarrollo Local)

### 1. Configurar el backend

```bash
cd backend
cp .env.example .env
# Edita .env con tus credenciales de Open edX y AI provider
```

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

### 2. Instalar y lanzar el frontend

```bash
cd frontend
npm install
npm run dev
```

El frontend corre en `http://localhost:5173`  
El backend corre en `http://localhost:8000`  
La documentación Swagger: `http://localhost:8000/docs`

### 3. Con Docker (producción)

```bash
cp backend/.env.example backend/.env
# Edita backend/.env
docker compose up --build
```

---

## ⚙️ Configuración en Open edX Studio

Al agregar un bloque **LTI Consumer** en Open edX, usa estos valores:

| Campo | Valor |
|---|---|
| **Tool Launch URL** | `http://TU-DOMINIO/lti/login` |
| **Tool Initiate Login URL** | `http://TU-DOMINIO/lti/login` |
| **Registered Redirect URIs** | `http://TU-DOMINIO/lti/launch` |
| **Key Set URL (JWKS)** | `http://TU-DOMINIO/lti/jwks` |

> 💡 **Usa HTTPS en producción.** Open edX exige HTTPS para LTI 1.3.

### Variables .env esenciales

```env
BASE_URL=https://tu-dominio.com
OPENEDX_ISSUER=https://tu-openedx.com
OPENEDX_CLIENT_ID=<client-id de Open edX>
OPENEDX_AUTH_ENDPOINT=https://tu-openedx.com/o/authorize
OPENEDX_JWKS_ENDPOINT=https://tu-openedx.com/api/lti_consumer/v1/public_keysets/

AI_PROVIDER=gemini          # o "ollama"
GEMINI_API_KEY=tu-api-key
```

---

## 🔒 Aislamiento de Sesiones

| Escenario | Comportamiento |
|---|---|
| Estudiante A, Instancia 1 vs 2 | **Aisladas por defecto** |
| Mismas instancias con contexto compartido activo | **Comparten historial** (mismo `share_group_id`) |
| Estudiante A vs Estudiante B | **Siempre aislados** |

### Compartir contexto entre instancias

El instructor puede activar "Compartir Contexto" en la vista de configuración y asignar el mismo `share_group_id` a las instancias que desea unir. Esto permite que el historial del estudiante sea continuo entre tutores de diferentes secciones de un mismo curso.

---

## 🤖 Proveedores de IA

| Provider | Variable | Config |
|---|---|---|
| Google Gemini | `AI_PROVIDER=gemini` | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| Ollama (local) | `AI_PROVIDER=ollama` | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` |

---

## 📡 API Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET/POST | `/lti/login` | OIDC Login Initiation |
| POST | `/lti/launch` | LTI JWT validation + session |
| GET | `/lti/jwks` | Public Key Set para Open edX |
| POST | `/api/chat` | Enviar mensaje al tutor |
| GET | `/api/chat/history` | Historial de chat |
| GET | `/api/config/me` | Info del usuario actual |
| GET/PUT | `/api/config` | Configuración del tutor (instructor) |
| POST | `/api/config/sharing` | Configurar contexto compartido |
| GET | `/api/health` | Health check |
