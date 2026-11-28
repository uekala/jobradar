# Änderungen der Jobradar-App

## 0.8.0

- **Bewerbungen.** Neue Ansicht mit drei Spalten Gemerkt, Beworben und Absage, jeweils mit Datum. Bewerbungen ohne Antwort seit 14 Tagen sind markiert.
- **Schnellknöpfe.** An jeder Stelle stehen die nächsten Schritte („Merken“, „Beworben“, „Verwerfen“ …). Sie wirken sofort, eine Meldung bietet „Rückgängig“.
- **Statusverlauf.** Jeder Statuswechsel wird mit Datum festgehalten und im Stellenfenster angezeigt.
- **Sortierung.** Beste Treffer, Neueste, Zuletzt gesehen oder Ort A–Z; die Wahl bleibt gespeichert.
- **Einrichtung.** Suchquellen, Suchprofil, Bewertungsregeln und Datenübernahme liegen jetzt in einem eigenen Reiter statt in der Seitenleiste.

## 0.7.1

- **Bedienung.** Fenster schließen mit Escape und Klick daneben, der Fokus springt ins erste Eingabefeld und danach zurück. Stellenkarten lassen sich mit Tab und Enter öffnen.
- Meldungen erscheinen unten als kurze Einblendung statt als Browser-Hinweis, Fehler rot.
- Der Status oben zeigt „Keine Verbindung“ oder „Letzter Suchlauf fehlgeschlagen“ statt immer „System bereit“; die Begrüßung folgt der Tageszeit.
- Leere Liste: Hinweis auf Quelle und Suchlauf, bei aktiven Filtern „Filter zurücksetzen“. Ladefehler mit „Erneut versuchen“.
- „… hinzufügen“ verschwindet, sobald die Quelle eingerichtet ist. Der überholte Hinweis „Score-Berechnung folgt separat“ ist weg.

## 0.7.0

- **service.bund.de als Quelle.** Stellen von Bund, Ländern und Kommunen aus dem RSS-Feed von service.bund.de, wie in der bisherigen Home-Assistant-Integration. Eine Abfrage je Suchbegriff mit 30 Sekunden Pause; einrichten über „service.bund.de hinzufügen“. Die Seite schließt ihren Suchpfad in der robots.txt für automatische Abrufe aus, deshalb fragt Jobradar vor dem Einrichten nach.
- **Einrichtungsdatei.** Liegt beim Start `data/einrichtung.json` vor, übernimmt Jobradar daraus Suchprofil, Quellen und Bewertungsregeln einmal und benennt die Datei danach um. Anleitung unter `deploy/standalone`.
- **Regeln nur im Titel.** Bewertungsregeln können nur den Titel durchsuchen („Nur im Titel suchen“). So werten Begriffe wie „Junior“ oder „Praktikum“ keine passende Stelle ab, nur weil sie in der Beschreibung vorkommen.

## 0.6.0

- **Eigenständiger Betrieb.** Jobradar läuft auch ohne Home Assistant OS als gewöhnlicher Docker-Container, zum Beispiel auf Unraid. Fertiges Image für amd64 und arm64 unter `ghcr.io/uekala/jobradar`, Anleitung unter `deploy/standalone`.
- **Eigene Anmeldung.** Mit `JOBRADAR_WEB_PASSWORD` fragen Oberfläche und API nach Benutzername und Passwort. Nach fünf falschen Anmeldungen ist die Adresse fünf Minuten gesperrt, und schreibende Anfragen von fremden Seiten werden abgelehnt. Als Home-Assistant-App meldet weiterhin Home Assistant an.
- **Meldungen ohne Supervisor.** Im eigenständigen Betrieb gehen die Benachrichtigungen über `HA_URL` und `HA_TOKEN` an Home Assistant.
- Uhrzeit, Benachrichtigungsdienst und Mindestpunktzahl lassen sich auch als Umgebungsvariablen setzen (`JOBRADAR_SEARCH_TIME`, `JOBRADAR_NOTIFY_SERVICE`, `JOBRADAR_NOTIFY_MIN_SCORE`).

## 0.5.1

- **Korrektur:** Die Seitenleiste des Dashboards war breiter als vorgesehen und lief über den rechten Rand; auf dem Handy war die Seite seitlich verschiebbar und die Punkte der Stellen abgeschnitten. Kopfzeilen mit mehreren Knöpfen brechen jetzt um.
- Der letzte Suchlauf zeigt seinen Status auf Deutsch („Erfolgreich“ statt „success“).

## 0.5.0

- **Arbeitsagentur als Quelle.** Jobradar sucht jetzt direkt in der Jobbörse der Bundesagentur für Arbeit: im Umkreis und, wenn im Suchprofil gewählt, bundesweit nach Stellen mit Homeoffice. Gehalt, Homeoffice und die Beschreibung kommen aus der Anzeige. Einrichten über „Arbeitsagentur hinzufügen“ im Dashboard.
- **Täglicher Suchlauf.** Die App sucht einmal am Tag von selbst, ab der Uhrzeit aus der Konfiguration (Standard 06:30 Uhr). War die App zu dieser Zeit aus, holt sie den Lauf am selben Tag nach.
- **Meldung neuer Stellen.** Nach dem täglichen Lauf meldet Jobradar neue Stellen ab einer einstellbaren Punktzahl über einen Benachrichtigungsdienst von Home Assistant, mit den drei besten Treffern. Ein fehlgeschlagener Lauf wird ebenfalls gemeldet. Dafür braucht die App Zugriff auf die Home-Assistant-Schnittstelle.
- Dieselbe Anzeige wird nicht doppelt angelegt, auch wenn sie aus dem bisherigen Jobradar unter einer anderen Kennung übernommen wurde. Status, Notiz und Punkte übernommener Stellen bleiben bei einem Suchlauf unverändert.
- Quellen können eine Mindestpunktzahl haben (`min_score`); neue Stellen darunter werden nicht aufgenommen.
- Es läuft immer nur ein Suchlauf gleichzeitig.
- **Korrektur:** Beim Bearbeiten einer Quelle im Dashboard gingen ihre Einstellungen verloren.
- Die Datenübernahme nimmt den Export auch als eingefügten Text an. Die bisherige Übersichtsseite hat dafür die Schaltfläche „Export kopieren“.
- Neue Schnittstelle `GET /api/schedule`.

## 0.4.0

- **Datenübernahme.** Im Dashboard unter „Datenübernahme“ lässt sich der Export des bisherigen Jobradars einlesen. Zuerst läuft immer ein Probelauf mit Bericht; übernommen wird erst nach Bestätigung und nur, wenn der Probelauf fehlerfrei ist.
- Übernommene Stellen behalten ihre ID, ihren Status, ihre Notiz und ihre Punkte. Die Detailansicht zeigt dazu die bisherige Einschätzung („Passt, weil“, „Aber“, Gehalt).
- Jedes Dokument des Exports wird zusätzlich unverändert archiviert. Ein zweiter Import derselben Datei ändert nichts.
- Neue Schnittstellen `POST /api/import` und `GET /api/imports`. Beschreibung in `docs/import.md`.
- **Korrektur:** Das Dashboard lud keine Daten und reagierte auf keine Schaltfläche, weil ein Zeichenfehler das ganze Skript ungültig machte.
- **Korrektur:** Pausierte Bewertungsregeln wurden trotzdem angewendet.
- Datenbankschema 4. Vor der Umstellung entsteht automatisch ein geprüftes Backup.

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
