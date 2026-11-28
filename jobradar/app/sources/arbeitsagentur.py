"""Adapter für die öffentliche Jobsuche der Bundesagentur für Arbeit.

Die Schnittstelle ist öffentlich und frei nutzbar; Doku aus der Community:
https://jobsuche.api.bund.dev/

Die Anfragen bleiben zurückhaltend: eine Suchanfrage je Begriff (plus eine für
die bundesweite Homeoffice-Suche), eine kurze Pause zwischen den Anfragen und
eine begrenzte Zahl an Detailanfragen je Lauf.
"""
from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
DETAIL_PAGE = "https://www.arbeitsagentur.de/jobsuche/jobdetail/"
# Mehrere bekannte Pfade: Die Bundesagentur hat sie über die Jahre geändert.
SEARCH_PATHS = ("/pc/v6/jobs", "/pc/v4/app/jobs", "/pc/v4/jobs")
DETAIL_PATHS = ("/pc/v4/jobdetails/{code}", "/pc/v3/jobdetails/{code}")
HEADERS = {
    "X-API-Key": "jobboerse-jobsuche",
    "Accept": "application/json",
    "User-Agent": "Jobradar",
}
PAUSE_SECONDS = 0.3
DESCRIPTION_LIMIT = 6000

# v4 nennt die Referenznummer refnr, v6 referenznummer.
ID_KEYS = ("refnr", "referenznummer", "referenzNummer")
TITLE_KEYS = ("titel", "stellenangebotsTitel", "stellentitel", "beruf", "hauptberuf")
DATE_KEYS = (
    "aktuelleVeroeffentlichungsdatum",
    "datumErsteVeroeffentlichung",
    "veroeffentlichungsdatum",
    "ersteVeroeffentlichungsdatum",
)
# v4 lists hits under stellenangebote, v6 under ergebnisliste.
LIST_KEYS = ("stellenangebote", "ergebnisliste", "ergebnisse", "jobs", "content", "items")

# Plausibler Bereich für ein Bruttojahresgehalt; "festgehalt": 1 kommt als Platzhalter vor.
MIN_ANNUAL = 12_000
MAX_ANNUAL = 500_000
HOURS_PER_YEAR = 2080


class ArbeitsagenturError(RuntimeError):
    """Die Stellenbörse war nicht erreichbar oder hat unerwartet geantwortet."""


class HttpStatusError(ArbeitsagenturError):
    def __init__(self, status: int, path: str) -> None:
        super().__init__(f"HTTP {status} für {path}")
        self.status = status

    @property
    def path_problem(self) -> bool:
        """Path unknown or blocked: another path may still work."""
        return 400 <= self.status < 500 and self.status != 429


def _get_json(path: str, params: dict[str, Any] | None = None, timeout: int = 30) -> Any:
    url = f"{BASE_URL}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    request = Request(url, headers=HEADERS)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise HttpStatusError(exc.code, path) from exc
    except (URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ArbeitsagenturError(f"Arbeitsagentur nicht erreichbar: {exc}") from exc


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _first(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(item.get(key))
        if value:
            return value
    return ""


def _name(value: Any) -> str:
    """Der Arbeitgeber ist je nach Version ein Text oder ein Objekt."""
    if isinstance(value, dict):
        return _first(value, "name", "bezeichnung", "arbeitgeber")
    return _text(value)


def _place(item: dict[str, Any]) -> dict[str, Any]:
    """Arbeitsort.

    v4: arbeitsort{ort, plz, ...} oder arbeitsorte[...];
    v6: stellenlokationen[{adresse{ort, plz, ...}}].
    """
    place: Any = item.get("arbeitsort")
    if not isinstance(place, dict):
        for key in ("arbeitsorte", "stellenlokationen"):
            places = item.get(key)
            if isinstance(places, list) and places and isinstance(places[0], dict):
                place = places[0]
                break
    if not isinstance(place, dict):
        return {}
    address = place.get("adresse")
    if isinstance(address, dict):
        place = {**place, **address}
    return place


def _from(item: dict[str, Any], key: str) -> str:
    """Datum aus einem Zeitraum-Objekt wie {"von": "2026-11-02"}."""
    value = item.get(key)
    return _text(value.get("von")) if isinstance(value, dict) else _text(value)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(".", "").replace(",", ".")) if "," in value else float(value)
        except ValueError:
            return None
    return None


def _annual(value: Any, kind: str) -> int | None:
    number = _number(value)
    if number is None or number <= 0:
        return None
    if "STUNDE" in kind:
        number *= HOURS_PER_YEAR
    elif "MONAT" in kind or number < 15_000:
        # Ein Monatsbetrag, auch wenn er versehentlich als Jahresgehalt markiert ist.
        number *= 12
    annual = round(number)
    return annual if MIN_ANNUAL <= annual <= MAX_ANNUAL else None


def pay_from_item(item: dict[str, Any]) -> tuple[int | None, int | None]:
    """Bruttojahresgehalt (von, bis) eines Treffers oder Detaildatensatzes."""
    kind = str(item.get("verguetungsangabe") or "").upper()
    if not kind or kind == "KEINE_ANGABEN":
        return None, None
    art = str(item.get("artDerVerguetung") or "").upper()
    if art == "GEHALTSSPANNE" or "gehaltsspanneVon" in item or "gehaltsspanneBis" in item:
        low = _annual(item.get("gehaltsspanneVon"), kind)
        high = _annual(item.get("gehaltsspanneBis"), kind)
        if low and high and low > high:
            low, high = high, low
        return low, high
    fixed = _annual(item.get("festgehalt"), kind)
    return fixed, fixed


def result_items(data: Any) -> list[dict[str, Any]]:
    """Trefferliste einer Antwort; ohne Treffer fehlt sie ganz."""
    if not isinstance(data, dict):
        return []
    for key in LIST_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            # One level deeper, e.g. {"ergebnisliste": {"stellenangebote": [...]}}
            for inner in value.values():
                if isinstance(inner, list) and inner:
                    return [item for item in inner if isinstance(item, dict)]
    return []


def total_hits(data: Any) -> int:
    try:
        return int(data.get("maxErgebnisse") or 0) if isinstance(data, dict) else 0
    except (TypeError, ValueError):
        return 0


def parse_search_item(item: dict[str, Any], remote_search: bool) -> dict[str, Any] | None:
    """Bringt einen Treffer in das Stellenformat der App."""
    refnr = _first(item, *ID_KEYS)
    if not refnr:
        return None
    place = _place(item)
    published = _first(item, *DATE_KEYS) or _from(item, "veroeffentlichungszeitraum")
    salary_min, salary_max = pay_from_item(item)
    remote = remote_search
    # v6 gibt je Stelle an, ob Homeoffice möglich ist; v4 nur über den Filter.
    home_office = item.get("homeofficemoeglich")
    if isinstance(home_office, bool):
        remote = home_office
    return {
        "id": f"arbeitsagentur:{refnr}",
        "refnr": refnr,
        "title": _first(item, *TITLE_KEYS) or "Ohne Titel",
        "company": (
            _name(item.get("arbeitgeber"))
            or _name(item.get("firma"))
            or _text(item.get("arbeitgeberName"))
            or None
        ),
        "location": _text(place.get("ort")) or None,
        "url": f"{DETAIL_PAGE}{refnr}",
        "source": "Arbeitsagentur",
        "description": "",
        "published_at": published[:10] or None,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "remote_type": "homeoffice" if remote else None,
        "raw": item,
    }


def apply_details(vacancy: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Ergänzt Beschreibung, Gehalt und Arbeitszeit aus dem Detaildatensatz."""
    description = _text(data.get("stellenangebotsBeschreibung")) or _text(
        data.get("stellenbeschreibung")
    )
    parts = [description[:DESCRIPTION_LIMIT]]
    # Vergütungstext und Befristungshinweise nennen Entgeltgruppen wie "EG 11 TVöD".
    for label, key in (("Vergütung", "verguetung"), ("Befristung", "befristung")):
        value = _text(data.get(key))
        if value:
            parts.append(f"{label}: {value}")
    vacancy["description"] = "\n\n".join(part for part in parts if part)
    low, high = pay_from_item(data)
    if low or high:
        vacancy["salary_min"], vacancy["salary_max"] = low, high
    models = [model for model in data.get("arbeitszeitmodelle") or [] if isinstance(model, str)]
    if data.get("homeofficemoeglich") is True or any(
        "HEIM" in model.upper() or "TELE" in model.upper() for model in models
    ):
        vacancy["remote_type"] = "homeoffice"
    title = _text(data.get("stellenangebotsTitel")) or _text(data.get("titel"))
    if title:
        vacancy["title"] = title
    if not vacancy.get("company"):
        vacancy["company"] = _name(data.get("arbeitgeber")) or _name(data.get("firma")) or None
    if not vacancy.get("location"):
        vacancy["location"] = _text(_place(data).get("ort")) or None
    vacancy["raw"] = {"treffer": vacancy.get("raw"), "details": data}
    return vacancy


def _too_old(published: str | None, days: int, today: date) -> bool:
    """Die v6-Suche beachtet veroeffentlichtseit nicht zuverlässig, daher auch hier filtern."""
    if not published:
        return False
    try:
        return date.fromisoformat(published[:10]) < today - timedelta(days=days)
    except ValueError:
        return False


class _Client:
    def __init__(self, get_json: Callable[..., Any], pause: Callable[[float], None]) -> None:
        self._get_json = get_json
        self._pause = pause
        self._search_path: str | None = None
        self._details_available = True
        self._detail_misses = 0

    def search(self, params: dict[str, Any], remote: bool) -> list[dict[str, Any]]:
        # Der zuletzt erfolgreiche Pfad kommt zuerst, die anderen sind Ausweichwege.
        paths = list(SEARCH_PATHS)
        if self._search_path in paths:
            paths.remove(self._search_path)
            paths.insert(0, self._search_path)
        last_error: Exception | None = None
        for path in paths:
            try:
                data = self._get_json(path, params)
            except HttpStatusError as err:
                if not err.path_problem:
                    raise
                last_error = err
                continue
            self._pause(PAUSE_SECONDS)
            items = result_items(data)
            vacancies = [v for v in (parse_search_item(item, remote) for item in items) if v]
            if (items and not vacancies) or (not items and total_hits(data) > 0):
                # Format geändert: anderen Weg versuchen, statt still nichts zu finden.
                last_error = ArbeitsagenturError(f"Unbekanntes Trefferformat unter {path}")
                continue
            self._search_path = path
            if remote:
                # Bundesweite Homeoffice-Suche: Stellen ohne Homeoffice gehören nicht hierher.
                vacancies = [v for v in vacancies if v["remote_type"]]
            return vacancies
        self._search_path = None
        raise ArbeitsagenturError(f"Kein Suchpfad erreichbar ({last_error})")

    def load_details(self, vacancy: dict[str, Any]) -> bool:
        if not self._details_available:
            return False
        code = base64.b64encode(vacancy["refnr"].encode()).decode()
        for path in DETAIL_PATHS:
            try:
                data = self._get_json(path.format(code=code))
            except HttpStatusError as err:
                if err.path_problem:
                    continue
                return False
            except ArbeitsagenturError:
                return False
            self._pause(PAUSE_SECONDS)
            if isinstance(data, dict):
                self._detail_misses = 0
                apply_details(vacancy, data)
                return True
        # Eine einzelne Lücke kann eine gerade gelöschte Stelle sein, mehrere hintereinander nicht.
        self._detail_misses += 1
        if self._detail_misses >= 3:
            self._details_available = False
        return False


def search_vacancies(
    terms: list[str],
    location: str | None = None,
    radius_km: int | None = None,
    *,
    include_remote: bool = False,
    days: int = 7,
    limit: int = 150,
    max_details: int = 40,
    exclude_temp_agencies: bool = False,
    known_ids: set[str] | None = None,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Sucht Stellen für alle Begriffe und lädt Details zu unbekannten.

    ``known_ids`` sind IDs bereits gespeicherter Stellen; ihre Details werden
    nicht erneut abgefragt. Eine einzelne scheiternde Suche hält die anderen
    nicht auf; scheitern alle Suchen, wird der Fehler geworfen.
    """
    normalized_terms = [term.strip() for term in terms if term and term.strip()]
    if not normalized_terms:
        raise ValueError("Mindestens ein Suchbegriff ist erforderlich")
    days = max(1, min(100, int(days)))
    today = today or datetime.now(UTC).date()
    known = known_ids or set()
    client = _Client(_get_json, time.sleep)

    searches: list[tuple[str, bool]] = []
    for term in normalized_terms:
        if location:
            searches.append((term, False))
        if include_remote or not location:
            searches.append((term, True))

    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    succeeded = 0
    for term, remote in searches:
        params: dict[str, Any] = {
            "was": term,
            "angebotsart": 1,
            "page": 1,
            "size": 50,
            "veroeffentlichtseit": days,
        }
        if remote:
            params["arbeitszeit"] = "ho"
        else:
            params["wo"] = location
            if radius_km:
                params["umkreis"] = int(radius_km)
        if exclude_temp_agencies:
            params["zeitarbeit"] = "false"
        try:
            vacancies = client.search(params, remote)
        except ArbeitsagenturError as err:
            errors.append(f"{term}: {err}")
            continue
        succeeded += 1
        for vacancy in vacancies:
            if _too_old(vacancy["published_at"], days, today):
                continue
            found.setdefault(vacancy["id"], vacancy)
    if searches and succeeded == 0:
        raise ArbeitsagenturError("; ".join(errors)[:500])

    # Neueste zuerst, damit Limit und Detailbudget an frische Stellen gehen.
    ordered = sorted(found.values(), key=lambda v: v["published_at"] or "", reverse=True)[:limit]
    details_left = max(0, int(max_details))
    for vacancy in ordered:
        if details_left <= 0:
            break
        if vacancy["id"] in known:
            continue
        details_left -= 1
        client.load_details(vacancy)
    for vacancy in ordered:
        vacancy.pop("refnr", None)
    return ordered
