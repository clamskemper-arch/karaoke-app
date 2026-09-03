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
