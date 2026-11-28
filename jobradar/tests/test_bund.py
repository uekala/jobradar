"""service.bund.de: RSS-Feed der Stellensuche als Quelle des Dienstes."""
from __future__ import annotations

import pytest
from app.sources.bund import BundError, feed_params, parse_feed, search_vacancies


def _item(number: int, title: str, employer: str, place: str, deadline: str = "15.11.2026 23:59") -> str:
    description = (
        f"&lt;strong&gt;Arbeitgeber:&lt;/strong&gt; {employer}&lt;br /&gt;"
        f"&lt;strong&gt;Ort:&lt;/strong&gt;&lt;br /&gt;{place}&lt;br /&gt;"
        f"&lt;strong&gt;Bewerbungsfrist:&lt;/strong&gt; {deadline}"
    )
    link = f"https://www.service.bund.de/IMPORTE/Stellenangebote/beispiel/2026/11/{number}.html"
    return (
        f"<item><title>{title}</title><link>{link}#track</link><guid>{link}</guid>"
        f"<pubDate>Mon, 02 Nov 2026 10:00:00 +0100</pubDate><description>{description}</description></item>"
    )


def _feed(*items: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Stellen</title>{"".join(items)}</channel></rss>'


def test_feed_items_become_vacancies() -> None:
    (vacancy,) = parse_feed(_feed(_item(6683770, "IT-Systemadministrator (m/w/d) E 11 TVöD",
                                        "Bundesamt für Muster &amp;amp; Co", "47798 Krefeld")))
    assert vacancy["id"] == "bund:6683770"
    assert vacancy["title"] == "IT-Systemadministrator (m/w/d) E 11 TVöD"
    assert vacancy["company"] == "Bundesamt für Muster & Co"
    assert vacancy["location"] == "Krefeld" and vacancy["raw"]["postcode"] == "47798"
    assert vacancy["published_at"] == "2026-11-02"
    assert vacancy["application_deadline"] == "2026-11-15"
    assert vacancy["url"].endswith("/6683770.html") and "#" not in vacancy["url"]
    assert vacancy["source"] == "service.bund.de"
    assert "Bewerbungsfrist: 15.11.2026" in vacancy["description"]


@pytest.mark.parametrize(
    "text",
    [
        "<html><body>Wartung</body></html>",
        "kein xml",
        '<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY a "x">]><rss><channel/></rss>',
    ],
)
def test_unexpected_answers_are_errors(text: str) -> None:
    with pytest.raises(BundError):
        parse_feed(text)


def test_feed_params_match_the_rss_link() -> None:
    params = feed_params("Systemadministrator", "Krefeld", 50)
    assert params["jobsrss"] == "true" and params["templateQueryString"] == "Systemadministrator"
    assert params["city_zipcode"] == "Krefeld" and params["ambit_distance"] == "50"
    assert "city_zipcode" not in feed_params("Systemadministrator", None, 50)


def test_search_pauses_between_terms_and_merges_duplicates() -> None:
    calls: list[tuple[str, str | None, int | None]] = []
    pauses: list[float] = []
    feeds = {
        "Systemadministrator": _feed(_item(1000001, "Systemadministrator", "Amt A", "47798 Krefeld"),
                                     _item(1000002, "IT-Administrator", "Amt B", "40210 Düsseldorf")),
        "IT-Administrator": _feed(_item(1000002, "IT-Administrator", "Amt B", "40210 Düsseldorf")),
    }

    def fetch(term, place, radius):
        calls.append((term, place, radius))
        return feeds[term]

    found = search_vacancies(["Systemadministrator", " ", "IT-Administrator"], "Krefeld", 50,
                             fetch=fetch, sleep=pauses.append)
    assert [v["id"] for v in found] == ["bund:1000001", "bund:1000002"]
    assert calls == [("Systemadministrator", "Krefeld", 50), ("IT-Administrator", "Krefeld", 50)]
    assert pauses == [30]


def test_one_failing_term_does_not_stop_the_others() -> None:
    def fetch(term, place, radius):
        if term == "kaputt":
            raise BundError("HTTP 503")
        return _feed(_item(1000003, "Systemadministrator", "Amt C", "47798 Krefeld"))

    found = search_vacancies(["kaputt", "Systemadministrator"], fetch=fetch, sleep=lambda _: None)
    assert [v["id"] for v in found] == ["bund:1000003"]


def test_all_terms_failing_is_an_error() -> None:
    def fetch(term, place, radius):
        raise BundError("HTTP 503")

    with pytest.raises(BundError, match="503"):
        search_vacancies(["a", "b"], fetch=fetch, sleep=lambda _: None)


def test_terms_are_required() -> None:
    with pytest.raises(ValueError):
        search_vacancies(["", "  "])
