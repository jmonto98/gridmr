FROM python:3.11-slim

# Crear directorio de trabajo
WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Crear carpeta de datos
RUN mkdir -p /data

# Exponer puerto (se definirá por variable de entorno en docker-compose)
EXPOSE 8001

# Comando para arrancar FastAPI con Uvicorn
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${WORKER_PORT}"]
