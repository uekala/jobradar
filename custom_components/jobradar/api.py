"""Zugriff auf die Jobsuche der Bundesagentur für Arbeit.

Die Schnittstelle ist öffentlich und frei nutzbar; Dokumentation der Community:
https://jobsuche.api.bund.dev/
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import aiohttp

from .scoring import Job

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
# Mehrere bekannte Pfade – die Bundesagentur hat sie über die Jahre umgestellt
SEARCH_PATHS = ("/pc/v6/jobs", "/pc/v4/app/jobs", "/pc/v4/jobs")
DETAIL_PATHS = ("/pc/v4/jobdetails/{code}", "/pc/v3/jobdetails/{code}")
HEADERS = {
    "X-API-Key": "jobboerse-jobsuche",
    "Accept": "application/json",
    "User-Agent": "Jobradar for Home Assistant",
}
TIMEOUT = aiohttp.ClientTimeout(total=30)
PAUSE = 0.3


class JobsucheError(Exception):
    """Die Jobbörse war nicht erreichbar oder antwortete unerwartet."""


class HttpStatusError(JobsucheError):
    """Antwort mit Fehlercode."""

    def __init__(self, status: int, path: str) -> None:
        super().__init__(f"HTTP {status} für {path}")
        self.status = status

    @property
    def path_problem(self) -> bool:
        """Pfad unbekannt oder gesperrt – ein anderer Pfad kann funktionieren."""
        return 400 <= self.status < 500 and self.status != 429


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def parse_search_item(item: dict[str, Any], remote: bool) -> Job | None:
    refnr = _text(item.get("refnr"))
    if not refnr:
        return None
    place = item.get("arbeitsort") or {}
    coords = place.get("koordinaten") or {}
    return Job(
        refnr=refnr,
        title=_text(item.get("titel")) or _text(item.get("beruf")),
        occupation=_text(item.get("beruf")),
        employer=_text(item.get("arbeitgeber")),
        place=_text(place.get("ort")),
        postcode=str(place.get("plz") or ""),
        region=_text(place.get("region")),
        lat=coords.get("lat") if isinstance(coords.get("lat"), (int, float)) else None,
        lon=coords.get("lon") if isinstance(coords.get("lon"), (int, float)) else None,
        published=_text(item.get("aktuelleVeroeffentlichungsdatum")),
        start=_text(item.get("eintrittsdatum")),
        external_url=_text(item.get("externeUrl")),
        remote=remote,
    )


def apply_details(job: Job, data: dict[str, Any]) -> Job:
    """Ergänzt Beschreibung, Vergütung und Arbeitszeit aus der Detailansicht."""
    job.description = (
        _text(data.get("stellenangebotsBeschreibung")) or _text(data.get("stellenbeschreibung"))
    )[:6000]
    job.salary = _text(data.get("verguetung"))
    job.limited = _text(data.get("befristung"))
    models = [m for m in data.get("arbeitszeitmodelle") or [] if isinstance(m, str)]
    job.working_time = models
    if any("HEIM" in m.upper() or "TELE" in m.upper() for m in models):
        job.remote = True
    title = _text(data.get("stellenangebotsTitel")) or _text(data.get("titel"))
    if title:
        job.title = title
    job.details_loaded = True
    return job


class JobsucheClient:
    """Sucht Stellen und lädt Details nach."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._search_path: str | None = None
        self._details_available = True
        self._detail_misses = 0
        self.requests = 0

    def new_run(self) -> None:
        """Jede Suche probiert die Detailansicht neu."""
        self._details_available = True
        self._detail_misses = 0

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self.requests += 1
        async with self._session.get(
            f"{BASE_URL}{path}", params=params, headers=HEADERS, timeout=TIMEOUT
        ) as response:
            if response.status >= 400:
                raise HttpStatusError(response.status, path)
            return await response.json(content_type=None)

    async def search(
        self,
        term: str,
        *,
        location: str | None,
        radius: int | None,
        remote: bool,
        days: int,
        exclude_temp_agencies: bool,
        size: int = 50,
    ) -> list[Job]:
        params: dict[str, Any] = {
            "was": term,
            "angebotsart": 1,
            "page": 1,
            "size": size,
            "veroeffentlichtseit": max(0, min(100, days)),
        }
        if location:
            params["wo"] = location
            if radius:
                params["umkreis"] = radius
        if remote:
            params["arbeitszeit"] = "ho"
        if exclude_temp_agencies:
            params["zeitarbeit"] = "false"

        paths = [self._search_path] if self._search_path else list(SEARCH_PATHS)
        last_error: Exception | None = None
        for path in paths:
            try:
                data = await self._get(path, params)
            except HttpStatusError as err:
                if not err.path_problem:
                    raise
                last_error = err
                continue
            except (aiohttp.ClientError, TimeoutError) as err:
                raise JobsucheError(str(err)) from err
            self._search_path = path
            await asyncio.sleep(PAUSE)
            items = data.get("stellenangebote") if isinstance(data, dict) else None
            jobs = [
                parse_search_item(item, remote) for item in items or [] if isinstance(item, dict)
            ]
            return [job for job in jobs if job]
        # Beim nächsten Mal alle Pfade neu probieren
        self._search_path = None
        raise JobsucheError(f"Kein Suchpfad erreichbar ({last_error})")

    async def load_details(self, job: Job) -> bool:
        """Lädt die Detailansicht; pausiert, wenn die Schnittstelle sie nicht liefert."""
        if not self._details_available:
            return False
        code = base64.b64encode(job.refnr.encode()).decode()
        for path in DETAIL_PATHS:
            try:
                data = await self._get(path.format(code=code))
            except HttpStatusError as err:
                if err.path_problem:
                    continue
                _LOGGER.debug("Details zu %s nicht ladbar: %s", job.refnr, err)
                return False
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.debug("Details zu %s nicht ladbar: %s", job.refnr, err)
                return False
            await asyncio.sleep(PAUSE)
            if isinstance(data, dict):
                self._detail_misses = 0
                apply_details(job, data)
                return True
        # Eine einzelne Lücke kann eine gerade gelöschte Stelle sein, mehrere in Folge nicht
        self._detail_misses += 1
        if self._detail_misses >= 3:
            _LOGGER.info("Die Jobbörse liefert keine Stellendetails – bewertet wird nur der Titel")
            self._details_available = False
        return False
