# Jobradar – zentrale Plattform

Dieses Repository bündelt die bisherigen Jobradar-Bestandteile in einem gemeinsamen Projekt:

- **Home-Assistant-Integration** unter `custom_components/jobradar/` (bisheriges HACS-/Custom-Component-Projekt).
- **Eigenständiger Jobradar-Dienst** unter `jobradar/` (FastAPI, SQLite und Home-Assistant-Add-on).
- **Gemeinsame Qualitätssicherung** über GitHub Actions, Integrationstests und Add-on-Build.
- **Dokumentation und Archiv** unter `docs/` und `archive/`.

## Zielarchitektur

Beide Betriebsarten bleiben während der Konsolidierung zunächst getrennt ausführbar. Die bestehende Home-Assistant-Integration und der neue eigenständige Dienst teilen vorerst noch nicht automatisch ihre Laufzeit oder Datenbank. Gemeinsame Bewertungs- und Suchlogik wird erst nach fachlichem und technischem Abgleich zusammengeführt.

## Projektstruktur

- `custom_components/jobradar/`: bisherige Home-Assistant-Integration.
- `jobradar/app/`: FastAPI-Anwendung und SQLite-Persistenz.
- `jobradar/tests/`: Tests des eigenständigen Dienstes.
- `tests/`: Tests der Home-Assistant-Integration.
- `docs/`: Architektur- und Betriebsdokumentation.
- `archive/`: bisherige Claude-Artifact-Referenzen.

## Entwicklung und Tests

### Eigenständiger Dienst

Im Verzeichnis `jobradar`:

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

### Home-Assistant-Integration

Im Repository-Root:

```bash
python -m pip install -r requirements_test.txt
python tools/check_versions.py
ruff check .
ruff format --check .
pytest -q
```

GitHub Actions prüft die Integration, den eigenständigen Dienst und den ARM64-Add-on-Build.

## Home Assistant Green

Der eigenständige Dienst ist für Home Assistant OS auf ARM64 vorgesehen. Er verwendet FastAPI, SQLite und Home-Assistant-Ingress. Seine Datenbank liegt persistent unter `/data/jobradar.db`.

Die bestehende Integration bleibt bis zur abgeschlossenen Migration verfügbar. Es erfolgt keine automatische Änderung an vorhandenen Home-Assistant-Installationen oder Datenbanken.

## Datenmigration und Sicherheit

- Die bisherige Claude-Artifact-Datenbank bleibt unangetastet, bis Export, Mapping, Trockenlauf und Import geprüft sind.
- Die bestehende Jobradar-Integration wird nicht automatisch deinstalliert oder ersetzt.
- Produktionsdaten, Secrets, Tokens und private Schlüssel gehören nicht ins Repository.
- Test- und Produktionsdatenbanken bleiben getrennt.
- Keine Installation, Aktivierung oder Migration auf dem produktiven Home Assistant ohne ausdrückliche Freigabe.

## Konsolidierungsstatus

Die bisherige Integration wurde in den Konsolidierungszweig übernommen. Noch ausstehend sind die vollständige CI-Prüfung, die Prüfung gemeinsamer Abhängigkeiten und die fachliche Konsolidierung doppelter Bewertungs- und Suchfunktionen.
