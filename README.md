# Jobradar

Jobradar sucht in Home Assistant regelmäßig nach neuen Stellen in der [Jobbörse der Bundesagentur für Arbeit](https://www.arbeitsagentur.de/jobsuche/) und bei [service.bund.de](https://www.service.bund.de/Content/DE/Stellen/Suche/Formular.html) (öffentlicher Dienst von Bund, Ländern und Kommunen), bewertet sie nach deinem Profil und meldet passende sofort aufs Handy – mit Knöpfen zum Öffnen und Ausblenden.

## Was es macht

- **Sucht** alle 30 Minuten (einstellbar) nach jedem deiner Suchbegriffe: im Umkreis deines Orts und auf Wunsch zusätzlich nach Homeoffice-Stellen in ganz Deutschland.
- **Fragt service.bund.de** höchstens alle zwei Stunden über den RSS-Feed, den die Seite für jede Stellensuche anbietet, im selben Umkreis. Dieselbe Stelle aus beiden Quellen wird nur einmal gemeldet; die Meldung nennt die Bewerbungsfrist.
- **Bewertet** jede neue Stelle mit 0 bis 100 Punkten: passende Rolle im Titel, deine Fähigkeiten in Titel und Beschreibung, Homeoffice und Nähe.
- **Filtert** Ausbildung, Praktika, Werkstudentenstellen, Zeitarbeit und Arbeitgeber, die du ausschließt – zum Beispiel deinen jetzigen.
- **Meldet** neue Stellen ab einer Mindestpunktzahl einzeln, höchstens fünf pro Suche; der Rest kommt als Sammelmeldung.
- **Merkt sich**, was schon gemeldet oder ausgeblendet wurde – auch über Neustarts hinweg.

## Installation über HACS

1. HACS → ⋮ → **Benutzerdefinierte Repositories**
2. `https://github.com/uekala/jobradar` als Kategorie **Integration** hinzufügen
3. **Jobradar** installieren und Home Assistant neu starten
4. Einstellungen → Geräte & Dienste → **Integration hinzufügen** → Jobradar

## Einrichtung

| Feld | Bedeutung |
|------|-----------|
| Ort, Umkreis | Wo du arbeiten möchtest. Leer lassen für reine Homeoffice-Suche. |
| Homeoffice bundesweit | Sucht zusätzlich Stellen mit Heim- oder Telearbeit, unabhängig vom Ort. |
| Suchbegriffe | Jeder Begriff ist eine eigene Suche, z. B. *Systemadministrator, VMware, Cloud Engineer*. |
| Fähigkeiten | Bringen Punkte, wenn sie im Titel (10) oder in der Beschreibung (5) stehen. |
| Arbeitgeber ausschließen | Ein Teil des Namens genügt. |
| Mindestpunktzahl | Ab hier wird gemeldet. Vorgabe 50 – das entspricht einer passenden Rolle im Titel. |
| Benachrichtigen über | Ein `notify`-Dienst, z. B. die Companion-App. Ohne Auswahl erscheint eine Benachrichtigung in Home Assistant. |

In den Optionen lassen sich außerdem Abwertungen (z. B. *Junior, Helpdesk*), Ausschlusswörter, Zeitarbeit und das Abfrageintervall einstellen, dazu:

| Option | Bedeutung |
| --- | --- |
| Gehaltsvorstellung (brutto pro Jahr) | Etwa jede fünfte Stelle der Jobbörse nennt ein Gehalt, als Spanne oder Festbetrag. Liegt auch das obere Ende darunter, verliert die Stelle 30 Punkte und wird in der Meldung markiert; passt es, gibt es 5 Punkte. 0 = nicht vergleichen. |
| Mindest-Entgeltgruppe (TVöD/TV-L) | Für Stellen im öffentlichen Dienst, die statt Euro eine Entgelt- oder Besoldungsgruppe nennen (z. B. *E 11 TVöD*, *A 11*). Darunter: wie oben. 0 = nicht vergleichen. |

### So entstehen die Punkte

| Merkmal | Punkte |
|---------|--------|
| Suchbegriff im Titel oder Beruf – oder Rollenwort wie *Administrator* zusammen mit einer deiner Fähigkeiten | 50 |
| je Fähigkeit im Titel / in der Beschreibung | 10 / 5, zusammen höchstens 40 |
| Homeoffice möglich | 5 |
| höchstens 25 km Luftlinie entfernt | 5 |
| je Abwertungswort im Titel | −25 |
| Gehalt oder Entgeltgruppe passt zur Gehaltsvorstellung / liegt darunter | 5 / −30 |

## Benachrichtigung

Mit der Companion-App öffnet ein Tipp die Stelle bei der Bundesagentur. Zwei Knöpfe:

- **Öffnen** – Stellenanzeige im Browser
- **Nicht interessant** – blendet die Stelle dauerhaft aus

Bei der ersten Suche schickt Jobradar nur eine Meldung mit der Zahl der passenden Stellen der letzten 14 Tage; danach meldet es jede neue einzeln.

## Entitäten, Aktionen, Ereignis

| | |
|---|---|
| `sensor.…_neue_stellen` | Zahl der ungelesenen passenden Stellen; Attribut `stellen` mit Titel, Arbeitgeber, Ort, Entfernung, Gehalt (falls angegeben), Punkten, Treffern und Link |
| `sensor.…_passende_stellen` | Alle passenden Stellen der letzten 30 Tage |
| `sensor.…_letzte_suche` | Zeitpunkt und Ergebnis der letzten Suche |
| `button.…_alle_als_gelesen_markieren`, `button.…_jetzt_suchen` | |
| `jobradar.search`, `jobradar.hide`, `jobradar.mark_read`, `jobradar.reset` | Aktionen für Automationen |
| Ereignis `jobradar_new_job` | Für jede neue passende Stelle, mit allen Angaben – etwa für eigene Meldungen per Telegram oder Sprachausgabe |

### Dashboard-Karte

```yaml
type: markdown
title: Neue Stellen
content: >
  {% for s in state_attr('sensor.jobradar_krefeld_neue_stellen', 'stellen') or [] %}
  **[{{ s.titel }}]({{ s.url }})**<br>
  {{ s.arbeitgeber }}, {{ s.ort }}{% if s.homeoffice %} (Homeoffice){% endif %}, {{ s.punkte }} Punkte
  {% else %}
  Keine neuen Stellen.
  {% endfor %}
```

Die Entitäts-ID richtet sich nach dem Namen des Eintrags (hier *Jobradar Krefeld*).

## Datenschutz

Jobradar sendet nur deine Suchbegriffe, den Ort und den Umkreis an die Jobbörse der Bundesagentur und an service.bund.de. Profil, Fähigkeiten, ausgeschlossene Arbeitgeber und alle gefundenen Stellen bleiben in deinem Home Assistant. Die Diagnose blendet die Arbeitgeberliste aus.

## Grenzen

- Jobradar kennt die Jobbörse der Bundesagentur und service.bund.de. Dort stehen sehr viele, aber nicht alle Stellen – manche gibt es nur bei StepStone, LinkedIn, Interamt oder auf Karriereseiten. Diese Börsen bieten weder offene Schnittstelle noch Feed an, und Indeed und LinkedIn untersagen das automatische Auslesen ausdrücklich; Jobradar fragt sie deshalb nicht ab.
- Bei Stellen von service.bund.de gibt es keine Detailansicht; bewertet wird der Titel, die Entfernung entfällt.
- Die Schnittstelle ist öffentlich, aber nicht offiziell dokumentiert ([Community-Dokumentation](https://jobsuche.api.bund.dev/)). Jobradar probiert bekannte Pfade nacheinander und bewertet nur den Titel, wenn die Detailansicht fehlt.
- Entfernungen sind Luftlinie vom Standort deines Home Assistant.

## Entwicklung

```bash
pip install -r requirements_test.txt ruff
ruff check . && ruff format --check .
pytest
```

## Lizenz

MIT – siehe [LICENSE](LICENSE). Kein Angebot der Bundesagentur für Arbeit.
