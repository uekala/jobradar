from fastapi.testclient import TestClient

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
