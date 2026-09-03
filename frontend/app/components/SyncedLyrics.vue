<script setup lang="ts">
interface Word { word: string, start: number, end: number, midi: number | null, note: string | null }
interface Line { line: string, start: number, end: number, words: Word[] }

const props = defineProps<{
  lines: Line[]
  currentTime: number
}>()

const currentLineIndex = computed(() => {
  if (!props.lines.length) return -1
  const idx = props.lines.findIndex(l => props.currentTime < l.end)
  return idx === -1 ? props.lines.length - 1 : idx
})

const notStartedYet = computed(() =>
  props.lines.length > 0 && props.currentTime < props.lines[0]!.start
)

const currentLine = computed(() => {
  if (notStartedYet.value) return null
  return currentLineIndex.value >= 0 ? props.lines[currentLineIndex.value] : null
})

const nextLine = computed(() => {
  // Waehrend der Intro (vor der ersten Zeile) ist die "naechste" Zeile die
  // allererste Zeile selbst - die soll als Vorschau sichtbar sein, nicht
  // uebersprungen werden
  if (notStartedYet.value) return props.lines[0] ?? null
  const idx = currentLineIndex.value + 1
  return idx < props.lines.length ? props.lines[idx] : null
})

function wordState(word: Word): 'sung' | 'active' | 'upcoming' {
  if (props.currentTime > word.end) return 'sung'
  if (props.currentTime >= word.start) return 'active'
  return 'upcoming'
}
</script>

<template>
  <div class="flex flex-col items-center gap-2 py-6 text-center select-none">
    <p v-if="notStartedYet" class="text-lg text-muted">
      Gleich geht's los...
    </p>

    <p v-else-if="currentLine" class="text-2xl font-bold leading-snug">
      <span
        v-for="(word, i) in currentLine.words"
        :key="i"
        class="transition-colors"
        :class="{
          'text-primary': wordState(word) === 'active',
          'text-muted': wordState(word) === 'sung',
          'text-default': wordState(word) === 'upcoming'
        }"
      >{{ word.word + ' ' }}</span>
    </p>

    <p v-if="nextLine" class="text-base text-muted">
      {{ nextLine.line }}
    </p>
  </div>
</template>
