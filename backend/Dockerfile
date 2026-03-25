FROM python:3.10-slim

WORKDIR /app

# Dependencias del sistema mínimas
RUN apt-get update -q && apt-get install -y --no-install-recommends \
    gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY . .

# Directorio de datos persistente
RUN mkdir -p /app/data

EXPOSE 8000

# Producción: 2 workers, sin --reload
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
