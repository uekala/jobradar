FROM python:3.12.16-slim-trixie

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade "pip==26.3" \
    && python -m pip install --no-cache-dir -r /app/requirements.txt

COPY app/ /app/app/

ENV PYTHONUNBUFFERED=1
ENV JOBRADAR_DB_PATH=/data/jobradar.db

EXPOSE 8099

# Exec form: uvicorn runs as PID 1 and receives SIGTERM directly when Home
# Assistant stops the app (e.g. for a cold backup). Open requests get at most
# 5 seconds, which stays below the Supervisor's default stop timeout of
# 10 seconds, so the app always shuts down cleanly instead of being killed.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8099", "--timeout-graceful-shutdown", "5"]
