<script setup lang="ts">
import type { WordResult } from '~/composables/useSingingScore'

interface Line { line: string, start: number, end: number, words: { word: string, start: number, end: number, midi: number | null, note: string | null }[] }

const props = defineProps<{
  lines: Line[]
  wordResults: WordResult[]
}>()

// Lookup nach Wort-Key (siehe wordKey() in useSingingScore.ts), damit sich
// jede Zeile Wort fuer Wort einfaerben laesst - gleiche Reihenfolge/Woerter
// wie die Lyrics selbst, nur mit Trefferstatus angereichert.
const resultByKey = computed(() => {
  const map = new Map<string, WordResult>()
  for (const r of props.wordResults) map.set(r.key, r)
  return map
})

function stateFor(word: { start: number, midi: number | null }): 'hit' | 'miss' | 'skipped' | null {
  if (word.midi === null) return null
  return resultByKey.value.get(String(word.start))?.state ?? 'skipped'
}

const summary = computed(() => {
  let hit = 0
  let miss = 0
  let skipped = 0
  for (const r of props.wordResults) {
    if (r.state === 'hit') hit++
    else if (r.state === 'miss') miss++
    else skipped++
  }
  return { hit, miss, skipped, total: props.wordResults.length }
})
</script>

<template>
  <div class="flex flex-col gap-3 rounded-lg border border-default px-4 py-3">
    <div class="flex items-center justify-between gap-3">
      <div class="text-sm font-medium">
        Ton für Ton
      </div>
      <div class="flex items-center gap-3 text-xs text-muted">
        <span class="flex items-center gap-1">
          <span class="h-2.5 w-2.5 rounded-full bg-success" /> {{ summary.hit }} getroffen
        </span>
        <span class="flex items-center gap-1">
          <span class="h-2.5 w-2.5 rounded-full bg-error" /> {{ summary.miss }} daneben
        </span>
        <span
          v-if="summary.skipped"
          class="flex items-center gap-1"
        >
          <span class="h-2.5 w-2.5 rounded-full bg-neutral-400" /> {{ summary.skipped }} nicht gesungen
        </span>
      </div>
    </div>

    <div class="flex flex-col gap-1.5 max-h-72 overflow-y-auto pr-1">
      <p
        v-for="(line, i) in lines"
        :key="i"
        class="leading-relaxed"
      >
        <span
          v-for="(word, j) in line.words"
          :key="j"
          class="rounded px-0.5"
          :class="{
            'text-success font-medium': stateFor(word) === 'hit',
            'text-error font-medium': stateFor(word) === 'miss',
            'text-muted': stateFor(word) === 'skipped' || stateFor(word) === null
          }"
          :title="word.note ?? undefined"
        >{{ word.word }} </span>
      </p>
    </div>
  </div>
</template>
