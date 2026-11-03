"""Stellen von service.bund.de: Bund, Länder, Städte und Kommunen.

service.bund.de bietet jede Stellensuche als RSS-Feed an ("Suchergebnis als
RSS-Feed"). Jobradar abonniert diesen Feed wie ein Feedreader: je Suchbegriff
eine Abfrage, höchstens alle zwei Stunden.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import aiohttp

from .scoring import Job

FEED_URL = "https://www.service.bund.de/Content/DE/Stellen/Suche/Formular.html"
PREFIX = "bund-"
SOURCE = "bund.de"
HEADERS = {
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.1",
    "User-Agent": "Jobradar for Home Assistant (+https://github.com/uekala/jobradar)",
}
TIMEOUT = aiohttp.ClientTimeout(total=30)

_ID = re.compile(r"/(\d{5,})\.html")
_TAG = re.compile(r"<[^>]+>")
_BREAK = re.compile(r"<\s*(?:br|/p|/div|/li|/tr)\s*/?\s*>", re.I)
_PLACE = re.compile(r"^(\d{4,5}(?:-\d{3})?)\s+(.+)$")


class BundError(Exception):
    """service.bund.de war nicht erreichbar oder antwortete unerwartet."""


# Wie der Ort übergeben wird. service.bund.de dokumentiert das nicht; der erste
# Lauf probiert die Varianten und nimmt die, die Treffer liefert.
MODES = ("radius", "radius_result", "place", "region")


def feed_params(
    term: str, location: str | None, radius: int | None, mode: str = "radius"
) -> dict[str, str]:
    """Parameter der Stellensuche, wie der Link "Suchergebnis als RSS-Feed" sie setzt."""
    params = {
        "nn": "4642046",
        "type": "0",
        "resultsPerPage": "100",
        "templateQueryString": term,
        "sortOrder": "dateOfIssue_dt desc",
        "jobsrss": "true",
    }
    if not location:
        return params
    if mode == "region":
        # Ort als Suchwort statt als Ortsfilter
        params["templateQueryString"] = f"{term} {location}"
        return params
    params["city_zipcode"] = location
    if radius and mode in ("radius", "radius_result"):
        params["ambit_distance"] = str(radius)
    if mode == "radius_result":
        params["searchResult"] = "true"
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


def _published(value: str) -> str:
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return ""


def _deadline(value: str) -> str:
    """'08.11.2026 00:00' → '2026-11-08'"""
    try:
        return datetime.strptime(value.strip()[:10], "%d.%m.%Y").date().isoformat()
    except ValueError:
        return ""


def parse_feed(text: str) -> list[Job]:
    lowered = text.lower()
    # Ein Stellenfeed braucht keine DTD; ohne sie gibt es keine Entity-Tricks
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise BundError("Antwort enthält eine DTD")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as err:
        raise BundError(f"Kein gültiger Feed ({err})") from err
    if root.tag.lower() == "html" or root.find("channel") is None:
        raise BundError("Antwort ist kein RSS-Feed")
    jobs: list[Job] = []
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
        jobs.append(
            Job(
                refnr=f"{PREFIX}{match.group(1)}",
                title=title,
                employer=fields.get("arbeitgeber", ""),
                place=place,
                postcode=postcode,
                published=_published(item.findtext("pubDate") or ""),
                link=link or guid,
                source=SOURCE,
                deadline=_deadline(fields.get("bewerbungsfrist", "")),
            )
        )
    return jobs


class BundClient:
    """Fragt den Stellenfeed von service.bund.de ab."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self.requests = 0
        self.hits = 0
        self.errors = 0
        self.last_error = ""
        self.last_response: dict[str, object] = {}
        self.mode = "radius"
        self.probe: dict[str, int | str] = {}

    async def async_probe(self, term: str, *, location: str, radius: int | None) -> None:
        """Findet heraus, wie service.bund.de den Ort annimmt (einmal pro Start)."""
        counts: dict[str, int | str] = {}
        for mode in MODES:
            try:
                counts[mode] = len(
                    await self.search(term, location=location, radius=radius, mode=mode)
                )
            except BundError as err:
                counts[mode] = f"Fehler: {err}"
        try:
            counts["bundesweit"] = len(await self.search(term, location=None, radius=None))
        except BundError as err:
            counts["bundesweit"] = f"Fehler: {err}"
        self.probe = counts
        working = [m for m in MODES if isinstance(counts.get(m), int) and counts[m]]
        self.mode = working[0] if working else "radius"

    async def search(
        self, term: str, *, location: str | None, radius: int | None, mode: str | None = None
    ) -> list[Job]:
        self.requests += 1
        try:
            async with self._session.get(
                FEED_URL,
                params=feed_params(term, location, radius, mode or self.mode),
                headers=HEADERS,
                timeout=TIMEOUT,
            ) as response:
                text = await response.text()
                # Nur Kopf und Zahlen, damit sich Formatwechsel erkennen lassen
                self.last_response = {
                    "url": str(response.url),
                    "status": response.status,
                    "content_type": response.content_type,
                    "length": len(text),
                    "items": text.count("<item>"),
                    "head": text[:400],
                }
                if response.status >= 400:
                    raise BundError(f"HTTP {response.status}")
            jobs = parse_feed(text)
        except BundError as err:
            self.errors += 1
            self.last_error = str(err)
            raise
        except (aiohttp.ClientError, TimeoutError, UnicodeDecodeError) as err:
            self.errors += 1
            self.last_error = f"{type(err).__name__}: {err}"
            raise BundError(str(err)) from err
        self.hits += len(jobs)
        return jobs
