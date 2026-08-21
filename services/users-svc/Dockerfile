FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
# Permite construir tras un proxy que intercepta TLS (p. ej. Zscaler): vacío por
# defecto, se activa con --build-arg PIP_TRUSTED_HOST="pypi.org files.pythonhosted.org".
ARG PIP_TRUSTED_HOST=""
ENV PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ ./shared/
COPY services/users-svc/main.py ./main.py
RUN useradd -m app && chown -R app /app
USER app
EXPOSE 8003
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
