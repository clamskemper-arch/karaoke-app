/**
 * Einsingen: algorithmisch erzeugte Tonmuster (5-Ton-Tonleiter, Dreiklang) statt
 * vorproduzierter Songs. Baut aus einem Muster + Starton eine lyrics.json-
 * kompatible Line[]-Struktur (gleiche Form wie bei den Konverter-Songs, damit
 * NoteHighway/useSingingScore unveraendert wiederverwendet werden koennen)
 * sowie eine kurze Referenzton-Spur als WAV-Blob (Mini-Synth, analog zum
 * Python-Pendant in konverter/convert_midi.py - hier aber direkt im Browser,
 * weil die Toene rein algorithmisch aus der Tonart folgen, keine Datei noetig).
 */

// Explizit importiert statt auf Nuxt-Auto-Import zu vertrauen: dieses File
// wird auch direkt unter Vitest getestet (kein Nuxt-Build/unimport dort),
// siehe test/warmup.test.ts und dasselbe Muster in test/pitch.test.ts.
import { midiToNoteName } from './pitch'

interface Word { word: string, start: number, end: number, midi: number | null, note: string | null }
interface Line { line: string, start: number, end: number, words: Word[] }

export interface WarmupPattern {
  id: string
  label: string
  degrees: number[]
  syllables: string[]
}

// Halbtonabstand jeder Tonleiterstufe zum Grundton (Dur-Tonleiter, 8 = Oktave)
const DEGREE_SEMITONES: Record<number, number> = { 1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11, 8: 12 }

export const WARMUP_PATTERNS: WarmupPattern[] = [
  {
    id: 'five-down',
    label: '5-Ton-Tonleiter abwärts',
    degrees: [5, 4, 3, 2, 1],
    syllables: ['mi', 'me', 'ma', 'mo', 'mu']
  },
  {
    id: 'five-updown',
    label: '5-Ton-Tonleiter rauf & runter',
    degrees: [1, 2, 3, 4, 5, 4, 3, 2, 1],
    syllables: ['no', 'no', 'no', 'no', 'no', 'no', 'no', 'no', 'no']
  },
  {
    id: 'triad',
    label: 'Dreiklang (1-3-5-3-1)',
    degrees: [1, 3, 5, 3, 1],
    syllables: ['la', 'la', 'la', 'la', 'la']
  }
]

export interface BuiltWarmup {
  lines: Line[]
  notes: { start: number, end: number, midi: number }[]
  totalDuration: number
}

/**
 * Baut ein Muster, das sich nach jedem Durchgang um `semitoneStep` Halbtoene
 * nach oben verschiebt - Standard-Einsingpraxis (Pattern singen, Halbton
 * hoch, wiederholen). Jeder Durchgang ist eine eigene "Zeile" mit kurzer
 * Pause danach zum Atmen.
 */
export function buildWarmup(
  pattern: WarmupPattern,
  startMidi: number,
  bpm: number,
  reps: number,
  semitoneStep = 1
): BuiltWarmup {
  const beat = 60 / bpm
  const restBeats = 1.5
  const lines: Line[] = []
  const notes: { start: number, end: number, midi: number }[] = []
  let t = 0

  for (let r = 0; r < reps; r++) {
    const baseMidi = startMidi + r * semitoneStep
    const words: Word[] = []
    for (let i = 0; i < pattern.degrees.length; i++) {
      const midi = baseMidi + DEGREE_SEMITONES[pattern.degrees[i]!]!
      const start = t
      const end = t + beat
      words.push({ word: pattern.syllables[i] ?? '-', start, end, midi, note: midiToNoteName(midi) })
      notes.push({ start, end, midi })
      t = end
    }
    lines.push({
      line: `Durchgang ${r + 1} – ab ${midiToNoteName(baseMidi)}`,
      start: words[0]!.start,
      end: words[words.length - 1]!.end,
      words
    })
    t += restBeats * beat
  }

  return { lines, notes, totalDuration: t }
}

const SR = 44100

function adsr(length: number, a = 0.01, d = 0.08, s = 0.7, r = 0.1): Float32Array {
  const env = new Float32Array(length)
  const ai = Math.min(Math.floor(a * SR), length)
  const di = Math.min(Math.floor(d * SR), Math.max(length - ai, 0))
  const ri = Math.min(Math.floor(r * SR), Math.max(length - ai - di, 0))
  for (let i = 0; i < ai; i++) env[i] = i / ai
  for (let i = 0; i < di; i++) env[ai + i] = 1 - (1 - s) * (i / di)
  for (let i = ai + di; i < length - ri; i++) env[i] = s
  for (let i = 0; i < ri; i++) env[length - ri + i] = s * (1 - i / ri)
  return env
}

function renderTone(midi: number, length: number): Float32Array {
  const f = 440 * 2 ** ((midi - 69) / 12)
  const out = new Float32Array(length)
  const env = adsr(length)
  for (let i = 0; i < length; i++) {
    const t = i / SR
    const sample = Math.sin(2 * Math.PI * f * t)
      + 0.35 * Math.sin(2 * Math.PI * f * 2 * t)
      + 0.15 * Math.sin(2 * Math.PI * f * 3 * t)
    out[i] = sample * env[i]! * 0.28
  }
  return out
}

/**
 * Rendert die Tonfolge zu PCM-Samples (Referenzton zum Mitsingen - derselbe
 * Mini-Synth-Gedanke wie in convert_midi.py, hier aber clientseitig per Web
 * Audio, weil keine Datei vorproduziert werden muss).
 */
export function renderWarmupAudio(notes: { start: number, end: number, midi: number }[], totalDuration: number): Float32Array {
  const buf = new Float32Array(Math.ceil((totalDuration + 1) * SR))
  for (const n of notes) {
    const length = Math.max(Math.floor((n.end - n.start) * SR), Math.floor(0.05 * SR))
    const tone = renderTone(n.midi, length)
    const startSample = Math.floor(n.start * SR)
    for (let i = 0; i < tone.length && startSample + i < buf.length; i++) {
      buf[startSample + i]! += tone[i]!
    }
  }
  let peak = 0
  for (let i = 0; i < buf.length; i++) peak = Math.max(peak, Math.abs(buf[i]!))
  if (peak > 0) {
    const gain = 0.85 / peak
    for (let i = 0; i < buf.length; i++) buf[i]! *= gain
  }
  return buf
}

/** Minimaler WAV-Encoder (mono, 16-bit PCM) - kein externes Package noetig,
 * das Ergebnis geht direkt als Blob-URL in useTrackMixer (wie eine normale
 * Song-Audiodatei). */
export function encodeWav(samples: Float32Array, sampleRate = SR): Blob {
  const bytesPerSample = 2
  const buffer = new ArrayBuffer(44 + samples.length * bytesPerSample)
  const view = new DataView(buffer)

  function writeString(offset: number, str: string) {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i))
  }

  writeString(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * bytesPerSample, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * bytesPerSample, true)
  view.setUint16(32, bytesPerSample, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, samples.length * bytesPerSample, true)

  let offset = 44
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]!))
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
    offset += 2
  }

  return new Blob([buffer], { type: 'audio/wav' })
}
