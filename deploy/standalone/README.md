# Eigenständiger Betrieb mit Docker (z. B. Unraid)

Der Jobradar-Dienst läuft auch ohne Home Assistant OS als gewöhnlicher Container. Die Oberfläche ist dann direkt
im Browser erreichbar und fragt nach Benutzername und Passwort. Home Assistant bleibt optional: Mit Adresse und
Zugriffstoken meldet Jobradar neue Stellen weiter über einen Benachrichtigungsdienst.

Image: `ghcr.io/uekala/jobradar` (amd64 und arm64), Tags `latest` und die Versionsnummer.

## Was anders ist als in der Home-Assistant-App

| | Home-Assistant-App | Eigenständig |
|---|---|---|
| Oberfläche | Seitenleiste von Home Assistant | eigene Adresse, Anmeldung mit `JOBRADAR_WEB_USER` und `JOBRADAR_WEB_PASSWORD` |
| Benachrichtigungen | über den Supervisor | nur mit `HA_URL` und `HA_TOKEN` |
| Einstellungen | Seite „Konfiguration“ der App | Umgebungsvariablen |
| Tipp auf eine Meldung | öffnet Jobradar in Home Assistant | öffnet keine Seite |
| Sicherung | Teil der Home-Assistant-Backups | Ordner `data` selbst sichern |

## Einrichten

1. Einen Ordner anlegen und `docker-compose.yml` aus diesem Verzeichnis hineinlegen.
2. Daneben eine Datei `.env` anlegen und schützen (`chmod 600 .env`):

   ```
   JOBRADAR_WEB_PASSWORD=ein-langes-eigenes-passwort
   ```

3. Starten und das Protokoll prüfen:

   ```bash
   mkdir -p data
   docker compose up -d
   docker compose logs -f
   ```

4. Im Browser `http://<IP des Servers>:8099` öffnen und anmelden. Der Benutzername ist `jobradar`, solange
   `JOBRADAR_WEB_USER` nichts anderes vorgibt.

**Unraid:** entweder mit dem Plugin „Docker Compose Manager“ wie oben, oder als einzelner Container mit dem
Repository `ghcr.io/uekala/jobradar`, dem Pfad `/data` (z. B. `/mnt/user/appdata/jobradar/data`) und dem
Container-Port 8099. Ist 8099 auf dem Server schon vergeben, außen einen anderen Port wählen (z. B. `8096:8099`).
Die Variablen lassen sich in einer Datei sammeln und unter „Extra Parameters“ mit `--env-file=<Pfad>` laden;
die Datei mit `chmod 600` schützen.

## Umgebungsvariablen

| Variable | Bedeutung | Standard |
|---|---|---|
| `JOBRADAR_WEB_PASSWORD` | Passwort für Oberfläche und API. Ohne Passwort ist beides für jeden offen, der den Port erreicht | leer |
| `JOBRADAR_WEB_USER` | Benutzername | `jobradar` |
| `TZ` | Zeitzone für den täglichen Suchlauf | `Europe/Berlin` (in der Compose-Datei) |
| `JOBRADAR_SEARCH_TIME` | Uhrzeit des täglichen Suchlaufs (HH:MM); leer schaltet ihn ab | `06:30` (in der Compose-Datei) |
| `JOBRADAR_NOTIFY_SERVICE` | Benachrichtigungsdienst von Home Assistant, z. B. `mobile_app_pixel` oder `persistent_notification` | leer |
| `JOBRADAR_NOTIFY_MIN_SCORE` | Punktzahl, ab der eine neue Stelle gemeldet wird | `70` |
| `HA_URL` | Adresse von Home Assistant, z. B. `http://192.168.1.20:8123`. Die IP eintragen, `.local`-Namen werden im Container oft nicht aufgelöst | leer |
| `HA_TOKEN` | langlebiges Zugriffstoken (Home Assistant → Profil → Sicherheit) | leer |

Meldungen brauchen `JOBRADAR_NOTIFY_SERVICE`, `HA_URL` und `HA_TOKEN` zusammen. Die Werte lassen sich statt als
Umgebungsvariablen auch in `data/options.json` setzen (`search_time`, `notify_service`, `notify_min_score`);
gesetzte Umgebungsvariablen haben Vorrang.

`/api/health` antwortet ohne Anmeldung, damit Container-Prüfung und Überwachung ohne Passwort auskommen. Die
Adresse verrät nur, ob der Dienst läuft.

## Umzug von der Home-Assistant-App

Alle Daten liegen in `jobradar.db` im Datenordner der App. Die Datei aus einem Backup der App oder aus dem
Ordner `backups` neben der Datenbank nach `data/jobradar.db` kopieren, solange der Container gestoppt ist.

## Sicherheit

- Die Oberfläche spricht unverschlüsseltes HTTP. Das Passwort ist dabei im Heimnetz mitlesbar. Den Port deshalb
  nur im Heimnetz nutzen und nie am Router freigeben; von unterwegs über ein VPN oder einen HTTPS-Proxy zugreifen.
- Nach fünf falschen Anmeldungen von einer Adresse ist die Anmeldung für fünf Minuten gesperrt.
- Schreibende Anfragen nimmt Jobradar nur von der eigenen Seite an, nicht von fremden Webseiten im selben Browser.
- Im Ordner `data` liegen Suchprofil, Stellen und Notizen. Den Ordner nur für den Besitzer lesbar halten und
  nicht über eine Netzwerkfreigabe anbieten.
