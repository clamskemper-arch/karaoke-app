"""
MusicXML-Chorsatz (SATB + Klavier) -> Karaoke-App-Artefakte

Dritter Konverter-Weg neben convert.py (rohe Aufnahme) und convert_midi.py
(Karaoke-MIDI): nimmt eine .mxl/.musicxml-Notensatzdatei mit mehreren
<part>-Elementen (z.B. Export aus MuseScore) und liest Noten, Timing UND
Songtext direkt aus dem Notensatz - keine Audioaufnahme, kein Forced
Alignment noetig, keine Pitch-Erkennung noetig. Praeziser als beide anderen
Wege, weil sowohl Ton als auch Text aus derselben Quelle (den <note>-
Elementen) kommen statt aus zwei separaten Dateien gematcht werden zu
muessen (Versuche, ein separates .mid + .mxl ueber die Notenreihenfolge zu
matchen, sind an kleinen Diskrepanzen - Stimmen mit divisi/Nebenstimme
("voice 2"), Bindebogen-Behandlung - gescheitert, siehe Session-Notiz).

Erwartet pro Stimme ein eigenes <part> mit eigenem <part-name> (Sopran/Alt/
Tenor/Bass/...) - <lyric>-Elemente direkt an den Noten liefern den Text,
Bindeboegen (<tie>) werden zu einer Note zusammengefasst, Melisma-Noten
(eigene Tonhoehe, aber kein eigenes <lyric>) bekommen wie bei convert_midi.py
einen eigenen "—"-Eintrag, damit die Tonbewegung sichtbar bleibt. Strophe
wird per --verse gewaehlt (Default 1) - mehrere Strophen auf denselben Noten
sind in MusicXML normal, die App spielt aber nur eine Strophe pro Song.

Begleitstimmen ohne Text (z.B. Klavier) werden wie bei convert_midi.py mit
einem eingebauten Mini-Synth gerendert (kein FluidSynth/SoundFont noetig).
Fuer die Melodiestimmen wird zusaetzlich eine eigene Audiospur gerendert
(ihre eigene Linie, damit der Mehrstimmen-Mixer im Frontend sie einzeln
h�rbar machen kann) - anders als bei convert_choir.py, wo diese Datei aus
einer echten Aufnahme kommt.

Nutzung:
    venv\\Scripts\\activate
    python convert_musicxml_choir.py "input/lied/lied.mxl" "output/lied"
    python convert_musicxml_choir.py in.mxl out/ --verse 2 --title "..." \\
        --voices Sopran,Alt,Tenor,Bass --piano-part Klavier
"""

import argparse
import json
import re
import sys
import zipfile
from fractions import Fraction
from pathlib import Path
import xml.etree.ElementTree as ET

import soundfile as sf

from convert_choir import build_register_command
from convert_midi import SR, midi_to_note_name, render_instrumental
from ksong import write_ksong

STEP_SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
VERSE_MARKER = re.compile(r"^\d+\.$")


def pitch_to_midi(pitch_el) -> int:
    step = pitch_el.find("step").text
    octave = int(pitch_el.find("octave").text)
    alter_el = pitch_el.find("alter")
    alter = int(float(alter_el.text)) if alter_el is not None else 0
    return (octave + 1) * 12 + STEP_SEMITONE[step] + alter


# ---------------------------------------------------------------------------
# Ein <part> ablaufen: Cursor in Viertelnoten (divisions-normalisiert, exakt
# per Fraction statt float - bei hunderten Additionen sonst Rundungsdrift).
# backup/forward spulen den Cursor zurueck/vor (mehrere Stimmen/Systeme je
# Part), chord-Noten teilen sich die Startzeit der vorherigen Note.
# ---------------------------------------------------------------------------

def walk_part(part_el, verse: str = "1"):
    """Liefert zwei Listen: notes (dicts je <note>, inkl. Pausen) und
    tempos (Cursor-Position in Viertelnoten, BPM) - beide in Dokument-
    reihenfolge. measure_number haengt an jeder Note fuer die Zeilenerkennung
    per Systemumbruch (<print new-system="yes">). Ein <note> kann mehrere
    <lyric number="N"> fuer mehrere Strophen tragen - es zaehlt nur die zu
    `verse` passende (fuer Stimmen/Parts ohne Text, z.B. Klavier, ist das
    ohnehin egal, da findet find() dann einfach nichts)."""
    divisions = None
    cursor = Fraction(0)
    notes = []
    tempos = []
    for measure in part_el.findall("measure"):
        mnum = measure.get("number")
        pr = measure.find("print")
        new_system = pr is not None and pr.get("new-system") == "yes"
        for el in measure:
            if el.tag == "attributes":
                div = el.find("divisions")
                if div is not None:
                    divisions = int(div.text)
            elif el.tag == "direction":
                snd = el.find("sound")
                if snd is not None and snd.get("tempo"):
                    tempos.append((cursor, float(snd.get("tempo"))))
            elif el.tag == "backup":
                cursor -= Fraction(int(el.find("duration").text), divisions)
            elif el.tag == "forward":
                cursor += Fraction(int(el.find("duration").text), divisions)
            elif el.tag == "note":
                if el.find("grace") is not None:
                    continue  # keine Vorschlagnoten in diesem Song, defensiv trotzdem ueberspringen
                is_chord = el.find("chord") is not None
                dur_el = el.find("duration")
                dur = Fraction(int(dur_el.text), divisions) if dur_el is not None else Fraction(0)
                start = cursor
                is_rest = el.find("rest") is not None
                voice_el = el.find("voice")
                pitch_el = el.find("pitch")
                lyric_el = el.find(f'lyric[@number="{verse}"]')
                if lyric_el is None:
                    lyric_el = el.find("lyric")  # Fallback: kein number-Attribut vergeben
                text_el = lyric_el.find("text") if lyric_el is not None else None
                syl_el = lyric_el.find("syllabic") if lyric_el is not None else None
                notes.append({
                    "measure": mnum,
                    "new_system": new_system,
                    "start": start,
                    "end": start + dur,
                    "voice": voice_el.text if voice_el is not None else "1",
                    "is_rest": is_rest,
                    "is_chord": is_chord,
                    "midi": pitch_to_midi(pitch_el) if pitch_el is not None else None,
                    "lyric": text_el.text if text_el is not None else None,
                    "syllabic": syl_el.text if syl_el is not None else None,
                    "ties": [t.get("type") for t in el.findall("tie")],
                })
                new_system = False  # nur die erste Note/Pause im Takt triggert den Umbruch
                if not is_chord:
                    cursor += dur
    return notes, tempos


def build_tempo_map(root: ET.Element):
    """Sammelt Tempo-Wechsel (<sound tempo=...>) aus ALLEN Parts (in diesem
    Song steht der einzige nur bei Klavier, siehe Session-Notiz) und baut
    eine Funktion Viertelnoten-Position -> Sekunden, analog zu tick2sec in
    convert_midi.py."""
    changes = []
    for part in root.findall("part"):
        _, tempos = walk_part(part)
        changes.extend(tempos)
    changes.sort(key=lambda c: c[0])

    cleaned = [(Fraction(0), 120.0)]  # Default 120 BPM bis zum ersten echten Event
    for pos, bpm in changes:
        if cleaned[-1][0] == pos:
            cleaned[-1] = (pos, bpm)
        else:
            cleaned.append((pos, bpm))

    cum = [0.0]
    for i in range(1, len(cleaned)):
        prev_pos, prev_bpm = cleaned[i - 1]
        gap = cleaned[i][0] - prev_pos
        cum.append(cum[-1] + float(gap) * 60.0 / prev_bpm)

    def q2s(q: Fraction) -> float:
        idx = 0
        for i, (pos, _) in enumerate(cleaned):
            if pos <= q:
                idx = i
            else:
                break
        pos, bpm = cleaned[idx]
        return cum[idx] + float(q - pos) * 60.0 / bpm

    return q2s


# ---------------------------------------------------------------------------
# Stimme mit Text -> lyrics.json (Bindeboegen zusammenfassen, Silben an
# Systemumbruechen in Zeilen gruppieren, Melisma-Noten als "—")
# ---------------------------------------------------------------------------

def merge_ties(notes: list[dict]) -> list[dict]:
    """Bindebogen-Folgenoten (tie stop ohne start, kein eigenes <lyric>) an
    die vorherige Note anhaengen statt als eigenen Eintrag zu fuehren - sonst
    wuerde ein gehaltener Ton als zweite, textlose Note erscheinen."""
    merged = []
    for n in notes:
        is_continuation = (
            "stop" in n["ties"] and "start" not in n["ties"] and n["lyric"] is None
        )
        if is_continuation and merged and merged[-1]["midi"] == n["midi"]:
            merged[-1]["end"] = n["end"]
        else:
            merged.append(dict(n))
    return merged


def build_voice_lyrics(part_el, verse: str, q2s) -> list[dict]:
    notes, _ = walk_part(part_el, verse)
    voice1 = [n for n in notes if n["voice"] == "1" and not n["is_rest"] and not n["is_chord"]]
    merged = merge_ties(voice1)

    lines: list[list[dict]] = []
    cur: list[dict] = []
    last_break_measure = None
    for n in merged:
        if n["new_system"] and n["measure"] != last_break_measure:
            if cur:
                lines.append(cur)
                cur = []
            last_break_measure = n["measure"]

        text = n["lyric"]
        if text is not None and VERSE_MARKER.fullmatch(text.strip()):
            continue  # Strophennummer ("1.", "2.") - kein gesungenes Wort

        if text is not None:
            word_end = n["syllabic"] in (None, "single", "end")
            cur.append({
                "word": text if word_end else text + "-",
                "raw": text,
                "word_end": word_end,
                "start": n["start"], "end": n["end"], "midi": n["midi"],
            })
        elif cur:
            # Melisma: eigene Tonhoehe ohne eigenes Lyric, gehoert noch zur
            # zuletzt offenen Silbe (Konvention wie convert_midi.py)
            cur.append({
                "word": "—", "raw": None, "word_end": None,
                "start": n["start"], "end": n["end"], "midi": n["midi"],
            })
    if cur:
        lines.append(cur)

    result = []
    for entries in lines:
        words = [{
            "word": e["word"],
            "start": round(q2s(e["start"]), 2),
            "end": round(q2s(e["end"]), 2),
            "midi": e["midi"],
            "note": midi_to_note_name(e["midi"]),
        } for e in entries]
        readable = "".join(
            (e["raw"] or "") + (" " if e["word_end"] else "") for e in entries
        ).strip()
        result.append({
            "line": readable,
            "start": words[0]["start"],
            "end": words[-1]["end"],
            "words": words,
        })
    return result


# ---------------------------------------------------------------------------
# Jede Stimme (auch Begleitstimmen) -> eigene Audiospur, Mini-Synth wie in
# convert_midi.py (importiert, nicht dupliziert)
# ---------------------------------------------------------------------------

def render_part_audio(part_el, q2s, program: int, total_sec: float):
    notes, _ = walk_part(part_el)
    events = []
    for n in notes:
        if n["is_rest"] or n["midi"] is None:
            continue
        events.append({
            "start": q2s(n["start"]), "end": q2s(n["end"]),
            "midi": n["midi"], "vel": 90, "channel": 0, "program": program,
        })
    return render_instrumental(events, total_sec)


# ---------------------------------------------------------------------------
# Orchestrierung
# ---------------------------------------------------------------------------

def load_score(path: Path) -> ET.Element:
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path) as z:
            xml_name = next(
                n for n in z.namelist()
                if n.lower().endswith((".musicxml", ".xml")) and not n.startswith("META-INF/")
            )
            xml_bytes = z.read(xml_name)
    else:
        xml_bytes = path.read_bytes()
    return ET.fromstring(xml_bytes)


def find_part(root: ET.Element, name: str) -> ET.Element:
    part_list = root.find("part-list")
    for sp in part_list.findall("score-part"):
        pn = sp.find("part-name")
        if pn is not None and pn.text and pn.text.strip().lower() == name.strip().lower():
            pid = sp.get("id")
            for p in root.findall("part"):
                if p.get("id") == pid:
                    return p
    sys.exit(f"Stimme '{name}' nicht gefunden. Vorhanden: "
              f"{[sp.find('part-name').text for sp in part_list.findall('score-part')]}")


def guess_title(root: ET.Element, path: Path) -> str:
    movement = root.find("movement-title")
    if movement is not None and movement.text and movement.text.strip():
        return movement.text.strip()
    work_title = root.find("work/work-title")
    if work_title is not None and work_title.text and work_title.text.strip():
        return work_title.text.strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def convert(input_path: Path, out_dir: Path, verse: str, title: str | None,
            voice_names: list[str], piano_name: str | None) -> None:
    root = load_score(input_path)
    title = title or guess_title(root, input_path)
    q2s = build_tempo_map(root)
    out_dir.mkdir(parents=True, exist_ok=True)

    parts = {name: find_part(root, name) for name in voice_names}
    piano_part = find_part(root, piano_name) if piano_name else None

    # Songlaenge: laengste Stimme (in Sekunden) ueber alle Parts (inkl. Klavier)
    total_sec = 0.0
    for p in list(parts.values()) + ([piano_part] if piano_part is not None else []):
        notes, _ = walk_part(p)
        if notes:
            total_sec = max(total_sec, float(q2s(notes[-1]["end"])))
    total_sec += 1.0  # etwas Nachhall/Puffer am Ende

    results = []
    for name, part_el in parts.items():
        print(f"--- Stimme '{name}' ---")
        lyrics = build_voice_lyrics(part_el, verse, q2s)
        if not lyrics:
            sys.exit(f"Stimme '{name}': keine Strophe {verse} gefunden (Lyric-Text fehlt?)")
        n_words = sum(len(l["words"]) for l in lyrics)
        print(f"    lyrics.json: {len(lyrics)} Zeilen, {n_words} Silben-/Ton-Eintraege "
              f"({lyrics[0]['start']:.1f}s .. {lyrics[-1]['end']:.1f}s)")
        audio = render_part_audio(part_el, q2s, program=52, total_sec=total_sec)  # 52 = Chor/Ensemble-Klang

        track_dir = out_dir / "tracks" / name
        track_dir.mkdir(parents=True, exist_ok=True)
        audio_path = track_dir / "audio.wav"
        sf.write(audio_path, audio, SR)
        lyrics_path = track_dir / "lyrics.json"
        lyrics_path.write_text(json.dumps(lyrics, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append({"name": name, "audio": audio_path, "lyrics": lyrics_path})

    if piano_part is not None:
        print(f"--- Begleitstimme '{piano_name}' (kein Text) ---")
        audio = render_part_audio(piano_part, q2s, program=0, total_sec=total_sec)  # 0 = Klavier
        track_dir = out_dir / "tracks" / piano_name
        track_dir.mkdir(parents=True, exist_ok=True)
        audio_path = track_dir / "audio.wav"
        sf.write(audio_path, audio, SR)
        results.append({"name": piano_name, "audio": audio_path, "lyrics": None})

    curl_cmd = build_register_command(title, results)
    (out_dir / "register.sh").write_text(curl_cmd + "\n", encoding="utf-8")

    write_ksong(out_dir / "song.ksong", title, results)

    print(f"\nFertig. Artefakte in {out_dir}/tracks/<Stimme>/")
    print(f"Registrier-Befehl steht in {out_dir / 'register.sh'} - einfach ausfuehren:\n")
    print(curl_cmd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="MusicXML-Datei (.mxl oder .musicxml)")
    parser.add_argument("output", type=Path, help="Ausgabeordner fuer die Artefakte")
    parser.add_argument("--verse", default="1", help="Welche Strophe (lyric number=...), Default 1")
    parser.add_argument("--title", default=None, help="Songtitel (sonst aus movement-title geraten)")
    parser.add_argument("--voices", default="Sopran,Alt,Tenor,Bass",
                         help="Komma-Liste der Gesangsstimmen-<part-name>s")
    parser.add_argument("--piano-part", default="Klavier",
                         help="<part-name> der Begleitstimme ohne Text, leer zum Weglassen")
    args = parser.parse_args()
    convert(
        args.input, args.output, args.verse, args.title,
        [v.strip() for v in args.voices.split(",") if v.strip()],
        args.piano_part.strip() or None,
    )
