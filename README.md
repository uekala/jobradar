# Claude Jobradar – Übersichtsseite

Eigenständiges Quellcode-Projekt für die Claude-Artifact-Übersichtsseite des Jobradars.

> Dieses Repository enthält **nicht** die frühere Home-Assistant-Integration. Es enthält auch keine Stellen-Datenbank, Zugangsdaten oder persönlichen Bewerbungsunterlagen. Die Daten bleiben in der Claude-Artifact-Datenbank.

## Inhalt

- `index.html` – verbesserte Übersichtsseite (Ausgangsbasis: vom Nutzer bereitgestellte `Uebersichtsseite.html`)
- `archive/Uebersichtsseite-v1.html` – unveränderte Sicherung der bereitgestellten Ausgangsversion
- `tests/smoke_test.py` – lokaler Browser-Smoke-Test mit simulierter Claude-Datenbank
- Die Desktop- und Mobile-Vorschauen werden separat mit dem Projektpaket bereitgestellt.
- `requirements-dev.txt` – Testabhängigkeit
- `CHANGELOG.md` – Änderungen gegenüber der Ausgangsversion

## Was die Version verbessert

- Fehler im zweispaltigen Stellenkarten-Layout behoben: Punktzahl und vollständiger Karteninhalt liegen in getrennten Bereichen.
- Initialisierung von `claude.use("db")` gegen fehlendes `claude`-Objekt und Initialisierungsfehler abgesichert.
- Datenbank-Schreibvorgänge für Status, Notizen und Suchprofil zeigen verständliche Speicherzustände und Fehler.
- Notizfelder besitzen stellenbezogene zugängliche Beschriftungen und Statusmeldungen.
- Statusaktionen erhalten sprechende ARIA-Beschriftungen.
- Kontrast des aktiven Status „Verworfen“ im hellen Farbschema verbessert.
- Die vorhandenen Sammlungen, Feldnamen, Statuswerte und Datenbankpfade bleiben unverändert.

## Lokal öffnen

Die HTML-Datei kann lokal geöffnet werden. Ohne angemeldete Claude-Artifact-Umgebung werden keine Stellen geladen; stattdessen erscheint ein Hinweis. Das ist erwartetes Verhalten, denn `claude.use("db")` ist nur im angemeldeten Claude-Artifact verfügbar.

## Browser-Smoke-Test

Voraussetzung: Python 3.10+ und Chromium.

```bash
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python tests/smoke_test.py
```

Der Test stellt eine kleine simulierte Datenbank bereit und prüft Laden, Filter, Statusänderung, Notizspeicherung, Profiländerung, Mobil-Layout und den lokalen Modus ohne Claude.

## In ein neues GitHub-Repository übernehmen

Empfohlener Repository-Name: `claude-jobradar`.

Da das Projekt persönliche Karriere- und Suchprofil-Kontexte betrifft, sollte das Repository **privat** angelegt werden. Nur Quellcode und Tests gehören hinein – keine Exporte aus der Artifact-Datenbank.

Die aktive Entwicklungsfassung liegt im Branch `dashboard-v2`. Der bestehende `main`-Branch wird nicht verändert.

## Veröffentlichung in Claude

`index.html` ist der Quelltext für das vorhandene Artifact. Vor einer Veröffentlichung muss die Version im Claude-Artifact-Kontext mit dessen Datenbank-API getestet werden. Diese lokale Version veröffentlicht sich nicht selbst und enthält absichtlich keine Datenbank-Credentials.