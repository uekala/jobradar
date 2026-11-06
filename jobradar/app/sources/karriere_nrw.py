"""Public Open-Data adapter for Karriere.NRW.

The API is documented for third-party integration. Keep requests conservative:
one search request and one detail request per returned vacancy.
"""
from __future__ import annotations

import json
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://api.karriere.nrw/v1.0/opennrw"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)


def _plain_text(markup: str | None) -> str:
    if not markup:
        return ""
    parser = _TextExtractor()
    parser.feed(markup)
    return " ".join(parser.parts)


def _get_json(url: str, timeout: int = 20) -> dict:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Jobradar/0.1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Karriere.NRW API request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Karriere.NRW API returned an unexpected response")
    return payload


def search_vacancies(
    terms: list[str],
    location: str | None = None,
    radius_km: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search public NRW vacancies and fetch their detail records."""
    normalized_terms = [term.strip() for term in terms if term and term.strip()]
    if not normalized_terms:
        raise ValueError("At least one search term is required")

    # The public API accepts one free-text value. Search terms are queried
    # individually to avoid silently losing profile keywords.
    found: dict[str, dict] = {}
    for term in normalized_terms:
        params: dict[str, str] = {"text": term, "taetigkeitsfeld": "3"}
        if location:
            params["ort"] = location
            if radius_km is not None:
                params["umkreis"] = str(_radius_code(radius_km))
        result = _get_json(f"{BASE_URL}/suche?{urlencode(params)}")
        rows = result.get("results", [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            vacancy_id = row.get("uuid")
            if vacancy_id:
                found[str(vacancy_id)] = row
            if len(found) >= limit:
                break
        if len(found) >= limit:
            break

    vacancies: list[dict] = []
    for vacancy_id, metadata in list(found.items())[:limit]:
        detail = _get_json(f"{BASE_URL}/stellenausschreibungen/{vacancy_id}")
        description = "\n\n".join(
            part for part in (
                _plain_text(detail.get("stellenbeschreibung")),
                _plain_text(detail.get("ergaenzende_inhalte")),
            ) if part
        )
        vacancies.append({
            "id": f"karriere-nrw:{vacancy_id}",
            "title": detail.get("titel_der_stelle") or metadata.get("titel_der_stelle") or "Ohne Titel",
            "company": detail.get("ausschreibende_behoerde") or metadata.get("ausschreibende_behoerde"),
            "location": detail.get("ort") or metadata.get("ort"),
            "url": detail.get("url"),
            "source": "Karriere.NRW",
            "description": description,
            "published_at": detail.get("erscheinungsdatum") or metadata.get("erscheinungsdatum"),
            "application_deadline": detail.get("bewerbungsfrist") or metadata.get("bewerbungsfrist"),
            "raw": detail,
        })
    return vacancies


def _radius_code(radius_km: int) -> int:
    """Map a requested radius to the API's supported distance bands."""
    bands = [(5, 0), (10, 1), (15, 2), (20, 3), (50, 4), (100, 5), (150, 6), (200, 7)]
    for maximum, code in bands:
        if radius_km <= maximum:
            return code
    return 7
