"""
Kanon-Generator: "Bruder Jakob" als mehrstimmiges .ksong (Vertical Slice:
weiteres Mehrstimmen-Beispiel neben Vom_Fluegel, diesmal OHNE Fremdmaterial).

Warum kein Audio-Import wie bei convert_choir.py: fuer eine belastbare
Wort-zu-Ton-Zuordnung braucht convert_choir.py entweder echte Gesangsspuren
(Forced Alignment) oder MIDI mit eingebetteten Lyrics-Events (convert_midi.py).
Fuer "Bruder Jakob" gibt es beides frei verfuegbar nur als MIDI-gerenderte
Chor-Uebungsdateien ohne Lyrics-Events - die Wort/Ton-Zuordnung liesse sich
nur schaetzen. Weil die Melodie denkbar einfach ist (ein Kanon: alle Stimmen
singen dieselbe, gemeinfreie Melodie, nur zeitversetzt), wird sie hier direkt
Silbe-fuer-Silbe von Hand kodiert - exakt statt geschaetzt, ganz ohne Download.

Baut N Stimmen, jede singt dieselbe Melodie, Stimme i startet i*OFFSET_BEATS
Schlaege spaeter (klassischer Kanon-Einsatz "nach der ersten Zeile"). Synth
und Notenlaenge wiederverwendet aus convert_midi.py (_tone/_adsr/SR).

Nutzung:
    venv\\Scripts\\activate
    python build_round.py
"""

from pathlib import Path

import numpy as np
import soundfile as sf

from convert_midi import SR, _tone, midi_to_note_name
from ksong import write_ksong

BPM = 100
BEAT = 60.0 / BPM          # Sekunden pro Viertel/Silbe
OFFSET_BEATS = 8           # Stimme i setzt i*OFFSET_BEATS spaeter ein (= 1. Zeile)
N_LOOPS = 2                # jede Stimme singt die Melodie 2x durch
PROGRAM = 52                # GM "Choir Aahs"-Bereich -> gehaltener, weicher Ton (siehe _harmonics in convert_midi.py)
VEL = 100

# (Zeilentext, [(Silbe, MIDI-Note, Wortende?), ...]) - jede Silbe = 1 Schlag.
PHRASES: list[tuple[str, list[tuple[str, int, bool]]]] = [
    ("Bruder Jakob,", [("Bru", 60, False), ("der", 62, True), ("Ja", 64, False), ("kob", 60, True)]),
    ("Bruder Jakob,", [("Bru", 60, False), ("der", 62, True), ("Ja", 64, False), ("kob", 60, True)]),
    ("schläfst du noch?", [("schläfst", 64, True), ("du", 65, True), ("noch", 67, True)]),
    ("schläfst du noch?", [("schläfst", 64, True), ("du", 65, True), ("noch", 67, True)]),
    ("Hörst du nicht die Glocken?", [("Hörst", 67, True), ("du", 69, True), ("nicht", 67, True),
                                      ("die", 65, True), ("Glo", 64, False), ("cken", 60, True)]),
    ("Hörst du nicht die Glocken?", [("Hörst", 67, True), ("du", 69, True), ("nicht", 67, True),
                                      ("die", 65, True), ("Glo", 64, False), ("cken", 60, True)]),
    ("Ding, dang, dong!", [("Ding", 60, True), ("dang", 55, True), ("dong", 60, True)]),
    ("Ding, dang, dong!", [("Ding", 60, True), ("dang", 55, True), ("dong", 60, True)]),
]

LOOP_BEATS = sum(len(syllables) for _, syllables in PHRASES)  # = 32


def build_voice_lyrics(offset_beats: int) -> list[dict]:
    """lyrics.json-Zeilen fuer eine Stimme, N_LOOPS Durchlaeufe, um offset_beats verschoben."""
    lines: list[dict] = []
    for loop in range(N_LOOPS):
        beat = offset_beats + loop * LOOP_BEATS
        for line_text, syllables in PHRASES:
            words = []
            for syll, midi, word_end in syllables:
                start = round(beat * BEAT, 3)
                end = round(start + BEAT * 0.9, 3)
                text = syll if word_end else syll + "-"
                words.append({"word": text, "start": start, "end": end,
                              "midi": midi, "note": midi_to_note_name(midi)})
                beat += 1
            lines.append({"line": line_text, "start": words[0]["start"],
                          "end": words[-1]["end"], "words": words})
    return lines


def render_voice_audio(offset_beats: int, total_beats: int) -> np.ndarray:
    buf = np.zeros(int((total_beats * BEAT + 1.0) * SR), dtype=np.float32)
    for loop in range(N_LOOPS):
        beat = offset_beats + loop * LOOP_BEATS
        for _line_text, syllables in PHRASES:
            for _syll, midi, _word_end in syllables:
                start = int(beat * BEAT * SR)
                length = int(BEAT * 0.9 * SR)
                wave = _tone(midi, length, PROGRAM, VEL)
                end = min(start + len(wave), len(buf))
                buf[start:end] += wave[:end - start]
                beat += 1
    peak = float(np.max(np.abs(buf)))
    if peak > 0:
        buf = (buf / peak) * 0.85
    return buf


def build(out_dir: Path, n_voices: int = 3) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    total_beats = (n_voices - 1) * OFFSET_BEATS + N_LOOPS * LOOP_BEATS

    tracks = []
    for i in range(n_voices):
        name = f"Stimme {i + 1}"
        offset_beats = i * OFFSET_BEATS
        print(f"--- {name} (Einsatz bei Schlag {offset_beats}, "
              f"{offset_beats * BEAT:.1f}s) ---")

        track_dir = out_dir / "tracks" / name
        track_dir.mkdir(parents=True, exist_ok=True)

        audio = render_voice_audio(offset_beats, total_beats)
        audio_path = track_dir / "audio.wav"
        sf.write(audio_path, audio, SR)

        lyrics = build_voice_lyrics(offset_beats)
        lyrics_path = track_dir / "lyrics.json"
        import json
        lyrics_path.write_text(json.dumps(lyrics, ensure_ascii=False, indent=2), encoding="utf-8")

        tracks.append({"name": name, "audio": audio_path, "lyrics": lyrics_path})

    title = "Bruder Jakob (Kanon)"
    voice_names = ",".join(t["name"] for t in tracks)
    curl_parts = [
        "curl -X POST http://localhost:8080/api/songs/multitrack",
        '  -F "_charset_=UTF-8"',
        f'  -F "title={title}"',
        f'  -F "voiceNames={voice_names}"',
    ]
    for t in tracks:
        curl_parts.append(f'  -F "audio_{t["name"]}=@{t["audio"]}"')
        curl_parts.append(f'  -F "lyrics_{t["name"]}=@{t["lyrics"]}"')
    (out_dir / "register.sh").write_text(" \\\n".join(curl_parts) + "\n", encoding="utf-8")

    write_ksong(out_dir / "song.ksong", title, tracks)
    print(f"\nFertig. {n_voices} Stimmen, Gesamtlaenge {total_beats * BEAT:.1f}s.")
    print(f"Artefakte in {out_dir}/, Registrier-Befehl in {out_dir / 'register.sh'}")


if __name__ == "__main__":
    build(Path("output/bruder-jakob"))
