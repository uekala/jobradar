# SBOM-Inventar von Jobradar

Der Workflow `Python SBOM` löst die Abhängigkeiten in frischen virtuellen Umgebungen der CI auf und erzeugt CycloneDX-JSON-Dateien sowie genau die `pip freeze`-Liste, aus der jede Datei entstanden ist.

## Enthaltene Bereiche

- **runtime**: Pakete für Python 3.12 aus `jobradar/requirements.txt`.
- **standalone-tests**: Pakete für Python 3.12 aus den Anforderungsdateien für Laufzeit und Entwicklung.
- **ha-integration-tests**: Pakete für Python 3.14 aus der `requirements_test.txt` im Wurzelverzeichnis. Das Test-Plugin für Home Assistant ist dort auf die passende, geprüfte Version festgelegt.

Der Workflow läuft bei relevanten Pull Requests und lässt sich mit `workflow_dispatch` auch von Hand starten. Seine Ergebnisse bleiben 90 Tage als Artefakte in GitHub Actions erhalten.

## Grenzen

Das sind SBOMs für Python-Pakete, keine vollständige SBOM für das Image der Home-Assistant-App. Noch nicht erfasst sind:

- Debian-Pakete und andere Inhalte des Betriebssystems in `python:3.12-slim-bookworm`.
- Der genaue Digest des Basis-Images für einen bestimmten ARM64-Build der App.
- Komponenten oder Dienste, die der Home-Assistant-Host bereitstellt.
- Externe Schnittstellen, Feeds, entfernt geladene Schriften und deren Daten- oder Nutzungsbedingungen.

Der SBOM-Generator wird in der Umgebung des Runners installiert, außerhalb der abgeschotteten virtuellen Zielumgebung. So gerät er nicht ins Paketinventar der Anwendung. Die aufgelöste Paketliste wird zusammen mit jeder SBOM hochgeladen, damit die Grundlage nachprüfbar ist.

## Reproduzierbarkeit und Prüfung

Die Versionsangaben in den Manifesten für Laufzeit und Entwicklung sind Bereiche, keine festen Stände. Die erzeugten Dateien zeigen deshalb die Versionen, die in genau diesem Workflow-Lauf aufgelöst wurden; ein späterer Lauf kann andere Versionen ergeben. Wer einen Prüfnachweis aufbewahren will, sichert das Artefakt zusammen mit dem zugehörigen Lauf und Commit.

Das Test-Plugin für die Home-Assistant-Integration ist eigens festgelegt, weil seine Versionen bestimmten Home-Assistant-Versionen folgen und eine neuere Python-Version verlangen können. Diese Festlegung zusammen mit der Python-Version anheben, nachdem die veröffentlichten Metadaten des Plugins geprüft und die Integrationstests erneut gelaufen sind.

Eine erfolgreich erzeugte SBOM ist kein Beleg, dass alle Lizenzen oder Bedingungen externer Dienste rechtlich freigegeben sind. Fehlende oder unklare Lizenzangaben prüfen und das Docker-Basis-Image sowie externe Datenquellen gesondert bewerten.
