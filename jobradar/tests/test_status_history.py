from app.main import app
from fastapi.testclient import TestClient


def client_for(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBRADAR_DB_PATH", str(tmp_path / "jobradar.sqlite3"))
    client = TestClient(app)
    client.__enter__()
    return client


def _job(client, title, score=50, location="Krefeld"):
    response = client.post("/api/jobs", json={"title": title, "company": "Firma", "location": location, "score": score})
    assert response.status_code == 201
    return response.json()["id"]


def test_status_change_is_logged_with_date(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    try:
        job_id = _job(client, "Admin")
        assert client.get(f"/api/jobs/{job_id}").json()["status_history"] == []

        client.patch(f"/api/jobs/{job_id}", json={"status": "gemerkt"})
        client.patch(f"/api/jobs/{job_id}", json={"status": "beworben"})
        # Gleicher Status und reine Notiz erzeugen keinen Eintrag.
        client.patch(f"/api/jobs/{job_id}", json={"status": "beworben"})
        client.patch(f"/api/jobs/{job_id}", json={"notes": "angerufen"})

        job = client.get(f"/api/jobs/{job_id}").json()
        assert [(h["previous"], h["status"]) for h in job["status_history"]] == [
            ("neu", "gemerkt"),
            ("gemerkt", "beworben"),
        ]
        assert job["status_changed_at"] == job["status_history"][-1]["at"]
    finally:
        client.__exit__(None, None, None)


def test_list_sort_options(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    try:
        low = _job(client, "A", score=10, location="Zülpich")
        high = _job(client, "B", score=90, location="Aachen")
        by_score = [j["id"] for j in client.get("/api/jobs?sort=score").json()["items"]]
        assert by_score == [high, low]
        by_place = [j["id"] for j in client.get("/api/jobs?sort=ort").json()["items"]]
        assert by_place == [high, low]
        client.patch(f"/api/jobs/{low}", json={"status": "gemerkt"})
        by_change = [j["id"] for j in client.get("/api/jobs?sort=status&status=gemerkt").json()["items"]]
        assert by_change == [low]
        assert client.get("/api/jobs?sort=drop table").status_code == 422
    finally:
        client.__exit__(None, None, None)


def test_dashboard_has_views(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    try:
        html = client.get("/").text
        for marker in ('id="view-stellen"', 'id="view-bewerbungen"', 'id="view-einrichtung"', 'id="sort"'):
            assert marker in html
    finally:
        client.__exit__(None, None, None)
