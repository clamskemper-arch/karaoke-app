"""
Kompletter Karaoke-Konvertierungs-Workflow (Prototyp)

Nimmt eine rohe Audio-/Videodatei und optional den bekannten Songtext und erzeugt
alle Artefakte, die die App fuer eine Singstar-artige Wiedergabe braucht:

    instrumental.wav   - Karaoke-Track (Pflicht fuer die App)
    lyrics.json        - Zeilen mit Woertern, je Wort Start/Ende + Zielton.
                          Deckt sowohl die synced-Lyrics-Anzeige als auch das
                          Note-Highway ab (Pflicht fuer die App)
    vocals.wav          - abgetrennte Gesangsspur (Debug/Referenz, nicht von der App gebraucht)
    pitch_curve.json    - rohe Pitch-Kurve vor der Wort-Aggregation (Debug/Referenz)

Ablauf:
    1. Vocal-Separation (Demucs)               -> instrumental.wav, vocals.wav
    2. Referenz-Pitch-Kurve (librosa pYIN)      -> pitch_curve.json
    3. Wort-Zeitstempel:
         - mit --lyrics: Forced Alignment (torchaudio MMS_FA) gegen den bekannten Text
         - ohne --lyrics: freie Transkription (faster-whisper) als Fallback
    4. Zielton pro Wort aus der Pitch-Kurve aggregieren (haeufigster Ton im Wort-Zeitfenster)
       -> lyrics.json

Nutzung:
    venv\\Scripts\\activate
    python convert.py "input/song.mp4" "output/song"                       # ohne bekannten Text
    python convert.py "input/song.mp4" "output/song" --lyrics "input/song-lyrics.txt"
"""

import argparse
import json
import math
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch
import torchaudio


# ---------------------------------------------------------------------------
# 1. Vocal-Separation
# ---------------------------------------------------------------------------

def separate_vocals(input_path: Path, work_dir: Path) -> tuple[Path, Path]:
    print("[1/4] Vocal-Separation (Demucs) ...")
    t0 = time.time()
    subprocess.run(
        [
            sys.executable, "-m", "demucs.separate",
            "-n", "htdemucs", "--two-stems=vocals",
            "-o", str(work_dir / "_demucs"),
            str(input_path),
        ],
        check=True,
    )
    stem_dir = work_dir / "_demucs" / "htdemucs" / input_path.stem
    print(f"      fertig in {time.time() - t0:.1f}s")
    return stem_dir / "vocals.wav", stem_dir / "no_vocals.wav"


# ---------------------------------------------------------------------------
# 2. Pitch-Referenzkurve
# ---------------------------------------------------------------------------

def extract_pitch_curve(vocals_path: Path) -> list[dict]:
    print("[2/4] Pitch-Referenzkurve (librosa pYIN) ...")
    t0 = time.time()
    y, sr = librosa.load(str(vocals_path), sr=22050, mono=True)
    f0, voiced_flag, _ = librosa.pyin(
        y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C6"),
        sr=sr, frame_length=2048,
    )
    times = librosa.times_like(f0, sr=sr, hop_length=512)
    curve = [
        {"t": round(float(t), 3), "hz": round(float(f), 2) if v and not np.isnan(f) else None}
        for t, f, v in zip(times, f0, voiced_flag)
    ]
    print(f"      fertig in {time.time() - t0:.1f}s ({len(curve)} Frames)")
    return curve


# ---------------------------------------------------------------------------
# 3a. Forced Alignment mit bekanntem Text
# ---------------------------------------------------------------------------

def normalize_word(word: str) -> str:
    # Umlaute falten statt (wie das reine [^a-z']-Filter) ganz zu verlieren -
    # sonst wird aus "Fluegel"/"beruehrt" beim deutschen Text "flgel"/"berhrt"
    # und das Forced Alignment franst aus. No-op fuer englische Texte.
    w = word.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        w = w.replace(a, b)
    return re.sub(r"[^a-z']", "", w)


def align_known_lyrics(vocals_path: Path, lyrics_path: Path) -> list[dict]:
    """Ordnet den bekannten Songtext per CTC Forced Alignment (torchaudio MMS_FA)
    dem Audio zu. Gibt Zeilen mit verschachtelten Woertern zurueck."""
    print("[3/4] Wort-Zeitstempel (Forced Alignment, bekannter Text) ...")
    t0 = time.time()
    bundle = torchaudio.pipelines.MMS_FA
    model = bundle.get_model()
    model.eval()
    tokenizer = bundle.get_tokenizer()
    aligner = bundle.get_aligner()

    data, sr = sf.read(str(vocals_path), dtype="float32", always_2d=True)
    waveform = torch.from_numpy(data.T)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sr != bundle.sample_rate:
        waveform = torchaudio.functional.resample(waveform, sr, bundle.sample_rate)
        sr = bundle.sample_rate

    raw_lines = [l for l in lyrics_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    line_words = [line.split() for line in raw_lines]
    flat_raw = [w for line in line_words for w in line]
    flat_norm = [normalize_word(w) for w in flat_raw]
    pairs = [(raw, norm) for raw, norm in zip(flat_raw, flat_norm) if norm]

    with torch.inference_mode():
        emission, _ = model(waveform)
    tokens = tokenizer([norm for _, norm in pairs])
    token_spans = aligner(emission[0], tokens)
    ratio = waveform.size(1) / emission.size(1) / sr

    flat_words = []
    for (raw, _norm), spans in zip(pairs, token_spans):
        flat_words.append({
            "word": raw,
            "start": round(float(ratio * spans[0].start), 2),
            "end": round(float(ratio * spans[-1].end), 2),
        })

    lines = _regroup_into_lines(raw_lines, flat_words)
    print(f"      fertig in {time.time() - t0:.1f}s ({len(flat_words)} Woerter)")
    return lines


def _regroup_into_lines(raw_lines: list[str], flat_words: list[dict]) -> list[dict]:
    """Verteilt eine flache Wortliste zurueck auf die urspruenglichen Zeilen
    (basierend auf Wortanzahl pro Zeile - Woerter, die bei der Normalisierung
    komplett wegfielen, wurden vorher schon rausgefiltert, daher hier ueber
    die Original-Zeilenlaenge in Worten gehen, nicht die gefilterte)."""
    lines = []
    idx = 0
    for raw_line in raw_lines:
        n = len(raw_line.split())
        words = flat_words[idx: idx + n]
        idx += n
        if not words:
            continue
        lines.append({
            "line": raw_line,
            "start": words[0]["start"],
            "end": words[-1]["end"],
            "words": words,
        })
    return lines


# ---------------------------------------------------------------------------
# 3b. Freie Transkription (Fallback ohne bekannten Text)
# ---------------------------------------------------------------------------

def transcribe_lyrics(vocals_path: Path) -> list[dict]:
    print("[3/4] Wort-Zeitstempel (freie Whisper-Transkription, kein Text vorgegeben) ...")
    t0 = time.time()
    from faster_whisper import WhisperModel

    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(vocals_path), word_timestamps=True)
    lines = []
    for seg in segments:
        words = [
            {"word": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)}
            for w in (seg.words or [])
        ]
        if not words:
            continue
        lines.append({
            "line": seg.text.strip(),
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "words": words,
        })
    print(f"      fertig in {time.time() - t0:.1f}s (Sprache erkannt: {info.language}, "
          f"Konfidenz: {info.language_probability:.2f}) - ACHTUNG: kann Zeilen "
          f"auslassen und Wortinhalt bei Gesang falsch erkennen, siehe Projekt-Notiz")
    return lines


# ---------------------------------------------------------------------------
# 4. Zielton pro Wort aus der Pitch-Kurve
# ---------------------------------------------------------------------------

def hz_to_midi(hz: float) -> int:
    return round(69 + 12 * math.log2(hz / 440.0))


def midi_to_note_name(midi: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{names[midi % 12]}{midi // 12 - 1}"


def attach_notes(lines: list[dict], pitch_curve: list[dict]) -> list[dict]:
    print("[4/4] Zielton pro Wort aus der Pitch-Kurve zuordnen ...")
    for line in lines:
        for w in line["words"]:
            frames = [c for c in pitch_curve if w["start"] <= c["t"] <= w["end"] and c["hz"]]
            if frames:
                midi = statistics.mode(hz_to_midi(f["hz"]) for f in frames)
                w["midi"] = midi
                w["note"] = midi_to_note_name(midi)
            else:
                w["midi"] = None
                w["note"] = None
    return lines


# ---------------------------------------------------------------------------
# Orchestrierung
# ---------------------------------------------------------------------------

def convert(input_path: Path, out_dir: Path, lyrics_path: Path | None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    vocals_src, instrumental_src = separate_vocals(input_path, out_dir)
    instrumental_dst = out_dir / "instrumental.wav"
    vocals_dst = out_dir / "vocals.wav"
    instrumental_dst.write_bytes(instrumental_src.read_bytes())
    vocals_dst.write_bytes(vocals_src.read_bytes())

    pitch_curve = extract_pitch_curve(vocals_dst)
    (out_dir / "pitch_curve.json").write_text(json.dumps(pitch_curve), encoding="utf-8")

    if lyrics_path:
        lines = align_known_lyrics(vocals_dst, lyrics_path)
    else:
        lines = transcribe_lyrics(vocals_dst)

    lines = attach_notes(lines, pitch_curve)
    (out_dir / "lyrics.json").write_text(
        json.dumps(lines, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nFertig. Artefakte in {out_dir}:")
    print("  - instrumental.wav   (Pflicht fuer die App)")
    print("  - lyrics.json        (Pflicht fuer die App: Text + Zielton pro Wort)")
    print("  - vocals.wav         (Debug/Referenz)")
    print("  - pitch_curve.json   (Debug/Referenz)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="Rohe Audio-/Videodatei")
    parser.add_argument("output", type=Path, help="Ausgabeordner fuer die Artefakte")
    parser.add_argument("--lyrics", type=Path, default=None,
                         help="Textdatei mit dem bekannten Songtext (eine Zeile pro Songzeile). "
                              "Ohne diese Option: freie Whisper-Transkription als Fallback.")
    args = parser.parse_args()
    convert(args.input, args.output, args.lyrics)
