# Deployment

Zwei getrennte Teile:

| Teil | Wo | Wie |
|---|---|---|
| **Frontend** | GitHub Pages (öffentlich, HTTPS) | `.github/workflows/deploy.yml`, automatisch bei Push auf `main` |
| **Backend** | eigener 24/7-Rechner, nur im Tailnet | Docker-Container hinter `tailscale serve` |

Die Pages-Version läuft ohne Backend (nur Offline-`.ksong`). Für Upload über die
UI und geteilte Bestenliste muss das Backend laufen **und** die Pages-App darauf
zeigen (siehe Schritt 4).

---

## Backend

### Voraussetzungen auf dem Server

- Docker (Engine + Compose-Plugin)
- Tailscale, im selben Tailnet wie Christian + Eli, mit aktiviertem MagicDNS + HTTPS
  (`Enable HTTPS` in den Tailnet-Einstellungen)

### 1. Container bauen & starten

```bash
git clone https://github.com/clamskemper-arch/karaoke-app.git
cd karaoke-app
docker compose up -d --build
```

- Der Port wird nur an `127.0.0.1:8080` gebunden – von aussen kommt man nur über
  `tailscale serve` ran.
- Persistenz: benanntes Volume `karaoke-data` → `/data` (H2-DB `karaoke-db.*` +
  hochgeladene Song-Dateien unter `/data/songs/{id}/`).
- Health: `curl http://127.0.0.1:8080/actuator/health` → `{"status":"UP"}`.

Alternativ ohne Compose:

```bash
docker build -t karaoke-app-backend ./backend
docker run -d --name karaoke-backend --restart unless-stopped \
  -p 127.0.0.1:8080:8080 \
  -e KARAOKE_CORS_ORIGINS="https://clamskemper-arch.github.io,https://*.ts.net" \
  -v karaoke-data:/data \
  karaoke-app-backend
```

### 2. Fertiges Image statt lokalem Build (optional)

`.github/workflows/backend-image.yml` baut bei Änderungen unter `backend/` ein
Image nach `ghcr.io/clamskemper-arch/karaoke-app-backend:latest`. Auf dem Server
dann nur noch:

```bash
docker login ghcr.io                 # einmalig, mit PAT (scope: read:packages)
docker pull ghcr.io/clamskemper-arch/karaoke-app-backend:latest
```

und in `docker-compose.yml` `build: ./backend` durch
`image: ghcr.io/clamskemper-arch/karaoke-app-backend:latest` ersetzen.
(Oder das Package in den GitHub-Package-Settings auf „public" stellen, dann
entfällt `docker login`.)

### 3. Über Tailscale erreichbar machen (HTTPS, nur Tailnet)

```bash
sudo tailscale serve --bg 8080
```

Danach ist das Backend unter `https://<hostname>.<tailnet>.ts.net/` erreichbar –
nur für Geräte im Tailnet, kein offener Port ins Internet. Prüfen:

```bash
tailscale serve status
curl https://<hostname>.<tailnet>.ts.net/actuator/health
```

### 4. Frontend auf das Backend zeigen lassen

`NUXT_PUBLIC_API_BASE` im Pages-Workflow (`.github/workflows/deploy.yml`) auf den
MagicDNS-Namen setzen:

```yaml
      - name: Generate static site
        run: npm run generate
        env:
          NUXT_APP_BASE_URL: /karaoke-app/
          NUXT_PUBLIC_API_BASE: "https://<hostname>.<tailnet>.ts.net"
```

committen → Pages baut neu. Ab dann:

- Gerät **im Tailnet** → „Auf dem Server"-Songs, Upload, Bestenliste funktionieren.
- Gerät **nicht im Tailnet** → die `/api`-Aufrufe schlagen fehl, die App fällt auf
  den Offline-`.ksong`-Betrieb zurück (schon so gebaut).

Der MagicDNS-Name steht dann im öffentlichen JS-Bundle – ohne Tailnet-Mitgliedschaft
ist er nutzlos, das ist Teil der bewussten Tailscale-Entscheidung.

### CORS

Erlaubte Origins kommen aus `KARAOKE_CORS_ORIGINS` (kommagetrennt, Wildcards wie
`https://*.ts.net`). Default in `application.properties` deckt lokalen Dev, Tailnet
und die Pages-App ab. Ändern ohne Rebuild: Env-Var im Container anpassen + neu starten.

### Backup

Alles Wichtige liegt im `karaoke-data`-Volume:

```bash
docker run --rm -v karaoke-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/karaoke-data-$(date +%F).tgz -C /data .
```

### Updaten

```bash
git pull && docker compose up -d --build      # oder: docker pull ... && docker compose up -d
```

`ddl-auto=update` zieht Schema-Änderungen automatisch nach.
