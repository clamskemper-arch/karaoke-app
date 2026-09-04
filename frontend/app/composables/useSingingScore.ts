interface Word { word: string, start: number, end: number, midi: number | null, note: string | null }
interface Line { line: string, start: number, end: number, words: Word[] }

export type PitchFeedback = 'perfect' | 'good' | 'off' | null
export type WordHitState = 'hit' | 'miss' | 'skipped'

export interface WordResult {
  key: string
  line: string
  word: string
  start: number
  end: number
  midi: number
  state: WordHitState
}

const POINTS_PER_SECOND = 10
const PERFECT_TOLERANCE = 1 // Halbtoene
const GOOD_TOLERANCE = 3

function wordKey(w: Pick<Word, 'start'>): string {
  return String(w.start)
}

/**
 * Bewertet die live per Mikrofon erkannte Tonhoehe gegen die Zielnoten aus
 * lyrics.json. Wertet bei jeder Aenderung von currentTime (getrieben vom
 * Playback-Tick in songs/[id].vue) das jeweils aktive Wort aus und sammelt
 * Punkte, solange das Mikrofon aktiv ist.
 */
export function useSingingScore(
  lines: Ref<Line[] | null | undefined>,
  currentTime: Ref<number>,
  currentHz: Ref<number | null>,
  isMicActive: Ref<boolean>
) {
  const score = ref(0)
  const maxScore = ref(0)
  const combo = ref(0)
  const bestCombo = ref(0)
  const feedback = ref<PitchFeedback>(null)

  // Pro Wort mitgeschriebene Treffer/Versuche, damit sich am Songende
  // nachvollziehen laesst, welche Toene getroffen wurden - siehe wordResults
  // unten. Reactive Map, nicht Ref<Map>, damit einzelne .set()-Aufrufe
  // Reaktivitaet auf wordResults ausloesen.
  const wordSamples = reactive(new Map<string, { hits: number, total: number }>())

  let lastTime = -1

  function reset() {
    score.value = 0
    maxScore.value = 0
    combo.value = 0
    bestCombo.value = 0
    feedback.value = null
    wordSamples.clear()
    lastTime = -1
  }

  function findActiveWord(t: number): Word | null {
    const list = lines.value
    if (!list) return null
    for (const line of list) {
      if (t < line.start - 0.3 || t > line.end + 0.3) continue
      for (const w of line.words) {
        if (w.midi !== null && t >= w.start && t <= w.end) return w
      }
    }
    return null
  }

  watch(currentTime, () => {
    const t = currentTime.value

    // Song neu gestartet oder zurueckgespult -> Score zuruecksetzen
    if (lastTime >= 0 && t < lastTime - 0.75) reset()
    const dt = lastTime >= 0 ? Math.max(0, t - lastTime) : 0
    lastTime = t

    if (!isMicActive.value) {
      feedback.value = null
      return
    }

    const activeWord = findActiveWord(t)
    if (!activeWord || activeWord.midi === null) {
      feedback.value = null
      return
    }

    maxScore.value += POINTS_PER_SECOND * dt

    if (currentHz.value) {
      const diff = Math.abs(hzToMidi(currentHz.value) - activeWord.midi)
      const key = wordKey(activeWord)
      const rec = wordSamples.get(key) ?? { hits: 0, total: 0 }
      rec.total++
      if (diff <= PERFECT_TOLERANCE) rec.hits++
      wordSamples.set(key, rec)

      if (diff <= PERFECT_TOLERANCE) {
        score.value += POINTS_PER_SECOND * dt
        combo.value++
        bestCombo.value = Math.max(bestCombo.value, combo.value)
        feedback.value = 'perfect'
      } else if (diff <= GOOD_TOLERANCE) {
        score.value += POINTS_PER_SECOND * dt * 0.5
        combo.value = 0
        feedback.value = 'good'
      } else {
        combo.value = 0
        feedback.value = 'off'
      }
    } else {
      combo.value = 0
      feedback.value = 'off'
    }
  })

  watch(isMicActive, (active) => {
    if (active) reset()
  })

  const percentage = computed(() => (
    maxScore.value > 0 ? Math.round((score.value / maxScore.value) * 100) : 0
  ))

  // Rueckblick fuers Songende: pro gesungenem Wort, ob getroffen ("hit",
  // Mehrheit der Samples im Toleranzband), verfehlt ("miss") oder gar nicht
  // erfasst ("skipped" - Mikro war da noch aus, oder das Wort kam nie dran).
  const wordResults = computed<WordResult[]>(() => {
    const list = lines.value
    if (!list) return []
    const out: WordResult[] = []
    for (const line of list) {
      for (const w of line.words) {
        if (w.midi === null) continue
        const rec = wordSamples.get(wordKey(w))
        const state: WordHitState = !rec || rec.total < 2
          ? 'skipped'
          : (rec.hits / rec.total >= 0.5 ? 'hit' : 'miss')
        out.push({ key: wordKey(w), line: line.line, word: w.word, start: w.start, end: w.end, midi: w.midi, state })
      }
    }
    return out
  })

  return { score, percentage, combo, bestCombo, feedback, wordResults, reset }
}
