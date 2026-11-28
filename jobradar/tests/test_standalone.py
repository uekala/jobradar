"""Eigenständiger Betrieb ohne Home Assistant OS: eigene Anmeldung, Home Assistant über Adresse und Token."""
from __future__ import annotations

import base64
import json

import pytest
from app import automation, main
from app.main import app
from fastapi.testclient import TestClient


def basic(user: str, password: str) -> dict[str, str]:
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


LOGIN = basic("jobradar", "geheim-und-lang")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBRADAR_DB_PATH", str(tmp_path / "jobradar.sqlite3"))
    for name in ("SUPERVISOR_TOKEN", "JOBRADAR_WEB_USER", "JOBRADAR_WEB_PASSWORD", "HA_URL", "HA_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    main._LOGIN_FAILURES.clear()
    with TestClient(app) as test_client:
        yield test_client
    main._LOGIN_FAILURES.clear()


def test_without_password_everything_stays_open(client):
    assert client.get("/api/meta").status_code == 200


def test_password_protects_page_and_api(client, monkeypatch):
    monkeypatch.setenv("JOBRADAR_WEB_PASSWORD", "geheim-und-lang")
    refused = client.get("/")
    assert refused.status_code == 401
    assert refused.headers["www-authenticate"].startswith("Basic")
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/jobs", headers=basic("jobradar", "falsch")).status_code == 401
    assert client.get("/api/jobs", headers=basic("anders", "geheim-und-lang")).status_code == 401
    assert client.get("/api/jobs", headers={"Authorization": "Basic %%%"}).status_code == 401
    assert client.get("/api/jobs", headers=LOGIN).status_code == 200
    assert client.get("/", headers=LOGIN).status_code == 200


def test_health_needs_no_login(client, monkeypatch):
    monkeypatch.setenv("JOBRADAR_WEB_PASSWORD", "geheim-und-lang")
    assert client.get("/api/health").json()["status"] == "ok"


def test_own_user_name(client, monkeypatch):
    monkeypatch.setenv("JOBRADAR_WEB_PASSWORD", "geheim-und-lang")
    monkeypatch.setenv("JOBRADAR_WEB_USER", "uemit")
    assert client.get("/api/meta", headers=LOGIN).status_code == 401
    assert client.get("/api/meta", headers=basic("uemit", "geheim-und-lang")).status_code == 200


def test_as_home_assistant_app_ingress_signs_in(client, monkeypatch):
    monkeypatch.setenv("JOBRADAR_WEB_PASSWORD", "geheim-und-lang")
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    assert client.get("/api/meta").status_code == 200


def test_wrong_passwords_are_rate_limited(client, monkeypatch):
    monkeypatch.setenv("JOBRADAR_WEB_PASSWORD", "geheim-und-lang")
    for _ in range(8):  # Anfragen ohne Anmeldedaten zählen nicht, so beginnt jeder Browser
        assert client.get("/api/meta").status_code == 401
    for _ in range(main.LOGIN_LIMIT):
        assert client.get("/api/meta", headers=basic("jobradar", "geraten")).status_code == 401
    blocked = client.get("/api/meta", headers=LOGIN)
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "300"


def test_foreign_sites_cannot_write(client, monkeypatch):
    monkeypatch.setenv("JOBRADAR_WEB_PASSWORD", "geheim-und-lang")
    job = {"title": "Systemadministrator"}
    foreign = {**LOGIN, "Origin": "https://fremd.example"}
    assert client.post("/api/jobs", json=job, headers=foreign).status_code == 403
    cross = {**LOGIN, "Sec-Fetch-Site": "cross-site"}
    assert client.post("/api/jobs", json=job, headers=cross).status_code == 403
    assert client.get("/api/jobs", headers=LOGIN).json()["total"] == 0
    own = {**LOGIN, "Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"}
    assert client.post("/api/jobs", json=job, headers=own).status_code == 201
    assert client.post("/api/jobs", json=job, headers=LOGIN).status_code == 201  # ohne Browser, z. B. curl


def test_notifications_go_to_the_configured_address(monkeypatch):
    sent = []
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.setenv("HA_URL", "http://192.168.1.20:8123/")
    monkeypatch.setenv("HA_TOKEN", " lang-lebig ")
    monkeypatch.setattr(automation, "_request",
                        lambda url, token, method, payload=None: sent.append((url, token, method, payload)))
    result = {"run": {"status": "success"}, "new_jobs": [{"title": "A", "score": 90}]}

    assert automation.notify_result(result, {"notify_service": "mobile_app_pixel", "notify_min_score": 70})
    url, token, method, payload = sent[-1]
    assert (url, token, method) == ("http://192.168.1.20:8123/api/services/notify/mobile_app_pixel", "lang-lebig", "POST")
    assert "data" not in payload  # ohne Supervisor gibt es kein Panel, das ein Tipp öffnen könnte

    assert automation.notify_result(result, {"notify_service": "persistent_notification", "notify_min_score": 70})
    assert sent[-1][0] == "http://192.168.1.20:8123/api/services/persistent_notification/create"


def test_as_home_assistant_app_the_supervisor_wins(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    monkeypatch.setenv("HA_URL", "http://192.168.1.20:8123")
    monkeypatch.setenv("HA_TOKEN", "lang-lebig")
    assert automation.home_assistant_address() is None
    sent = []
    monkeypatch.setattr(automation, "_request",
                        lambda url, token, method, payload=None: sent.append((url, token)))
    automation.send_notification("persistent_notification", "Titel", "Text")
    assert sent == [("http://supervisor/core/api/services/persistent_notification/create", "supervisor-token")]


def test_address_needs_scheme_and_token(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.setenv("HA_URL", "192.168.1.20:8123")
    monkeypatch.setenv("HA_TOKEN", "lang-lebig")
    assert automation.home_assistant_address() is None
    monkeypatch.setenv("HA_URL", "https://ha.example")
    monkeypatch.delenv("HA_TOKEN")
    assert automation.home_assistant_address() is None


def test_options_from_environment_win(tmp_path, monkeypatch):
    file = tmp_path / "options.json"
    file.write_text(json.dumps({"search_time": "06:30", "notify_service": "mobile_app_alt", "notify_min_score": 50}))
    for name in automation.ENV_OPTIONS.values():
        monkeypatch.delenv(name, raising=False)
    assert automation.load_options(str(file)) == {
        "search_time": "06:30", "notify_service": "mobile_app_alt", "notify_min_score": 50}
    monkeypatch.setenv("JOBRADAR_SEARCH_TIME", "07:15")
    monkeypatch.setenv("JOBRADAR_NOTIFY_SERVICE", "notify.mobile_app_neu")
    monkeypatch.setenv("JOBRADAR_NOTIFY_MIN_SCORE", "80")
    expected = {"search_time": "07:15", "notify_service": "mobile_app_neu", "notify_min_score": 80}
    assert automation.load_options(str(file)) == expected
    assert automation.load_options(str(tmp_path / "fehlt.json")) == expected
    monkeypatch.setenv("JOBRADAR_SEARCH_TIME", "25:00")
    assert automation.load_options(str(file))["search_time"] == ""
