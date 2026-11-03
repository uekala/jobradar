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

from .pay import grade_from_text, pay_from_item
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


def _place(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Arbeitsort und Koordinaten.

    v4: arbeitsort{ort, plz, koordinaten{lat, lon}} oder arbeitsorte[...];
    v6: stellenlokationen[{adresse{ort, plz, ...}, breite, laenge}].
    """
    place: Any = item.get("arbeitsort")
    if not isinstance(place, dict):
        for key in ("arbeitsorte", "stellenlokationen"):
            places = item.get(key)
            if isinstance(places, list) and places and isinstance(places[0], dict):
                place = places[0]
                break
    if not isinstance(place, dict):
        return {}, {}
    coords = place.get("koordinaten")
    coords = coords if isinstance(coords, dict) else place
    address = place.get("adresse")
    if isinstance(address, dict):
        if not isinstance(place.get("koordinaten"), dict) and isinstance(
            address.get("koordinaten"), dict
        ):
            coords = address["koordinaten"]
        place = {**place, **address}
    return place, coords


def _coord(coords: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = coords.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.replace(",", "."))
            except ValueError:
                continue
    return None


def _from(item: dict[str, Any], key: str) -> str:
    """Datum aus einem Zeitraum-Objekt wie {"von": "2026-11-02"}."""
    value = item.get(key)
    return _text(value.get("von")) if isinstance(value, dict) else _text(value)


def _km(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ".").replace("km", "").strip())
        except ValueError:
            return None
    return None


# Felder je nach Version: v4 nennt die Kennung refnr, v6 referenznummer
ID_KEYS = ("refnr", "referenznummer", "referenzNummer")
TITLE_KEYS = ("titel", "stellenangebotsTitel", "stellentitel", "beruf", "hauptberuf")
DATE_KEYS = (
    "aktuelleVeroeffentlichungsdatum",
    "datumErsteVeroeffentlichung",
    "veroeffentlichungsdatum",
    "ersteVeroeffentlichungsdatum",
)
# v4 liefert die Treffer unter stellenangebote, v6 unter ergebnisliste
LIST_KEYS = ("stellenangebote", "ergebnisliste", "ergebnisse", "jobs", "content", "items")


def _fuzzy(item: dict[str, Any], *parts: str) -> str:
    """Notnagel: erstes Textfeld, dessen Name einen der Wortteile enthält."""
    for key, value in item.items():
        if any(part in key.lower() for part in parts):
            text = _text(value)
            if text:
                return text
    return ""


def parse_search_item(item: dict[str, Any], remote: bool) -> Job | None:
    refnr = _first(item, *ID_KEYS) or _fuzzy(item, "refnr", "referenz")
    if not refnr:
        return None
    place, coords = _place(item)
    published = (
        _first(item, *DATE_KEYS)
        or _from(item, "veroeffentlichungszeitraum")
        or _fuzzy(item, "veroeffentlich")
    )
    job = Job(
        refnr=refnr,
        title=_first(item, *TITLE_KEYS) or _fuzzy(item, "titel"),
        occupation=_first(item, "beruf", "hauptberuf"),
        employer=(
            _name(item.get("arbeitgeber"))
            or _name(item.get("firma"))
            or _text(item.get("arbeitgeberName"))
        ),
        place=_text(place.get("ort")),
        postcode=str(place.get("plz") or ""),
        region=_text(place.get("region")),
        lat=_coord(coords, "lat", "breite"),
        lon=_coord(coords, "lon", "laenge"),
        published=published[:10],
        start=(_text(item.get("eintrittsdatum")) or _from(item, "eintrittszeitraum"))[:10],
        external_url=_first(item, "externeUrl", "externeURL"),
        remote=remote,
    )
    job.pay_low, job.pay_high = pay_from_item(item)
    # v6 sagt je Stelle, ob Homeoffice möglich ist; v4 nur über den Suchfilter
    home_office = item.get("homeofficemoeglich")
    if isinstance(home_office, bool):
        job.remote = home_office
    # v6 rechnet die Entfernung zum Suchort selbst aus
    if not remote:
        job.distance_km = _km(item.get("entfernung"))
    return job


def _dicts(value: Any) -> list[dict[str, Any]] | None:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return None


def result_items(data: Any) -> list[dict[str, Any]]:
    """Trefferliste aus der Antwort; ohne Treffer fehlt sie ganz."""
    if not isinstance(data, dict):
        return []
    for key in LIST_KEYS:
        value = data.get(key)
        items = _dicts(value)
        if items is not None:
            return items
        if isinstance(value, dict):
            # Liste eine Ebene tiefer, etwa {"ergebnisliste": {"stellenangebote": [...]}}
            for inner in value.values():
                items = _dicts(inner)
                if items:
                    return items
    return []


def total_hits(data: Any) -> int:
    try:
        return int(data.get("maxErgebnisse") or 0) if isinstance(data, dict) else 0
    except (TypeError, ValueError):
        return 0


def _keys(value: Any) -> Any:
    if isinstance(value, dict):
        return sorted(value)[:40]
    if isinstance(value, list):
        first = value[0] if value else None
        return [_keys(first)] if isinstance(first, dict) else f"list[{len(value)}]"
    return type(value).__name__


def response_shape(path: str, data: Any) -> dict[str, Any]:
    """Nur Feldnamen und Zahlen – hilft, wenn die Bundesagentur das Format ändert."""
    if not isinstance(data, dict):
        return {"path": path, "type": type(data).__name__}
    items = result_items(data)
    shape: dict[str, Any] = {
        "path": path,
        "keys": {key: _keys(value) for key, value in list(data.items())[:20] if key != "facetten"},
        "total": data.get("maxErgebnisse"),
        "items": len(items),
        "item_keys": sorted(items[0])[:40] if items else [],
    }
    if items:
        nested: dict[str, Any] = {}
        for key, value in items[0].items():
            if not isinstance(value, (dict, list)):
                continue
            nested[key] = _keys(value)
            first = value[0] if isinstance(value, list) and value else value
            if isinstance(first, dict):
                for sub, inner in first.items():
                    if isinstance(inner, (dict, list)):
                        nested[f"{key}.{sub}"] = _keys(inner)
        shape["item_nested"] = nested
    return shape


PAY_PARTS = ("verguet", "gehalt", "entgelt", "tarif", "lohn", "salary", "bezahl")


def pay_fields(data: Any) -> dict[str, Any]:
    """Alle Felder, die nach Vergütung klingen – nur für die Diagnose."""
    if not isinstance(data, dict):
        return {}
    found: dict[str, Any] = {}
    for key, value in data.items():
        if not any(part in key.lower() for part in PAY_PARTS):
            continue
        if isinstance(value, str):
            value = value[:200]
        elif isinstance(value, (dict, list)):
            value = str(value)[:200]
        found[key] = value
    return found


class ShapeError(JobsucheError):
    """Treffer da, aber in einem Format, das Jobradar nicht kennt."""


def apply_details(job: Job, data: dict[str, Any]) -> Job:
    """Ergänzt Beschreibung, Vergütung und Arbeitszeit aus der Detailansicht."""
    description = _text(data.get("stellenangebotsBeschreibung")) or _text(
        data.get("stellenbeschreibung")
    )
    job.description = description[:6000]
    job.salary = _text(data.get("verguetung"))
    low, high = pay_from_item(data)
    if low or high:
        job.pay_low, job.pay_high = low, high
    elif not (job.pay_low or job.pay_high):
        # Die Entgeltgruppe steht oft am Ende der Anzeige, also im vollen Text suchen
        job.pay_grade, job.pay_scale = grade_from_text(f"{job.title}\n{description}")
    job.limited = _text(data.get("befristung"))
    models = [m for m in data.get("arbeitszeitmodelle") or [] if isinstance(m, str)]
    job.working_time = models
    if any("HEIM" in m.upper() or "TELE" in m.upper() for m in models):
        job.remote = True
    if data.get("homeofficemoeglich") is True:
        job.remote = True
    title = _text(data.get("stellenangebotsTitel")) or _text(data.get("titel"))
    if title:
        job.title = title
    if not job.employer:
        job.employer = _name(data.get("arbeitgeber")) or _name(data.get("firma"))
    if not job.place:
        place, coords = _place(data)
        job.place = _text(place.get("ort"))
        job.postcode = job.postcode or str(place.get("plz") or "")
        job.region = job.region or _text(place.get("region"))
        if job.lat is None:
            job.lat = _coord(coords, "lat", "breite")
            job.lon = _coord(coords, "lon", "laenge")
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
        self.shapes: dict[str, dict[str, Any]] = {}
        self.pay_samples: dict[str, int] = {}
        self.detail_shape: dict[str, Any] | None = None

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
            for item in items:
                for key, value in pay_fields(item).items():
                    sample = f"{key}={value}"
                    if sample in self.pay_samples or len(self.pay_samples) < 25:
                        self.pay_samples[sample] = self.pay_samples.get(sample, 0) + 1
            if items or total_hits(data) or path not in self.shapes:
                self.shapes[path] = response_shape(path, data)
            if (items and not jobs) or (not items and total_hits(data) > 0):
                # Format geändert: andere Route probieren statt still nichts zu finden
                _LOGGER.warning(
                    "Unbekanntes Trefferformat unter %s, Felder: %s",
                    path,
                    ", ".join(sorted(items[0] if items else data)[:20]),
                )
                last_error = ShapeError(f"Unbekanntes Trefferformat unter {path}")
                continue
            self._search_path = path
            if remote:
                # Bundesweite Homeoffice-Suche: Stellen ohne Homeoffice sind hier fehl am Platz
                jobs = [job for job in jobs if job.remote]
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
                self.detail_shape = {
                    "path": path.split("/{")[0],
                    "keys": sorted(data)[:80],
                    "pay": pay_fields(data),
                }
                apply_details(job, data)
                return True
        # Eine einzelne Lücke kann eine gerade gelöschte Stelle sein, mehrere in Folge nicht
        self._detail_misses += 1
        if self._detail_misses >= 3:
            _LOGGER.info("Die Jobbörse liefert keine Stellendetails – bewertet wird nur der Titel")
            self._details_available = False
        return False
