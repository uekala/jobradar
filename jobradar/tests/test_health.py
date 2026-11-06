from fastapi.testclient import TestClient

from app.database import connect, initialize_database
from app.main import app


def client_for(tmp_path, monkeypatch):
    db_file = tmp_path / "jobradar.sqlite3"
    monkeypatch.setenv("JOBRADAR_DB_PATH", str(db_file))
    client = TestClient(app)
    client.__enter__()
    return client, db_file


def test_health_initializes_database(tmp_path, monkeypatch):
    client, db_file = client_for(tmp_path, monkeypatch)
    try:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "service": "jobradar",
            "database": "ready",
        }
        assert db_file.exists()
    finally:
        client.__exit__(None, None, None)


def test_metadata(tmp_path, monkeypatch):
    client, db_file = client_for(tmp_path, monkeypatch)
    try:
        response = client.get("/api/meta")
        assert response.status_code == 200
        assert response.json()["name"] == "Jobradar"
        assert response.json()["mode"] == "standalone"
        assert db_file.exists()
    finally:
        client.__exit__(None, None, None)


def test_database_schema_and_version(tmp_path):
    db_file = tmp_path / "schema.sqlite3"
    initialize_database(str(db_file))
    with connect(str(db_file)) as db:
        tables = {
            row["name"]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        version = db.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
    assert {"schema_meta", "jobs", "runs", "profile", "search_rules"} <= tables
    assert version["value"] == "1"


def test_profile_survives_reinitialization(tmp_path):
    db_file = tmp_path / "persistent.sqlite3"
    initialize_database(str(db_file))
    with connect(str(db_file)) as db:
        db.execute(
            "INSERT INTO profile (id, data_json, updated_at) VALUES (1, ?, ?)",
            ('{"role": "Systemadministrator"}', "2026-11-06T08:00:00"),
        )
    initialize_database(str(db_file))
    with connect(str(db_file)) as db:
        profile = db.execute("SELECT data_json FROM profile WHERE id = 1").fetchone()
    assert profile["data_json"] == '{"role": "Systemadministrator"}'


def test_job_create_list_filter_and_status_update(tmp_path, monkeypatch):
    client, _ = client_for(tmp_path, monkeypatch)
    try:
        created = client.post("/api/jobs", json={
            "title": "Linux Systemadministrator",
            "company": "Beispiel GmbH",
            "location": "Krefeld",
            "score": 82,
        })
        assert created.status_code == 201
        job = created.json()
        assert job["status"] == "neu"
        assert job["score"] == 82

        filtered = client.get("/api/jobs", params={"q": "Linux", "min_score": 70})
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 1
        assert filtered.json()["items"][0]["id"] == job["id"]

        updated = client.patch(f"/api/jobs/{job['id']}", json={
            "status": "gemerkt",
            "notes": "Interessante Stelle",
        })
        assert updated.status_code == 200
        assert updated.json()["status"] == "gemerkt"
        assert updated.json()["notes"] == "Interessante Stelle"
    finally:
        client.__exit__(None, None, None)


def test_invalid_status_is_rejected(tmp_path, monkeypatch):
    client, _ = client_for(tmp_path, monkeypatch)
    try:
        job = client.post("/api/jobs", json={"title": "Admin"}).json()
        response = client.patch(f"/api/jobs/{job['id']}", json={"status": "unbekannt"})
        assert response.status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_profile_and_rule_roundtrip(tmp_path, monkeypatch):
    client, _ = client_for(tmp_path, monkeypatch)
    try:
        profile = {"region": "Krefeld + 50 km", "minimum_score": 55}
        saved_profile = client.put("/api/profile", json={"data": profile})
        assert saved_profile.status_code == 200
        assert client.get("/api/profile").json()["data"] == profile

        rule = {"exclude_employers": ["Beispiel AG"]}
        saved_rule = client.put("/api/rules/employers", json={"data": rule})
        assert saved_rule.status_code == 200
        listed = client.get("/api/rules")
        assert listed.status_code == 200
        assert listed.json()["items"][0]["data"] == rule
    finally:
        client.__exit__(None, None, None)


def test_missing_job_returns_404(tmp_path, monkeypatch):
    client, _ = client_for(tmp_path, monkeypatch)
    try:
        assert client.get("/api/jobs/not-there").status_code == 404
        assert client.patch("/api/jobs/not-there", json={"status": "gemerkt"}).status_code == 404
    finally:
        client.__exit__(None, None, None)



def test_overview_and_search_run_lifecycle(tmp_path, monkeypatch):
    client, _ = client_for(tmp_path, monkeypatch)
    try:
        created = client.post("/api/jobs", json={
            "title": "Platform Engineer",
            "company": "Muster GmbH",
            "score": 91,
        })
        assert created.status_code == 201

        run = client.post("/api/runs", json={})
        assert run.status_code == 201
        run_id = run.json()["id"]
        assert run.json()["status"] == "running"

        finished = client.post(f"/api/runs/{run_id}/finish", json={
            "status": "success",
            "jobs_found": 12,
            "jobs_new": 3,
        })
        assert finished.status_code == 200
        assert finished.json()["jobs_found"] == 12
        assert finished.json()["status"] == "success"

        overview = client.get("/api/overview")
        assert overview.status_code == 200
        assert overview.json()["jobs_total"] == 1
        assert overview.json()["jobs_by_status"]["neu"] == 1
        assert overview.json()["average_score"] == 91.0
        assert overview.json()["latest_run"]["id"] == run_id

        runs = client.get("/api/runs")
        assert runs.status_code == 200
        assert runs.json()["items"][0]["id"] == run_id

        duplicate_finish = client.post(f"/api/runs/{run_id}/finish", json={
            "status": "success",
        })
        assert duplicate_finish.status_code == 409
    finally:
        client.__exit__(None, None, None)


def test_finish_unknown_run_returns_404(tmp_path, monkeypatch):
    client, _ = client_for(tmp_path, monkeypatch)
    try:
        response = client.post("/api/runs/999/finish", json={"status": "failed"})
        assert response.status_code == 404
    finally:
        client.__exit__(None, None, None)
