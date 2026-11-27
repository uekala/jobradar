"""Einrichtungsdatei: Suchprofil, Quellen und Regeln beim Start übernehmen."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app, apply_setup_file
from app.scoring import evaluate_vacancy

SETUP = {
    "profil": {"location": "Musterstadt", "radius_km": 30, "roles": ["Systemadministrator"]},
    "quellen": [
        {"id": "arbeitsagentur", "name": "Arbeitsagentur", "source_type": "api",
         "base_url": "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service",
         "queries": ["Systemadministrator"], "config": {"days": 7}},
        {"id": "bund", "name": "service.bund.de", "source_type": "api", "enabled": False},
    ],
    "regeln": [
        {"id": "abwerten", "data": {"name": "Abwerten", "category": "negative", "terms": ["Junior"],
                                     "weight": 25, "scope": "title"}},
    ],
}


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBRADAR_DB_PATH", str(tmp_path / "jobradar.db"))
    monkeypatch.setenv("JOBRADAR_OPTIONS_PATH", str(tmp_path / "options.json"))
    return TestClient(app)


def test_setup_file_is_applied_once_at_start(tmp_path, monkeypatch):
    setup = tmp_path / "einrichtung.json"
    setup.write_text(json.dumps(SETUP), encoding="utf-8")
    with _client(tmp_path, monkeypatch) as client:
        assert client.get("/api/profile").json()["data"]["location"] == "Musterstadt"
        sources = {s["id"]: s for s in client.get("/api/sources").json()["items"]}
        assert sources["arbeitsagentur"]["enabled"] and sources["arbeitsagentur"]["queries"] == ["Systemadministrator"]
        assert sources["bund"]["enabled"] is False
        (rule,) = client.get("/api/rules").json()["items"]
        assert rule["id"] == "abwerten" and rule["data"]["scope"] == "title"
    assert not setup.exists()
    (done,) = tmp_path.glob("einrichtung.json.uebernommen-*")
    assert json.loads(done.read_text(encoding="utf-8")) == SETUP

    # Änderungen in der Oberfläche überstehen einen Neustart.
    with _client(tmp_path, monkeypatch) as client:
        client.put("/api/profile", json={"data": {"location": "Anderswo"}})
    with _client(tmp_path, monkeypatch) as client:
        assert client.get("/api/profile").json()["data"]["location"] == "Anderswo"


def test_setup_file_keeps_other_sources_and_replaces_the_profile(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.put("/api/profile", json={"data": {"location": "Alt", "skills": ["Linux"]}})
        client.put("/api/sources/eigene", json={"name": "Eigene", "source_type": "web"})
    (tmp_path / "einrichtung.json").write_text(json.dumps(SETUP), encoding="utf-8")
    with _client(tmp_path, monkeypatch) as client:
        assert client.get("/api/profile").json()["data"] == SETUP["profil"]
        ids = {s["id"] for s in client.get("/api/sources").json()["items"]}
        assert ids == {"arbeitsagentur", "bund", "eigene"}


def test_faulty_setup_file_changes_nothing(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        client.put("/api/profile", json={"data": {"location": "Alt"}})
    setup = tmp_path / "einrichtung.json"
    broken = {**SETUP, "quellen": [{"id": "x", "name": "X", "source_type": "telefon"}]}
    setup.write_text(json.dumps(broken), encoding="utf-8")
    result = apply_setup_file(str(setup))
    assert result["applied"] is False and "source_type" in result["error"]
    assert setup.exists()
    with _client(tmp_path, monkeypatch) as client:
        assert client.get("/api/profile").json()["data"] == {"location": "Alt"}
        assert client.get("/api/sources").json()["items"] == []


def test_unknown_sections_are_rejected(tmp_path, monkeypatch):
    setup = tmp_path / "einrichtung.json"
    setup.write_text(json.dumps({"profil": {}, "passwort": "x"}), encoding="utf-8")
    monkeypatch.setenv("JOBRADAR_DB_PATH", str(tmp_path / "jobradar.db"))
    result = apply_setup_file(str(setup))
    assert result == {"applied": False, "error": "Unbekannte Abschnitte: passwort"}


def test_without_setup_file_nothing_happens(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBRADAR_DB_PATH", str(tmp_path / "jobradar.db"))
    assert apply_setup_file() is None


def test_title_only_rules_ignore_the_description():
    rule = {"id": "abwerten", "data": {"name": "Abwerten", "category": "negative",
                                       "terms": ["1st Level"], "weight": 25, "scope": "title"}}
    exclude = {"id": "aus", "data": {"name": "Aus", "category": "exclude",
                                     "terms": ["Ausbildung"], "scope": "title"}}
    job = {"title": "Systemadministrator", "description": "Abgeschlossene Ausbildung, kein 1st Level"}
    score_plain, excluded = evaluate_vacancy(job, {}, [])
    assert evaluate_vacancy(job, {}, [rule, exclude]) == (score_plain, False)
    trainee = {"title": "Ausbildung Fachinformatiker", "description": ""}
    assert evaluate_vacancy(trainee, {}, [exclude])[1] is True
    junior = {"title": "1st Level Support", "description": ""}
    assert evaluate_vacancy(junior, {}, [rule])[0] == score_plain - 25
