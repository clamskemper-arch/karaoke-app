# share/

`.ksong`-Bundles, die im Heimnetz zum Download bereitstehen sollen.

Das laufende Backend liefert sie aus:

- `http://<pc-ip>:8080/songs` – Liste zum Antippen (im Handy-Browser öffnen)
- `http://<pc-ip>:8080/songs/<name>.ksong` – die Datei

Danach in der App unter **„Auf diesem Gerät"** importieren.

## Song hinzufügen

Eine `.ksong` aus dem Konverter hierher kopieren, Dateiname `[A-Za-z0-9._-]+.ksong`:

```powershell
Copy-Item konverter\output\amazing-grace\song.ksong share\amazing-grace.ksong
```

Der angezeigte Titel kommt aus dem `manifest.json` im Bundle, nicht aus dem Dateinamen.

Die `.ksong`-Dateien selbst sind nicht eingecheckt (nur diese README).
