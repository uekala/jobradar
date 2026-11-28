"""Adapter für den Stellenfeed von service.bund.de (Bund, Länder, Städte und Kommunen).

service.bund.de bietet jede Stellensuche als RSS-Feed an („Suchergebnis als RSS-Feed“).
Jobradar liest diesen Feed wie ein Feedreader: eine Abfrage je Suchbegriff, mit einer
Pause von 30 Sekunden dazwischen (Crawl-delay der Seite). Die robots.txt der Seite
schließt den Suchpfad für automatische Abrufe aus; die Quelle ist deshalb nur auf
ausdrücklichen Wunsch aktiv.
"""
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FEED_URL = "https://www.service.bund.de/Content/DE/Stellen/Suche/Formular.html"
SOURCE = "service.bund.de"
ID_PREFIX = "bund:"
HEADERS = {
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.1",
    "User-Agent": "Jobradar (+https://github.com/uekala/jobradar)",
}
PAUSE_SECONDS = 30
MAX_BYTES = 5_000_000

_ID = re.compile(r"/(\d{5,})\.html")
_TAG = re.compile(r"<[^>]+>")
_BREAK = re.compile(r"<\s*(?:br|/p|/div|/li|/tr)\s*/?\s*>", re.I)
_PLACE = re.compile(r"^(\d{4,5}(?:-\d{3})?)\s+(.+)$")


class BundError(RuntimeError):
    """service.bund.de war nicht erreichbar oder antwortete unerwartet."""


def feed_params(term: str, place: str | None, radius_km: int | None) -> dict[str, str]:
    """Parameter der Stellensuche, wie der Link „Suchergebnis als RSS-Feed“ sie setzt."""
    params = {
        "nn": "4642046",
        "type": "0",
        "resultsPerPage": "100",
        "templateQueryString": term,
        "sortOrder": "dateOfIssue_dt desc",
        "jobsrss": "true",
    }
    if place:
        params["city_zipcode"] = place
        if radius_km:
            params["ambit_distance"] = str(radius_km)
    return params


def _fields(description: str) -> dict[str, str]:
    """'<strong>Arbeitgeber:</strong> Amt X<br />…' → {"arbeitgeber": "Amt X", …}"""
    text = html.unescape(_TAG.sub("", _BREAK.sub("\n", description or "")))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    fields: dict[str, str] = {}
    for index, line in enumerate(lines):
        key, sep, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        # Wert in der nächsten Zeile: "Ort:\n47798 Krefeld"
        if sep and not value and index + 1 < len(lines) and ":" not in lines[index + 1][:25]:
            value = lines[index + 1]
        if sep and key and value and key not in fields:
            fields[key] = value
    return fields


def _published(value: str) -> str | None:
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return None


def _deadline(value: str) -> str | None:
    """'08.11.2026 00:00' → '2026-11-08'"""
    try:
        return datetime.strptime(value.strip()[:10], "%d.%m.%Y").date().isoformat()
    except ValueError:
        return None


def parse_feed(text: str) -> list[dict[str, Any]]:
    """Wandelt den RSS-Feed in Stellen im Format der übrigen Quellen."""
    lowered = text.lower()
    # Ein Stellenfeed braucht keine DTD; ohne sie gibt es keine Entity-Tricks.
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise BundError("Antwort enthält eine DTD")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise BundError(f"Kein gültiger Feed ({exc})") from exc
    if root.tag.lower() == "html" or root.find("channel") is None:
        raise BundError("Antwort ist kein RSS-Feed")
    vacancies: list[dict[str, Any]] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip().split("#", 1)[0]
        guid = (item.findtext("guid") or "").strip()
        match = _ID.search(guid) or _ID.search(link)
        if not title or not match:
            continue
        fields = _fields(item.findtext("description") or "")
        place, postcode = fields.get("ort", ""), ""
        if found := _PLACE.match(place):
            postcode, place = found.group(1), found.group(2)
        deadline = _deadline(fields.get("bewerbungsfrist", ""))
        company = fields.get("arbeitgeber") or None
        details = [f"Arbeitgeber: {company}" if company else "",
                   f"Bewerbungsfrist: {fields['bewerbungsfrist']}" if fields.get("bewerbungsfrist") else ""]
        vacancies.append({
            "id": f"{ID_PREFIX}{match.group(1)}",
            "title": title,
            "company": company,
            "location": place or None,
            "url": link or guid,
            "source": SOURCE,
            "description": "\n".join(part for part in details if part),
            "published_at": _published(item.findtext("pubDate") or ""),
            "application_deadline": deadline,
            "raw": {"postcode": postcode, **fields},
        })
    return vacancies


def _fetch(term: str, place: str | None, radius_km: int | None, timeout: int = 30) -> str:
    url = f"{FEED_URL}?{urlencode(feed_params(term, place, radius_km))}"
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=timeout) as response:
            return response.read(MAX_BYTES).decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise BundError(f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise BundError(f"service.bund.de nicht erreichbar: {exc}") from exc


def search_vacancies(
    terms: list[str],
    location: str | None = None,
    radius_km: int | None = None,
    limit: int = 150,
    pause_seconds: float = PAUSE_SECONDS,
    fetch: Callable[[str, str | None, int | None], str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Sucht je Begriff im Umkreis des Wohnorts und führt die Treffer zusammen."""
    normalized = [term.strip() for term in terms if term and term.strip()]
    if not normalized:
        raise ValueError("Mindestens ein Suchbegriff ist nötig")
    fetch = fetch or _fetch
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for index, term in enumerate(normalized):
        if index:
            sleep(pause_seconds)
        try:
            vacancies = parse_feed(fetch(term, location or None, radius_km))
        except BundError as exc:
            errors.append(f"{term}: {exc}")
            continue
        for vacancy in vacancies:
            found.setdefault(vacancy["id"], vacancy)
        if len(found) >= limit:
            break
    if errors and len(errors) == len(normalized):
        raise BundError("; ".join(errors)[:500])
    return list(found.values())[:limit]
