ARG BUILD_FROM=python:3.12-slim-bookworm
FROM ${BUILD_FROM}

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app/ /app/app/

ENV PYTHONUNBUFFERED=1
ENV JOBRADAR_DB_PATH=/data/jobradar.db

EXPOSE 8099

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8099"]
