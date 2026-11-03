"""service.bund.de: RSS-Feed der Stellensuche."""

from __future__ import annotations

import pytest

from custom_components.jobradar.bund import BundError, feed_params, parse_feed

from .conftest import bund_feed, bund_item


def test_feed_items_become_jobs() -> None:
    feed = bund_feed(
        [
            bund_item(
                6683770,
                "IT-Systemadministrator (m/w/d) E 11 TVöD",
                "Bundesamt für Muster &amp; Co",
                "47798 Krefeld",
                published="2026-11-02",
                deadline="15.11.2026 23:59",
            )
        ]
    )
    (job,) = parse_feed(feed)
    assert job.refnr == "bund-6683770"
    assert job.title == "IT-Systemadministrator (m/w/d) E 11 TVöD"
    assert job.employer == "Bundesamt für Muster & Co"
    assert (job.postcode, job.place) == ("47798", "Krefeld")
    assert job.published == "2026-11-02" and job.deadline == "2026-11-15"
    assert job.url.endswith("/6683770.html") and "#" not in job.url
    assert job.source == "bund.de" and not job.from_jobboerse


def test_foreign_postcode_and_missing_fields() -> None:
    feed = bund_feed([bund_item(6679709, "Sozialpädagoge (m/w/d)", "", "1600-891 Lissabon")])
    (job,) = parse_feed(feed)
    assert (job.postcode, job.place, job.employer) == ("1600-891", "Lissabon", "")


@pytest.mark.parametrize(
    "text",
    [
        '<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY a "x">]><rss><channel/></rss>',
        "<html><body>Wartungsarbeiten</body></html>",
        "kein xml",
    ],
)
def test_unexpected_answers_are_errors(text: str) -> None:
    with pytest.raises(BundError):
        parse_feed(text)


def test_empty_feed_is_no_error() -> None:
    assert parse_feed(bund_feed([])) == []


def test_feed_params_match_the_rss_link() -> None:
    params = feed_params("Systemadministrator", "Krefeld", 50)
    assert params["jobsrss"] == "true" and params["templateQueryString"] == "Systemadministrator"
    assert params["city_zipcode"] == "Krefeld" and params["ambit_distance"] == "50"
    assert params["sortOrder"] == "dateOfIssue_dt desc"
    assert "city_zipcode" not in feed_params("VMware", None, None)


def test_location_modes() -> None:
    assert "searchResult" in feed_params("x", "Krefeld", 50, "radius_result")
    place = feed_params("x", "Krefeld", 50, "place")
    assert place["city_zipcode"] == "Krefeld" and "ambit_distance" not in place
    region = feed_params("x", "Krefeld", 50, "region")
    assert region["templateQueryString"] == "x Krefeld" and "city_zipcode" not in region
