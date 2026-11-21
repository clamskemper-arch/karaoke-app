<script setup lang="ts">
import type { BuiltWarmup } from '~/utils/warmup'

// Ein geteilter Mikrofon-Zugriff fuer beide Uebungen auf dieser Seite (statt
// pro Uebung ein eigener usePitchDetector) - vermeidet doppelte getUserMedia-
// Anfragen beim Hin- und Herwechseln zwischen den Tabs.
const { currentHz, isActive: isMicActive, errorMessage: micError, start: startMic, stop: stopMic } = usePitchDetector()
function toggleMic() {
  if (isMicActive.value) stopMic()
  else startMic()
}

const tab = ref<'tonleiter' | 'sirene'>('tonleiter')

// --- Tonleiter -------------------------------------------------------------

const patternId = ref(WARMUP_PATTERNS[0]!.id)
const pattern = computed(() => WARMUP_PATTERNS.find(p => p.id === patternId.value) ?? WARMUP_PATTERNS[0]!)

const START_NOTE_OPTIONS = [55, 57, 59, 60, 62, 64, 65].map(midi => ({ midi, label: midiToNoteName(midi) }))
const startMidi = ref(60) // C4 - fuer gemischten Chor meist bequem als Startpunkt
const bpm = ref(92)
const reps = ref(6)

const built = ref<BuiltWarmup | null>(null)
const lines = computed(() => built.value?.lines ?? null)

let audioUrl: string | null = null
const trackDefs = ref<{ voiceName: string, audioUrl: string }[]>([])
const mixer = useTrackMixer(trackDefs)

function buildAndLoad() {
  mixer.pause()
  built.value = buildWarmup(pattern.value, startMidi.value, bpm.value, reps.value)
  const samples = renderWarmupAudio(built.value.notes, built.value.totalDuration)
  const blob = encodeWav(samples)
  if (audioUrl) URL.revokeObjectURL(audioUrl)
  audioUrl = URL.createObjectURL(blob)
  trackDefs.value = [{ voiceName: 'Klavier', audioUrl }]
}

onBeforeUnmount(() => {
  if (audioUrl) URL.revokeObjectURL(audioUrl)
})

const { percentage, combo, bestCombo, feedback } = useSingingScore(lines, mixer.currentTime, currentHz, isMicActive)

function togglePlayback() {
  if (mixer.isPlaying.value) mixer.pause()
  else mixer.play()
}

const isSeeking = ref(false)
const seekPreview = ref(0)
const sliderValue = computed(() => isSeeking.value ? seekPreview.value : mixer.currentTime.value)
function onSeekInput(e: Event) {
  seekPreview.value = Number((e.target as HTMLInputElement).value)
}
function onSeekCommit() {
  mixer.seek(seekPreview.value)
  isSeeking.value = false
}

function formatTime(seconds: number): string {
  const clamped = Number.isFinite(seconds) && seconds > 0 ? seconds : 0
  const m = Math.floor(clamped / 60)
  const s = Math.floor(clamped % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

// --- Sirene ------------------------------------------------------------

const LOW_NOTE_OPTIONS = [45, 48, 50, 52, 55].map(midi => ({ midi, label: midiToNoteName(midi) }))
const HIGH_NOTE_OPTIONS = [62, 64, 65, 67, 69, 72].map(midi => ({ midi, label: midiToNoteName(midi) }))
const lowMidi = ref(52)
const highMidi = ref(69)
const sweepSeconds = ref(6)
</script>

<template>
  <div class="flex flex-col gap-6">
    <div>
      <h1 class="text-2xl font-bold">
        Einsingen
      </h1>
      <p class="text-sm text-muted">
        Ein paar Minuten Stimme aufwärmen, bevor's an die Lieder geht.
      </p>
    </div>

    <div class="flex gap-2">
      <UButton
        size="sm"
        :variant="tab === 'tonleiter' ? 'solid' : 'subtle'"
        :color="tab === 'tonleiter' ? 'primary' : 'neutral'"
        @click="tab = 'tonleiter'"
      >
        5-Ton-Tonleiter
      </UButton>
      <UButton
        size="sm"
        :variant="tab === 'sirene' ? 'solid' : 'subtle'"
        :color="tab === 'sirene' ? 'primary' : 'neutral'"
        @click="tab = 'sirene'"
      >
        Sirene
      </UButton>
    </div>

    <UAlert
      v-if="micError"
      color="error"
      variant="subtle"
      :title="micError"
    />

    <template v-if="tab === 'tonleiter'">
      <div class="flex flex-col gap-3 rounded-lg border border-default bg-elevated px-4 py-3">
        <div>
          <div class="text-sm font-medium mb-1.5">
            Muster
          </div>
          <div class="flex flex-wrap gap-2">
            <UButton
              v-for="p in WARMUP_PATTERNS"
              :key="p.id"
              size="sm"
              :variant="patternId === p.id ? 'solid' : 'subtle'"
              :color="patternId === p.id ? 'primary' : 'neutral'"
              @click="patternId = p.id"
            >
              {{ p.label }}
            </UButton>
          </div>
        </div>

        <div class="flex flex-wrap gap-4">
          <UFormField label="Starton">
            <select
              v-model.number="startMidi"
              class="rounded-md border border-default bg-default px-2 py-1.5 text-sm"
            >
              <option
                v-for="o in START_NOTE_OPTIONS"
                :key="o.midi"
                :value="o.midi"
              >
                {{ o.label }}
              </option>
            </select>
          </UFormField>

          <UFormField label="Wiederholungen">
            <input
              v-model.number="reps"
              type="number"
              min="1"
              max="10"
              class="w-20 rounded-md border border-default bg-default px-2 py-1.5 text-sm"
            >
          </UFormField>

          <UFormField :label="`Tempo (${bpm} BPM)`">
            <input
              v-model.number="bpm"
              type="range"
              min="60"
              max="130"
              class="w-32"
            >
          </UFormField>
        </div>

        <UButton
          icon="i-lucide-wand-2"
          class="self-start"
          @click="buildAndLoad"
        >
          {{ built ? 'Neu aufbauen' : 'Muster erzeugen' }}
        </UButton>
        <p class="text-xs text-muted">
          Jeder Durchgang geht einen Halbton höher - üblich sind 4-8 Durchgänge, bis es am oberen Ende unbequem wird.
        </p>
      </div>

      <template v-if="built">
        <ScoreBar
          :is-mic-active="isMicActive"
          :mic-error="micError"
          :percentage="percentage"
          :combo="combo"
          :best-combo="bestCombo"
          :feedback="feedback"
          @toggle-mic="toggleMic"
        />

        <div class="flex items-center gap-3 rounded-lg border border-default bg-elevated px-4 py-3">
          <UButton
            :icon="mixer.isPlaying.value ? 'i-lucide-pause' : 'i-lucide-play'"
            :disabled="!mixer.isReady.value"
            size="sm"
            @click="togglePlayback"
          />
          <span class="text-xs text-muted tabular-nums w-10 text-right">{{ formatTime(sliderValue) }}</span>
          <input
            type="range"
            class="flex-1"
            min="0"
            :max="mixer.duration.value || 0"
            step="0.1"
            :value="sliderValue"
            :disabled="!mixer.isReady.value"
            @pointerdown="isSeeking = true"
            @input="onSeekInput"
            @change="onSeekCommit"
          >
          <span class="text-xs text-muted tabular-nums w-10">{{ formatTime(mixer.duration.value) }}</span>
          <span
            v-if="mixer.isLoading.value"
            class="text-xs text-muted"
          >Baue Referenzton ...</span>
        </div>

        <SyncedLyrics
          :lines="lines ?? []"
          :current-time="mixer.currentTime.value"
        />
        <NoteHighway
          :lines="lines ?? []"
          :current-time="mixer.currentTime.value"
          :current-hz="currentHz"
          :is-mic-active="isMicActive"
        />
      </template>
    </template>

    <template v-else>
      <div class="flex flex-col gap-3 rounded-lg border border-default bg-elevated px-4 py-3">
        <div class="flex flex-wrap gap-4">
          <UFormField label="Tiefster Ton">
            <select
              v-model.number="lowMidi"
              class="rounded-md border border-default bg-default px-2 py-1.5 text-sm"
            >
              <option
                v-for="o in LOW_NOTE_OPTIONS"
                :key="o.midi"
                :value="o.midi"
              >
                {{ o.label }}
              </option>
            </select>
          </UFormField>

          <UFormField label="Höchster Ton">
            <select
              v-model.number="highMidi"
              class="rounded-md border border-default bg-default px-2 py-1.5 text-sm"
            >
              <option
                v-for="o in HIGH_NOTE_OPTIONS"
                :key="o.midi"
                :value="o.midi"
              >
                {{ o.label }}
              </option>
            </select>
          </UFormField>

          <UFormField :label="`Tempo (${sweepSeconds}s pro Richtung)`">
            <input
              v-model.number="sweepSeconds"
              type="range"
              min="3"
              max="10"
              class="w-32"
            >
          </UFormField>
        </div>

        <UButton
          :icon="isMicActive ? 'i-lucide-mic' : 'i-lucide-mic-off'"
          :color="isMicActive ? 'primary' : 'neutral'"
          :variant="isMicActive ? 'solid' : 'subtle'"
          size="sm"
          class="self-start"
          @click="toggleMic"
        >
          {{ isMicActive ? 'Mikrofon an' : 'Mikrofon aktivieren' }}
        </UButton>
        <p class="text-xs text-muted">
          Von tief nach hoch gleiten (z.B. auf "u"), am höchsten Punkt wenden und zurück - ohne Bruch zwischen den Registern.
        </p>
      </div>

      <SirenGauge
        :low-midi="lowMidi"
        :high-midi="highMidi"
        :current-hz="currentHz"
        :is-active="isMicActive"
        :sweep-seconds="sweepSeconds"
      />
    </template>
  </div>
</template>
