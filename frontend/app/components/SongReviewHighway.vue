<script setup lang="ts">
import type { TrailPoint, WordResult } from '~/composables/useSingingScore'

interface Word { word: string, start: number, end: number, midi: number | null, note: string | null }
interface Line { line: string, start: number, end: number, words: Word[] }

const props = defineProps<{
  lines: Line[]
  wordResults: WordResult[]
  trail: TrailPoint[]
  duration: number
}>()

// Gleiche Optik/Geometrie wie NoteHighway.vue (dort live waehrend des
// Singens, hier durchspulbar nach Songende) - bewusst dieselben Konstanten,
// damit sich der Rueckblick vertraut anfuehlt.
const WINDOW_SECONDS = 6
const PLAYHEAD_PERCENT = 18

const reviewTime = ref(0)
const isSeeking = ref(false)
const seekPreview = ref(0)
const displayTime = computed(() => isSeeking.value ? seekPreview.value : reviewTime.value)

function onSeekInput(e: Event) {
  seekPreview.value = Number((e.target as HTMLInputElement).value)
  reviewTime.value = seekPreview.value
}
function onSeekStart() {
  seekPreview.value = reviewTime.value
  isSeeking.value = true
}
function onSeekEnd() {
  isSeeking.value = false
}

function step(deltaSeconds: number) {
  reviewTime.value = Math.max(0, Math.min(props.duration, reviewTime.value + deltaSeconds))
}

function formatTime(seconds: number): string {
  const clamped = Number.isFinite(seconds) && seconds > 0 ? seconds : 0
  const m = Math.floor(clamped / 60)
  const s = Math.floor(clamped % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

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
  return { min: min - 2, max: max + 2 }
})

const visibleWords = computed(() => {
  const t = reviewTime.value
  return allWords.value.filter(w => w.end >= t - 1 && w.start <= t + WINDOW_SECONDS)
})

function leftPercent(word: Word): number {
  return PLAYHEAD_PERCENT + ((word.start - reviewTime.value) / WINDOW_SECONDS) * 100
}

function widthPercent(word: Word): number {
  return Math.max(((word.end - word.start) / WINDOW_SECONDS) * 100, 1.5)
}

function bottomPercentForMidi(midi: number): number {
  const { min, max } = midiRange.value
  const span = Math.max(max - min, 1)
  return 8 + ((midi - min) / span) * 70
}

function bottomPercent(word: Word): number {
  return bottomPercentForMidi(word.midi!)
}

function isActive(word: Word): boolean {
  return reviewTime.value >= word.start && reviewTime.value <= word.end
}

// Trefferstatus kommt hier nicht aus der lokalen Live-Spur (wie bei
// NoteHighway waehrend des Singens), sondern direkt aus den am Songende
// fertig ausgewerteten wordResults - deshalb fuer jedes Wort fest, nicht
// mehr davon abhaengig, ob der Playhead schon drueber war.
const resultByKey = computed(() => {
  const map = new Map<string, WordResult['state']>()
  for (const r of props.wordResults) map.set(r.key, r.state)
  return map
})

function sungState(word: Word): 'hit' | 'miss' | 'skipped' | null {
  if (word.midi === null) return null
  return resultByKey.value.get(String(word.start)) ?? 'skipped'
}

function playheadXPercent(t: number): number {
  return PLAYHEAD_PERCENT + ((t - reviewTime.value) / WINDOW_SECONDS) * 100
}

// Nur der um reviewTime sichtbare Ausschnitt der kompletten Spur wird
// gerendert - gleiche Fensterlogik wie bei den Notenbalken oben.
const visibleTrail = computed(() => {
  const t = reviewTime.value
  return props.trail.filter(s => s.t >= t - 1 && s.t <= t + WINDOW_SECONDS)
})

const trailDots = computed(() =>
  visibleTrail.value
    .filter(s => s.midi !== null)
    .map(s => ({
      x: playheadXPercent(s.t),
      y: bottomPercentForMidi(s.midi as number),
      hit: s.hit
    }))
    .filter(d => d.x >= -2 && d.x <= 102)
)
</script>

<template>
  <div class="flex flex-col gap-2">
    <div class="text-sm font-medium">
      Aufnahme durchspulen
    </div>

    <div class="relative w-full h-56 rounded-lg bg-elevated overflow-hidden border border-default">
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
        <span
          class="text-[11px] font-medium whitespace-nowrap transition-colors"
          :class="isActive(word) ? 'text-primary' : 'text-muted'"
        >{{ word.word }}</span>

        <div
          class="h-3 w-full min-w-3 rounded-full transition-colors"
          :class="{
            'bg-success': sungState(word) === 'hit',
            'bg-error': sungState(word) === 'miss',
            'bg-accented': sungState(word) === 'skipped'
          }"
          :title="word.note ?? undefined"
        />
      </div>

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

      <p
        v-if="!allWords.length"
        class="absolute inset-0 flex items-center justify-center text-sm text-muted"
      >
        Keine Ton-Daten in lyrics.json gefunden
      </p>
    </div>

    <!-- Durchspulen: eigener Regler, unabhaengig von der Wiedergabe (die ist
         ja schon zuende) - gleiche Optik wie der Transport oben im Player. -->
    <div class="flex items-center gap-3 rounded-lg border border-default bg-elevated px-4 py-3">
      <UButton
        icon="i-lucide-rewind"
        variant="subtle"
        color="neutral"
        size="sm"
        @click="step(-5)"
      />
      <span class="text-xs text-muted tabular-nums w-10 text-right">{{ formatTime(displayTime) }}</span>
      <input
        type="range"
        class="flex-1"
        min="0"
        :max="duration || 0"
        step="0.1"
        :value="displayTime"
        @pointerdown="onSeekStart"
        @input="onSeekInput"
        @change="onSeekEnd"
      >
      <span class="text-xs text-muted tabular-nums w-10">{{ formatTime(duration) }}</span>
      <UButton
        icon="i-lucide-fast-forward"
        variant="subtle"
        color="neutral"
        size="sm"
        @click="step(5)"
      />
    </div>
  </div>
</template>
