# Architektur – Jobradar

## Zielbild

Der eigenständige Jobradar auf Home Assistant Green wird die zentrale Anwendung. Er übernimmt die bewährten Funktionen des bisherigen Jobradars und läuft vollständig lokal. Die Oberfläche wird modernisiert und für Desktop sowie Smartphone optimiert.

## Leitprinzipien

- Eine Anwendung, eine zentrale SQLite-Datenbank und ein einheitliches Dashboard.
- Regelbasierte Suche, Normalisierung, Dublettenerkennung und Bewertung; reproduzierbar und testbar.
- Bestehende Daten werden erst nach geprüftem Export, Mapping und erfolgreichem Import übernommen.
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

1. Funktionen, Datenfelder, Quellen und Regeln des bisherigen Jobradars dokumentieren.
2. API und Datenmodell vervollständigen.
3. Dashboard modernisieren und an die API anbinden.
4. Quellenadapter und regelbasierte Bewertung implementieren.
5. Export des bisherigen Datenbestands erstellen und in einer Testkopie importieren.
6. Datensatzanzahl, Status, Notizen, Scores und Lernregeln vergleichen.
7. Erst nach erfolgreicher Abnahme den neuen Jobradar als alleinige tägliche Lösung verwenden.

## Persistenz und Betrieb

Die Datenbank liegt unter `/data/jobradar.db`. Der dauerhafte Speicherbereich des Add-ons wird für Daten und Backups genutzt. Der Add-on-Port 8099 wird nicht öffentlich am Router freigegeben.

### Backup und Wiederherstellung

- **Täglich:** Beim Start und danach stündlich (`JOBRADAR_BACKUP_CHECK_SECONDS`, Standard 3600) prüft die App, ob das letzte Backup älter als 24 Stunden ist, und legt dann `/data/backups/jobradar-<Zeitstempel>-daily.db` an. Von den täglichen und manuellen Backups bleiben die 14 neuesten; Backups vor Migrationen und mit anderem Anlass werden nie automatisch gelöscht.
- **Vor Migrationen:** Vor jeder Schemaänderung entsteht `…-pre-migration-vX-to-vY.db`. Schlägt das Backup fehl, bricht der Start ab und die Datenbank bleibt unverändert.
- **Verfahren:** SQLite-Online-Backup (konsistent auch während Schreibzugriffen), danach `PRAGMA integrity_check`; nur geprüfte Dateien gelten als Backup. Rechte `0600`.
- **Home-Assistant-Backups:** `backup: cold` (ab 0.3.0, per Test erzwungen) – Home Assistant stoppt die App per SIGTERM, sichert `/data` und startet sie wieder. Die Dateien unter `/data/backups` sind in jedem HA-Backup enthalten.
- **Anhalten für das Cold Backup:** uvicorn läuft als PID 1 (Exec-Form im Dockerfile) und bekommt das SIGTERM direkt. Offene Anfragen bekommen höchstens 5 Sekunden (`--timeout-graceful-shutdown 5`), danach endet die App sauber: Eine laufende Sicherung wird fertig geschrieben, es bleibt keine offene Verbindung und kein Journal liegen. Der Supervisor wartet standardmäßig 10 Sekunden, bevor er hart abbricht. uvicorn beendet sich nach dem sauberen Herunterfahren mit dem Signal selbst (Docker zeigt Exit-Code 143); das ist erwartet. Reste einer abgebrochenen Sicherung (`*.db.partial`) entfernt der nächste Start.
- **Manuell:** `POST /api/backups` oder im Container `python -m app.backup create --reason vor-update`.

Wiederherstellen (nur nach Freigabe, die Live-Datenbank wird nie direkt überschrieben):

1. `python -m app.backup list` und `python -m app.backup verify /data/backups/<Datei>` – Zeilenzahlen prüfen.
2. `python -m app.backup restore-to /data/backups/<Datei> /data/jobradar.restored.db` – schreibt in eine neue Datei und prüft sie.
3. App stoppen, `/data/jobradar.db` in `/data/jobradar.before-restore.db` umbenennen, `/data/jobradar.restored.db` in `/data/jobradar.db` umbenennen, App starten.
4. Die alte Datei erst löschen, wenn die wiederhergestellten Daten geprüft sind.

Wiederherstellen aus einem Home-Assistant-Backup: in Home Assistant unter Einstellungen → System → Backups das Backup öffnen und nur die Jobradar-App wiederherstellen. Home Assistant ersetzt dabei `/data` vollständig, auch neuere Daten. Deshalb vorher ein aktuelles Backup anlegen.

Automatisierte Tests:

- `jobradar/tests/test_backup.py`: Backup, Prüfung, Aufräumen (Backups vor Migrationen bleiben), stündliche Prüfung, Abschluss einer laufenden Sicherung beim Stoppen, Entfernen von `*.partial`, Wiederherstellung in eine neue Datei, Backup vor Migrationen und Abbruch bei fehlgeschlagenem Backup.
- `jobradar/tests/test_cold_backup_cycle.py`: echter Dienst mit dem Startbefehl aus dem Dockerfile; Stopp per SIGTERM innerhalb von 10 Sekunden, saubere Datenbank in `/data`, Archiv wie ein HA-Backup, Wiederherstellung in ein leeres `/data` und mit `restore-to`, Vergleich aller Jobs, Notizen, Status, Profil, Regeln und Quellen. Ein zweiter Test stoppt mitten in Schreibzugriffen: Jeder bestätigte Datensatz muss danach vorhanden sein.
- `jobradar/tests/test_release_metadata.py`: Version in `config.yaml`, App und CHANGELOG stimmen überein; ab 0.3.0 ist `backup: cold` gesetzt.

Selbst prüfen: `cd jobradar && pytest -q tests/test_cold_backup_cycle.py -v`.

## Umsetzungsphasen

- **Phase 1 – Fundament:** Add-on, Health-API, SQLite, Schema- und Persistenztests.
- **Phase 2 – Datenmodell und API:** Jobs, Profile, Regeln, Status, Notizen und Suchläufe.
- **Phase 3 – Dashboard:** modernes responsives Dashboard mit vollständigem Workflow.
- **Phase 4 – Suchmaschine:** Quellenadapter, Normalisierung, Dubletten und regelbasierte Bewertung.
- **Phase 5 – Migration:** kontrollierter Import der bisherigen Jobradar-Daten.
- **Phase 6 – Automatisierung:** Zeitplanung, Push-Nachrichten und Wochenpflege.
- **Phase 7 – Bewerbungsworkflow:** optionale Anbindung des bestehenden Bewerbungs-Assistenten.

Jede Phase erhält automatisierte Tests und wird erst danach auf Home Assistant aktualisiert.

## Suchlauf, Zeitplan und Benachrichtigung (ab 0.5.0)

- **Quellen mit Adapter:** `arbeitsagentur` (Jobsuche der Bundesagentur für Arbeit) und `karriere-nrw`. Eine Quelle wird abgefragt, wenn sie aktiv ist, den Typ „API“ hat und ihre ID einen Adapter besitzt; alle anderen aktiven Quellen nennt der Lauf als „noch nicht angebunden“.
- **Einstellungen je Quelle** (`config`): `days` (Alter der Anzeigen in Tagen, Standard 7), `min_score` (neue Stellen darunter werden nicht aufgenommen), `max_details` (Detailabrufe je Lauf, Standard 40), `limit`, `include_remote`, `exclude_temp_agencies`, `location`, `radius_km`. Ohne eigene Suchbegriffe gelten die Zielpositionen aus dem Suchprofil.
- **Arbeitsagentur:** je Suchbegriff eine Abfrage im Umkreis und, bei „bundesweite Remote-Stellen“, eine bundesweite Abfrage nach Stellen mit Homeoffice. Zwischen den Abfragen liegt eine kurze Pause. Details werden nur für Stellen geladen, die noch nicht gespeichert sind.
- **Dubletten:** Gleiche Kennung oder gleiche Adresse der Anzeige gilt als dieselbe Stelle. Übernommene Stellen aus dem bisherigen Jobradar behalten Status, Notiz und Punkte.
- **Zeitplan:** Die App prüft jede Minute, ob der tägliche Lauf fällig ist (Option `search_time`, Zeitzone von Home Assistant). Der Tag wird vor dem Start vermerkt: Ein fehlgeschlagener oder unterbrochener Lauf wird nicht minütlich wiederholt, der nächste Versuch ist am Folgetag. Ohne `/data/options.json` (lokale Entwicklung, Tests) gibt es keinen Zeitplan.
- **Benachrichtigung:** Nach dem täglichen Lauf geht eine Meldung an den Dienst aus `notify_service`, wenn neue Stellen mindestens `notify_min_score` Punkte haben, oder wenn der Lauf fehlgeschlagen ist. Manuelle Läufe über das Dashboard melden nichts.
- **Gleichzeitigkeit:** Es läuft nur ein Suchlauf; ein zweiter Start wird mit 409 abgelehnt.
