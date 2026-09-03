"""
.ksong-Bundle bauen (gemeinsam genutzt von convert_midi.py / convert_choir.py)

Ein .ksong ist ein ZIP mit
    manifest.json                {ksongVersion, title, createdAt,
                                  tracks:[{voiceName, audio, lyrics}]}
    tracks/<Stimme>/audio.m4a    AAC 128k (per ffmpeg aus der WAV) - faellt auf
                                 audio.wav zurueck, wenn ffmpeg nicht im PATH ist
    tracks/<Stimme>/lyrics.json  nur wenn die Stimme Text hat

Gedacht fuer den Import in die mobile PWA (siehe useSongLibrary.ts im Frontend):
ein einzelnes File pro Song, offline abspielbar, ganz ohne Backend. Die
Ordnerstruktur tracks/<Stimme>/ ist bewusst dieselbe wie bei convert_choir.py,
damit ein- und mehrstimmige Songs im Frontend gleich behandelt werden koennen.
"""

import json
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

KSONG_VERSION = 1


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def transcode_for_bundle(src: Path, work_dir: Path, stem: str) -> Path:
    """WAV -> AAC/.m4a, damit der Song aufs Handy passt (eine 3-Min-Stereo-WAV
    ist ~30 MB, als AAC ~3 MB). AAC statt Opus, weil decodeAudioData es auf
    allen Browsern inkl. iOS-Safari abspielt. Ohne ffmpeg im PATH bleibt die
    WAV unveraendert - dann ist das Bundle halt groesser."""
    if src.suffix.lower() != ".wav":
        return src
    ff = _ffmpeg()
    if ff is None:
        print(f"    ffmpeg nicht im PATH - {src.name} bleibt als WAV im Bundle (groesser)")
        return src
    dst = work_dir / f"{stem}.m4a"
    subprocess.run(
        [ff, "-y", "-loglevel", "error", "-i", str(src),
         "-c:a", "aac", "-b:a", "128k", str(dst)],
        check=True,
    )
    return dst


def write_ksong(out_path: Path, title: str, tracks: list[dict],
                created_at: str | None = None) -> Path:
    """tracks: [{"name": str, "audio": Path (WAV oder schon .m4a/.mp3),
    "lyrics": Path | None}]. Schreibt das fertige .ksong nach out_path."""
    created = created_at or (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    work = out_path.parent / "_ksong_tmp"
    work.mkdir(parents=True, exist_ok=True)

    manifest_tracks: list[dict] = []
    staged: list[tuple[str, Path]] = []  # (arcname im ZIP, Quelldatei)
    try:
        for t in tracks:
            name = t["name"]
            audio_stage = transcode_for_bundle(Path(t["audio"]), work, f"{name}-audio")
            arc_audio = f"tracks/{name}/audio{audio_stage.suffix.lower()}"
            staged.append((arc_audio, audio_stage))
            entry = {"voiceName": name, "audio": arc_audio, "lyrics": None}
            if t.get("lyrics"):
                arc_lyrics = f"tracks/{name}/lyrics.json"
                staged.append((arc_lyrics, Path(t["lyrics"])))
                entry["lyrics"] = arc_lyrics
            manifest_tracks.append(entry)

        manifest = {
            "ksongVersion": KSONG_VERSION,
            "title": title,
            "createdAt": created,
            "tracks": manifest_tracks,
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for arcname, src in staged:
                # JSON komprimieren; Audio ist schon komprimiert (AAC) bzw. bei
                # WAV-Fallback zu gross, als dass DEFLATE viel braechte -> STORED
                zf.write(
                    src, arcname,
                    compress_type=zipfile.ZIP_DEFLATED if arcname.endswith(".json")
                    else zipfile.ZIP_STORED,
                )
    finally:
        shutil.rmtree(work, ignore_errors=True)

    size_kb = out_path.stat().st_size / 1024
    print(f"song.ksong: {len(manifest_tracks)} Stimme(n), {size_kb:.0f} KB -> {out_path}")
    return out_path
