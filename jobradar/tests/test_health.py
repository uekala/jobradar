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
    assert version["value"] == "3"
    assert "job_sources" in tables
    assert "base_score" in {row["name"] for row in connect(str(db_file)).execute("PRAGMA table_info(jobs)")}


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



def test_dashboard_is_responsive_and_uses_api(tmp_path, monkeypatch):
    client, _ = client_for(tmp_path, monkeypatch)
    try:
        response = client.get("/")
        assert response.status_code == 200
        assert "Jobradar" in response.text
        assert "viewport" in response.text
        assert "api/overview" in response.text
        assert "detail-notes" in response.text
        assert "max-width:600px" in response.text
    finally:
        client.__exit__(None, None, None)



def test_source_registry_create_update_list_delete(tmp_path, monkeypatch):
    client, _ = client_for(tmp_path, monkeypatch)
    try:
        source = {
            "name": "Arbeitsagentur",
            "source_type": "api",
            "base_url": "https://www.arbeitsagentur.de/jobsuche/",
            "enabled": True,
            "queries": ["Systemadministrator", "Linux Administrator"],
            "config": {"region": "Krefeld"},
        }
        saved = client.put("/api/sources/arbeitsagentur", json=source)
        assert saved.status_code == 200
        assert saved.json()["name"] == "Arbeitsagentur"

        listed = client.get("/api/sources")
        assert listed.status_code == 200
        assert listed.json()["items"][0]["queries"] == source["queries"]

        source["enabled"] = False
        updated = client.put("/api/sources/arbeitsagentur", json=source)
        assert updated.status_code == 200
        assert updated.json()["enabled"] is False

        deleted = client.delete("/api/sources/arbeitsagentur")
        assert deleted.status_code == 204
        assert client.get("/api/sources").json()["items"] == []
        assert client.delete("/api/sources/missing").status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_existing_version_one_database_is_upgraded_without_data_loss(tmp_path):
    from app.database import initialize_database

    db_file = tmp_path / "legacy.sqlite3"
    initialize_database(str(db_file))
    with connect(str(db_file)) as db:
        db.execute(
            "INSERT INTO jobs (id,title,status,first_seen_at,last_seen_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            ("legacy-1", "Vorhandene Stelle", "gemerkt", "2026-11-01", "2026-11-01", "2026-11-01", "2026-11-01"),
        )
        db.execute("UPDATE schema_meta SET value = '1' WHERE key = 'schema_version'")
    initialize_database(str(db_file))
    with connect(str(db_file)) as db:
        job = db.execute("SELECT title,status FROM jobs WHERE id='legacy-1'").fetchone()
        version = db.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
        sources = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='job_sources'").fetchone()
    assert job["title"] == "Vorhandene Stelle"
    assert job["status"] == "gemerkt"
    assert version["value"] == "3"
    assert sources is not None


def test_feedback_adjusts_similar_job_scores_without_compounding(tmp_path, monkeypatch):
    client, _ = client_for(tmp_path, monkeypatch)
    try:
        liked = client.post("/api/jobs", json={
            "title": "Linux Systemadministrator",
            "description": "VMware Windows Server Betrieb",
            "score": 70,
        }).json()
        candidate = client.post("/api/jobs", json={
            "title": "Linux Administrator",
            "description": "VMware Infrastruktur",
            "score": 60,
        }).json()
        discarded = client.post("/api/jobs", json={
            "title": "Windows Entwickler",
            "description": "Softwareentwicklung",
            "score": 80,
        }).json()
        response = client.patch(f"/api/jobs/{liked['id']}", json={"status": "gemerkt"})
        assert response.status_code == 200
        boosted = client.get(f"/api/jobs/{candidate['id']}").json()["score"]
        assert boosted > 60
        client.patch(f"/api/jobs/{discarded['id']}", json={"status": "verworfen"})
        assert client.get(f"/api/jobs/{candidate['id']}").json()["score"] == boosted
        client.patch(f"/api/jobs/{liked['id']}", json={"status": "neu"})
        reset = client.get(f"/api/jobs/{candidate['id']}").json()["score"]
        assert reset == 60
    finally:
        client.__exit__(None, None, None)



def test_existing_version_two_database_adds_base_score_without_data_loss(tmp_path):
    db_file = tmp_path / "version-two.sqlite3"
    initialize_database(str(db_file))
    with connect(str(db_file)) as db:
        db.execute(
            "INSERT INTO jobs (id,title,score,status,first_seen_at,last_seen_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            ("legacy-v2", "VMware Administrator", 74, "gemerkt", "2026-11-01", "2026-11-01", "2026-11-01", "2026-11-01"),
        )
        db.execute("ALTER TABLE jobs DROP COLUMN base_score")
        db.execute("UPDATE schema_meta SET value = '2' WHERE key = 'schema_version'")

    initialize_database(str(db_file))

    with connect(str(db_file)) as db:
        job = db.execute(
            "SELECT title, score, base_score, status FROM jobs WHERE id='legacy-v2'"
        ).fetchone()
        version = db.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()

    assert job["title"] == "VMware Administrator"
    assert job["score"] == 74
    assert job["base_score"] == 74
    assert job["status"] == "gemerkt"
    assert version["value"] == "3"


def test_rule_can_be_deleted_and_unknown_rule_returns_404(tmp_path, monkeypatch):
    client, _ = client_for(tmp_path, monkeypatch)
    try:
        saved = client.put(
            "/api/rules/linux",
            json={"data": {"name": "Linux-Kenntnisse", "terms": ["Linux"]}},
        )
        assert saved.status_code == 200
        assert client.get("/api/rules").json()["items"]

        deleted = client.delete("/api/rules/linux")
        assert deleted.status_code == 204
        assert client.get("/api/rules").json()["items"] == []
        assert client.delete("/api/rules/missing").status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_dashboard_exposes_manual_search_control(tmp_path, monkeypatch):
    client, _ = client_for(tmp_path, monkeypatch)
    try:
        response = client.get("/")
        assert response.status_code == 200
        assert 'id="run-search"' in response.text
        assert 'id="add-karriere-source"' in response.text
        assert 'api/sources/karriere-nrw' in response.text
        assert 'api/search/run' in response.text
        assert "karriere-nrw" in response.text
    finally:
        client.__exit__(None, None, None)
