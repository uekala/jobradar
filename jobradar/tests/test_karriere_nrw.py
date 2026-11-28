from app.sources.karriere_nrw import _plain_text, _radius_code, search_vacancies


def test_radius_maps_to_supported_api_bands():
    assert _radius_code(5) == 0
    assert _radius_code(12) == 2
    assert _radius_code(50) == 4
    assert _radius_code(500) == 7


def test_plain_text_removes_html_markup():
    assert _plain_text("<p>Linux <strong>Administrator</strong></p><p>NRW</p>") == "Linux Administrator NRW"


def test_search_fetches_details_and_normalizes_vacancy(monkeypatch):
    responses = iter([
        {"results": [{
            "uuid": "vacancy-123",
            "titel_der_stelle": "IT-Administrator",
            "ausschreibende_behoerde": "Land NRW",
            "ort": "Düsseldorf",
        }]},
        {
            "uuid": "vacancy-123",
            "titel_der_stelle": "IT-Administrator",
            "ausschreibende_behoerde": "Land NRW",
            "ort": "Düsseldorf",
            "stellenbeschreibung": "<p>Linux und VMware</p>",
            "ergaenzende_inhalte": "<p>TV-L</p>",
            "erscheinungsdatum": "2026-11-01",
            "bewerbungsfrist": "2026-12-01",
            "url": "https://www.karriere.nrw/stellenangebot",
        },
    ])
    requested = []

    def fake_get_json(url, timeout=20):
        requested.append(url)
        return next(responses)

    monkeypatch.setattr("app.sources.karriere_nrw._get_json", fake_get_json)
    vacancies = search_vacancies(["IT-Administrator"], location="Krefeld", radius_km=50)

    assert len(vacancies) == 1
    vacancy = vacancies[0]
    assert vacancy["id"] == "karriere-nrw:vacancy-123"
    assert vacancy["title"] == "IT-Administrator"
    assert vacancy["company"] == "Land NRW"
    assert vacancy["description"] == "Linux und VMware\n\nTV-L"
    assert vacancy["published_at"] == "2026-11-01"
    assert len(requested) == 2
    assert "ort=Krefeld" in requested[0]
    assert "umkreis=4" in requested[0]


def test_search_run_persists_vacancies_and_updates_existing_without_resetting_status(tmp_path, monkeypatch):
    from app.main import app
    from fastapi.testclient import TestClient

    db_file = tmp_path / "search.sqlite3"
    monkeypatch.setenv("JOBRADAR_DB_PATH", str(db_file))
    client = TestClient(app)
    vacancy = {
        "id": "karriere-nrw:abc-123",
        "title": "Linux Systemadministrator",
        "company": "Land NRW",
        "location": "Düsseldorf",
        "url": "https://example.org/job",
        "source": "Karriere.NRW",
        "description": "Linux VMware",
        "published_at": "2026-11-01",
        "raw": {"uuid": "abc-123"},
    }
    monkeypatch.setattr("app.main.search_vacancies", lambda **kwargs: [vacancy])
    with client:
        client.put("/api/profile", json={"data": {"location": "Krefeld", "radius_km": 50, "roles": ["Linux Admin"]}})
        client.put("/api/sources/karriere-nrw", json={
            "name": "Karriere.NRW",
            "source_type": "api",
            "enabled": True,
            "queries": ["Linux Admin"],
            "config": {},
        })

        first = client.post("/api/search/run")
        assert first.status_code == 200
        assert first.json()["run"]["status"] == "success"
        assert first.json()["run"]["jobs_found"] == 1
        assert first.json()["run"]["jobs_new"] == 1
        job = client.get("/api/jobs/karriere-nrw:abc-123").json()
        assert job["title"] == "Linux Systemadministrator"
        assert job["score"] == 40
        assert job["base_score"] == 40

        client.patch("/api/jobs/karriere-nrw:abc-123", json={"status": "gemerkt", "notes": "Interessant"})
        second = client.post("/api/search/run")
        assert second.status_code == 200
        assert second.json()["run"]["jobs_new"] == 0
        updated = client.get("/api/jobs/karriere-nrw:abc-123").json()
        assert updated["status"] == "gemerkt"
        assert updated["notes"] == "Interessant"
