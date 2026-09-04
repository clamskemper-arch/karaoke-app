/**
 * Umrechnung Frequenz (Hz) <-> MIDI-Notennummer. Gemeinsam genutzt vom
 * Pitch-Detector (Mikrofon) und der Note-Highway-Anzeige, damit beide exakt
 * dieselbe Skala verwenden wie der Konverter (siehe konverter/convert.py).
 */

export function hzToMidi(hz: number): number {
  return 69 + 12 * Math.log2(hz / 440)
}

export function midiToNoteName(midi: number): string {
  const names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
  const rounded = Math.round(midi)
  return `${names[((rounded % 12) + 12) % 12]}${Math.floor(rounded / 12) - 1}`
}

/**
 * Autokorrelations-basierte Grundfrequenzschaetzung (ACF2+). Liefert -1,
 * wenn das Signal zu leise ist oder keine klare Periodizitaet erkennbar ist.
 * Gleicher Grundansatz wie in aelteren Web-Audio-Pitch-Detector-Demos ueblich.
 * Reine Funktion (kein Web-Audio) - daher hier bei den Pitch-Utils und
 * unit-getestet, siehe test/pitch.test.ts.
 */
export function autoCorrelate(buf: Float32Array, sampleRate: number): number {
  const size = buf.length

  let rms = 0
  for (let i = 0; i < size; i++) rms += buf[i]! * buf[i]!
  rms = Math.sqrt(rms / size)
  if (rms < 0.005) return -1

  // Stille am Anfang/Ende abschneiden, damit sich die Autokorrelation auf
  // den eigentlichen Signalausschnitt konzentriert
  let start = 0
  let end = size - 1
  const threshold = 0.2
  for (let i = 0; i < size / 2; i++) {
    if (Math.abs(buf[i]!) >= threshold) {
      start = i
      break
    }
  }
  for (let i = 1; i < size / 2; i++) {
    if (Math.abs(buf[size - i]!) >= threshold) {
      end = size - i
      break
    }
  }

  const trimmed = buf.slice(start, end)
  const n = trimmed.length
  if (n < 2) return -1

  const correlations = new Float32Array(n)
  for (let lag = 0; lag < n; lag++) {
    let sum = 0
    for (let i = 0; i < n - lag; i++) sum += trimmed[i]! * trimmed[i + lag]!
    correlations[lag] = sum
  }

  // Erstes Abfallen ueberspringen (lag 0 ist immer das Maximum), dann das
  // naechste Maximum suchen - das entspricht der Grundperiode der Stimme
  let d = 0
  while (d < n - 1 && correlations[d]! > correlations[d + 1]!) d++

  let maxPos = -1
  let maxVal = -Infinity
  for (let i = d; i < n; i++) {
    if (correlations[i]! > maxVal) {
      maxVal = correlations[i]!
      maxPos = i
    }
  }
  if (maxPos <= 0) return -1

  // Parabolische Interpolation um den Peak fuer eine subsample-genaue
  // Periodenlaenge
  let period = maxPos
  const x1 = (maxPos > 0 ? correlations[maxPos - 1] : correlations[maxPos])!
  const x2 = correlations[maxPos]!
  const x3 = (maxPos < n - 1 ? correlations[maxPos + 1] : correlations[maxPos])!
  const a = (x1 + x3 - 2 * x2) / 2
  const b = (x3 - x1) / 2
  if (a !== 0) period = maxPos - b / (2 * a)

  if (period <= 0) return -1
  return sampleRate / period
}
