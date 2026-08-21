FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ ./shared/
# Solo main.py: db/ es la semilla que monta booking-db, no tiene nada que hacer aquí.
COPY services/booking-svc/main.py ./
RUN useradd -m app && chown -R app /app
USER app
EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
