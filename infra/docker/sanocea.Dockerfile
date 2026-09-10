FROM python:3.13-slim

WORKDIR /app
COPY sanocea /app/sanocea
RUN pip install --no-cache-dir -e /app/sanocea

CMD ["python", "-m", "uvicorn", "sanocea.apps.api.app:app", "--host", "0.0.0.0", "--port", "8010"]

