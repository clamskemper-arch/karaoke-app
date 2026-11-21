import { describe, expect, it } from 'vitest'
import { buildWarmup, encodeWav, renderWarmupAudio, WARMUP_PATTERNS } from '../app/utils/warmup'

const fiveDown = WARMUP_PATTERNS.find(p => p.id === 'five-down')!

describe('buildWarmup', () => {
  it('builds one line per repetition, one word per scale degree', () => {
    const { lines } = buildWarmup(fiveDown, 60, 60, 2) // bpm 60 -> 1s pro Ton
    expect(lines).toHaveLength(2)
    expect(lines[0]!.words).toHaveLength(5)
    expect(lines[1]!.words).toHaveLength(5)
  })

  it('maps scale degrees to the correct semitone offsets from the tonic', () => {
    const { lines } = buildWarmup(fiveDown, 60, 60, 1)
    // Grad 5,4,3,2,1 relativ zu Grundton 60 -> 67,65,64,62,60
    expect(lines[0]!.words.map(w => w.midi)).toEqual([67, 65, 64, 62, 60])
  })

  it('transposes each repetition up by one semitone by default', () => {
    const { lines } = buildWarmup(fiveDown, 60, 60, 3)
    expect(lines[0]!.words[0]!.midi).toBe(67)
    expect(lines[1]!.words[0]!.midi).toBe(68)
    expect(lines[2]!.words[0]!.midi).toBe(69)
  })

  it('leaves a breathing gap between repetitions and keeps times monotonic', () => {
    const { lines, totalDuration } = buildWarmup(fiveDown, 60, 60, 2)
    const firstEnd = lines[0]!.end
    const secondStart = lines[1]!.start
    expect(secondStart).toBeGreaterThan(firstEnd) // Pause zum Atmen
    expect(totalDuration).toBeGreaterThan(lines[1]!.end)
  })

  it('assigns the hyphen-free warm-up syllables as word text', () => {
    const { lines } = buildWarmup(fiveDown, 60, 60, 1)
    expect(lines[0]!.words.map(w => w.word)).toEqual(['mi', 'me', 'ma', 'mo', 'mu'])
  })
})

describe('renderWarmupAudio + encodeWav', () => {
  it('renders roughly totalDuration seconds of audio, normalized below clipping', () => {
    const { notes, totalDuration } = buildWarmup(fiveDown, 60, 90, 1)
    const samples = renderWarmupAudio(notes, totalDuration)
    const sr = 44100
    expect(samples.length).toBeGreaterThanOrEqual(Math.floor(totalDuration * sr))
    let peak = 0
    for (const s of samples) peak = Math.max(peak, Math.abs(s))
    expect(peak).toBeGreaterThan(0)
    expect(peak).toBeLessThanOrEqual(1)
  })

  it('produces a valid WAV header (RIFF/WAVE, 16-bit mono PCM)', async () => {
    const samples = new Float32Array([0, 0.5, -0.5, 0])
    const blob = encodeWav(samples, 44100)
    const buf = await blob.arrayBuffer()
    const view = new DataView(buf)
    const readStr = (offset: number, len: number) =>
      String.fromCharCode(...new Uint8Array(buf, offset, len))

    expect(readStr(0, 4)).toBe('RIFF')
    expect(readStr(8, 4)).toBe('WAVE')
    expect(view.getUint16(20, true)).toBe(1) // PCM
    expect(view.getUint16(22, true)).toBe(1) // mono
    expect(view.getUint32(24, true)).toBe(44100)
    expect(view.getUint16(34, true)).toBe(16) // bits per sample
    expect(buf.byteLength).toBe(44 + samples.length * 2)
  })
})
