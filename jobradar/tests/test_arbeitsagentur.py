"""Adapter for the job search of the Bundesagentur für Arbeit."""
from datetime import date

import pytest

from app.sources import arbeitsagentur
from app.sources.arbeitsagentur import (
    ArbeitsagenturError,
    HttpStatusError,
    apply_details,
    parse_search_item,
    pay_from_item,
    result_items,
    search_vacancies,
)

TODAY = date(2026, 11, 13)

V6_ITEM = {
    "referenznummer": "10001-1003936970-S",
    "stellenangebotsTitel": "Systemadministrator (m/w/d) VMware",
    "firma": "Beispiel GmbH",
    "stellenlokationen": [{"adresse": {"ort": "Düsseldorf", "plz": "40210"}}],
    "datumErsteVeroeffentlichung": "2026-11-11",
    "homeofficemoeglich": True,
    "verguetungsangabe": "JAHRESGEHALT",
    "artDerVerguetung": "GEHALTSSPANNE",
    "gehaltsspanneVon": 65000,
    "gehaltsspanneBis": 78000,
}

V4_ITEM = {
    "refnr": "10000-1200000001-S",
    "titel": "Linux Administrator",
    "arbeitgeber": "Stadtwerke Musterstadt",
    "arbeitsort": {"ort": "Duisburg", "plz": "47051"},
    "aktuelleVeroeffentlichungsdatum": "2026-11-12",
}


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(arbeitsagentur.time, "sleep", lambda seconds: None)


def test_parses_v6_hit_with_salary_and_home_office():
    vacancy = parse_search_item(V6_ITEM, remote_search=False)

    assert vacancy["id"] == "arbeitsagentur:10001-1003936970-S"
    assert vacancy["title"] == "Systemadministrator (m/w/d) VMware"
    assert vacancy["company"] == "Beispiel GmbH"
    assert vacancy["location"] == "Düsseldorf"
    assert vacancy["url"] == "https://www.arbeitsagentur.de/jobsuche/jobdetail/10001-1003936970-S"
    assert vacancy["published_at"] == "2026-11-11"
    assert (vacancy["salary_min"], vacancy["salary_max"]) == (65000, 78000)
    assert vacancy["remote_type"] == "homeoffice"


def test_parses_v4_hit_and_skips_hits_without_reference():
    vacancy = parse_search_item(V4_ITEM, remote_search=False)

    assert vacancy["id"] == "arbeitsagentur:10000-1200000001-S"
    assert vacancy["company"] == "Stadtwerke Musterstadt"
    assert vacancy["location"] == "Duisburg"
    assert vacancy["remote_type"] is None
    assert parse_search_item({"titel": "Ohne Kennung"}, remote_search=False) is None


def test_result_items_reads_all_known_list_shapes():
    assert result_items({"stellenangebote": [V4_ITEM]}) == [V4_ITEM]
    assert result_items({"ergebnisliste": [V6_ITEM]}) == [V6_ITEM]
    assert result_items({"ergebnisliste": {"stellenangebote": [V6_ITEM]}}) == [V6_ITEM]
    assert result_items({"maxErgebnisse": 0}) == []


def test_pay_converts_monthly_amounts_and_ignores_placeholders():
    assert pay_from_item({"verguetungsangabe": "KEINE_ANGABEN"}) == (None, None)
    assert pay_from_item({"verguetungsangabe": "JAHRESGEHALT", "festgehalt": 1}) == (None, None)
    assert pay_from_item({"verguetungsangabe": "MONATSGEHALT", "festgehalt": "5.500,00"}) == (66000, 66000)


def test_details_add_description_pay_text_and_home_office():
    vacancy = parse_search_item(V4_ITEM, remote_search=False)
    apply_details(vacancy, {
        "stellenangebotsBeschreibung": "Betrieb von VMware vSphere und Ansible.",
        "verguetung": "Entgeltgruppe E 11 TVöD",
        "arbeitszeitmodelle": ["VOLLZEIT", "HEIMARBEIT_TELEARBEIT"],
    })

    assert "VMware vSphere" in vacancy["description"]
    assert "E 11 TVöD" in vacancy["description"]
    assert vacancy["remote_type"] == "homeoffice"


def test_search_combines_local_and_remote_search_and_loads_details(monkeypatch):
    calls = []

    def fake_get_json(path, params=None, timeout=30):
        calls.append((path, params))
        if "jobdetails" in path:
            return {"stellenangebotsBeschreibung": "Linux, VMware, Ansible"}
        if params.get("arbeitszeit") == "ho":
            return {"ergebnisliste": [V6_ITEM, {**V4_ITEM, "homeofficemoeglich": False}]}
        return {"ergebnisliste": [V4_ITEM, V6_ITEM]}

    monkeypatch.setattr(arbeitsagentur, "_get_json", fake_get_json)
    vacancies = search_vacancies(
        ["Systemadministrator"], location="Krefeld", radius_km=50,
        include_remote=True, days=7, today=TODAY,
    )

    searches = [params for path, params in calls if "jobdetails" not in path]
    assert searches[0]["wo"] == "Krefeld" and searches[0]["umkreis"] == 50
    assert searches[1]["arbeitszeit"] == "ho" and "wo" not in searches[1]
    assert [v["id"] for v in vacancies] == [
        "arbeitsagentur:10000-1200000001-S",
        "arbeitsagentur:10001-1003936970-S",
    ]
    assert all(v["description"] == "Linux, VMware, Ansible" for v in vacancies)
    assert all("refnr" not in v for v in vacancies)


def test_search_drops_old_hits_and_skips_details_of_known_vacancies(monkeypatch):
    detail_calls = []
    old = {**V4_ITEM, "refnr": "alt-1", "aktuelleVeroeffentlichungsdatum": "2026-09-01"}

    def fake_get_json(path, params=None, timeout=30):
        if "jobdetails" in path:
            detail_calls.append(path)
            return {"stellenangebotsBeschreibung": "Text"}
        return {"stellenangebote": [V4_ITEM, V6_ITEM, old]}

    monkeypatch.setattr(arbeitsagentur, "_get_json", fake_get_json)
    vacancies = search_vacancies(
        ["Linux"], location="Krefeld", radius_km=50, days=7, today=TODAY,
        known_ids={"arbeitsagentur:10000-1200000001-S"},
    )

    assert {v["id"] for v in vacancies} == {
        "arbeitsagentur:10000-1200000001-S",
        "arbeitsagentur:10001-1003936970-S",
    }
    assert len(detail_calls) == 1


def test_search_falls_back_to_older_path(monkeypatch):
    paths = []

    def fake_get_json(path, params=None, timeout=30):
        paths.append(path)
        if path == "/pc/v6/jobs":
            raise HttpStatusError(404, path)
        if "jobdetails" in path:
            return {}
        return {"stellenangebote": [V4_ITEM]}

    monkeypatch.setattr(arbeitsagentur, "_get_json", fake_get_json)
    vacancies = search_vacancies(["Linux"], location="Krefeld", today=TODAY, max_details=0)

    assert paths[:2] == ["/pc/v6/jobs", "/pc/v4/app/jobs"]
    assert len(vacancies) == 1


def test_unknown_hit_format_is_an_error_not_an_empty_result(monkeypatch):
    monkeypatch.setattr(
        arbeitsagentur, "_get_json",
        lambda path, params=None, timeout=30: {"maxErgebnisse": 12, "neuesFormat": {}},
    )
    with pytest.raises(ArbeitsagenturError):
        search_vacancies(["Linux"], location="Krefeld", today=TODAY)


def test_one_failing_term_does_not_stop_the_others(monkeypatch):
    def fake_get_json(path, params=None, timeout=30):
        if "jobdetails" in path:
            return {}
        if params["was"] == "kaputt":
            raise HttpStatusError(500, path)
        return {"stellenangebote": [V4_ITEM]}

    monkeypatch.setattr(arbeitsagentur, "_get_json", fake_get_json)
    vacancies = search_vacancies(["kaputt", "Linux"], location="Krefeld", today=TODAY, max_details=0)

    assert len(vacancies) == 1


def test_search_requires_a_term():
    with pytest.raises(ValueError):
        search_vacancies([" "], location="Krefeld")
