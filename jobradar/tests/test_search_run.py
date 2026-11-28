"""Suchlauf über mehrere Quellen, täglicher Zeitplan und Benachrichtigungen."""
import json
from datetime import UTC, datetime

from app import automation, main
from app.automation import (
    build_notification,
    load_options,
    notify_result,
    run_scheduled_search,
    search_due,
)
from app.database import connect
from app.main import app
from fastapi.testclient import TestClient


def client_for(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBRADAR_DB_PATH", str(tmp_path / "jobradar.sqlite3"))
    monkeypatch.setenv("JOBRADAR_OPTIONS_PATH", str(tmp_path / "options.json"))
    client = TestClient(app)
    client.__enter__()
    return client


def vacancy(number, title="Systemadministrator VMware", **extra):
    return {
        "id": f"arbeitsagentur:ref-{number}",
        "title": title,
        "company": "Beispiel GmbH",
        "location": "Düsseldorf",
        "url": f"https://www.arbeitsagentur.de/jobsuche/jobdetail/ref-{number}",
        "source": "Arbeitsagentur",
        "description": "Linux und VMware",
        "published_at": "2026-11-12",
        "salary_min": 72000,
        "salary_max": 80000,
        "remote_type": "homeoffice",
        "raw": {},
        **extra,
    }


def add_source(client, config=None):
    response = client.put("/api/sources/arbeitsagentur", json={
        "name": "Arbeitsagentur", "source_type": "api", "enabled": True,
        "queries": [], "config": config or {},
    })
    assert response.status_code == 200


def test_run_stores_arbeitsagentur_vacancies_with_profile_settings(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    seen = {}

    def fake_search(**kwargs):
        seen.update(kwargs)
        return [vacancy(1)]

    monkeypatch.setattr(main, "search_arbeitsagentur", fake_search)
    try:
        client.put("/api/profile", json={"data": {
            "location": "Krefeld", "radius_km": 50, "nationwide_remote": True,
            "roles": ["Systemadministrator"], "skills": ["VMware", "Linux"],
        }})
        add_source(client, {"days": 3})
        result = client.post("/api/search/run").json()

        assert result["sources_checked"] == 1
        assert result["run"]["status"] == "success"
        assert result["run"]["jobs_new"] == 1
        assert result["run"]["sources"] == "Arbeitsagentur"
        assert seen["terms"] == ["Systemadministrator"]
        assert seen["location"] == "Krefeld" and seen["radius_km"] == 50
        assert seen["include_remote"] is True and seen["days"] == 3
        job = client.get("/api/jobs/arbeitsagentur:ref-1").json()
        assert job["salary_min"] == 72000 and job["remote_type"] == "homeoffice"
        assert result["new_jobs"][0]["id"] == "arbeitsagentur:ref-1"
    finally:
        client.__exit__(None, None, None)


def test_run_skips_new_vacancies_below_the_minimum_score(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "search_arbeitsagentur", lambda **kwargs: [
        vacancy(1), vacancy(2, title="Hausmeister", description="Gebäude"),
    ])
    try:
        client.put("/api/profile", json={"data": {
            "roles": ["Systemadministrator"], "skills": ["VMware", "Linux"],
        }})
        add_source(client, {"min_score": 55})
        result = client.post("/api/search/run").json()

        assert result["run"]["jobs_new"] == 1
        assert client.get("/api/jobs/arbeitsagentur:ref-2").status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_run_does_not_duplicate_an_advertisement_known_under_another_id(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "search_arbeitsagentur", lambda **kwargs: [vacancy(1)])
    try:
        created = client.post("/api/jobs", json={
            "title": "Systemadministrator VMware", "score": 81,
            "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/ref-1",
        }).json()
        client.patch(f"/api/jobs/{created['id']}", json={"status": "beworben", "notes": "Gespräch am 20.11."})
        add_source(client)
        result = client.post("/api/search/run").json()

        assert result["run"]["jobs_new"] == 0
        assert client.get("/api/jobs/arbeitsagentur:ref-1").status_code == 404
        kept = client.get(f"/api/jobs/{created['id']}").json()
        assert (kept["status"], kept["notes"], kept["score"]) == ("beworben", "Gespräch am 20.11.", 81)
    finally:
        client.__exit__(None, None, None)


def test_known_vacancy_without_fresh_details_keeps_its_description(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    answers = iter([[vacancy(1)], [vacancy(1, description="")]])
    monkeypatch.setattr(main, "search_arbeitsagentur", lambda **kwargs: next(answers))
    try:
        client.put("/api/profile", json={"data": {"roles": ["Systemadministrator"], "skills": ["Linux"]}})
        add_source(client)
        client.post("/api/search/run")
        first = client.get("/api/jobs/arbeitsagentur:ref-1").json()
        second_run = client.post("/api/search/run").json()
        second = client.get("/api/jobs/arbeitsagentur:ref-1").json()

        assert second_run["run"]["jobs_new"] == 0
        assert second["description"] == "Linux und VMware"
        assert second["score"] == first["score"]
    finally:
        client.__exit__(None, None, None)


def test_second_run_at_the_same_time_is_refused(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    try:
        assert main._search_lock.acquire(blocking=False)
        try:
            response = client.post("/api/search/run")
        finally:
            main._search_lock.release()
        assert response.status_code == 409
        assert client.get("/api/runs").json()["items"] == []
    finally:
        client.__exit__(None, None, None)


def test_options_default_to_no_schedule_without_file(tmp_path):
    assert load_options(str(tmp_path / "fehlt.json")) == {
        "search_time": "", "notify_service": "", "notify_min_score": 70,
    }


def test_options_are_validated(tmp_path):
    path = tmp_path / "options.json"
    path.write_text(json.dumps({
        "search_time": "06:30", "notify_service": "notify.mobile_app_pixel", "notify_min_score": 150,
    }), encoding="utf-8")
    assert load_options(str(path)) == {
        "search_time": "06:30", "notify_service": "mobile_app_pixel", "notify_min_score": 100,
    }

    path.write_text(json.dumps({"search_time": "25:00", "notify_service": "a/../b"}), encoding="utf-8")
    assert load_options(str(path)) == {
        "search_time": "", "notify_service": "", "notify_min_score": 70,
    }


def test_search_is_due_once_per_day_from_the_configured_time():
    morning = datetime(2026, 11, 13, 6, 29, tzinfo=UTC)
    due = datetime(2026, 11, 13, 6, 30, tzinfo=UTC)
    late = datetime(2026, 11, 13, 15, 0, tzinfo=UTC)

    assert not search_due(morning, "06:30", None)
    assert search_due(due, "06:30", "2026-11-12")
    assert search_due(late, "06:30", None)
    assert not search_due(late, "06:30", "2026-11-13")
    assert not search_due(late, "", None)


def test_notification_lists_the_best_new_jobs_above_the_threshold():
    result = {"run": {"status": "success"}, "new_jobs": [
        {"title": "A", "company": "Firma", "location": "Krefeld", "score": 90},
        {"title": "B", "company": None, "location": None, "score": 80},
        {"title": "C", "company": "X", "location": "Y", "score": 75},
        {"title": "D", "company": "X", "location": "Y", "score": 71},
        {"title": "E", "company": "X", "location": "Y", "score": 60},
    ]}
    title, message = build_notification(result, 70)

    assert title == "4 neue Stellen im Jobradar"
    assert message.splitlines() == [
        "A – Firma, Krefeld (90)", "B (80)", "C – X, Y (75)", "… und 1 weitere",
    ]
    assert build_notification({"run": {"status": "success"}, "new_jobs": []}, 70) is None
    assert build_notification(result, 95) is None


def test_failed_run_is_reported():
    title, message = build_notification(
        {"run": {"status": "failed"}, "errors": ["Arbeitsagentur: HTTP 500"], "new_jobs": []}, 70
    )
    assert title == "Jobradar: Suchlauf fehlgeschlagen"
    assert message == "Arbeitsagentur: HTTP 500"


def test_notification_goes_to_the_configured_service(monkeypatch):
    sent = []
    monkeypatch.setattr(
        automation, "_supervisor",
        lambda method, path, payload=None: sent.append((method, path, payload))
        or ({"data": {"slug": "abc_jobradar"}} if path == "/addons/self/info" else None),
    )
    result = {"run": {"status": "success"}, "new_jobs": [
        {"title": "A", "company": "Firma", "location": "Krefeld", "score": 90},
    ]}

    assert notify_result(result, {"notify_service": "mobile_app_pixel", "notify_min_score": 70})
    method, path, payload = sent[-1]
    assert (method, path) == ("POST", "/core/api/services/notify/mobile_app_pixel")
    assert payload["title"] == "1 neue Stelle im Jobradar"
    assert payload["data"]["url"] == "/hassio/ingress/abc_jobradar"
    assert not notify_result(result, {"notify_service": "", "notify_min_score": 70})


def test_failed_push_does_not_raise(monkeypatch):
    def broken(method, path, payload=None):
        raise RuntimeError("Home Assistant antwortet nicht")

    monkeypatch.setattr(automation, "_supervisor", broken)
    result = {"run": {"status": "success"}, "new_jobs": [{"title": "A", "score": 90}]}
    assert not notify_result(result, {"notify_service": "mobile_app_pixel", "notify_min_score": 70})


def test_scheduled_search_runs_once_per_day_even_if_it_fails(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    calls = []

    def run(trigger):
        calls.append(trigger)
        if len(calls) == 1:
            raise RuntimeError("Netz weg")
        return {"run": {"status": "success", "jobs_found": 0, "jobs_new": 0}, "new_jobs": []}

    options = {"search_time": "06:30", "notify_service": "", "notify_min_score": 70}
    try:
        day1 = datetime(2026, 11, 13, 7, 0, tzinfo=UTC)
        assert run_scheduled_search(run, options, now=day1) is None
        assert run_scheduled_search(run, options, now=day1) is None
        assert calls == ["schedule"]
        day2 = datetime(2026, 11, 14, 6, 30, tzinfo=UTC)
        assert run_scheduled_search(run, options, now=day2) is not None
        assert calls == ["schedule", "schedule"]
        assert client.get("/api/schedule").json()["last_scheduled"] == "2026-11-14"
    finally:
        client.__exit__(None, None, None)


def test_scheduled_run_is_marked_in_the_run_list(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    try:
        result = main.perform_search_run("schedule")
        assert result["run"]["note"] == "Täglicher Suchlauf"
        with connect() as db:
            assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    finally:
        client.__exit__(None, None, None)


def test_schedule_endpoint_reports_the_options(tmp_path, monkeypatch):
    (tmp_path / "options.json").write_text(json.dumps({
        "search_time": "06:30", "notify_service": "mobile_app_pixel", "notify_min_score": 75,
    }), encoding="utf-8")
    client = client_for(tmp_path, monkeypatch)
    try:
        schedule = client.get("/api/schedule").json()
        assert schedule["search_time"] == "06:30"
        assert schedule["notify"] is True and schedule["notify_min_score"] == 75
        assert schedule["supported_sources"] == ["arbeitsagentur", "bund", "karriere-nrw"]
    finally:
        client.__exit__(None, None, None)
