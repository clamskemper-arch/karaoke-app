"""
MIDI/Karaoke-MIDI -> Karaoke-App-Artefakte (Alternative zu convert.py)

Anders als convert.py (rohe Audioaufnahme -> Demucs/pYIN/Forced Alignment)
nimmt dieses Skript eine MIDI-Datei und liest Noten, Timing und Songtext
direkt aus den Events. Ergebnis ist praeziser als der Audio-Weg: die
Zieltoene kommen aus echten Note-Events statt aus einer geschaetzten
Pitch-Kurve, das Timing aus der Tempo-Map statt aus CTC-Alignment.

Erzeugt denselben Contract wie convert.py:
    instrumental.wav   - alle Spuren ausser der Gesangs-/Melodiespur, mit
                          einem eingebauten kleinen Synth gerendert (kein
                          FluidSynth/SoundFont noetig - klingt synthetisch,
                          reicht als Karaoke-Backing)
    lyrics.json        - Zeilen mit words[]: ein Eintrag pro Silbe UND pro
                          Melodienote (mehrsilbige Woerter / gehaltene Toene
                          behalten so ihre Tonbewegung), je start/end/midi/note

Erkennung der Gesangsspur (in dieser Reihenfolge):
    1. --lyrics-track N  (explizit)
    2. Spur mit den meisten "lyrics"-Meta-Events
    3. Spur mit Noten, deren Name auf vocal/melody/lead/voice/sopran/... passt
    4. Soft-Karaoke: getrennte "Words"-Textspur (@T/@L, \\ und / als Umbruch)
Bricht mit klarer Meldung ab, wenn nichts davon greift.

Nutzung:
    venv\\Scripts\\activate
    python convert_midi.py "input/amazing-grace.kar" "output/amazing-grace"
    python convert_midi.py in.mid out/ --lyrics-track 3 --keep-backing-vocals
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

import mido
import numpy as np
import soundfile as sf

from ksong import write_ksong

SR = 44100
NEW_LINE = object()  # Marker im Silben-Strom fuer "neue Zeile"

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_to_note_name(midi: int) -> str:
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


# ---------------------------------------------------------------------------
# Tempo-Map: absolute Ticks -> Sekunden
# ---------------------------------------------------------------------------

def build_tick2sec(mid: mido.MidiFile):
    """Sammelt alle set_tempo-Events (koennen in jeder Spur stehen) und baut
    eine Funktion abs_tick -> Sekunden, die ueber die Tempo-Segmente
    integriert. Kleine Ritardando-Rampen (viele Mini-Events) sind damit
    korrekt abgebildet."""
    tpb = mid.ticks_per_beat
    changes = []
    for track in mid.tracks:
        t = 0
        for msg in track:
            t += msg.time
            if msg.type == "set_tempo":
                changes.append((t, msg.tempo))
    changes.sort(key=lambda c: c[0])

    cleaned = [(0, 500000)]  # Default 120 BPM bis zum ersten echten Event
    for tick, tempo in changes:
        if cleaned[-1][0] == tick:
            cleaned[-1] = (tick, tempo)
        else:
            cleaned.append((tick, tempo))

    cum = [0.0]
    for i in range(1, len(cleaned)):
        prev_tick, prev_tempo = cleaned[i - 1]
        gap = cleaned[i][0] - prev_tick
        cum.append(cum[-1] + mido.tick2second(gap, tpb, prev_tempo))

    def tick2sec(abs_tick: int) -> float:
        idx = 0
        for i, (ct, _) in enumerate(cleaned):
            if ct <= abs_tick:
                idx = i
            else:
                break
        ct, tempo = cleaned[idx]
        return cum[idx] + mido.tick2second(abs_tick - ct, tpb, tempo)

    return tick2sec


# ---------------------------------------------------------------------------
# Noten + Programme je Spur
# ---------------------------------------------------------------------------

def extract_notes(track) -> list[dict]:
    """note_on/note_off-Paare einer Spur zu {start_tick,end_tick,midi,vel,channel}."""
    notes = []
    active = {}
    t = 0
    for msg in track:
        t += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            active.setdefault((msg.channel, msg.note), []).append((t, msg.velocity))
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            stack = active.get((msg.channel, msg.note))
            if stack:
                start, vel = stack.pop(0)
                notes.append({
                    "start_tick": start, "end_tick": max(t, start + 1),
                    "midi": msg.note, "vel": vel, "channel": msg.channel,
                })
    notes.sort(key=lambda n: n["start_tick"])
    return notes


def channel_programs(mid: mido.MidiFile) -> dict[int, int]:
    """Letztes program_change je Kanal (grob - fuer den Mini-Synth reicht das)."""
    prog = {}
    for track in mid.tracks:
        for msg in track:
            if msg.type == "program_change":
                prog[msg.channel] = msg.program
    return prog


# ---------------------------------------------------------------------------
# Gesangsspur finden
# ---------------------------------------------------------------------------

NAME_HINT = re.compile(r"vocal|melody|lead|voice|sing|sopran|soprano|alt|alto|tenor|bass|cantus", re.I)


def count_lyric_events(track) -> int:
    return sum(1 for m in track if m.type == "lyrics" and not m.text.startswith("@"))


def find_lyrics_track(mid: mido.MidiFile, forced: int | None) -> int:
    if forced is not None:
        if not (0 <= forced < len(mid.tracks)):
            sys.exit(f"--lyrics-track {forced} out of range (0..{len(mid.tracks) - 1})")
        return forced

    by_lyrics = [(count_lyric_events(t), i) for i, t in enumerate(mid.tracks)]
    best_n, best_i = max(by_lyrics)
    if best_n >= 3:
        return best_i

    for i, t in enumerate(mid.tracks):
        name = next((m.name for m in t if m.type == "track_name"), "")
        if NAME_HINT.search(name) and extract_notes(t):
            return i

    words_idx = _soft_karaoke_words_track(mid)
    if words_idx is not None:
        return words_idx

    sys.exit(
        "Keine Gesangsspur gefunden. Bitte --lyrics-track N angeben "
        "(N = Index der Spur mit der Melodie/dem Text)."
    )


def _soft_karaoke_words_track(mid: mido.MidiFile) -> int | None:
    for i, t in enumerate(mid.tracks):
        texts = [m.text for m in t if m.type == "text"]
        if any(x.startswith("@T") or x.startswith("@L") for x in texts) and len(texts) > 5:
            return i
    return None


# ---------------------------------------------------------------------------
# Silben -> Zeilen  (bewusst KEINE Zusammenfassung zu Woertern: jede Silbe /
# jede Melodienote bekommt einen eigenen words[]-Eintrag, sonst geht die
# Tonbewegung innerhalb mehrsilbiger Woerter verloren - "A-ma-zing" liegt
# z.B. auf A#3->D#4->G4)
# ---------------------------------------------------------------------------

def extract_syllables(track) -> list:
    """Strom aus (tick, text) und NEW_LINE-Markern. Deckt beide Formate ab:
    echte 'lyrics'-Events mit \\r/\\n als Umbruch, und die Soft-Karaoke
    'text'-Variante (@T/@L Kopf, fuehrendes \\ oder / = Umbruch)."""
    out = []
    t = 0
    for msg in track:
        t += msg.time
        if msg.type not in ("lyrics", "text"):
            continue
        raw = msg.text
        if raw.startswith("@"):
            continue
        if raw in ("\r", "\n", "\r\n", "\r\r", "\n\n"):
            out.append((t, NEW_LINE))
            continue
        s = raw.replace("\r\n", "\n").replace("\r", "\n")
        while s.startswith(("\\", "/", "\n")):
            out.append((t, NEW_LINE))
            s = s[1:]
        s = s.replace("\n", " ")
        if s != "":
            out.append((t, s))
    return out


_WORD_END_PUNCT = (".", ",", ";", ":", "!", "?", '"', ")")


def group_syllables(syllables: list) -> list[list[dict]]:
    """Silben in Zeilen gruppieren (NEW_LINE-Marker). Jede Silbe:
    {text, tick, word_end}. word_end=True, wenn das Roh-Fragment mit
    Leerzeichen oder Satzzeichen endet - daran haengt spaeter nur die
    Darstellung (Bindestrich an Nicht-Wortenden, lesbare line-Zeile)."""
    lines: list[list[dict]] = []
    cur: list[dict] = []

    def close_line():
        if cur:
            cur[-1]["word_end"] = True  # Zeilenende ist immer auch Wortende
            lines.append(cur[:])
            cur.clear()

    for tick, text in syllables:
        if text is NEW_LINE:
            close_line()
            continue
        word_end = text.endswith((" ", "\t")) or text.rstrip().endswith(_WORD_END_PUNCT)
        frag = text.strip()
        if not frag:
            if cur:
                cur[-1]["word_end"] = True
            continue
        cur.append({"text": frag, "tick": tick, "word_end": word_end})
    close_line()
    return lines


# ---------------------------------------------------------------------------
# Woerter an Melodienoten haengen -> lyrics.json
# ---------------------------------------------------------------------------

def nearest_note(notes: list[dict], tick: int, tpb: int) -> dict | None:
    if not notes:
        return None
    best = min(notes, key=lambda n: abs(n["start_tick"] - tick))
    if abs(best["start_tick"] - tick) > tpb * 2:  # mehr als 2 Schläge daneben -> kein Treffer
        return None
    return best


def _assign_notes_to_syllables(syl_lines: list[list[dict]], melody: list[dict], tpb: int) -> dict:
    """Jede Melodienote der spaetesten Silbe zuordnen, die nicht nennenswert
    nach der Note beginnt. Silben mit mehr als einer Note = Melisma."""
    flat = [s for line in syl_lines for s in line]
    flat.sort(key=lambda s: s["tick"])
    tol = tpb // 4
    buckets: dict[int, list[dict]] = {id(s): [] for s in flat}
    for n in melody:
        cand = [s for s in flat if s["tick"] <= n["start_tick"] + tol]
        if cand:
            buckets[id(cand[-1])].append(n)
    for b in buckets.values():
        b.sort(key=lambda n: n["start_tick"])
    return buckets


def build_lyrics_json(syl_lines: list[list[dict]], melody: list[dict], tick2sec, tpb: int) -> list[dict]:
    buckets = _assign_notes_to_syllables(syl_lines, melody, tpb)
    result = []
    for sylls in syl_lines:
        entries = []
        for s in sylls:
            notes = buckets[id(s)] or ([nearest_note(melody, s["tick"], tpb)] if melody else [])
            notes = [n for n in notes if n]
            for i, n in enumerate(notes):
                if i == 0:
                    text = s["text"] if s["word_end"] else s["text"] + "-"
                else:
                    text = "—"  # gehaltener Ton (Melisma) - eigene Note, kein neuer Text
                start = round(tick2sec(n["start_tick"]), 2)
                end = round(tick2sec(n["end_tick"]), 2)
                if end <= start:
                    end = round(start + 0.15, 2)
                entries.append({
                    "word": text,
                    "start": start,
                    "end": end,
                    "midi": n["midi"],
                    "note": midi_to_note_name(n["midi"]),
                })
        if not entries:
            continue
        readable = "".join(s["text"] + (" " if s["word_end"] else "") for s in sylls).strip()
        result.append({
            "line": readable,
            "start": entries[0]["start"],
            "end": entries[-1]["end"],
            "words": entries,
        })
    return result


# ---------------------------------------------------------------------------
# Mini-Synth (kein FluidSynth noetig)
# ---------------------------------------------------------------------------

def _adsr(length: int, a=0.008, d=0.12, s=0.6, r=0.10) -> np.ndarray:
    env = np.ones(length, dtype=np.float32)
    ai = min(int(a * SR), length)
    di = min(int(d * SR), max(length - ai, 0))
    ri = min(int(r * SR), max(length - ai - di, 0))
    if ai:
        env[:ai] = np.linspace(0, 1, ai)
    if di:
        env[ai:ai + di] = np.linspace(1, s, di)
    env[ai + di:length - ri] = s
    if ri:
        env[length - ri:] = np.linspace(s, 0, ri)
    return env


def _harmonics(program: int):
    if 0 <= program <= 15:          # Klavier / chromatische Perkussion
        return [(1, 1.0), (2, 0.45), (3, 0.2)], True
    if 16 <= program <= 23:         # Orgel
        return [(1, 1.0), (2, 0.7), (3, 0.5), (4, 0.3)], False
    if 24 <= program <= 31:         # Gitarre
        return [(1, 1.0), (2, 0.4), (3, 0.18)], True
    if 32 <= program <= 39:         # Bass
        return [(1, 1.0), (2, 0.25)], True
    if 40 <= program <= 55:         # Streicher / Ensemble
        return [(1, 1.0), (2, 0.6), (3, 0.4), (5, 0.15)], False
    return [(1, 1.0), (2, 0.3)], True


def _tone(midi: int, length: int, program: int, vel: int) -> np.ndarray:
    f = 440.0 * 2 ** ((midi - 69) / 12.0)
    t = np.arange(length, dtype=np.float32) / SR
    harm, decayed = _harmonics(program)
    sig = np.zeros(length, dtype=np.float32)
    for k, amp in harm:
        sig += amp * np.sin(2 * np.pi * f * k * t)
    env = np.exp(-3.2 * t).astype(np.float32) if decayed else _adsr(length)
    return sig * env * (vel / 127.0) * 0.28


def _drum(midi: int, length: int) -> np.ndarray:
    t = np.arange(length, dtype=np.float32) / SR
    if midi in (35, 36):                       # Kick
        f = 120.0 * np.exp(-30 * t) + 45.0
        ph = 2 * np.pi * np.cumsum(f) / SR
        return (np.sin(ph) * np.exp(-13 * t) * 0.9).astype(np.float32)
    if midi in (38, 40):                       # Snare
        noise = np.random.uniform(-1, 1, length).astype(np.float32)
        body = np.sin(2 * np.pi * 190 * t).astype(np.float32)
        return ((noise * np.exp(-24 * t) + body * np.exp(-18 * t)) * 0.45).astype(np.float32)
    if midi in (42, 44, 46, 49, 51, 57, 59):   # Hi-Hat / Becken
        noise = np.random.uniform(-1, 1, length).astype(np.float32)
        return (noise * np.exp(-42 * t) * 0.33).astype(np.float32)
    noise = np.random.uniform(-1, 1, length).astype(np.float32)
    return (noise * np.exp(-30 * t) * 0.3).astype(np.float32)


def render_instrumental(events: list[dict], total_sec: float) -> np.ndarray:
    np.random.seed(0)  # Drum-Rauschen reproduzierbar machen
    buf = np.zeros(int(math.ceil(total_sec * SR)) + SR, dtype=np.float32)
    for ev in events:
        start = int(ev["start"] * SR)
        length = max(int((ev["end"] - ev["start"]) * SR), int(0.05 * SR))
        wave = _drum(ev["midi"], length) if ev["channel"] == 9 else \
            _tone(ev["midi"], length, ev["program"], ev["vel"])
        end = min(start + len(wave), len(buf))
        buf[start:end] += wave[:end - start]
    peak = float(np.max(np.abs(buf)))
    if peak > 0:
        buf = (buf / peak) * 0.89
    return buf


# ---------------------------------------------------------------------------
# Orchestrierung
# ---------------------------------------------------------------------------

def convert(input_path: Path, out_dir: Path, forced_track: int | None, keep_backing: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    mid = mido.MidiFile(input_path)
    tpb = mid.ticks_per_beat
    tick2sec = build_tick2sec(mid)
    programs = channel_programs(mid)

    lyr_idx = find_lyrics_track(mid, forced_track)
    lyr_track = mid.tracks[lyr_idx]
    lyr_name = next((m.name for m in lyr_track if m.type == "track_name"), f"Track {lyr_idx}")
    print(f"Gesangsspur: [{lyr_idx}] {lyr_name!r}")

    melody = extract_notes(lyr_track)
    syllables = extract_syllables(lyr_track)
    if not syllables:
        # Text steht in einer separaten Soft-Karaoke-"Words"-Spur
        words_idx = _soft_karaoke_words_track(mid)
        if words_idx is not None:
            print(f"  Text aus separater Spur [{words_idx}] {mid.tracks[words_idx].name!r}")
            syllables = extract_syllables(mid.tracks[words_idx])
    if not melody or not syllables:
        sys.exit(f"Spur [{lyr_idx}] hat {len(melody)} Noten / {len(syllables)} Silben - zu wenig.")

    syl_lines = group_syllables(syllables)
    lyrics = build_lyrics_json(syl_lines, melody, tick2sec, tpb)
    (out_dir / "lyrics.json").write_text(json.dumps(lyrics, ensure_ascii=False, indent=2), encoding="utf-8")
    n_notes = sum(len(l["words"]) for l in lyrics)
    n_melisma = sum(1 for l in lyrics for w in l["words"] if w["word"] == "—")
    print(f"lyrics.json: {len(lyrics)} Zeilen, {n_notes} Silben-/Ton-Eintraege "
          f"(davon {n_melisma} gehaltene Toene) "
          f"({lyrics[0]['start']:.1f}s .. {lyrics[-1]['end']:.1f}s)")

    # Backing: alle Spuren ausser der Gesangsspur (optional inkl. Begleit-Gesang)
    skip = {lyr_idx}
    if not keep_backing:
        for i, t in enumerate(mid.tracks):
            name = next((m.name for m in t if m.type == "track_name"), "")
            if i != lyr_idx and re.search(r"backup|backing|harmony|choir|vox", name, re.I):
                skip.add(i)
                print(f"  Backing-Gesang uebersprungen: [{i}] {name!r} (--keep-backing-vocals zum Behalten)")

    events = []
    for i, track in enumerate(mid.tracks):
        if i in skip:
            continue
        for n in extract_notes(track):
            events.append({
                "start": tick2sec(n["start_tick"]),
                "end": tick2sec(n["end_tick"]),
                "midi": n["midi"],
                "vel": n["vel"],
                "channel": n["channel"],
                "program": programs.get(n["channel"], 0),
            })
    if not events:
        sys.exit("Keine Backing-Noten uebrig - Song besteht nur aus der Gesangsspur?")

    total = max(e["end"] for e in events + [{"end": lyrics[-1]["end"]}])
    print(f"instrumental.wav: {len(events)} Noten aus {len(mid.tracks) - len(skip)} Spuren rendern ...")
    audio = render_instrumental(events, total)
    sf.write(out_dir / "instrumental.wav", audio, SR)
    print(f"  {len(audio) / SR:.1f}s @ {SR} Hz")

    title = _guess_title(mid, input_path)
    curl = (
        f'curl -X POST http://localhost:8080/api/songs \\\n'
        f'  -F "_charset_=UTF-8" \\\n'  # Umlaute im Titel sonst als ISO-8859-1 dekodiert
        f'  -F "title={title}" \\\n'
        f'  -F "instrumental=@{out_dir / "instrumental.wav"}" \\\n'
        f'  -F "lyrics=@{out_dir / "lyrics.json"}"'
    )
    (out_dir / "register.sh").write_text(curl + "\n", encoding="utf-8")

    # .ksong-Bundle fuer den Offline-Import in die App (siehe ksong.py)
    write_ksong(
        out_dir / "song.ksong",
        title,
        [{"name": "Gesang", "audio": out_dir / "instrumental.wav",
          "lyrics": out_dir / "lyrics.json"}],
    )

    print(f"\nFertig. Artefakte in {out_dir}/")
    print(f"Registrieren (steht auch in {out_dir / 'register.sh'}):\n\n{curl}")


def _guess_title(mid: mido.MidiFile, input_path: Path) -> str:
    # Soft-Karaoke @T-Zeilen (erste ist der Titel, weitere sind Interpret/Credits)
    for track in mid.tracks:
        for m in track:
            if m.type == "text" and m.text.startswith("@T"):
                cand = m.text[2:].strip()
                low = cand.lower()
                if cand and "midi" not in low and "sequence" not in low and "by " not in low:
                    return cand.title() if cand.isupper() else cand
    # sonst der erste sinnvolle Spurname (Soft-Karaoke-Steuerspuren ausblenden)
    for track in mid.tracks:
        for m in track:
            if m.type == "track_name":
                name = m.name.strip()
                if name and name.lower() not in ("soft karaoke", "words", "melody", "backup melody"):
                    return name
    return input_path.stem.replace("-", " ").replace("_", " ").title()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="MIDI-/Karaoke-MIDI-Datei (.mid/.kar)")
    parser.add_argument("output", type=Path, help="Ausgabeordner fuer die Artefakte")
    parser.add_argument("--lyrics-track", type=int, default=None,
                        help="Index der Gesangs-/Melodiespur (sonst automatisch erkannt)")
    parser.add_argument("--keep-backing-vocals", action="store_true",
                        help="Begleit-Gesangsspuren (Backup/Harmony/Choir) im Instrumental behalten")
    args = parser.parse_args()
    convert(args.input, args.output, args.lyrics_track, args.keep_backing_vocals)
