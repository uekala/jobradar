# Architektur – eigenständiger Jobradar

## Ziel

Der Jobradar läuft lokal auf Home Assistant Green und benötigt für den täglichen Betrieb weder Claude noch eine andere KI. GitHub dient ausschließlich der Quellcodeverwaltung, Tests und dem reproduzierbaren Build.

## Komponenten

| Komponente | Umsetzung | Verantwortung |
|---|---|---|
| Laufzeit | Home Assistant OS Add-on, ARM64 | Dauerbetrieb auf dem Green |
| Backend | Python + FastAPI | API und Anwendungslogik |
| Datenbank | SQLite | Stellen, Suchläufe, Profil und Regeln |
| Zeitplanung | Geplant: APScheduler | tägliche Suche |
| Oberfläche | Geplant: bestehendes Dashboard an REST-API anbinden | Browser und Smartphone |
| Quellcode | privates GitHub-Repository | Versionierung und CI |

## Zugriff

- Home Assistant Ingress stellt die Oberfläche innerhalb der Home-Assistant-Oberfläche bereit.
- Der Add-on-Port 8099 wird nicht als öffentlicher Router-Port eingerichtet.
- Unterwegs wird Home Assistant über die bereits vorhandene VPN-Verbindung zum Heimnetz aufgerufen.
- Es wird kein zusätzlicher Cloud-Tunnel und keine öffentliche Verwaltungsoberfläche eingerichtet.

## Persistenz

Die Datenbank liegt unter /data/jobradar.db. Home Assistant stellt den Add-on-Datenbereich persistent bereit. Backups müssen später zusätzlich über die Home-Assistant-Backup-Funktion und einen getesteten Export abgesichert werden.

## Datenmodell – erster Entwurf

- jobs: Stellenanzeige, Quelle, URL, Score, Status, Notiz und Zeitstempel.
- runs: Beginn, Ende, Ergebnis und Fehler eines Suchlaufs.
- profile: Suchprofil als JSON.
- search_rules: versionierte Bewertungs- und Filterregeln.
- schema_meta: Schema-Version für spätere Migrationen.

Das Schema ist ein Startpunkt und wird vor dem Import der vorhandenen Daten gegen die echte JSON-Sicherung abgeglichen.

## Datenfluss

1. Scheduler startet einen Suchlauf.
2. Quellenadapter laden Stellenanzeigen.
3. Normalisierung und Dublettenerkennung vereinheitlichen Treffer.
4. Regelbasierte Bewertung berechnet den Score.
5. Neue bzw. aktualisierte Stellen werden in SQLite gespeichert.
6. Dashboard und Benachrichtigungen lesen die Ergebnisse.

## Bewusste Grenzen der ersten Phase

Noch nicht enthalten sind Quellenadapter, Scheduler, E-Mail-Verarbeitung, Bewerbungsworkflow, Datenimport und produktive Benachrichtigungen. Diese folgen in getrennten, testbaren Schritten.
