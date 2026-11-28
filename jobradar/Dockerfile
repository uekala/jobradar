FROM python:3.15-slim-bookworm@sha256:498829c717b1e59fc42f0e7865eafe4e04ca0f70a3769d4ae70ba218df54507c

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt

COPY app/ /app/app/

ENV PYTHONUNBUFFERED=1
ENV JOBRADAR_DB_PATH=/data/jobradar.db

EXPOSE 8099

# Exec-Form: uvicorn läuft als PID 1 und bekommt SIGTERM direkt, wenn Home
# Assistant die App stoppt (z. B. für ein Cold-Backup). Offene Anfragen haben
# höchstens 5 Sekunden Zeit; das bleibt unter dem Standard-Stopp-Timeout des
# Supervisors von 10 Sekunden, die App endet also immer sauber, statt
# abgewürgt zu werden.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8099", "--timeout-graceful-shutdown", "5"]
