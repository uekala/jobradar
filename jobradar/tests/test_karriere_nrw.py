from app.sources.karriere_nrw import _plain_text, _radius_code, search_vacancies


def test_radius_maps_to_supported_api_bands():
    assert _radius_code(5) == 0
    assert _radius_code(12) == 2
    assert _radius_code(50) == 4
    assert _radius_code(500) == 7


def test_plain_text_removes_html_markup():
    assert _plain_text("<p>Linux <strong>Administrator</strong></p><p>NRW</p>") == "Linux Administrator NRW"


def test_search_fetches_details_and_normalizes_vacancy(monkeypatch):
    responses = iter([
        {"results": [{
            "uuid": "vacancy-123",
            "titel_der_stelle": "IT-Administrator",
            "ausschreibende_behoerde": "Land NRW",
            "ort": "Düsseldorf",
        }]},
        {
            "uuid": "vacancy-123",
            "titel_der_stelle": "IT-Administrator",
            "ausschreibende_behoerde": "Land NRW",
            "ort": "Düsseldorf",
            "stellenbeschreibung": "<p>Linux und VMware</p>",
            "ergaenzende_inhalte": "<p>TV-L</p>",
            "erscheinungsdatum": "2026-11-01",
            "bewerbungsfrist": "2026-12-01",
            "url": "https://www.karriere.nrw/stellenangebot",
        },
    ])
    requested = []

    def fake_get_json(url, timeout=20):
        requested.append(url)
        return next(responses)

    monkeypatch.setattr("app.sources.karriere_nrw._get_json", fake_get_json)
    vacancies = search_vacancies(["IT-Administrator"], location="Krefeld", radius_km=50)

    assert len(vacancies) == 1
    vacancy = vacancies[0]
    assert vacancy["id"] == "karriere-nrw:vacancy-123"
    assert vacancy["title"] == "IT-Administrator"
    assert vacancy["company"] == "Land NRW"
    assert vacancy["description"] == "Linux und VMware\n\nTV-L"
    assert vacancy["published_at"] == "2026-11-01"
    assert len(requested) == 2
    assert "ort=Krefeld" in requested[0]
    assert "umkreis=4" in requested[0]
