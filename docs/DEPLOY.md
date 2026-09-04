# Deployment

Zwei getrennte Teile:

| Teil | Wo | Wie |
|---|---|---|
| **Frontend** | GitHub Pages (öffentlich, HTTPS) | `.github/workflows/deploy.yml`, automatisch bei Push auf `main` |
| **Backend** | Christians 24/7-Rechner | native Java-Jar (Windows, aktuell) **oder** Docker; im Heimnetz direkt, von unterwegs über `tailscale serve` |

Die Pages-Version läuft ohne Backend (nur Offline-`.ksong`).

Es gibt zwei Wege, wie Songs aufs Handy kommen:

- **A · `.ksong` im Heimnetz herunterladen** (empfohlen, kein Tailscale) — das
  Backend stellt vorbereitete Bundles unter `/songs` bereit, das Handy lädt sie
  im Browser und importiert sie in der PWA. Kein Backend-HTTPS nötig.
- **B · Voller Client-Server-Betrieb** (Upload über die UI, geteilte Bestenliste)
  — dafür muss die Pages-App per HTTPS ans Backend, also über `tailscale serve`.

---

## Variante A — `.ksong` im Heimnetz herunterladen

Kein Tailscale, kein Zertifikat. Die HTTPS-App lädt **nicht** selbst vom Backend
(das wäre Mixed Content) — der Download läuft über direkte Browser-Navigation.

1. **Backend läuft** (siehe „Backend starten — nativ auf diesem Windows-Rechner").
   Beim `install` öffnet das Skript die Windows-Firewall für TCP 8080 (privates
   Netz); sonst einmal elevated: `scripts\backend-service.ps1 allow-lan`.
2. **Songs ablegen**: `.ksong`-Dateien nach `C:\ki\karaoke-app\share\` kopieren
   (`Copy-Item konverter\output\<name>\song.ksong share\<name>.ksong`). Der
   angezeigte Titel kommt aus dem `manifest.json` im Bundle.
3. **Am Handy** (im Heim-WLAN):
   - `http://<pc-ip>:8080/songs` im Browser öffnen (die IP zeigt
     `scripts\backend-service.ps1 status`). Oder in der PWA unter „Auf diesem
     Gerät" die IP eintragen und „Song-Liste öffnen".
   - Song antippen → `.ksong` wird heruntergeladen.
   - PWA → „Auf diesem Gerät" → importieren → die Datei auswählen.

Danach ist der Song dauerhaft in der Geräte-Bibliothek, auch offline und
unterwegs. Scores bleiben pro Gerät lokal.

---

## Backend starten — nativ auf diesem Windows-Rechner (aktuell in Betrieb)

Kein Docker nötig. Voraussetzung: Java 21 (Temurin, ist installiert).

`scripts\backend-service.ps1` erledigt Build, Deploy und Autostart:

```powershell
# aus C:\ki\karaoke-app
powershell -ExecutionPolicy Bypass -File scripts\backend-service.ps1 update      # baut + startet neu
powershell -ExecutionPolicy Bypass -File scripts\backend-service.ps1 status
powershell -ExecutionPolicy Bypass -File scripts\backend-service.ps1 stop
```

- Läuft mit Arbeitsverzeichnis `backend\`, damit die relativen Pfade aus
  `application.properties` greifen: H2-DB `backend\data\karaoke-db.*`,
  Song-Dateien `data\songs\{id}\` — also **dieselben Daten wie im Dev-Betrieb**.
- Läuft die Jar-Kopie unter `deploy\karaoke-app.jar`, Logs unter
  `deploy\logs\backend.log` (rotiert, 7 Tage). `deploy\` ist gitignored.
- Health: `curl http://localhost:8080/actuator/health` → `{"status":"UP"}`.

### Autostart / 24/7

`install` versucht zuerst einen **Scheduled Task** (Trigger: Anmeldung + Systemstart,
Auto-Neustart bei Absturz). Das braucht **eine PowerShell "als Administrator"**:

```powershell
# elevated PowerShell
cd C:\ki\karaoke-app
powershell -ExecutionPolicy Bypass -File scripts\backend-service.ps1 install
# optional: auch ohne aktive Anmeldung weiterlaufen lassen (S4U)
powershell -ExecutionPolicy Bypass -File scripts\backend-service.ps1 install -RunWhenLoggedOff
```

Ohne Admin fällt das Skript automatisch auf eine **Autostart-Verknüpfung** zurück
(`shell:startup` → `start-backend-hidden.vbs`): startet bei jeder Anmeldung, aber
**kein** automatischer Neustart nach einem Absturz. Das ist der aktuelle Stand.

Manuell umschalten: `... install-startup` bzw. `... uninstall` / `... uninstall-startup`.

### Updaten

```powershell
git pull
powershell -ExecutionPolicy Bypass -File scripts\backend-service.ps1 update
```

`ddl-auto=update` zieht Schema-Änderungen automatisch nach.

### Backup

```powershell
$d = Get-Date -Format yyyy-MM-dd
Compress-Archive -Path C:\ki\karaoke-app\backend\data\*, C:\ki\karaoke-app\data\songs `
  -DestinationPath "C:\ki\karaoke-app-backup-$d.zip"
```

---

## Backend starten — Docker (für einen späteren Linux-Rechner)

`backend/Dockerfile` + `docker-compose.yml` sind vorbereitet.

```bash
git clone https://github.com/clamskemper-arch/karaoke-app.git && cd karaoke-app
docker compose up -d --build
```

- Port nur an `127.0.0.1:8080` gebunden.
- Persistenz im benannten Volume `karaoke-data` → `/data` (H2-DB + `/data/songs/{id}/`).
- Fertiges Image statt lokalem Build: `.github/workflows/backend-image.yml` baut
  `ghcr.io/clamskemper-arch/karaoke-app-backend:latest`; auf dem Server
  `docker login ghcr.io` (PAT mit `read:packages`) + in `docker-compose.yml`
  `build: ./backend` durch `image: …` ersetzen.
- Backup: `docker run --rm -v karaoke-data:/data -v "$PWD":/backup alpine tar czf /backup/karaoke-data-$(date +%F).tgz -C /data .`

---

## Variante B — voller Client-Server-Betrieb über Tailscale

Ohne das kommt die HTTPS-Pages-App nicht ans HTTP-Backend (Mixed Content).

1. **Tailscale installieren** (auf dem Backend-Rechner):
   ```powershell
   winget install Tailscale.Tailscale
   tailscale up
   ```
2. **Im Tailnet-Adminkonsole** (login.tailscale.com): MagicDNS aktivieren und
   „HTTPS Certificates" einschalten. Christian + Eli müssen im selben Tailnet sein.
3. **Serve einrichten** (macht 8080 als HTTPS nach aussen, nur Tailnet):
   ```powershell
   tailscale serve --bg 8080
   tailscale serve status      # zeigt die URL: https://<host>.<tailnet>.ts.net
   ```
4. Prüfen von einem anderen Tailnet-Gerät:
   `curl https://<host>.<tailnet>.ts.net/actuator/health`

Kein Port-Forwarding, kein offener Port ins Internet.

---

### Frontend auf das Backend verdrahten

`NUXT_PUBLIC_API_BASE` im Pages-Workflow (`.github/workflows/deploy.yml`) auf den
MagicDNS-Namen setzen:

```yaml
      - name: Generate static site
        run: npm run generate
        env:
          NUXT_APP_BASE_URL: /karaoke-app/
          NUXT_PUBLIC_API_BASE: "https://<host>.<tailnet>.ts.net"
```

committen → Pages baut neu. Danach:

- Gerät **im Tailnet** → „Auf dem Server"-Songs, Upload, Bestenliste funktionieren.
- Gerät **nicht im Tailnet** → `/api`-Aufrufe schlagen fehl, die App fällt auf den
  Offline-`.ksong`-Betrieb zurück (so gebaut).

Der MagicDNS-Name steht dann im öffentlichen JS-Bundle — ohne Tailnet-Mitgliedschaft
nutzlos, Teil der bewussten Tailscale-Entscheidung.

## CORS

Erlaubte Origins kommen aus `KARAOKE_CORS_ORIGINS` (kommagetrennt, Wildcards wie
`https://*.ts.net`). Default in `application.properties` deckt lokalen Dev, Tailnet
(`100.*`, `*.ts.net`) und die Pages-App ab. Ändern ohne Rebuild: Env-Var setzen +
Backend neu starten (Docker) bzw. `-D`-Property in `scripts\backend-service.ps1`
ergänzen (nativ).
