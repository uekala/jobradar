"""Gemeinsame Test-Fixtures: eine nachgebaute Jobbörse."""

from __future__ import annotations

import base64
import re
from collections.abc import Callable
from datetime import date, timedelta
from http import HTTPStatus
from typing import Any

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from custom_components.jobradar.api import BASE_URL

pytest_plugins = ["pytest_homeassistant_custom_component"]

KREFELD = (51.3388, 6.5853)


def days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def job(
    refnr: str, title: str, employer: str, place: str, lat: float, lon: float, **extra: Any
) -> dict:
    """Ein Treffer, wie ihn /pc/v6/jobs liefert (Feldnamen aus einer echten Antwort)."""
    return {
        "referenznummer": refnr,
        "stellenangebotsTitel": title,
        "hauptberuf": extra.pop("beruf", "Systemadministrator/in"),
        "firma": employer,
        "datumErsteVeroeffentlichung": extra.pop("published", days_ago(1)),
        "veroeffentlichungszeitraum": {"von": days_ago(1)},
        "eintrittszeitraum": {"von": "2027-01-01"},
        "stellenlokationen": [
            {
                "adresse": {"ort": place, "plz": "40210", "region": "Nordrhein-Westfalen"},
                "breite": lat,
                "laenge": lon,
            }
        ],
        "entfernung": "25",
        "arbeitszeitVollzeit": True,
        **extra,
    }


LOCAL_JOBS = [
    job(
        "10000-0000000001-S",
        "Systemadministrator (m/w/d) Linux und VMware",
        "Muster IT GmbH",
        "Düsseldorf",
        51.2277,
        6.7735,
    ),
    job("10000-0000000002-S", "IT-Administrator (m/w/d)", "Stadt Krefeld", "Krefeld", 51.33, 6.56),
    job(
        "10000-0000000003-S",
        "Ausbildung Fachinformatiker Systemintegration (m/w/d)",
        "Lehrbetrieb AG",
        "Neuss",
        51.2,
        6.69,
    ),
    job(
        "10000-0000000005-S",
        "Vertriebsmitarbeiter Innendienst (m/w/d)",
        "Handel GmbH",
        "Duisburg",
        51.43,
        6.76,
        beruf="Kaufmann/-frau",
    ),
    job(
        "10000-0000000006-S",
        "Junior Helpdesk Administrator (m/w/d)",
        "Support KG",
        "Moers",
        51.45,
        6.62,
    ),
]
REMOTE_JOBS = [
    job(
        "10000-0000000004-S",
        "Cloud Engineer (m/w/d) Kubernetes",
        "Remote AG",
        "Berlin",
        52.52,
        13.40,
        beruf="Cloud-Engineer",
    ),
]
DETAILS = {
    "10000-0000000001-S": {
        "stellenangebotsTitel": "Systemadministrator (m/w/d) Linux und VMware",
        "stellenangebotsBeschreibung": (
            "Sie betreuen unsere Windows Server und automatisieren mit Ansible."
        ),
        "verguetung": "nach Vereinbarung",
        "arbeitszeitmodelle": ["VOLLZEIT", "HEIM_TELEARBEIT"],
        "befristung": "UNBEFRISTET",
    },
}


class FakeJobboerse:
    """Liefert Suchtreffer je nach Parametern und zählt Anfragen."""

    def __init__(self) -> None:
        self.local = list(LOCAL_JOBS)
        self.remote = list(REMOTE_JOBS)
        self.details = dict(DETAILS)
        self.fail = False
        self.search_calls: list[dict[str, str]] = []

    def register(self, aioclient_mock) -> None:
        aioclient_mock.get(f"{BASE_URL}/pc/v6/jobs", side_effect=self._search)
        aioclient_mock.get(re.compile(r"/pc/v4/jobdetails/"), side_effect=self._details)
        aioclient_mock.get(re.compile(r"/pc/v3/jobdetails/"), status=HTTPStatus.NOT_FOUND)

    async def _search(self, method, url, data) -> AiohttpClientMockResponse:
        query = dict(url.query)
        self.search_calls.append(query)
        if self.fail:
            return AiohttpClientMockResponse(method, url, status=HTTPStatus.SERVICE_UNAVAILABLE)
        pool = self.remote if query.get("arbeitszeit") == "ho" else self.local
        term = query.get("was", "").lower().replace("-", "")
        hits = [j for j in pool if _hit(term, j)]
        # So antwortet /pc/v6/jobs: Liste unter ergebnisliste, Ortsangabe in woOutput
        body: dict = {"maxErgebnisse": len(hits), "page": 1, "size": 50, "facetten": {}}
        if hits:
            body["ergebnisliste"] = hits
        if query.get("wo"):
            body["woOutput"] = {"ort": query["wo"]}
        return AiohttpClientMockResponse(method, url, json=body)

    async def _details(self, method, url, data) -> AiohttpClientMockResponse:
        code = url.path.rsplit("/", 1)[-1]
        refnr = base64.b64decode(code).decode()
        if refnr in self.details:
            return AiohttpClientMockResponse(method, url, json=self.details[refnr])
        return AiohttpClientMockResponse(method, url, status=HTTPStatus.NOT_FOUND)


def _hit(term: str, item: dict) -> bool:
    text = f"{item['stellenangebotsTitel']} {item['hauptberuf']}".lower().replace("-", "")
    return any(part in text for part in term.split())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


@pytest.fixture
def jobboerse(aioclient_mock) -> FakeJobboerse:
    fake = FakeJobboerse()
    fake.register(aioclient_mock)
    return fake


@pytest.fixture
def no_pause(monkeypatch) -> None:
    monkeypatch.setattr("custom_components.jobradar.api.PAUSE", 0)


@pytest.fixture
def at_home(hass) -> Callable[[], None]:
    hass.config.latitude, hass.config.longitude = KREFELD
    return lambda: None
