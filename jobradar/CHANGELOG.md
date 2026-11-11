# Änderungen der Jobradar-App

## 0.3.0

- **Tägliche Datensicherung.** Beim Start und danach stündlich prüft die App, ob das letzte Backup älter als 24 Stunden ist, und legt dann ein geprüftes Backup unter `/data/backups` an. So entstehen auch dann tägliche Backups, wenn die App wochenlang ohne Neustart läuft. Von den täglichen und manuellen Backups bleiben die 14 neuesten; Backups vor Migrationen werden nie automatisch gelöscht.
- **Backup vor jeder Migration.** Bevor eine bestehende Datenbank auf ein neues Schema gebracht wird, entsteht ein geprüftes Backup. Schlägt es fehl, läuft die Migration nicht.
- **Konsistente Home-Assistant-Backups.** Home Assistant hält die App während einer Sicherung kurz an (`backup: cold`), damit die SQLite-Datei nie mitten in einem Schreibvorgang gesichert wird.
- **Sauberes Anhalten für Cold Backups.** Beim Stoppen beendet die App eine laufende Sicherung und schließt die Datenbank, bevor sie sich beendet. Offene Anfragen bekommen höchstens 5 Sekunden, damit Home Assistant die App nie hart abbrechen muss (Standard-Wartezeit 10 Sekunden). Reste einer abgebrochenen Sicherung (`*.db.partial`) werden beim nächsten Start entfernt.
- **Prüfbarer Backup-/Restore-Test.** `tests/test_cold_backup_cycle.py` startet den Dienst mit dem Befehl aus dem Dockerfile, stoppt ihn wie Home Assistant per SIGTERM, archiviert `/data`, stellt das Archiv in ein leeres `/data` wieder her und vergleicht alle Datensätze. Ein zweiter Test stoppt die App mitten in Schreibzugriffen und prüft, dass jeder bestätigte Datensatz erhalten bleibt.
- Neue Schnittstellen `GET /api/backups` und `POST /api/backups` (räumt danach alte tägliche und manuelle Backups auf), dazu `python -m app.backup` (`create`, `list`, `verify`, `restore-to`).
- Versionsangaben in `config.yaml`, App und CHANGELOG werden per Test abgeglichen; ab 0.3.0 muss `backup: cold` gesetzt sein.
- Wiederherstellen schreibt immer in eine neue Datei; die Live-Datenbank wird nie überschrieben.

## 0.2.0

- Eigenständiger Dienst mit FastAPI, SQLite und Dashboard.
