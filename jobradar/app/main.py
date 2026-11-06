"""HTTP application entry point and API for the standalone Jobradar."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from .database import connect, database_is_ready, initialize_database

JobStatus = Literal["neu", "gemerkt", "beworben", "absage", "verworfen"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Jobradar",
    version="0.2.0",
    description="Lokaler, KI-unabhängiger Jobradar für Home Assistant",
    lifespan=lifespan,
)


class JobCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=500)
    company: str | None = None
    location: str | None = None
    url: str | None = None
    source: str | None = None
    description: str | None = None
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    remote_type: str | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    published_at: str | None = None


class JobPatch(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    status: JobStatus | None = None
    notes: str | None = Field(default=None, max_length=10000)
    score: int | None = Field(default=None, ge=0, le=100)


class ProfileUpdate(BaseModel):
    data: dict[str, Any]


class RuleUpdate(BaseModel):
    data: dict[str, Any]


@app.get("/", response_class=HTMLResponse)
def dashboard_placeholder() -> str:
    return """
    <!doctype html>
    <html lang="de">
      <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Jobradar</title></head>
      <body><main><h1>Jobradar</h1><p>Der eigenständige Jobradar-Dienst läuft.</p><p>Das Dashboard wird in einer späteren Phase angebunden.</p><p><a href="api/health">Systemstatus</a></p></main></body>
    </html>
    """


@app.get("/api/health")
def health() -> dict[str, str]:
    ready = database_is_ready()
    return {"status": "ok" if ready else "degraded", "service": "jobradar", "database": "ready" if ready else "not_ready"}


@app.get("/api/meta")
def metadata() -> dict[str, str]:
    return {"name": "Jobradar", "version": app.version, "mode": "standalone"}


@app.get("/api/jobs")
def list_jobs(
    status: JobStatus | None = None,
    q: str | None = Query(default=None, max_length=200),
    min_score: int | None = Query(default=None, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if q:
        clauses.append("(title LIKE ? OR company LIKE ? OR location LIKE ?)")
        term = f"%{q}%"
        params.extend([term, term, term])
    if min_score is not None:
        clauses.append("COALESCE(score, 0) >= ?")
        params.append(min_score)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as db:
        total = db.execute(f"SELECT COUNT(*) FROM jobs {where}", params).fetchone()[0]
        rows = db.execute(
            f"SELECT * FROM jobs {where} ORDER BY COALESCE(score, 0) DESC, first_seen_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@app.post("/api/jobs", status_code=201)
def create_job(payload: JobCreate) -> dict[str, Any]:
    now = now_iso()
    job_id = str(uuid4())
    data = payload.model_dump()
    with connect() as db:
        db.execute(
            """INSERT INTO jobs
            (id,title,company,location,url,source,description,salary_min,salary_max,remote_type,score,
             status,notes,published_at,first_seen_at,last_seen_at,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,'neu','',?,?,?,?,?)""",
            (job_id, data["title"], data["company"], data["location"], data["url"], data["source"],
             data["description"], data["salary_min"], data["salary_max"], data["remote_type"],
             data["score"], data["published_at"], now, now, now, now),
        )
        row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with connect() as db:
        row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Stelle nicht gefunden")
    return dict(row)


@app.patch("/api/jobs/{job_id}")
def update_job(job_id: str, payload: JobPatch) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Keine Änderungen übergeben")
    if all(value is None for value in changes.values()):
        raise HTTPException(status_code=400, detail="Änderungswerte dürfen nicht null sein")
    changes["updated_at"] = now_iso()
    assignments = ", ".join(f"{key} = ?" for key in changes)
    with connect() as db:
        cursor = db.execute(
            f"UPDATE jobs SET {assignments} WHERE id = ?",
            [*changes.values(), job_id],
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Stelle nicht gefunden")
        row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row)


@app.get("/api/profile")
def get_profile() -> dict[str, Any]:
    with connect() as db:
        row = db.execute("SELECT data_json, updated_at FROM profile WHERE id = 1").fetchone()
    if row is None:
        return {"data": {}, "updated_at": None}
    return {"data": json.loads(row["data_json"]), "updated_at": row["updated_at"]}


@app.put("/api/profile")
def save_profile(payload: ProfileUpdate) -> dict[str, Any]:
    updated = now_iso()
    with connect() as db:
        db.execute(
            """INSERT INTO profile (id, data_json, updated_at) VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at""",
            (json.dumps(payload.data, ensure_ascii=False), updated),
        )
    return {"data": payload.data, "updated_at": updated}


@app.get("/api/rules")
def list_rules() -> dict[str, list[dict[str, Any]]]:
    with connect() as db:
        rows = db.execute("SELECT id, data_json, updated_at FROM search_rules ORDER BY id").fetchall()
    return {"items": [{"id": row["id"], "data": json.loads(row["data_json"]), "updated_at": row["updated_at"]} for row in rows]}


@app.put("/api/rules/{rule_id}")
def save_rule(rule_id: str, payload: RuleUpdate) -> dict[str, Any]:
    if not rule_id.strip() or len(rule_id) > 100:
        raise HTTPException(status_code=400, detail="Ungültige Regel-ID")
    updated = now_iso()
    with connect() as db:
        db.execute(
            """INSERT INTO search_rules (id, data_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at""",
            (rule_id, json.dumps(payload.data, ensure_ascii=False), updated),
        )
    return {"id": rule_id, "data": payload.data, "updated_at": updated}
