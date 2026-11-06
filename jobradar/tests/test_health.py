from fastapi.testclient import TestClient

from app.database import connect, initialize_database
from app.main import app


def test_health_initializes_database(tmp_path, monkeypatch):
    db_file = tmp_path / "jobradar.sqlite3"
    monkeypatch.setenv("JOBRADAR_DB_PATH", str(db_file))

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "jobradar",
        "database": "ready",
    }
    assert db_file.exists()


def test_metadata(tmp_path, monkeypatch):
    db_file = tmp_path / "metadata.sqlite3"
    monkeypatch.setenv("JOBRADAR_DB_PATH", str(db_file))

    with TestClient(app) as client:
        response = client.get("/api/meta")

    assert response.status_code == 200
    assert response.json()["name"] == "Jobradar"
    assert response.json()["mode"] == "standalone"
    assert db_file.exists()


def test_database_schema_and_version(tmp_path):
    db_file = tmp_path / "schema.sqlite3"
    initialize_database(str(db_file))

    with connect(str(db_file)) as db:
        tables = {
            row["name"]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        version = db.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()

    assert {"schema_meta", "jobs", "runs", "profile", "search_rules"} <= tables
    assert version["value"] == "1"


def test_profile_data_survives_database_reinitialization(tmp_path):
    db_file = tmp_path / "persistent.sqlite3"
    initialize_database(str(db_file))

    with connect(str(db_file)) as db:
        db.execute(
            """
            INSERT INTO profile (id, data_json, updated_at)
            VALUES (1, ?, ?)
            """,
            ('{"role": "Systemadministrator"}', "2026-11-06T08:00:00"),
        )

    initialize_database(str(db_file))

    with connect(str(db_file)) as db:
        profile = db.execute(
            "SELECT data_json, updated_at FROM profile WHERE id = 1"
        ).fetchone()

    assert profile is not None
    assert profile["data_json"] == '{"role": "Systemadministrator"}'
    assert profile["updated_at"] == "2026-11-06T08:00:00"
