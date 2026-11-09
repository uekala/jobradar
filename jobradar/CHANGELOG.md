# Änderungen der Jobradar-App

## 0.3.0

- **Tägliche Datensicherung.** Beim Start legt die App ein geprüftes Backup der Datenbank unter `/data/backups` an, wenn das letzte älter als 24 Stunden ist. Die 14 neuesten bleiben erhalten.
- **Backup vor jeder Migration.** Bevor eine bestehende Datenbank auf ein neues Schema gebracht wird, entsteht ein geprüftes Backup. Schlägt es fehl, läuft die Migration nicht.
- **Konsistente Home-Assistant-Backups.** Home Assistant hält die App während einer Sicherung kurz an (`backup: cold`), damit die SQLite-Datei nie mitten in einem Schreibvorgang gesichert wird.
- Neue Schnittstellen `GET /api/backups` und `POST /api/backups`, dazu `python -m app.backup` (`create`, `list`, `verify`, `restore-to`).
- Wiederherstellen schreibt immer in eine neue Datei; die Live-Datenbank wird nie überschrieben.

## 0.2.0

- Eigenständiger Dienst mit FastAPI, SQLite und Dashboard.
