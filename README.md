# Karaoke App

Mitsing-App fürs Chorüben: Songs registrieren, abspielen, Töne treffen. SingStar-artige
Note-Highway mit vorausschauenden Ton-Balken, synced Lyrics und Live-Tonhöhen-Feedback
übers Mikrofon. Mehrstimmige Chorsätze mit Stimmwahl und Mixer.

Das Repo hat drei Teile:

| Ordner | Was | Stack |
|---|---|---|
| `frontend/` | Web-App (PWA/SPA) | Nuxt 4, Vue 3, Nuxt UI, Web Audio API |
| `backend/` | API + Song-Speicher | Spring Boot 4, Java 21, H2 (Datei-DB) |
| `konverter/` | Song-Aufbereitung, **separat** von der App | Python: Demucs, librosa, torchaudio, mido |

## Ablauf

1. **Konvertieren** (`konverter/`): aus einer Aufnahme, MIDI oder Notensatz-Export
   `instrumental.wav` + `lyrics.json` (Text + Zielton pro Wort/Silbe) erzeugen.
2. **Registrieren**: Artefakte über die Startseite hochladen (`POST /api/songs` bzw.
   `/api/songs/multitrack`) – oder als `.ksong`-Bundle direkt in die App importieren
   (offline, ohne Backend).
3. **Singen**: Player-Seite mit Note-Highway, Lyrics und Mikrofon-Scoring.

## Entwicklung

### Backend
```
cd backend
./mvnw spring-boot:run          # http://localhost:8080, H2-Datei-DB unter backend/data/
```

### Frontend
```
cd frontend
npm install
npm run dev                     # http://localhost:3000
npm run lint && npm run typecheck
npm run generate                # statischer PWA-Build -> .output/public (für HTTPS-Hosting)
```
`NUXT_PUBLIC_API_BASE` setzt die Backend-Adresse (Default `http://localhost:8080`).
Leer lassen = reiner Offline-Betrieb mit importierten `.ksong`-Songs.

### Konverter
```
cd konverter
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt              # ffmpeg muss im PATH sein
python convert.py       "input/song.mp4" "output/song" --lyrics "input/song-lyrics.txt"
python convert_midi.py  "input/amazing-grace.kar" "output/amazing-grace"
python convert_choir.py "input/lied.json" "output/lied"
```
Jeder Lauf schreibt zusätzlich ein `song.ksong` (ZIP mit Manifest + AAC-Audio + Lyrics)
für den Offline-Import in die App.

## Deployment

Ausführliche Anleitung: [`docs/DEPLOY.md`](docs/DEPLOY.md).

**Frontend** – `.github/workflows/deploy.yml` baut bei jedem Push auf `main`
(`nuxt generate`) und veröffentlicht auf GitHub Pages →
`https://clamskemper-arch.github.io/karaoke-app/`. Einmalig im Repo:
Settings → Pages → Source: GitHub Actions. Ohne konfiguriertes Backend läuft
die Pages-Version rein offline (nur importierte `.ksong`-Songs); Mikrofon geht,
weil Pages HTTPS liefert.

**Backend** – läuft 24/7 auf Christians Windows-Rechner als native Java-Jar
(`scripts\backend-service.ps1`, Autostart via `shell:startup`, optional als
Scheduled Task). Docker-Variante (`backend/Dockerfile`, `docker-compose.yml`) für
einen späteren Linux-Rechner vorbereitet. Von aussen nur über `tailscale serve`
(HTTPS, nur Tailnet) erreichbar; danach `NUXT_PUBLIC_API_BASE` im Pages-Workflow
auf den MagicDNS-Namen setzen. Details: [`docs/DEPLOY.md`](docs/DEPLOY.md).

## `.ksong`-Format

ZIP mit `manifest.json` (`ksongVersion`, `title`, `tracks[]`) und je Stimme
`tracks/<Stimme>/audio.m4a` + optional `tracks/<Stimme>/lyrics.json`. Wird im Frontend
über `useSongLibrary` in IndexedDB abgelegt und ist danach offline spielbar.

## Hinweise

- `konverter/input/` und `konverter/output/` sind bewusst nicht eingecheckt (große
  Mediendateien, teils urheberrechtlich geschütztes Quellmaterial). Einzige Ausnahme:
  die gemeinfreie Test-MIDI `amazing-grace.kar`.
- `frontend/.github/workflows/ci.yml` liegt unterhalb von `frontend/` und ist damit
  **keine** aktive GitHub-Action (die müsste unter `/.github/workflows/` liegen) – und
  nutzt pnpm, während das Projekt npm/`package-lock.json` verwendet.
