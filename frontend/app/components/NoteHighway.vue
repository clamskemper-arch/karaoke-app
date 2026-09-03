<script setup lang="ts">
interface Word { word: string, start: number, end: number, midi: number | null, note: string | null }
interface Line { line: string, start: number, end: number, words: Word[] }

const props = defineProps<{
  lines: Line[]
  currentTime: number
  currentHz?: number | null
  isMicActive?: boolean
}>()

// Wie viele Sekunden insgesamt sichtbar sind, und wo (in %) der "Jetzt singen"-
// Playhead im sichtbaren Fenster steht. Noten scrollen von rechts nach links
// auf den Playhead zu - so weiss man vorher, welcher Ton als naechstes kommt.
const WINDOW_SECONDS = 6
const PLAYHEAD_PERCENT = 18
const PITCH_TOLERANCE = 1 // Halbtoene, entspricht useSingingScore

const allWords = computed(() => {
  const words: Word[] = []
  for (const line of props.lines) {
    for (const w of line.words) {
      if (w.midi !== null && w.midi !== undefined) words.push(w)
    }
  }
  return words
})

const midiRange = computed(() => {
  if (!allWords.value.length) return { min: 55, max: 72 }
  let min = Infinity
  let max = -Infinity
  for (const w of allWords.value) {
    if (w.midi! < min) min = w.midi!
    if (w.midi! > max) max = w.midi!
  }
  // etwas Platz oben/unten lassen
  return { min: min - 2, max: max + 2 }
})

const visibleWords = computed(() => {
  const t = props.currentTime
  return allWords.value.filter(w => w.end >= t - 1 && w.start <= t + WINDOW_SECONDS)
})

function leftPercent(word: Word): number {
  return PLAYHEAD_PERCENT + ((word.start - props.currentTime) / WINDOW_SECONDS) * 100
}

function widthPercent(word: Word): number {
  return Math.max(((word.end - word.start) / WINDOW_SECONDS) * 100, 1.5)
}

function bottomPercentForMidi(midi: number): number {
  const { min, max } = midiRange.value
  const span = Math.max(max - min, 1)
  // Nur bis 78% statt 90% hoch, damit oberhalb des Balkens noch Platz fuer
  // das Wort-Label bleibt (siehe Template)
  return 8 + ((midi - min) / span) * 70
}

function bottomPercent(word: Word): number {
  return bottomPercentForMidi(word.midi!)
}

function isActive(word: Word): boolean {
  return props.currentTime >= word.start && props.currentTime <= word.end
}

// Live erkannte Tonhoehe vom Mikrofon: als Punkt am Playhead angezeigt.
// Farbe zeigt, wie nah dran man an der gerade aktiven Zielnote ist (gleiche
// Toleranz wie useSingingScore, damit UI und Score konsistent sind).
const targetWordAtPlayhead = computed(() => allWords.value.find(isActive) ?? null)

const userMidi = computed(() => (props.currentHz ? hzToMidi(props.currentHz) : null))

const userBottomPercent = computed(() => (
  userMidi.value === null ? null : bottomPercentForMidi(userMidi.value)
))

const userPitchState = computed<'perfect' | 'off' | 'idle'>(() => {
  if (userMidi.value === null) return 'idle'
  const target = targetWordAtPlayhead.value
  if (!target || target.midi === null) return 'idle'
  return Math.abs(userMidi.value - target.midi) <= PITCH_TOLERANCE ? 'perfect' : 'off'
})

// --- Live-Gesangsspur -----------------------------------------------------
// Solange Mikrofon + Wiedergabe laufen, wird die erkannte Tonhoehe pro Tick
// mitgeschrieben und als farbige Punktespur ueber die Notenbalken gelegt:
// gruen = im Toleranzband der gerade faelligen Zielnote, rot = daneben,
// grau = kein Ziel aktiv. Die Spur scrollt mit den Balken nach links, so
// sieht man Note fuer Note, was getroffen wurde.
interface PitchSample { t: number, midi: number | null, hit: boolean | null }
const trail = ref<PitchSample[]>([])
let lastSampleT = -1

function playheadXPercent(t: number): number {
  return PLAYHEAD_PERCENT + ((t - props.currentTime) / WINDOW_SECONDS) * 100
}

watch(() => props.currentTime, (t) => {
  // Zurueckgespult / neu gestartet -> Spur leeren
  if (t < lastSampleT - 0.4) {
    trail.value = []
    lastSampleT = t
    return
  }
  if (lastSampleT >= 0 && t - lastSampleT < 0.03) return
  lastSampleT = t
  if (!props.isMicActive) return

  const um = userMidi.value
  let hit: boolean | null = null
  if (um !== null) {
    const target = targetWordAtPlayhead.value
    hit = target && target.midi !== null
      ? Math.abs(um - target.midi) <= PITCH_TOLERANCE
      : null
  }
  trail.value.push({ t, midi: um, hit })

  // nur den links vom Playhead sichtbaren Bereich behalten
  const cutoff = props.currentTime - (WINDOW_SECONDS * PLAYHEAD_PERCENT) / 100 - 0.5
  let drop = 0
  while (drop < trail.value.length && trail.value[drop]!.t < cutoff) drop++
  if (drop) trail.value.splice(0, drop)
})

watch(() => props.isMicActive, () => {
  trail.value = []
  lastSampleT = -1
})

const trailDots = computed(() =>
  trail.value
    .filter(s => s.midi !== null)
    .map(s => ({
      x: playheadXPercent(s.t),
      y: bottomPercentForMidi(s.midi as number),
      hit: s.hit
    }))
    .filter(d => d.x >= -2 && d.x <= 102)
)

// Balkenfarbe nachtraeglich: fuer schon gesungene Woerter zeigt der Balken
// selbst, ob getroffen (Mehrheit der Spur-Samples im Toleranzband) oder nicht.
function sungState(word: Word): 'hit' | 'miss' | null {
  if (!props.isMicActive || word.midi === null || word.end >= props.currentTime) return null
  const inWord = trail.value.filter(s => s.midi !== null && s.t >= word.start && s.t <= word.end)
  if (inWord.length < 2) return null
  const hits = inWord.filter(s => Math.abs((s.midi as number) - word.midi!) <= PITCH_TOLERANCE).length
  return hits / inWord.length >= 0.5 ? 'hit' : 'miss'
}
</script>

<template>
  <div class="relative w-full h-56 rounded-lg bg-elevated overflow-hidden border border-default">
    <!-- Playhead: hier muss der Ton JETZT getroffen werden -->
    <div
      class="absolute top-0 bottom-0 w-0.5 bg-primary/70 z-10"
      :style="{ left: `${PLAYHEAD_PERCENT}%` }"
    />

    <div
      v-for="(word, i) in visibleWords"
      :key="`${word.start}-${i}`"
      class="absolute flex flex-col items-center gap-0.5"
      :style="{
        left: `${leftPercent(word)}%`,
        width: `${widthPercent(word)}%`,
        bottom: `${bottomPercent(word)}%`
      }"
    >
      <!-- Wort-Text: zeigt, welcher Wortteil zu diesem Ton gehoert. Darf
           breiter sein als der schmale Ton-Balken darunter, daher ohne
           overflow-hidden auf diesem Label. -->
      <span
        class="text-[11px] font-medium whitespace-nowrap transition-colors"
        :class="isActive(word) ? 'text-primary' : 'text-muted'"
      >{{ word.word }}</span>

      <!-- Ton-Balken: Position = Tonhoehe, Notenname als Tooltip beim Hovern.
           Nach dem Playhead faerbt sich der Balken nach Trefferergebnis. -->
      <div
        class="h-3 w-full min-w-3 rounded-full transition-colors"
        :class="{
          'bg-success': sungState(word) === 'hit',
          'bg-error': sungState(word) === 'miss',
          'bg-primary': sungState(word) === null && isActive(word),
          'bg-accented': sungState(word) === null && !isActive(word)
        }"
        :title="word.note ?? undefined"
      />
    </div>

    <!-- Live-Gesangsspur: erkannte Tonhoehe der letzten Sekunden als Punkte,
         gruen getroffen / rot daneben / grau kein Ziel aktiv -->
    <div
      v-for="(d, i) in trailDots"
      :key="`trail-${i}`"
      class="absolute z-20 h-1.5 w-1.5 -translate-x-1/2 rounded-full"
      :class="{
        'bg-success': d.hit === true,
        'bg-error': d.hit === false,
        'bg-neutral-400': d.hit === null
      }"
      :style="{ left: `${d.x}%`, bottom: `${d.y}%` }"
    />

    <!-- Live-Tonhoehe vom Mikrofon: Punkt direkt am Playhead, Farbe zeigt
         die Trefferguete relativ zur gerade aktiven Zielnote -->
    <div
      v-if="userBottomPercent !== null"
      class="absolute z-20 h-4 w-4 -translate-x-1/2 rounded-full shadow-md transition-[bottom] duration-75"
      :class="{
        'bg-success': userPitchState === 'perfect',
        'bg-error': userPitchState === 'off',
        'bg-neutral-400': userPitchState === 'idle'
      }"
      :style="{ left: `${PLAYHEAD_PERCENT}%`, bottom: `${userBottomPercent}%` }"
    />

    <p
      v-if="!allWords.length"
      class="absolute inset-0 flex items-center justify-center text-sm text-muted"
    >
      Keine Ton-Daten in lyrics.json gefunden
    </p>
  </div>
</template>
