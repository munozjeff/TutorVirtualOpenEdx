# ── Producción: build estático servido por nginx ──────────────────────────────
# Stage 1: compilar la app Vite
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --silent
COPY . .
RUN npm run build

# Stage 2: nginx sirve el bundle estático
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html

# Config para SPA: todas las rutas sirven index.html
RUN printf 'server {\n\
    listen 80;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80
