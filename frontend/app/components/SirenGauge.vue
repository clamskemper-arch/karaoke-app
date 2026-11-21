<script setup lang="ts">
// Sirene: freies Gleiten vom tiefsten zum hoechsten bequemen Ton und zurueck -
// bewusst OHNE Zielton/Trefferwertung (anders als NoteHighway), das ist bei
// dieser Uebung nicht der Punkt. Die duenne Linie ist nur ein Tempo-Richtwert
// zum Mitgleiten, keine zu treffende Note.
const props = defineProps<{
  lowMidi: number
  highMidi: number
  currentHz: number | null
  isActive: boolean
  sweepSeconds: number
}>()

const elapsed = ref(0)
let rafId: number | null = null
let startTime = 0

function tick(now: number) {
  elapsed.value = (now - startTime) / 1000
  rafId = requestAnimationFrame(tick)
}

watch(() => props.isActive, (active) => {
  if (active) {
    startTime = performance.now()
    elapsed.value = 0
    rafId = requestAnimationFrame(tick)
  } else if (rafId !== null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
}, { immediate: true })

onBeforeUnmount(() => {
  if (rafId !== null) cancelAnimationFrame(rafId)
})

function bottomPercent(midi: number): number {
  const span = Math.max(props.highMidi - props.lowMidi, 1)
  return 8 + ((midi - props.lowMidi) / span) * 84
}

// Dreieckswelle: 0 -> 1 ueber sweepSeconds, dann wieder 1 -> 0
const guideMidi = computed(() => {
  const period = props.sweepSeconds * 2
  const phase = (elapsed.value % period) / props.sweepSeconds
  const pos = phase <= 1 ? phase : 2 - phase
  return props.lowMidi + pos * (props.highMidi - props.lowMidi)
})

const userMidi = computed(() => (props.currentHz ? hzToMidi(props.currentHz) : null))

const guideBottomPercent = computed(() => bottomPercent(guideMidi.value))
const userBottomPercent = computed(() => (
  userMidi.value === null ? null : bottomPercent(Math.max(props.lowMidi - 2, Math.min(props.highMidi + 2, userMidi.value)))
))

// Rein informelle Naehe zur Leitlinie - keine Trefferwertung, nur ein
// sanfter Hinweis, ob man ungefaehr im selben Bereich gleitet.
const isNearGuide = computed(() => (
  userMidi.value !== null && Math.abs(userMidi.value - guideMidi.value) <= 2.5
))
</script>

<template>
  <div class="relative w-full h-56 rounded-lg bg-elevated overflow-hidden border border-default">
    <div
      class="absolute left-0 right-0 h-px bg-primary/40 transition-[bottom] duration-75"
      :style="{ bottom: `${guideBottomPercent}%` }"
    />

    <span class="absolute left-2 bottom-1.5 text-xs text-muted">{{ midiToNoteName(lowMidi) }}</span>
    <span class="absolute left-2 top-1.5 text-xs text-muted">{{ midiToNoteName(highMidi) }}</span>
    <span
      v-if="userMidi !== null"
      class="absolute right-2 top-1.5 text-xs font-medium"
    >{{ midiToNoteName(userMidi) }}</span>

    <div
      v-if="userBottomPercent !== null"
      class="absolute left-1/2 z-20 h-4 w-4 -translate-x-1/2 rounded-full shadow-md transition-[bottom] duration-75"
      :class="isNearGuide ? 'bg-success' : 'bg-neutral-400'"
      :style="{ bottom: `${userBottomPercent}%` }"
    />

    <p
      v-if="!isActive"
      class="absolute inset-0 flex items-center justify-center text-sm text-muted px-6 text-center"
    >
      Mikrofon aktivieren, dann von tief nach hoch und zurück gleiten - die dünne Linie ist nur ein Tempo-Richtwert.
    </p>
  </div>
</template>
