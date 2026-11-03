"""Zugriff auf die Jobbörse."""

from __future__ import annotations

import re
from http import HTTPStatus

import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.jobradar.api import (
    BASE_URL,
    JobsucheClient,
    JobsucheError,
    ShapeError,
    apply_details,
    parse_search_item,
)
from custom_components.jobradar.scoring import Job

pytestmark = pytest.mark.usefixtures("no_pause")

ITEM = {
    "refnr": "10000-1-S",
    "beruf": "Systemadministrator/in",
    "arbeitgeber": "Muster GmbH",
    "aktuelleVeroeffentlichungsdatum": "2026-11-01",
    "arbeitsort": {"ort": "Krefeld", "plz": 47798, "koordinaten": {"lat": 51.33, "lon": 6.56}},
}


async def test_falls_back_to_older_search_path_and_remembers_it(hass, aioclient_mock) -> None:
    aioclient_mock.get(f"{BASE_URL}/pc/v6/jobs", status=HTTPStatus.NOT_FOUND)
    aioclient_mock.get(f"{BASE_URL}/pc/v4/app/jobs", json={"stellenangebote": [ITEM]})
    client = JobsucheClient(async_get_clientsession(hass))
    jobs = await client.search(
        "Admin", location="Krefeld", radius=50, remote=False, days=2, exclude_temp_agencies=True
    )
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Systemadministrator/in"  # ohne "titel" zählt der Beruf
    assert job.postcode == "47798" and job.lat == 51.33
    await client.search(
        "Admin", location="Krefeld", radius=50, remote=False, days=2, exclude_temp_agencies=True
    )
    paths = [str(call[1]) for call in aioclient_mock.mock_calls]
    assert sum("/pc/v6/jobs" in p for p in paths) == 1
    request = aioclient_mock.mock_calls[1][1]
    assert request.query["wo"] == "Krefeld" and request.query["zeitarbeit"] == "false"
    assert aioclient_mock.mock_calls[1][3]["X-API-Key"] == "jobboerse-jobsuche"


async def test_server_error_is_reported(hass, aioclient_mock) -> None:
    aioclient_mock.get(f"{BASE_URL}/pc/v6/jobs", status=HTTPStatus.BAD_GATEWAY)
    client = JobsucheClient(async_get_clientsession(hass))
    with pytest.raises(JobsucheError):
        await client.search(
            "x", location=None, radius=None, remote=True, days=2, exclude_temp_agencies=False
        )


async def test_empty_result_and_unknown_shape(hass, aioclient_mock) -> None:
    aioclient_mock.get(f"{BASE_URL}/pc/v6/jobs", json={"maxErgebnisse": "0"})
    client = JobsucheClient(async_get_clientsession(hass))
    assert (
        await client.search(
            "x", location="Krefeld", radius=10, remote=False, days=2, exclude_temp_agencies=False
        )
        == []
    )


def test_v6_item_as_seen_live() -> None:
    job = parse_search_item(
        {
            "referenznummer": "10001-1003936970-S",
            "stellenangebotsTitel": "Senior VMware & Storage Engineer (m/w/d)",
            "hauptberuf": "Systemadministrator/in",
            "firma": "Muster Rechenzentrum GmbH",
            "datumErsteVeroeffentlichung": "2026-10-30",
            "veroeffentlichungszeitraum": {"von": "2026-10-30"},
            "eintrittszeitraum": {"von": "2026-12-01"},
            "stellenlokationen": [
                {"adresse": {"ort": "Düsseldorf", "plz": "40210"}, "breite": 51.22, "laenge": 6.78}
            ],
            "entfernung": "21",
        },
        remote=False,
    )
    assert job is not None
    assert job.employer == "Muster Rechenzentrum GmbH" and job.place == "Düsseldorf"
    assert job.lat == 51.22 and job.lon == 6.78 and job.postcode == "40210"
    assert job.published == "2026-10-30" and job.start == "2026-12-01"
    assert job.occupation == "Systemadministrator/in" and job.distance_km == 21


def test_v6_item_with_referenznummer() -> None:
    job = parse_search_item(
        {
            "referenznummer": "10000-2-S",
            "titel": "Systemadministrator (m/w/d)",
            "arbeitgeber": {"name": "Muster AG"},
            "arbeitsorte": [{"ort": "Neuss", "koordinaten": {"lat": 51.2, "lon": 6.69}}],
            "veroeffentlichungsdatum": "2026-11-02T08:00:00",
        },
        remote=False,
    )
    assert job is not None
    assert job.refnr == "10000-2-S" and job.employer == "Muster AG"
    assert job.place == "Neuss" and job.lon == 6.69 and job.published == "2026-11-02"


async def test_unknown_item_format_tries_next_path(hass, aioclient_mock) -> None:
    aioclient_mock.get(f"{BASE_URL}/pc/v6/jobs", json={"stellenangebote": [{"kennung": "x"}]})
    aioclient_mock.get(f"{BASE_URL}/pc/v4/app/jobs", json={"stellenangebote": [ITEM]})
    client = JobsucheClient(async_get_clientsession(hass))
    jobs = await client.search(
        "x", location=None, radius=None, remote=True, days=2, exclude_temp_agencies=False
    )
    assert [j.refnr for j in jobs] == ["10000-1-S"]
    assert client.hits == 1 and client._search_path == "/pc/v4/app/jobs"
    assert client.shapes["/pc/v6/jobs"]["item_keys"] == ["kennung"]
    assert client.shapes["/pc/v4/app/jobs"]["item_keys"] == sorted(ITEM)


async def test_unknown_format_everywhere_is_an_error(hass, aioclient_mock) -> None:
    for path in ("/pc/v6/jobs", "/pc/v4/app/jobs", "/pc/v4/jobs"):
        aioclient_mock.get(f"{BASE_URL}{path}", json={"stellenangebote": [{"kennung": "x"}]})
    client = JobsucheClient(async_get_clientsession(hass))
    with pytest.raises(ShapeError):
        await client.search(
            "x", location=None, radius=None, remote=True, days=2, exclude_temp_agencies=False
        )
    assert client.shapes["/pc/v4/jobs"]["item_keys"] == ["kennung"]


async def test_v6_list_under_ergebnisliste(hass, aioclient_mock) -> None:
    hit = {"referenznummer": "10000-3-S", "titel": "Cloud Engineer (m/w/d)"}
    aioclient_mock.get(
        f"{BASE_URL}/pc/v6/jobs",
        json={"ergebnisliste": [hit], "maxErgebnisse": 137, "woOutput": {"ort": "Krefeld"}},
    )
    client = JobsucheClient(async_get_clientsession(hass))
    jobs = await client.search(
        "x", location="Krefeld", radius=50, remote=False, days=2, exclude_temp_agencies=False
    )
    assert [j.title for j in jobs] == ["Cloud Engineer (m/w/d)"]
    shape = client.shapes["/pc/v6/jobs"]
    assert shape["items"] == 1 and shape["keys"]["woOutput"] == ["ort"]


async def test_total_without_readable_list_is_an_error(hass, aioclient_mock) -> None:
    for path in ("/pc/v6/jobs", "/pc/v4/app/jobs", "/pc/v4/jobs"):
        aioclient_mock.get(f"{BASE_URL}{path}", json={"treffer": "?", "maxErgebnisse": "12"})
    client = JobsucheClient(async_get_clientsession(hass))
    with pytest.raises(ShapeError):
        await client.search(
            "x", location=None, radius=None, remote=True, days=2, exclude_temp_agencies=False
        )


async def test_details_switch_off_after_repeated_misses(hass, aioclient_mock) -> None:
    aioclient_mock.get(re.compile(r"/jobdetails/"), status=HTTPStatus.NOT_FOUND)
    client = JobsucheClient(async_get_clientsession(hass))
    for i in range(4):
        assert await client.load_details(Job(refnr=f"r{i}", title="t")) is False
    # Nach drei Lücken in Folge wird nicht mehr gefragt: 3 × 2 Pfade
    assert len(aioclient_mock.mock_calls) == 6


def test_apply_details_marks_remote_and_keeps_text_short() -> None:
    job = apply_details(
        Job(refnr="1", title="alt"),
        {
            "stellenangebotsTitel": "Neu",
            "stellenangebotsBeschreibung": "x" * 9000,
            "arbeitszeitmodelle": ["VOLLZEIT", "HEIM_TELEARBEIT"],
            "verguetung": "E11 TVöD",
        },
    )
    assert job.title == "Neu" and job.remote and job.details_loaded
    assert len(job.description) == 6000 and job.salary == "E11 TVöD"
