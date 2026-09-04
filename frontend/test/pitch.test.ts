import { describe, expect, it } from 'vitest'
import { autoCorrelate, hzToMidi, midiToNoteName } from '../app/utils/pitch'

describe('hzToMidi', () => {
  it('maps A4 (440 Hz) to MIDI 69', () => {
    expect(hzToMidi(440)).toBeCloseTo(69, 6)
  })

  it('an octave up is +12 semitones', () => {
    expect(hzToMidi(880) - hzToMidi(440)).toBeCloseTo(12, 6)
  })

  it('C4 (~261.63 Hz) is close to MIDI 60', () => {
    expect(hzToMidi(261.6256)).toBeCloseTo(60, 3)
  })
})

describe('midiToNoteName', () => {
  it.each([
    [69, 'A4'],
    [60, 'C4'],
    [61, 'C#4'],
    [21, 'A0'],
    [108, 'C8']
  ])('MIDI %i -> %s', (midi, name) => {
    expect(midiToNoteName(midi)).toBe(name)
  })

  it('rounds fractional MIDI values', () => {
    expect(midiToNoteName(60.4)).toBe('C4')
    expect(midiToNoteName(60.6)).toBe('C#4')
  })
})

function sineBuffer(freq: number, sampleRate = 44100, length = 2048, amp = 0.6): Float32Array {
  const buf = new Float32Array(length)
  for (let i = 0; i < length; i++) {
    buf[i] = amp * Math.sin((2 * Math.PI * freq * i) / sampleRate)
  }
  return buf
}

describe('autoCorrelate', () => {
  it('recovers the fundamental of a clean sine (220 Hz)', () => {
    const hz = autoCorrelate(sineBuffer(220), 44100)
    expect(Math.abs(hz - 220)).toBeLessThan(2) // < ~15 cent
  })

  it('recovers a higher pitch (440 Hz)', () => {
    const hz = autoCorrelate(sineBuffer(440), 44100)
    expect(Math.abs(hz - 440)).toBeLessThan(4)
  })

  it('returns -1 for silence (below the RMS gate)', () => {
    expect(autoCorrelate(new Float32Array(2048), 44100)).toBe(-1)
  })

  it('returns -1 for a signal that is just noise floor', () => {
    const buf = new Float32Array(2048)
    for (let i = 0; i < buf.length; i++) buf[i] = 0.001 * (Math.random() - 0.5)
    expect(autoCorrelate(buf, 44100)).toBe(-1)
  })
})
