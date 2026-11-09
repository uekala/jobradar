# Architektur – Jobradar

## Zielbild

Der eigenständige Jobradar auf Home Assistant Green wird die zentrale Anwendung. Er übernimmt die bewährten Funktionen des bisherigen Claude-Jobradars, läuft im Alltag aber ohne Claude und ohne andere KI. Die Oberfläche wird modernisiert und für Desktop sowie Smartphone optimiert.

Claude bleibt optionaler Helfer für Analyse, Weiterentwicklung und Bewerbungsunterlagen. Es ist keine Laufzeitabhängigkeit.

## Leitprinzipien

- Eine Anwendung, eine zentrale SQLite-Datenbank und ein einheitliches Dashboard.
- Regelbasierte Suche, Normalisierung, Dublettenerkennung und Bewertung; reproduzierbar und testbar.
- Bestehende Daten werden erst nach geprüftem Export, Mapping und erfolgreichem Import übernommen.
- Bestehende Claude-Artifact-Daten und der Bewerbungs-Assistent bleiben bis zur bestätigten Migration unangetastet.
- Keine öffentlichen Router-Ports und kein zusätzlicher Cloud-Tunnel. Zugriff über Home Assistant Ingress im Heimnetz und über das vorhandene VPN unterwegs.
- Änderungen werden in kleinen, getesteten Schritten auf dem Branch `ha-green-foundation` entwickelt.

## Komponenten

| Komponente | Umsetzung | Verantwortung |
|---|---|---|
| Laufzeit | Home Assistant OS Add-on, ARM64 | Dauerbetrieb auf Home Assistant Green |
| Backend | Python + FastAPI | API, Geschäftslogik und Validierung |
| Datenbank | SQLite unter `/data/jobradar.db` | Stellen, Suchläufe, Profil, Regeln und Historie |
| Suche | Python-Quellenadapter | Stellenquellen unabhängig von KI abrufen |
| Bewertung | deterministische Regeln | Score, Filter, Ausschlüsse und Lernsignale |
| Zeitplanung | Scheduler im Add-on | tägliche Suche und wöchentliche Wartung |
| Oberfläche | responsives Web-Dashboard | Desktop und Smartphone, eingebettet über Ingress |
| Benachrichtigungen | Home Assistant | tägliche Zusammenfassung und wichtige Hinweise |
| Quellcode | privates GitHub-Repository | Versionierung, Tests und reproduzierbare Builds |

## Dashboard – Gestaltungsrichtung

Die bisherige Funktionalität bleibt erhalten, die Darstellung wird aber neu gestaltet:

- klare Startseite mit letzter Suche, nächstem Lauf und Kennzahlen;
- Stellenliste mit Suche, Filtern, Sortierung und gut sichtbarem Score;
- kompakte, mobil nutzbare Detailansicht mit Quelle, Gehalt, Ort, Remote-Angabe und Original-Link;
- Statusworkflow: Neu, Gemerkt, Beworben, Absage und Verworfen;
- Notizen und nachvollziehbare Rückmeldungen zur Verbesserung der Bewertung;
- eigene Ansichten für Suchprofil, Quellen, Suchläufe und Lernregeln;
- barrierearme Kontraste, gut bedienbare Touch-Flächen und ruhiges, modernes Layout.

Die Oberfläche greift ausschließlich über die versionierte REST-API auf Daten zu. Keine direkte Datenbankverbindung aus dem Browser.

## Suchprofil und Bewertungsmodell

Das vorhandene Profil wird als Ausgangspunkt übernommen: Krefeld plus 50 km sowie bundesweite Homeoffice-Stellen; Rollen aus Systemadministration, IT-Infrastruktur, Virtualisierung, Cloud und Platform Engineering. Gehaltsziel und Mindest-Entgeltgruppe sowie Ausschlussregeln werden als konfigurierbare Profildaten behandelt, nicht fest in den Code eingebaut.

Treffer ab 55 Punkten werden zunächst als relevant markiert. Die Bewertung soll transparent erklären, welche Kriterien Punkte geben oder abziehen. Rückmeldungen wie „Gemerkt“ und „Verworfen“ können später in versionierte Lernregeln einfließen; sie verändern nicht unbemerkt die Grundregeln.

## Datenmodell

- `jobs`: Stellenanzeige, Quelle, URL, Score, Status, Notiz und Zeitstempel.
- `runs`: Beginn, Ende, Ergebnis, Trefferzahlen und Fehler.
- `profile`: Suchprofil als JSON.
- `search_rules`: versionierte Bewertungs- und Filterregeln.
- `schema_meta`: Schema-Version für Migrationen.

Das bestehende Schema ist ein Startpunkt. Vor dem Import werden Felder, Statuswerte, Lernregeln und Beziehungen mit dem tatsächlichen Export des bisherigen Jobradars abgeglichen. Der Import wird zunächst als Vorschau mit Duplikatbericht ausgeführt.

## Datenfluss

1. Scheduler startet einen Suchlauf.
2. Quellenadapter laden Anzeigen und Metadaten.
3. Normalisierung und Dublettenerkennung vereinheitlichen Treffer.
4. Regelbasierte Bewertung berechnet Score und Begründung.
5. Neue und aktualisierte Stellen werden transaktional gespeichert.
6. Dashboard und Benachrichtigungen lesen dieselbe Datenbasis.
7. Nutzerfeedback wird als nachvollziehbare Statusänderung gespeichert.

## Migrationsstrategie

1. Funktionen, Datenfelder, Quellen und Regeln des Claude-Jobradars dokumentieren.
2. API und Datenmodell vervollständigen.
3. Dashboard modernisieren und an die API anbinden.
4. Quellenadapter und Bewertung unabhängig von Claude implementieren.
5. Export des bisherigen Artifact-Datenbestands erstellen und in einer Testkopie importieren.
6. Datensatzanzahl, Status, Notizen, Scores und Lernregeln vergleichen.
7. Erst nach erfolgreicher Abnahme den neuen Jobradar als alleinige tägliche Lösung verwenden.

Die bisherige Artifact-Datenbank wird während der Entwicklung weder überschrieben noch gelöscht.

## Persistenz und Betrieb

Die Datenbank liegt unter `/data/jobradar.db`. Der dauerhafte Speicherbereich des Add-ons wird für Daten und Backups genutzt. Der Add-on-Port 8099 wird nicht öffentlich am Router freigegeben.

### Backup und Wiederherstellung

- **Täglich:** Beim Start entsteht ein Backup unter `/data/backups/jobradar-<Zeitstempel>-daily.db`, wenn das letzte älter als 24 Stunden ist. Die 14 neuesten bleiben erhalten.
- **Vor Migrationen:** Vor jeder Schemaänderung entsteht `…-pre-migration-vX-to-vY.db`. Schlägt das Backup fehl, bricht der Start ab und die Datenbank bleibt unverändert.
- **Verfahren:** SQLite-Online-Backup (konsistent auch während Schreibzugriffen), danach `PRAGMA integrity_check`; nur geprüfte Dateien gelten als Backup. Rechte `0600`.
- **Home-Assistant-Backups:** `backup: cold` – Home Assistant hält die App während der Sicherung an. Die Dateien unter `/data/backups` sind in jedem HA-Backup enthalten.
- **Manuell:** `POST /api/backups` oder im Container `python -m app.backup create --reason vor-update`.

Wiederherstellen (nur nach Freigabe, die Live-Datenbank wird nie direkt überschrieben):

1. `python -m app.backup list` und `python -m app.backup verify /data/backups/<Datei>` – Zeilenzahlen prüfen.
2. `python -m app.backup restore-to /data/backups/<Datei> /data/jobradar.restored.db` – schreibt in eine neue Datei und prüft sie.
3. App stoppen, `/data/jobradar.db` in `/data/jobradar.before-restore.db` umbenennen, `/data/jobradar.restored.db` in `/data/jobradar.db` umbenennen, App starten.
4. Die alte Datei erst löschen, wenn die wiederhergestellten Daten geprüft sind.

Automatisierte Tests decken Backup, Prüfung, Aufräumen, Wiederherstellung in eine neue Datei, das Backup vor Migrationen und den Abbruch bei fehlgeschlagenem Backup ab (`jobradar/tests/test_backup.py`).

## Umsetzungsphasen

- **Phase 1 – Fundament:** Add-on, Health-API, SQLite, Schema- und Persistenztests.
- **Phase 2 – Datenmodell und API:** Jobs, Profile, Regeln, Status, Notizen und Suchläufe.
- **Phase 3 – Dashboard:** modernes responsives Dashboard mit vollständigem Workflow.
- **Phase 4 – Suchmaschine:** Quellenadapter, Normalisierung, Dubletten und regelbasierte Bewertung.
- **Phase 5 – Migration:** kontrollierter Import der bisherigen Jobradar-Daten.
- **Phase 6 – Automatisierung:** Zeitplanung, Push-Nachrichten und Wochenpflege.
- **Phase 7 – Bewerbungsworkflow:** optionale Anbindung des bestehenden Bewerbungs-Assistenten.

Jede Phase erhält automatisierte Tests und wird erst danach auf Home Assistant aktualisiert.
