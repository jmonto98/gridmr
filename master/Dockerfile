FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY master.py .
VOLUME ["/data"]
CMD ["uvicorn", "master:app", "--host", "0.0.0.0", "--port", "8000"]
