"""
Forced Alignment mit bekanntem Songtext (statt freier Whisper-ASR)

Wenn der Songtext schon bekannt ist (z.B. aus Notenmaterial/offiziellen Lyrics),
liefert das genauere und zuverlaessigere Wort-Zeitstempel als freie Spracherkennung -
Whisper muss den Text nicht mehr *erkennen*, nur noch dem Audio *zuordnen*.

Nutzt torchaudio's CTC Forced-Alignment-Pipeline (MMS_FA, Meta's "Massively
Multilingual Speech" Modell), das genau fuer diesen Zweck gebaut ist.

Nutzung:
    venv\\Scripts\\activate
    python forced_align.py <vocals.wav> <lyrics.txt> <output.json>
"""

import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torchaudio


def normalize_word(word: str) -> str:
    word = word.lower()
    word = re.sub(r"[^a-z']", "", word)
    return word


def align(vocals_path: Path, lyrics_path: Path, out_path: Path) -> None:
    bundle = torchaudio.pipelines.MMS_FA
    print("Lade Forced-Alignment-Modell (MMS_FA) ...")
    t0 = time.time()
    model = bundle.get_model()
    model.eval()
    tokenizer = bundle.get_tokenizer()
    aligner = bundle.get_aligner()
    print(f"  fertig in {time.time() - t0:.1f}s")

    # soundfile statt torchaudio.load, da torchaudio.load in dieser Version
    # zusaetzlich "torchcodec" braucht - soundfile kommt schon ohne aus
    data, sr = sf.read(str(vocals_path), dtype="float32", always_2d=True)  # (frames, channels)
    waveform = torch.from_numpy(data.T)  # (channels, frames)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sr != bundle.sample_rate:
        waveform = torchaudio.functional.resample(waveform, sr, bundle.sample_rate)
        sr = bundle.sample_rate

    raw_lines = [l for l in lyrics_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    raw_words = [w for line in raw_lines for w in line.split()]
    norm_words = [normalize_word(w) for w in raw_words]
    # Woerter, die nach der Normalisierung leer sind (z.B. reine Klammern), rausfiltern -
    # dabei die Zuordnung zum Original-Wort behalten
    pairs = [(raw, norm) for raw, norm in zip(raw_words, norm_words) if norm]

    print(f"Richte {len(pairs)} Woerter am Audio aus ...")
    t0 = time.time()
    with torch.inference_mode():
        emission, _ = model(waveform)

    tokens = tokenizer([norm for _, norm in pairs])
    token_spans = aligner(emission[0], tokens)
    print(f"  fertig in {time.time() - t0:.1f}s")

    ratio = waveform.size(1) / emission.size(1) / sr
    result = []
    for (raw, _norm), spans in zip(pairs, token_spans):
        start = ratio * spans[0].start
        end = ratio * spans[-1].end
        score = sum(s.score * len(s) for s in spans) / sum(len(s) for s in spans)
        result.append({
            "word": raw,
            "start": round(float(start), 2),
            "end": round(float(end), 2),
            "score": round(float(score), 3),
        })

    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGespeichert: {out_path}")
    avg_score = sum(r["score"] for r in result) / len(result)
    low_conf = [r for r in result if r["score"] < 0.5]
    print(f"Durchschnittlicher Alignment-Score: {avg_score:.3f} "
          f"({len(low_conf)} von {len(result)} Woertern mit Score < 0.5)")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Nutzung: python forced_align.py <vocals.wav> <lyrics.txt> <output.json>")
        sys.exit(1)
    align(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
