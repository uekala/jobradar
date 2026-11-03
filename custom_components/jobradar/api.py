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


def _first(item: dict[str, Any], *keys: str) -> str:
    """Erster nicht leere Text unter mehreren möglichen Feldnamen."""
    for key in keys:
        value = _text(item.get(key))
        if value:
            return value
    return ""


def _name(value: Any) -> str:
    """Arbeitgeber kommt je nach Version als Text oder als Objekt."""
    if isinstance(value, dict):
        return _first(value, "name", "bezeichnung", "arbeitgeber")
    return _text(value)


def _place(item: dict[str, Any]) -> dict[str, Any]:
    place = item.get("arbeitsort")
    if not isinstance(place, dict):
        places = item.get("arbeitsorte")
        place = places[0] if isinstance(places, list) and places else {}
    return place if isinstance(place, dict) else {}


def _coord(coords: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = coords.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


# Felder je nach Version: v4 nennt die Kennung refnr, v6 referenznummer
ID_KEYS = ("refnr", "referenznummer", "referenzNummer")
TITLE_KEYS = ("titel", "stellenangebotsTitel", "stellentitel", "beruf")
DATE_KEYS = (
    "aktuelleVeroeffentlichungsdatum",
    "veroeffentlichungsdatum",
    "ersteVeroeffentlichungsdatum",
)
LIST_KEYS = ("stellenangebote", "ergebnisse", "jobs", "content", "items", "results")


def parse_search_item(item: dict[str, Any], remote: bool) -> Job | None:
    refnr = _first(item, *ID_KEYS)
    if not refnr:
        return None
    place = _place(item)
    coords = place.get("koordinaten") or {}
    if not isinstance(coords, dict):
        coords = {}
    return Job(
        refnr=refnr,
        title=_first(item, *TITLE_KEYS),
        occupation=_text(item.get("beruf")),
        employer=_name(item.get("arbeitgeber")) or _text(item.get("arbeitgeberName")),
        place=_text(place.get("ort")),
        postcode=str(place.get("plz") or ""),
        region=_text(place.get("region")),
        lat=_coord(coords, "lat", "breite"),
        lon=_coord(coords, "lon", "laenge"),
        published=_first(item, *DATE_KEYS)[:10],
        start=_text(item.get("eintrittsdatum"))[:10],
        external_url=_first(item, "externeUrl", "externeURL"),
        remote=remote,
    )


def result_items(data: Any) -> list[dict[str, Any]]:
    """Trefferliste aus der Antwort; ohne Treffer fehlt sie ganz."""
    if not isinstance(data, dict):
        return []
    for key in LIST_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def response_shape(path: str, data: Any) -> dict[str, Any]:
    """Nur Feldnamen und Zahlen – hilft, wenn die Bundesagentur das Format ändert."""
    if not isinstance(data, dict):
        return {"path": path, "type": type(data).__name__}
    items = result_items(data)
    return {
        "path": path,
        "keys": sorted(data)[:30],
        "total": data.get("maxErgebnisse"),
        "items": len(items),
        "item_keys": sorted(items[0])[:40] if items else [],
    }


class ShapeError(JobsucheError):
    """Treffer da, aber in einem Format, das Jobradar nicht kennt."""


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
        self.hits = 0
        self.last_shape: dict[str, Any] | None = None

    def new_run(self) -> None:
        """Jede Suche probiert die Detailansicht neu."""
        self._details_available = True
        self._detail_misses = 0
        self.hits = 0

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

        # Der zuletzt funktionierende Pfad zuerst, die anderen als Ausweichroute
        paths = list(SEARCH_PATHS)
        if self._search_path in paths:
            paths.remove(self._search_path)
            paths.insert(0, self._search_path)
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
            await asyncio.sleep(PAUSE)
            items = result_items(data)
            jobs = [job for job in (parse_search_item(i, remote) for i in items) if job]
            if items or self.last_shape is None or self.last_shape.get("path") != path:
                self.last_shape = response_shape(path, data)
            if items and not jobs:
                # Format geändert: andere Route probieren statt still nichts zu finden
                _LOGGER.warning(
                    "Unbekanntes Trefferformat unter %s, Felder: %s",
                    path,
                    ", ".join(sorted(items[0])[:20]),
                )
                last_error = ShapeError(f"Unbekanntes Trefferformat unter {path}")
                continue
            self._search_path = path
            self.hits += len(jobs)
            return jobs
        # Beim nächsten Mal alle Pfade neu probieren
        self._search_path = None
        if isinstance(last_error, ShapeError):
            raise last_error
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
