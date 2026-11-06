# Fachliche Bestandsaufnahme und Migrationskonzept

Stand: 2026-11-06  
Branch: `consolidate-legacy-integration`  
Ziel: die bisherige Claude-Jobradar-Übersicht, die Home-Assistant-Integration und den neuen eigenständigen Dienst kontrolliert zu einer zentralen Jobradar-Anwendung zusammenführen.

## 1. Ergebnis in Kürze

Die Repository-Konsolidierung ist technisch erfolgreich: alle CI-Prüfungen einschließlich ARM64-Add-on-Build sind grün. Das ist noch keine fachliche oder betriebliche Migrationsfreigabe.

**Empfohlene Zielarchitektur:** Der eigenständige FastAPI-Dienst wird langfristig die zentrale Anwendung auf Home Assistant Green. Er erhält eine einzige SQLite-Datenbank, ein responsives Dashboard, Quellenadapter, regelbasierte Bewertung und Benachrichtigungen. Die alte Home-Assistant-Integration und das Claude-Artifact bleiben bis zur Daten- und Funktionsabnahme unverändert verfügbar.

**Wichtige Einschränkung:** Der tatsächliche Live-Datenbestand des Claude-Artifacts und der aktuelle Home-Assistant-Speicher wurden bei dieser Prüfung nicht ausgelesen. Die folgenden Daten-Mappings beruhen auf den versionierten Quelltexten und müssen anhand eines echten Exports validiert werden. Es werden keine Datensatzanzahlen oder Dateninhalte angenommen.

## 2. Bestand und Funktionsumfang

### 2.1 Claude-Artifact

Die versionierte `uebersichtsseite.html` zeigt folgenden Datenvertrag:

| Bereich | Quelle / Feld | Verwendung |
|---|---|---|
| Stellen | Collection `jobs` | Stellenliste |
| Status | `status` | `neu`, `merken`, `beworben`, `absage`, `verworfen` |
| Notiz | `notiz` | Freitextnotiz pro Stelle |
| Bewertung | `punkte` | Score 0–100 |
| Passung | `warum`, `bedenken` | Erläuterung und Gegenargumente |
| Stammdaten | `titel`, `arbeitgeber`, `ort`, `url`, `quelle` | Anzeige und Original-Link |
| weitere Merkmale | `gehalt`, `homeoffice`, `gefunden` | Anzeige und Sortierung |
| Suchläufe | Collection `laeufe` | letzter Lauf über `datum`, `neu`, `quellen`, `hinweis` |
| Profil | Dokument `profil/aktuell` | Suchparameter |

Das Profilformular verwendet die Felder `ort`, `umkreis_km`, `rollen`, `faehigkeiten`, `gehalt_wunsch`, `min_entgeltgruppe`, `wuensche`, `ausschliessen_arbeitgeber` und `homeoffice`.

Die HTML-Datei belegt den verwendeten Datenvertrag, aber nicht den vollständigen Inhalt der gespeicherten Dokumente, frühere Felder, Unterkollektionen oder geplante Claude-Aufgaben. Dafür ist ein Export erforderlich.

### 2.2 Bisherige Home-Assistant-Integration

Die Integration hat eine eigenständige Such- und Bewertungslogik. Sie verwendet unter anderem:

- Jobsuche der Bundesagentur für Arbeit und service.bund.de.
- Suchbegriffe, Fähigkeiten, unerwünschte Begriffe, Ausschlusswörter und ausgeschlossene Arbeitgeber.
- Standort, Umkreis, Homeoffice-Suche und Entfernungsberechnung.
- Gehaltsangaben und TVöD-/TV-L-Entgeltgruppen.
- Ruhezeiten, Benachrichtigungen und Markierung als gelesen.
- Erkennung bereits bekannter Stellen, Dublettenbereinigung und Ablauf-/Online-Prüfung.
- Lernsignal: Arbeitgeber werden nach wiederholtem Ausblenden abgewertet.

Der dauerhafte Zustand wird über Home Assistants `Store` gespeichert. Die gespeicherten Daten umfassen nicht nur Stellen, sondern auch `seen`, `hidden`, `geo`, `held`, `hidden_employers`, `unread`, `initialized` und den Stellenbestand. Dieser Zustand muss bei einer Migration berücksichtigt werden; nur die sichtbare Stellenliste zu kopieren wäre unvollständig.

Die Integration bietet die Statuswerte nicht als Bewerbungsworkflow mit Notizfeld, sondern arbeitet vor allem mit ungelesen/gelesen und ausgeblendet. Diese Zustände dürfen nicht mit den Statuswerten des Claude-Artifacts gleichgesetzt werden.

### 2.3 Eigenständiger FastAPI-Dienst

Der neue Dienst hat bereits:

- SQLite-Schema für `jobs`, `runs`, `profile`, `search_rules`, `job_sources` und `schema_meta`.
- REST-Endpunkte für Stellen, Status/Notizen, Profil, Regeln, Quellen, Suchläufe und Übersicht.
- Ein responsives Dashboard.
- Detaillierte Score-Erklärung und Lernanpassungen.
- Einen Quellenadapter für Karriere.NRW.

**Noch nicht gleichwertig zum Altbestand:**

1. Im Suchlauf ist derzeit nur die Quelle `karriere-nrw` als ausführbarer Adapter freigeschaltet. Andere aktivierte Quellen werden als übersprungen ausgewiesen.
2. Die Adapter der Bundesagentur und von service.bund.de aus der alten Integration sind noch nicht in den eigenständigen Dienst übernommen.
3. In der geprüften Dienstimplementierung ist ein manueller Endpunkt `POST /api/search/run` vorhanden. Ein täglicher Scheduler ist im Add-on-Code und in den Runtime-Abhängigkeiten derzeit nicht nachgewiesen. Die tägliche Suche aus der Architektur-Dokumentation ist daher noch Zielzustand, nicht bestätigte Ist-Funktion.
4. Die Zustände `unread`, `hidden`, Ruhezeit, Arbeitgeber-Abwertung und die Aufbewahrungs-/Online-Prüfung der alten Integration haben noch kein nachgewiesenes vollständiges Gegenstück.
5. Das bestehende Schema speichert einen Score und einen Basis-Score, aber nicht alle ursprünglichen Scoring-Eingaben und nicht zwingend die komplette historische Bewertungsbegründung.

## 3. Bewertungslogik: nicht vereinheitlichen, bevor Parität geprüft ist

### Alte Integration

Die alte Integration startet bei 0 Punkten und bewertet insbesondere:

- passende Rolle: +50;
- Fähigkeit im Titel: +10, im Beschreibungstext: +5, maximal +40;
- unerwünschte Titelbegriffe: −25;
- Remote: +5;
- Entfernung bis 25 km: +5;
- Gehalt passend: +5, nicht passend: −30;
- wiederholt ausgeblendeter Arbeitgeber: −20;
- Ausschlüsse für Arbeitgeber und Ausschlusswörter.

### Eigenständiger Dienst

Der neue Dienst startet bei 40 Punkten und ergänzt:

- Zielpositionen: +12 pro Treffer, maximal +40;
- Kenntnisse: +4 pro Treffer, maximal +24;
- Gehaltsziel: +8 oder −8;
- erkannte Mindest-Entgeltgruppe: +8 oder −8;
- frei konfigurierbare positive/negative Regeln und Ausschlussregeln.

Die Modelle unterscheiden sich bereits beim Grundwert, den Gewichtungen, den Eingabefeldern und den Kriterien. Ein identischer Stellen-Datensatz kann daher einen deutlich anderen Score erhalten. Ein importierter Score darf nicht stillschweigend mit dem neu berechneten Score überschrieben werden.

### Empfehlung

- Das alte Bewertungsverhalten als Referenz `legacy_v1` dokumentieren und mit Regressionstests absichern.
- Das neue Modell als `rules_v1` getrennt halten.
- Für jeden Score `scoring_version`, `base_score`, `learning_adjustment`, Zeitstempel und nachvollziehbare Breakdown-Daten speichern.
- Während einer Shadow-Phase beide Modelle auf denselben Anzeigen rechnen und Abweichungen auswerten, ohne sichtbare Scores automatisch zu verändern.
- Erst nach fachlicher Entscheidung ein Modell als Standard für neue Anzeigen festlegen.
- Vorhandene Scores und Nutzerentscheidungen bleiben als historische Werte erhalten. Ein Re-Scoring erfolgt nur als explizite, protokollierte Aktion.

## 4. Ziel-Datenmodell und Feldzuordnung

Die bestehende SQLite-Struktur kann als Basis dienen, benötigt aber Ergänzungen für verlustarme Migration und nachvollziehbare Bewertungen.

| Quelle | Zielfeld | Regel |
|---|---|---|
| Claude `jobs/{id}` | `jobs.id` / `external_id` | ursprüngliche Dokument-ID erhalten; Quellpräfix ergänzen, falls ID-Kollisionen möglich sind |
| Claude `titel` | `jobs.title` | direkt übernehmen |
| Claude `arbeitgeber` | `jobs.company` | direkt übernehmen |
| Claude `ort` | `jobs.location` | direkt übernehmen |
| Claude `url` | `jobs.url` | Original-Link erhalten |
| Claude `quelle` | `jobs.source` | Originalquelle erhalten |
| Claude `punkte` | `jobs.imported_score` | historischen Score erhalten; nicht als neuer Modell-Score ausgeben |
| Claude `status` | `jobs.status` | Mapping siehe unten |
| Claude `notiz` | `jobs.notes` | direkt übernehmen |
| Claude `gefunden` | `jobs.first_seen_at` | Datum normalisieren; Rohwert zusätzlich sichern |
| Claude `gehalt`, `homeoffice`, `warum`, `bedenken` | strukturierte Felder bzw. `raw_json` | Originalwerte erhalten; Normalisierung erst nach Prüfung |
| Claude `laeufe` | `runs` | Laufdatum, Anzahl, Quellen und Hinweise in passende Felder bzw. Rohdaten übernehmen |
| Claude `profil/aktuell` | `profile.data_json` | Schlüssel kontrolliert auf kanonisches Profil abbilden |

### Status-Mapping

| Claude-Status | Kanonischer Status |
|---|---|
| `neu` | `neu` |
| `merken` | `gemerkt` |
| `beworben` | `beworben` |
| `absage` | `absage` |
| `verworfen` | `verworfen` |

Unbekannte Statuswerte werden nicht verworfen oder automatisch auf `neu` gesetzt. Sie kommen in einen Import-Fehlerbericht und müssen vor Freigabe zugeordnet werden.

### Profil-Mapping

| Claude-Profil | Kanonisches Profil (Vorschlag) |
|---|---|
| `ort` | `location` |
| `umkreis_km` | `radius_km` |
| `rollen` | `roles` |
| `faehigkeiten` | `skills` |
| `gehalt_wunsch` | `salary_min` |
| `min_entgeltgruppe` | `public_service_minimum` |
| `ausschliessen_arbeitgeber` | `exclusions` |
| `homeoffice` | `include_remote` |
| `wuensche` | zunächst `preferences_raw`; erst nach fachlicher Aufteilung in Regeln überführen |

Die Profilwerte der alten Integration (insbesondere Suchbegriffe, unerwünschte Wörter, Ausschlusswörter, Mindestscore, Ruhezeit, Benachrichtigungsdienst und Quellenoptionen) benötigen eigene kanonische Felder. Sie dürfen nicht in einem allgemeinen Freitextfeld verschwinden.

### Zusätzliche Datenbankfelder / Tabellen

Vor einem produktiven Import sollten mindestens geprüft und bei Bedarf ergänzt werden:

- `jobs.external_id`, `jobs.import_source`, `jobs.imported_at`, `jobs.imported_score`, `jobs.scoring_version`, `jobs.score_breakdown_json`, `jobs.raw_import_json`;
- separate Tabelle `job_events` für Statuswechsel, Notizänderungen und Herkunft;
- separate Tabelle `job_seen_state` oder gleichwertige Felder für `seen`, `hidden`, `unread` und Aufbewahrungsfristen;
- Profilfelder für Ruhezeit, Benachrichtigung, Remote, Entfernung, Gehalt und Entgeltgruppe;
- versionierte Bewertungsregeln und eine nachvollziehbare Lernsignal-Historie.

Die Schema-Version muss über echte, vorwärtsgerichtete Migrationen verwaltet werden. Die aktuelle Initialisierung setzt die Schema-Version auf 3; künftige Änderungen dürfen nicht einfach die Versionsnummer überschreiben, ohne ein Upgrade für bestehende Datenbanken auszuführen.

## 5. Quellen- und Automatisierungsparität

Vor dem Wechsel muss eine Quellenmatrix erstellt und für jede Quelle einzeln abgenommen werden:

| Quelle/Funktion | Altbestand | Eigenständiger Dienst | Nächster Schritt |
|---|---|---|---|
| Bundesagentur für Arbeit | vorhanden | kein Adapter nachgewiesen | Adapter portieren und testen |
| service.bund.de | vorhanden | kein Adapter nachgewiesen | Adapter portieren und testen |
| Karriere.NRW | nicht als eigener Adapter in der alten Integration nachgewiesen | Adapter vorhanden | testen und fachlich bewerten |
| tägliche Suche | Claude-Bericht / HA-Intervall | Scheduler nicht nachgewiesen | lokalen Scheduler mit Locking und Fehlerstatus implementieren |
| Push/HA-Benachrichtigung | vorhanden | nicht vollständig nachgewiesen | Benachrichtigungskonzept umsetzen |
| Ablauf-/Online-Prüfung | vorhanden | nicht nachgewiesen | definierte Aufbewahrungs- und Prüflogik übernehmen |
| Lernsignal Arbeitgeber | vorhanden | Teilfunktion im Dienst | Historie und Verhalten abgleichen |

Quellen gelten erst als migriert, wenn Suchparameter, Trefferumfang, Fehlerbehandlung, Dublettenerkennung, Rate-Limits und rechtlich/technische Nutzungsbedingungen geprüft sind.

## 6. Migrationsablauf ohne Datenverlust

### Phase A – Datensicherung und Export

1. Claude-Artifact-Datenbank vollständig exportieren: alle Dokumente aus `jobs`, `laeufe`, `profil/aktuell` und ggf. weiteren vorhandenen Collections.
2. Home-Assistant-Integration sichern: Config-Entry (Daten und Optionen) sowie den vollständigen persistenten Store der Integration.
3. Aktuelle produktive Jobradar-Add-on-Datenbank sichern, sofern vorhanden; nur lesend inventarisieren.
4. Exporte mit Zeitstempel, SHA-256-Prüfsumme und Datensatzanzahl ablegen.
5. Exporte lokal und geschützt halten; keine privaten Stellen- oder Profildaten in GitHub einchecken.

**Abbruchbedingung:** Fehlt ein Export, ist unvollständig oder lässt sich die Herkunft nicht nachvollziehen, wird nicht importiert.

### Phase B – Mapping und Trockenlauf

1. Exporte nur in eine separate Testumgebung einlesen.
2. Rohdaten unverändert in einem Import-Staging-Bereich sichern.
3. Feld- und Status-Mapping anwenden.
4. Dubletten über Quell-ID, URL und normalisierte Kombination aus Arbeitgeber/Titel/Ort erkennen. Unsichere Treffer nur als Kandidaten markieren, nicht automatisch zusammenführen.
5. Fehlende Pflichtfelder, unbekannte Statuswerte, ungültige URLs und Datumsformate in einen Bericht schreiben.
6. Importbericht mit Quellanzahl, übernommenen Datensätzen, Dubletten, Konflikten und nicht zugeordneten Feldern erstellen.

### Phase C – Fachliche und technische Abnahme

Die Testmigration ist nur erfolgreich, wenn:

- Anzahl der exportierten und importierten Stellen je Quelle erklärbar übereinstimmt;
- alle Statuswerte und Notizen erhalten sind;
- Profilwerte vollständig und semantisch korrekt übernommen wurden;
- Laufhistorie und Zeitstempel nachvollziehbar sind;
- Scores als historische Werte erhalten bleiben;
- keine Nutzerentscheidung durch Dublettenbereinigung verloren geht;
- Suchquellen und Automatisierung ausreichend Parität besitzen;
- Backup und Wiederherstellung praktisch getestet wurden.

### Phase D – Parallelbetrieb

1. Neue Anwendung ausschließlich in Testumgebung betreiben.
2. Suchläufe parallel ausführen, zunächst ohne produktive Benachrichtigungen.
3. Trefferzahlen, Quellenfehler, Dubletten und Score-Abweichungen vergleichen.
4. Korrekturen durchführen, bis die Abweichungen verstanden und akzeptiert sind.
5. Produktivwechsel nur nach ausdrücklicher Freigabe.

### Phase E – Umschaltung und Rückfall

1. Letzten vollständigen Export unmittelbar vor Umschaltung erstellen.
2. Import wiederholen und Prüfsummen/Anzahlen vergleichen.
3. Neuen Dienst aktivieren und einen kontrollierten Suchlauf durchführen.
4. Alte Integration und Claude-Daten zunächst nur deaktivieren bzw. im Nur-Lese-Modus belassen – nicht löschen.
5. Rückfallplan: neue Anwendung stoppen, gesicherte alte Konfiguration/Daten weiterverwenden und alte Integration wieder aktivieren.
6. Erst nach einer vereinbarten stabilen Betriebsphase über Archivierung entscheiden.

## 7. Freigabekriterien vor Produktivmigration

- [ ] Claude-Artifact-Export vollständig und geprüft.
- [ ] HA-Config-Entry und vollständiger Integration-Store gesichert.
- [ ] Produktive Add-on-Datenbank inventarisiert und gesichert.
- [ ] Kanonisches Datenmodell und Status-Mapping abgenommen.
- [ ] Scoring-Referenzmodell und Versionierung beschlossen.
- [ ] Bundesagentur- und Bund.de-Adapter portiert oder bewusste Quellenentscheidung getroffen.
- [ ] Täglicher Scheduler, Benachrichtigungen und Fehlerüberwachung implementiert.
- [ ] Dry-Run ohne Datenverlust abgeschlossen.
- [ ] Parallelbetrieb und Backup-Wiederherstellung erfolgreich.
- [ ] Explizite Freigabe des Benutzers für Produktivumschaltung erteilt.

## 8. Konkrete nächste Schritte

1. **Zuerst Exporte beschaffen**, nicht die Datenbank oder den produktiven Add-on-Stand verändern.
2. Exportformat für Claude-Artifact und Home Assistant festlegen und die tatsächlichen Feldlisten auslesen.
3. Kanonisches Schema und Importer mit Dry-Run-Modus implementieren.
4. Scoring-Paritätstests auf einem anonymisierten Satz repräsentativer Stellen erstellen.
5. Quellen- und Scheduler-Lücken schließen.
6. Erst danach eine separate Testmigration durchführen.

## 9. Was diese Prüfung nicht bestätigt

- Keine tatsächliche Anzahl oder Vollständigkeit der Live-Claude-Dokumente.
- Keine tatsächliche Anzahl oder Vollständigkeit der Home-Assistant-Store-Datensätze.
- Keine Übereinstimmung der heutigen Scores beider Modelle.
- Keine vollständige Quellenparität des eigenständigen Dienstes.
- Keine produktive Einsatzbereitschaft oder Freigabe zur Installation.

Diese Punkte benötigen echte Exporte und einen kontrollierten Testlauf.
