# Datenübernahme aus dem bisherigen Jobradar

Ab Version 0.4.0 liest die App einen Datenexport des bisherigen Jobradars ein (Format `jobradar-datenexport`, Formatversion 1). Der Export ist eine JSON-Datei mit den Sammlungen `jobs`, `laeufe`, `profil`, `regeln` und `pflege`; jedes Dokument trägt seine ursprüngliche ID, `version`, `updatedAt` und die unveränderten Felder unter `data`.

Exportdateien enthalten persönliche Angaben (Gehaltsvorstellung, Ausschlüsse, Notizen). Sie gehören nicht in dieses Repository. Die Tests verwenden ausschließlich die erfundene Datei `jobradar/tests/fixtures/export_beispiel.json`.

## Ablauf

1. Im Dashboard unter **Datenübernahme** die Exportdatei wählen und **Probelauf** starten. Der Probelauf schreibt nichts; er zeigt je Sammlung, was übernommen würde, sowie Fehler und Hinweise.
2. Gibt es Fehler, bleibt **Übernehmen** gesperrt. Typische Fehler: unbekannter Status, falsche Dokumentanzahl, Stelle mit derselben ID schon vorhanden.
3. **Übernehmen** schreibt alles in einer einzigen Transaktion. Bricht etwas ab, wird nichts geschrieben.
4. Ein zweiter Import derselben Datei ändert nichts; bereits übernommene Dokumente werden übersprungen.

Ohne Dashboard: `POST /api/import` mit der Exportdatei als Body (Probelauf), `POST /api/import?dry_run=false` zum Übernehmen. `overwrite_profile=true` ersetzt ein bereits vorhandenes Suchprofil. `GET /api/imports` zeigt das Importprotokoll.

Vor dem ersten Start mit Schema 4 legt die App automatisch ein geprüftes Backup der Datenbank an (siehe `CHANGELOG.md`, Version 0.3.0).

## Was wohin kommt

Jedes Dokument des Exports wird zuerst unverändert in die Tabelle `import_archive` geschrieben (Pfad, ID, `version`, `updatedAt`, Daten). Damit geht nichts verloren, auch nicht Felder ohne Entsprechung in der App.

| Export | App | Hinweis |
|---|---|---|
| `jobs/<id>` | `jobs` mit derselben ID | `titel` → `title`, `arbeitgeber` → `company`, `ort` → `location`, `url`, `quelle` → `source`, `notiz` → `notes`, `veroeffentlicht` → `published_at`, `gefunden` → `first_seen_at`/`created_at`, `geaendert` bzw. `updatedAt` → `updated_at`, `homeoffice: true` → `remote_type = homeoffice` |
| `punkte` | `score`, `base_score`, `imported_score` | Die bisherigen Punkte bleiben Grundwert. Die Detailansicht rechnet sie nicht mit der neuen Bewertung nach, sondern zeigt „Übernommene Bewertung“ und eine spätere Lernanpassung getrennt. |
| `status` | `status` | `neu` → `neu`, `merken` → `gemerkt`, `beworben`, `absage`, `verworfen` unverändert. Jeder andere Wert ist ein Fehler. |
| `warum`, `bedenken`, `gehalt` | `jobs.import_json` | Das ganze Originaldokument liegt an der Stelle; die Detailansicht zeigt „Passt, weil“, „Aber“ und „Gehalt“. |
| `laeufe/<datum>` | `runs` | `datum` → `started_at`/`finished_at`, `neu` → `jobs_new`, `quellen` → `sources`, `hinweis` → `note`. `jobs_found` ist die Summe der Treffer aus `je_quelle`, sonst `neu`. |
| `profil/aktuell` | `profile` | `ort`, `umkreis_km`, `homeoffice` → `nationwide_remote`, `rollen`/`faehigkeiten`/`ausschliessen_arbeitgeber` als Listen (Kommas in Klammern bleiben erhalten), `gehalt_wunsch` → `salary_min`, `min_entgeltgruppe` → `public_service_minimum` („EG 11“), `wuensche` → `preferences_raw`. Ein vorhandenes Profil wird nur mit `overwrite_profile=true` ersetzt; das alte steht dann im Importbericht. |
| `regeln/aktuell.abwerten` | Bewertungsregel `uebernommen-abwerten` | negative Regel, Gewicht 25 |
| `regeln/aktuell.bevorzugen` | Bewertungsregel `uebernommen-bevorzugen` | nur wenn gefüllt; positive Regel, Gewicht 5 |
| `regeln/aktuell.suchbegriffe_zusatz`, `karriereseiten`, `quellen_hinweise`, `pflege/*` | nur `import_archive` | Dafür gibt es in der App noch keine Funktion; gefüllte Felder erscheinen als Hinweis. |

Die übernommene Abwertungsregel wirkt etwas anders als bisher: Die App zieht 25 Punkte einmal ab, wenn eines der Wörter in Titel, Arbeitgeber, Ort oder Beschreibung vorkommt; der bisherige Jobradar zog 25 Punkte je Wort im Titel ab. Bereits übernommene Stellen behalten ihre Punkte.

## Prüfungen beim Import

- Exporttyp, Formatversion und Dokumentanzahl (gesamt und je Sammlung) müssen zu den Angaben im Abschnitt `_export` passen.
- Doppelte Dokument-IDs, fehlender Titel, unbekannter Status, ungültige Punkte, ungültiges Laufdatum: Fehler, nichts wird übernommen.
- Link ohne `http(s)`, abgeschnittener Link, gleicher Link bei zwei Stellen, gleicher Link wie eine vorhandene Stelle: Hinweis, die Stelle wird trotzdem unverändert übernommen. Dubletten werden nie automatisch zusammengeführt.

## Rückgängig machen

Der Import schreibt nur neue Datensätze. Zum Zurücksetzen das Backup verwenden, das vor der Migration bzw. täglich angelegt wird (`python -m app.backup list` und `restore-to`), oder die Stellen, Läufe und Regeln mit der Import-ID aus `GET /api/imports` gezielt entfernen.
