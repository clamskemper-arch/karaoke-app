"""
Mehrstimmen-Konvertierung fuer Chorlieder (Vertical Slice 5, Teil 2)

Anders als convert.py fuer normale Songs macht dieses Skript KEINE
Vocal-Separation (Demucs): die Eingabe ist pro Stimme schon ein sauber
isolierter Audio-Export aus einer Notensatz-Software (z.B. MuseScore) - siehe
Align-Entscheidung in der Projekt-Notiz vom 01.09.2026. Automatische Trennung
einzelner Chorstimmen aus einer Gesamtaufnahme ist bewusst NICHT das Ziel
dieses Skripts (mit heutiger Technik nicht zuverlaessig moeglich).

Fuer jede Stimme mit bekanntem Text (z.B. Sopran/Alt/Tenor/Bass): Pitch-Kurve
(pYIN) + Forced Alignment wie in convert.py, macht daraus lyrics.json mit
Ton pro Wort. Fuer reine Begleitstimmen ohne Text (z.B. Klavier): Audio wird
nur nach WAV konvertiert, kein lyrics.json (Pitch-Erkennung auf polyphonem
Klavier waere ohnehin nicht sinnvoll).

Erwartet eine JSON-Konfigurationsdatei mit Titel + Stimmenliste, siehe Beispiel
unten. Ausgabe liegt direkt passend fuer POST /api/songs/multitrack (Ordner
output/tracks/{Stimme}/) - inkl. eines fertigen curl-Befehls in register.sh,
damit die Registrierung nicht von Hand zusammengebaut werden muss.

Nutzung:
    venv\\Scripts\\activate
    python convert_choir.py "input/lied.json" "output/lied"

Beispiel-Konfigurationsdatei (input/lied.json):
{
  "title": "Ave Verum Corpus",
  "voices": [
    {"name": "Klavier", "audio": "input/lied/klavier.wav"},
    {"name": "Sopran",  "audio": "input/lied/sopran.wav",  "lyrics": "input/lied/text.txt"},
    {"name": "Alt",     "audio": "input/lied/alt.wav",     "lyrics": "input/lied/text.txt"},
    {"name": "Tenor",   "audio": "input/lied/tenor.wav",   "lyrics": "input/lied/text.txt"},
    {"name": "Bass",    "audio": "input/lied/bass.wav",    "lyrics": "input/lied/text.txt"}
  ]
}

"voices" ohne "lyrics" (wie Klavier oben) werden als reine Begleitstimme
behandelt. "lyrics" darf fuer mehrere Stimmen auf dieselbe Textdatei zeigen,
wenn der Text (wie bei Chorsaetzen ueblich) fuer alle Stimmen gleich ist -
Forced Alignment laeuft trotzdem pro Stimme separat, weil Timing/Betonung
zwischen den Stimmen leicht abweichen kann.
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from convert import align_known_lyrics, attach_notes, extract_pitch_curve
from ksong import write_ksong


def ensure_wav(src: Path, dst: Path) -> None:
    """Kopiert/konvertiert eine Audiodatei nach WAV. Notensatz-Exporte sind meist
    schon WAV - falls nicht (z.B. mp3), per ffmpeg konvertieren (muss im PATH sein,
    siehe Projekt-Notiz zum ffmpeg-PATH-Stolperstein bei frischer Shell)."""
    if src.suffix.lower() == ".wav":
        shutil.copyfile(src, dst)
    else:
        subprocess.run(["ffmpeg", "-y", "-i", str(src), str(dst)], check=True)


def convert_voice(name: str, audio_path: Path, lyrics_path: Path | None, out_dir: Path) -> dict:
    track_dir = out_dir / "tracks" / name
    track_dir.mkdir(parents=True, exist_ok=True)
    audio_dst = track_dir / "audio.wav"

    print(f"--- Stimme '{name}' ---")
    ensure_wav(audio_path, audio_dst)

    if lyrics_path is None:
        print("    keine Lyrics angegeben - reine Begleitstimme, nur Audio konvertiert")
        return {"name": name, "audio": audio_dst, "lyrics": None}

    # Kein Demucs-Schritt: die Datei ist schon eine isolierte Einzelstimme,
    # direkt fuer Pitch-Kurve + Forced Alignment verwenden (wie sonst vocals.wav).
    pitch_curve = extract_pitch_curve(audio_dst)
    lines = align_known_lyrics(audio_dst, lyrics_path)
    lines = attach_notes(lines, pitch_curve)

    lyrics_dst = track_dir / "lyrics.json"
    lyrics_dst.write_text(json.dumps(lines, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    fertig: {len(lines)} Zeilen")
    return {"name": name, "audio": audio_dst, "lyrics": lyrics_dst}


def build_register_command(title: str, results: list[dict]) -> str:
    """Baut den curl-Befehl fuer POST /api/songs/multitrack aus den erzeugten
    Artefakten - passend zum Contract in SongController.java."""
    voice_names = ",".join(r["name"] for r in results)
    parts = [
        "curl -X POST http://localhost:8080/api/songs/multitrack",
        '  -F "_charset_=UTF-8"',  # sonst dekodiert der Servlet-Container Umlaute im Titel als ISO-8859-1
        f'  -F "title={title}"',
        f'  -F "voiceNames={voice_names}"',
    ]
    for r in results:
        parts.append(f'  -F "audio_{r["name"]}=@{r["audio"]}"')
        if r["lyrics"]:
            parts.append(f'  -F "lyrics_{r["name"]}=@{r["lyrics"]}"')
    return " \\\n".join(parts)


def convert_choir(config_path: Path, out_dir: Path) -> None:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    title = config["title"]
    voices = config["voices"]
    if not voices:
        raise ValueError("Konfiguration braucht mindestens eine Stimme in 'voices'")
    if not any(v.get("lyrics") for v in voices):
        raise ValueError("Mindestens eine Stimme braucht 'lyrics' - sonst gibt's nichts zum Mitsingen "
                          "(gleiche Regel wie beim /multitrack-Endpunkt im Backend)")

    out_dir.mkdir(parents=True, exist_ok=True)
    results = [
        convert_voice(
            voice["name"],
            Path(voice["audio"]),
            Path(voice["lyrics"]) if voice.get("lyrics") else None,
            out_dir,
        )
        for voice in voices
    ]

    curl_cmd = build_register_command(title, results)
    (out_dir / "register.sh").write_text(curl_cmd + "\n", encoding="utf-8")

    # .ksong-Bundle fuer den Offline-Import in die App (siehe ksong.py)
    write_ksong(
        out_dir / "song.ksong",
        title,
        [{"name": r["name"], "audio": r["audio"], "lyrics": r["lyrics"]} for r in results],
    )

    print(f"\nFertig. Artefakte in {out_dir}/tracks/<Stimme>/")
    print(f"Registrier-Befehl steht in {out_dir / 'register.sh'} - einfach ausfuehren:\n")
    print(curl_cmd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", type=Path, help="JSON-Konfigurationsdatei mit Titel + Stimmenliste")
    parser.add_argument("output", type=Path, help="Ausgabeordner fuer die Artefakte")
    args = parser.parse_args()
    convert_choir(args.config, args.output)
