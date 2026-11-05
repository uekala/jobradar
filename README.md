# Claude-Jobradar

Versionierte Quellen und Dokumentation für das Jobradar auf Basis geplanter Claude-Aufgaben und einer Claude-Artifact-Übersichtsseite.

**Wichtig:** Die Live-Suche und die Datenbank laufen in Claude. Dieses Repository ist die private Ablage für Quelltext und Dokumentation; es hostet weder die Live-Datenbank noch führt es die geplanten Claude-Aufgaben aus.

## Aufbau

- **Tagesbericht:** tägliche Suche und Bewertung der Stellen; die Ergebnisse werden in die Übersichtsseite geschrieben.
- **Übersichtsseite:** Status, Notizen, Suchprofil und Laufhistorie. Live-Artifact: [Jobradar](https://claude.ai/artifact/W4hbHfCozfMmnr5YSkDb8j).
- **Wochenpflege:** prüft Quellen, Suchregeln, Datenqualität und die Übersichtsseite und pflegt die Dokumentation.
- **Bewerbungs-Assistent:** bleibt ein separates privates Projekt im Repository [bewerbung](https://github.com/uekala/bewerbung).

## Datenmodell der Übersichtsseite

Die Live-Datenbank liegt im Claude-Artifact und wird nicht in dieses Repository kopiert.

| Sammlung / Dokument | Zweck |
|---|---|
| `jobs` | Eine Stelle pro Dokument: Titel, Arbeitgeber, Ort, URL, Punkte, Status und Notiz |
| `laeufe` | Ein Berichtslauf pro Tag mit Trefferzahlen und Quellen |
| `profil/aktuell` | Suchprofil |
| `regeln/aktuell` | Lernregeln, zusätzliche Suchbegriffe, Karriereseiten und Quellenhinweise |
| `pflege` | Wartungsstand und Protokoll der Wochenpflege |

Mögliche Stellenstatus: `neu`, `merken`, `beworben`, `absage`, `verworfen`.

## Quelldatei

- `uebersichtsseite.html` ist der versionierte HTML-/JavaScript-Quellstand der Übersichtsseite.
- Die Seite verwendet `claude.use("db")` und ist deshalb für die Laufzeit eines angemeldeten Claude-Artifacts bestimmt. Als normale lokale HTML-Datei kann sie die Live-Datenbank nicht öffnen.
- Änderungen an dieser Datei aktualisieren das Live-Artifact **nicht automatisch**. Sie müssen separat in Claude veröffentlicht werden.

## Prüfung

Mit Node.js 22 oder neuer:

```bash
node --test tests/*.test.mjs
```

Die Tests prüfen die JavaScript-Syntax des eingebetteten Skripts und die zentralen DOM-/Datenbankverträge der Übersichtsseite.

## Datenschutz

Dieses Repository bleibt **privat**. Das Suchprofil, konkrete Stellen, Notizen, Lernregeln und Laufdaten bleiben in der Claude-Artifact-Datenbank und werden nicht als echte Nutzerdaten eingecheckt. Keine Zugangsdaten, Tokens oder persönlichen Profildaten in Quelldateien oder Commits ablegen.
