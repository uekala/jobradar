# Änderungsprotokoll

## Version 2.0.0 – lokale Überarbeitung

- Layout der Stellenkarten auf einen separaten Inhaltsbereich umgestellt; „Passt, weil …“ und „Aber: …“ können nicht mehr in die Punktespalte rutschen.
- Claude-Datenbankinitialisierung abgesichert und verständliche Hinweise für lokalen Betrieb bzw. Fehler ergänzt.
- Fehlertexte vereinheitlicht und begrenzt.
- Statusänderungen zeigen Ladezustand und aktualisieren die lokale Ansicht nach erfolgreichem Schreiben.
- Notizfelder zeigen „Ungespeicherte Änderung“, „Speichert …“, „Gespeichert“ oder einen Fehler.
- Suchprofil-Speicherung deaktiviert den Absenden-Knopf während des Schreibvorgangs und zeigt Erfolg/Fehler.
- ARIA-Beschriftungen und Live-Statusmeldungen ergänzt.
- Kontrast für den aktiven Status „Verworfen“ im hellen Farbschema erhöht.
- Originaldatei unter `archive/Uebersichtsseite-v1.html` unverändert archiviert.

## Kompatibilität

Die Collections `jobs` und `laeufe`, das Dokument `profil/aktuell`, die vorhandenen Feldnamen und Statuswerte wurden nicht geändert.