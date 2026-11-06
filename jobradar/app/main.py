"""HTTP application entry point for the standalone Jobradar."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .database import database_is_ready, initialize_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Jobradar",
    version="0.1.0",
    description="Lokaler, KI-unabhängiger Jobradar für Home Assistant",
    lifespan=lifespan,
)


@app.get("/", response_class=HTMLResponse)
def dashboard_placeholder() -> str:
    return """
    <!doctype html>
    <html lang="de">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Jobradar</title>
      </head>
      <body>
        <main>
          <h1>Jobradar</h1>
          <p>Der eigenständige Jobradar-Dienst läuft.</p>
          <p>Das Dashboard wird in einer späteren Phase angebunden.</p>
          <p><a href="api/health">Systemstatus</a></p>
        </main>
      </body>
    </html>
    """


@app.get("/api/health")
def health() -> dict[str, str]:
    ready = database_is_ready()
    return {
        "status": "ok" if ready else "degraded",
        "service": "jobradar",
        "database": "ready" if ready else "not_ready",
    }


@app.get("/api/meta")
def metadata() -> dict[str, str]:
    return {"name": "Jobradar", "version": app.version, "mode": "standalone"}
