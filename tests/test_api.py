"""Zugriff auf die Jobbörse."""

from __future__ import annotations

import re
from http import HTTPStatus

import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.jobradar.api import BASE_URL, JobsucheClient, JobsucheError, apply_details
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
