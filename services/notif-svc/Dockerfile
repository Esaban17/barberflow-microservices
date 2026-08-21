# Contexto de build: la raíz del repo, para poder copiar shared/.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ ./shared/
COPY services/notif-svc/main.py ./main.py
RUN useradd -m app && chown -R app /app
USER app
EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
