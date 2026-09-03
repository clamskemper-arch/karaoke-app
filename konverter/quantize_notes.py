"""
Pitch-Kurve -> quantisierte Noten-Bars fuers Note-Highway-UI (Singstar-Stil)

Die rohe Pitch-Kurve aus pYIN (~23ms-Raster, Frequenz in Hz) ist fuer eine
Piano-Roll-artige Visualisierung zu "zittrig" (natuerliches Vibrato/leichte
Tonhoehenschwankungen beim Singen). Dieses Skript rundet jeden Frame auf den
naechsten Halbton (MIDI-Notennummer) und fasst zusammenhaengende Frames mit
gleicher Note zu einem "Balken" (Start, Ende, Note) zusammen - das ist die
Datenbasis, die die App fuers Note-Highway rendert.

Nutzung:
    python quantize_notes.py <pitch_curve.json> <notes_out.json>
"""

import json
import sys
from pathlib import Path

# Kleine Luecken zwischen zwei Segmenten der gleichen Note zusammenfassen
# (z.B. kurzer stimmloser Frame mittendrin) - toleranz in Sekunden
MERGE_GAP_S = 0.08
# Segmente kuerzer als das rausfiltern (Rauschen/einzelne Fehlmessungen)
MIN_DURATION_S = 0.06


def hz_to_midi(hz: float) -> int:
    import math
    return round(69 + 12 * math.log2(hz / 440.0))


def midi_to_note_name(midi: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{names[midi % 12]}{midi // 12 - 1}"


def quantize(curve: list[dict]) -> list[dict]:
    raw_notes = []
    for frame in curve:
        if frame["hz"] is None:
            raw_notes.append((frame["t"], None))
        else:
            raw_notes.append((frame["t"], hz_to_midi(frame["hz"])))

    # Frame-Dauer aus dem Abstand zweier Zeitpunkte schaetzen (fuer das Ende des letzten Segments)
    frame_dur = (raw_notes[-1][0] - raw_notes[0][0]) / max(len(raw_notes) - 1, 1)

    segments = []
    cur_note = None
    cur_start = None
    prev_t = None
    for t, note in raw_notes:
        if note is None:
            prev_t = t
            continue
        if cur_note is None:
            cur_note, cur_start, prev_t = note, t, t
            continue
        gap = t - prev_t
        if note == cur_note and gap <= MERGE_GAP_S + frame_dur:
            prev_t = t
            continue
        # Segment abschliessen
        segments.append((cur_start, prev_t + frame_dur, cur_note))
        cur_note, cur_start, prev_t = note, t, t
    if cur_note is not None:
        segments.append((cur_start, prev_t + frame_dur, cur_note))

    bars = []
    for start, end, midi in segments:
        if end - start < MIN_DURATION_S:
            continue
        bars.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "midi": midi,
            "note": midi_to_note_name(midi),
        })
    return bars


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Nutzung: python quantize_notes.py <pitch_curve.json> <notes_out.json>")
        sys.exit(1)
    curve = json.loads(Path(sys.argv[1]).read_text())
    bars = quantize(curve)
    Path(sys.argv[2]).write_text(json.dumps(bars, indent=2))
    print(f"{len(bars)} Noten-Bars aus {len(curve)} Frames erzeugt -> {sys.argv[2]}")
    print("\nErste 20 Bars:")
    for b in bars[:20]:
        print(f"  {b['start']:>7.2f}s - {b['end']:>7.2f}s  {b['note']:>4}  (midi {b['midi']})")
