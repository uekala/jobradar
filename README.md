# Jobradar – eigenständiger Betrieb

Dieses Repository entwickelt den persönlichen Jobradar schrittweise von der bisherigen Claude-Artifact-Lösung zu einer eigenständigen Anwendung weiter.

**Zielbetrieb:** Home Assistant Green (ARM64), Zugriff im Heimnetz und unterwegs ausschließlich über die bestehende VPN-Verbindung.

**Keine KI im Regelbetrieb:** Suche, Dublettenerkennung, Bewertung, Speicherung und Tagesbericht sollen deterministisch mit Python laufen. KI bleibt optional und wird nicht für tägliche Suchläufe benötigt.

## Projektbereiche

- index.html und archive/: bisherige Claude-Artifact-Oberfläche und Archiv; bleiben vorerst als Referenz erhalten.
- jobradar/: eigenständiger Home-Assistant-Add-on-Dienst (FastAPI + SQLite).
- .github/workflows/: automatisierte Tests und ARM64-Build-Prüfung.
- docs/: Architektur- und Betriebsdokumentation.

## Entwicklungsstand

Branch ha-green-foundation enthält das erste technische Grundgerüst:
- Home-Assistant-Add-on-Manifest für ARM64.
- FastAPI-Anwendung mit Health- und Meta-Endpunkt.
- SQLite-Schema mit persistentem Datenpfad /data/jobradar.db.
- GitHub-Actions-Workflow für Python-Tests.
- ARM64-Docker-Build-Prüfung ohne Veröffentlichung eines Images.

**Noch nicht produktiv:** Es gibt noch keine Suchquellen, keinen Scheduler, keine fertige Dashboard-Anbindung und keine Datenmigration. Die Claude-Version und deren Datenbank bleiben bis zur abgeschlossenen Migration unverändert.

## Lokal testen

Im Verzeichnis jobradar ausführen:

    python -m pip install -r requirements.txt -r requirements-dev.txt
    pytest -q

## Home Assistant Green

Das Repository ist privat. Deshalb wird es vorerst **nicht** als öffentliches Home-Assistant-Add-on-Repository eingebunden und es werden keine Zugangsdaten oder Repository-Rechte offengelegt.

Für die spätere Installation wird ausschließlich der Ordner jobradar/ als lokales Add-on nach /addons/jobradar/ auf Home Assistant OS übertragen. Da in config.yaml kein Remote-Image hinterlegt ist, baut Home Assistant das Add-on lokal aus dem Dockerfile für ARM64.

Die Installation erfolgt erst nach erfolgreichem Test und ausdrücklicher Freigabe. Das Grundgerüst jetzt noch nicht auf dem produktiven Home Assistant installieren.

## Sicherheit und Daten

- SQLite-Datei liegt im persistenten Add-on-Verzeichnis /data.
- Keine Ports werden öffentlich freigegeben.
- Der Zugriff ist für Home Assistant Ingress vorgesehen; unterwegs erfolgt er über VPN zum Heimnetz.
- Keine Tokens, Passwörter oder persönlichen Bewerbungsdaten gehören ins Git-Repository.
- Die vorhandene Claude-Datenbank wird nicht automatisch verändert oder migriert.
