<script setup lang="ts">
interface Word { word: string, start: number, end: number, midi: number | null, note: string | null }
interface Line { line: string, start: number, end: number, words: Word[] }
interface Track { voiceName: string, audioUrl: string, lyricsUrl: string | null }
interface Song {
  id: number
  title: string
  createdAt: string
  instrumentalUrl: string
  lyricsUrl: string
  tracks: Track[]
}

const route = useRoute()
const config = useRuntimeConfig()
const apiBase = config.public.apiBase as string
const songId = route.params.id as string

// "local:<uuid>" -> Song kommt aus der Geraete-Bibliothek (IndexedDB, offline),
// nicht vom Backend. Siehe useSongLibrary.ts.
const isLocal = songId.startsWith('local:')
const localId = isLocal ? songId.slice('local:'.length) : ''
const { refresh: refreshLibrary, findSong: findLocalSong, assetUrl: localAssetUrl, getLyricsByKey } = useSongLibrary()

const { data: song, error: songError } = await useFetch<Song>(
  `${apiBase}/api/songs/${songId}`,
  { immediate: !isLocal }
)
const localError = ref('')

// Lokalen Song aus der Bibliothek nachladen. Bewusst in onMounted (nicht als
// Top-Level-await): so ist der erste Render auf Server und Client identisch
// (song === null), kein Hydration-Mismatch. useTrackMixer reagiert unten per
// Watcher auf trackDefs, sobald song.value gesetzt ist.
onMounted(async () => {
  if (!isLocal) return
  await refreshLibrary()
  const ls = findLocalSong(localId)
  if (!ls) {
    localError.value = 'Song nicht in der Geräte-Bibliothek gefunden (evtl. gelöscht?).'
    return
  }
  const tracks: Track[] = []
  for (const t of ls.tracks) {
    tracks.push({
      voiceName: t.voiceName,
      audioUrl: await localAssetUrl(t.audioKey),
      // fuer lokale Songs kommt lyrics ueber getLyricsByKey (s. loadLyrics);
      // hier steht der lyricsKey drin, damit singableTracks/Stimmwahl greifen
      lyricsUrl: t.lyricsKey
    })
  }
  song.value = {
    id: -1,
    title: ls.title,
    createdAt: ls.createdAt,
    instrumentalUrl: tracks[0]?.audioUrl ?? '',
    lyricsUrl: tracks[0]?.lyricsUrl ?? '',
    tracks
  }
})

// Mehrstimmen-Mixer (Vertical Slice 5, Teil 3): bei einstimmigen (alten) Songs
// hat "tracks" nur einen synthetischen Eintrag - dann gibt's nichts zu waehlen
// oder zu mischen, siehe isMultiVoice unten.
const singableTracks = computed(() => (song.value?.tracks ?? []).filter(t => t.lyricsUrl))
const isMultiVoice = computed(() => (song.value?.tracks.length ?? 0) > 1)

const selectedVoice = ref('')
watch(song, (s) => {
  if (!s) return
  selectedVoice.value = s.tracks.find(t => t.lyricsUrl)?.voiceName ?? s.tracks[0]?.voiceName ?? ''
}, { immediate: true })

const selectedTrack = computed(() =>
  song.value?.tracks.find(t => t.voiceName === selectedVoice.value) ?? null
)

// Lyrics haengen von der gewaehlten Stimme ab (jede singbare Stimme hat ihr
// eigenes lyrics.json, siehe SongResponse.TrackResponse im Backend) - deshalb
// hier neu geladen, sobald selectedVoice wechselt, statt einmalig wie vorher.
const lines = ref<Line[] | null>(null)
const lyricsError = ref('')

async function loadLyrics() {
  lyricsError.value = ''
  lines.value = null
  const url = selectedTrack.value?.lyricsUrl
  if (!url) return
  try {
    lines.value = isLocal
      ? await getLyricsByKey(url)
      : await $fetch<Line[]>(`${apiBase}${url}`)
  } catch (e) {
    lyricsError.value = e instanceof Error ? e.message : 'Lyrics konnten nicht geladen werden'
  }
}
watch(selectedVoice, loadLyrics, { immediate: true })

// Mehrspur-Wiedergabe statt einzelnem <audio>-Element, siehe useTrackMixer.ts
const trackDefs = computed(() => (song.value?.tracks ?? []).map(t => ({
  voiceName: t.voiceName,
  // lokale Songs liefern schon eine fertige blob:-URL, Backend-Songs einen Pfad
  audioUrl: isLocal ? t.audioUrl : `${apiBase}${t.audioUrl}`
})))
const mixer = useTrackMixer(trackDefs)

// Default-Mix, sobald Audio geladen ist: bei mehrstimmigen Songs nur Klavier
// hoerbar (die eigene gewaehlte Stimme singt man ja selbst), bei alten
// einstimmigen Songs die einzige Spur wie bisher direkt an.
watch(mixer.isReady, (ready) => {
  if (!ready || !song.value) return
  const names = song.value.tracks.map(t => t.voiceName)
  if (names.length <= 1) {
    for (const n of names) mixer.setEnabled(n, true)
    return
  }
  for (const n of names) mixer.setEnabled(n, /^klavier$/i.test(n))
})

function togglePlayback() {
  if (mixer.isPlaying.value) mixer.pause()
  else mixer.play()
}

// Seek-Slider: waehrend des Ziehens nicht vom Playback-Tick ueberschreiben lassen
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

const songFinished = computed(() =>
  mixer.isReady.value && !mixer.isPlaying.value
  && mixer.currentTime.value > 0
  && mixer.currentTime.value >= mixer.duration.value - 0.05
)

// Mikrofon + Live-Scoring (siehe usePitchDetector / useSingingScore) - jetzt
// gegen die Lyrics/Zeit der gewaehlten Stimme statt fest verdrahtet
const { currentHz, isActive: isMicActive, errorMessage: micError, level: micLevel, deviceLabel: micDevice, start: startMic, stop: stopMic } = usePitchDetector()
const { percentage, combo, bestCombo, feedback } = useSingingScore(lines, mixer.currentTime, currentHz, isMicActive)

function toggleMic() {
  if (isMicActive.value) {
    stopMic()
  } else {
    startMic()
  }
}

// Debug-Overlay (?debug=1): zeigt die ganze Kette Mikrofon -> Tonhoehe ->
// aktives Wort -> Ziel-Ton, damit man sieht, wo die Erkennung haengt.
const debug = computed(() => route.query.debug === '1')
const debugMidi = computed(() => {
  const hz = currentHz.value
  if (!hz) return null
  return Math.round(69 + 12 * Math.log2(hz / 440))
})
const debugActiveWord = computed(() => {
  const t = mixer.currentTime.value
  for (const line of lines.value ?? []) {
    if (t < line.start - 0.3 || t > line.end + 0.3) continue
    for (const w of line.words) {
      if (w.midi !== null && t >= w.start && t <= w.end) return w
    }
  }
  return null
})

// --- Ergebnis speichern (Vertical Slice 3.5) --------------------------------
// Bewusst schlank: am Songende ein Namensfeld. Mit Namen -> speichern, ohne
// Namen -> gar nichts (dann kommt beim Backend auch kein POST an). Der zuletzt
// benutzte Name wird im Browser gemerkt und beim naechsten Mal vorausgefuellt.
interface ScoreView {
  id: number
  playerName: string
  voiceName: string | null
  percentage: number
  bestCombo: number
  createdAt: string
}

const LAST_NAME_KEY = 'karaoke:lastPlayerName'

const playerName = ref('')
const savingScore = ref(false)
const scoreSaved = ref(false)
const scoreDismissed = ref(false)
const saveError = ref('')

onMounted(() => {
  try {
    playerName.value = localStorage.getItem(LAST_NAME_KEY) ?? ''
  } catch {
    // localStorage nicht verfuegbar (privater Modus o.ae.) - dann halt kein Vorbelegen
  }
})

// Bei lokalen Songs gibt's kein Backend fuer die Bestenliste - dann pro Song
// eine kleine Liste im localStorage des Geraets.
const LOCAL_SCORES_KEY = `karaoke:localscores:${localId}`

function loadLocalScores(): ScoreView[] {
  try {
    return JSON.parse(localStorage.getItem(LOCAL_SCORES_KEY) ?? '[]') as ScoreView[]
  } catch {
    return []
  }
}

const { data: scores, refresh: refreshScores } = await useFetch<ScoreView[]>(
  `${apiBase}/api/scores`,
  { query: { songId }, default: () => [], immediate: !isLocal }
)

onMounted(() => {
  if (isLocal) scores.value = loadLocalScores()
})

// Neuer Durchgang (zurueckgespult / neu gestartet) -> Speichern-Box wieder anbieten
watch(songFinished, (finished) => {
  if (!finished) {
    scoreSaved.value = false
    scoreDismissed.value = false
    saveError.value = ''
  }
})

const showScoreBox = computed(() =>
  songFinished.value && isMicActive.value && !scoreDismissed.value
)

async function saveScore() {
  const name = playerName.value.trim()
  if (!name || savingScore.value) return
  savingScore.value = true
  saveError.value = ''
  try {
    if (isLocal) {
      const entry: ScoreView = {
        id: Date.now(),
        playerName: name,
        voiceName: isMultiVoice.value ? selectedVoice.value : null,
        percentage: percentage.value,
        bestCombo: bestCombo.value,
        createdAt: new Date().toISOString()
      }
      const next = [...loadLocalScores(), entry]
        .sort((a, b) => b.percentage - a.percentage || b.bestCombo - a.bestCombo)
        .slice(0, 20)
      localStorage.setItem(LOCAL_SCORES_KEY, JSON.stringify(next))
      scores.value = next
    } else {
      await $fetch(`${apiBase}/api/scores`, {
        method: 'POST',
        body: {
          songId: Number(songId),
          playerName: name,
          voiceName: isMultiVoice.value ? selectedVoice.value : null,
          percentage: percentage.value,
          bestCombo: bestCombo.value
        }
      })
      await refreshScores()
    }
    try {
      localStorage.setItem(LAST_NAME_KEY, name)
    } catch {
      // s.o. - dann wird der Name beim naechsten Mal eben nicht vorbelegt
    }
    scoreSaved.value = true
  } catch (e) {
    saveError.value = e instanceof Error ? e.message : 'Speichern fehlgeschlagen'
  } finally {
    savingScore.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <UButton
      to="/"
      variant="ghost"
      icon="i-lucide-arrow-left"
      size="sm"
      class="self-start"
    >
      Zurück zur Songliste
    </UButton>

    <UAlert
      v-if="songError || localError"
      color="error"
      variant="subtle"
      title="Song konnte nicht geladen werden"
      :description="localError || String(songError)"
    />

    <template v-else-if="song">
      <h1 class="text-2xl font-bold">
        {{ song.title }}
      </h1>

      <div
        v-if="isMultiVoice"
        class="flex flex-col gap-3 rounded-lg border border-default bg-elevated px-4 py-3"
      >
        <div>
          <div class="text-sm font-medium mb-1.5">
            Welche Stimme singst du?
          </div>
          <div class="flex flex-wrap gap-2">
            <UButton
              v-for="t in singableTracks"
              :key="t.voiceName"
              size="sm"
              :variant="selectedVoice === t.voiceName ? 'solid' : 'subtle'"
              :color="selectedVoice === t.voiceName ? 'primary' : 'neutral'"
              @click="selectedVoice = t.voiceName"
            >
              {{ t.voiceName }}
            </UButton>
          </div>
        </div>

        <div>
          <div class="text-sm font-medium mb-1.5">
            Zusätzlich hören
          </div>
          <div class="flex flex-wrap gap-2">
            <label
              v-for="t in song.tracks"
              :key="t.voiceName"
              class="flex items-center gap-1.5 text-sm rounded-full border px-3 py-1 cursor-pointer select-none transition-colors"
              :class="mixer.enabled[t.voiceName]
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-default text-muted'"
            >
              <input
                type="checkbox"
                class="sr-only"
                :checked="mixer.enabled[t.voiceName]"
                @change="mixer.toggleEnabled(t.voiceName)"
              >
              {{ t.voiceName }}
            </label>
          </div>
        </div>
      </div>

      <ScoreBar
        :is-mic-active="isMicActive"
        :mic-error="micError"
        :percentage="percentage"
        :combo="combo"
        :best-combo="bestCombo"
        :feedback="feedback"
        @toggle-mic="toggleMic"
      />

      <div
        v-if="debug"
        class="rounded-lg border border-default bg-elevated px-4 py-3 text-xs font-mono flex flex-col gap-1"
      >
        <div>mic aktiv: <b>{{ isMicActive }}</b> &nbsp; mic-fehler: <b>{{ micError || '-' }}</b></div>
        <div>geraet: <b>{{ micDevice || '-' }}</b></div>
        <div>pegel (RMS): <b>{{ micLevel.toFixed(4) }}</b> <span v-if="isMicActive">{{ micLevel < 0.005 ? '(zu leise - unter Schwelle 0.005)' : '(ok)' }}</span></div>
        <div>currentHz: <b>{{ currentHz ? currentHz.toFixed(1) + ' Hz' : 'null' }}</b> &nbsp; erkannter midi: <b>{{ debugMidi ?? '-' }}</b></div>
        <div>gewaehlte Stimme: <b>{{ selectedVoice }}</b> &nbsp; lyrics-Zeilen: <b>{{ lines?.length ?? 0 }}</b></div>
        <div>playing: <b>{{ mixer.isPlaying.value }}</b> &nbsp; t: <b>{{ mixer.currentTime.value.toFixed(2) }}s</b></div>
        <div>aktives Wort: <b>{{ debugActiveWord ? `"${debugActiveWord.word}" -> ${debugActiveWord.note} (midi ${debugActiveWord.midi})` : '-' }}</b></div>
        <div>feedback: <b>{{ feedback ?? 'null' }}</b> &nbsp; Trefferquote: <b>{{ percentage }}%</b></div>
      </div>

      <!-- Eigener Transport statt <audio>: mehrere Spuren laufen synchron
           ueber die Web Audio API, siehe useTrackMixer.ts -->
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
        >Lädt Audio ...</span>
      </div>

      <UAlert
        v-if="mixer.error.value"
        color="error"
        variant="subtle"
        title="Audio konnte nicht geladen werden"
        :description="mixer.error.value"
      />

      <div
        v-if="showScoreBox"
        class="flex flex-col gap-3 rounded-lg border border-default bg-elevated px-4 py-3"
      >
        <div>
          <div class="font-semibold">
            Song beendet!
          </div>
          <div class="text-sm text-muted">
            Endergebnis: {{ percentage }}% Trefferquote, beste Streak: {{ bestCombo }}
          </div>
        </div>

        <template v-if="!scoreSaved">
          <UFormField label="Name (zum Speichern des Ergebnisses)">
            <UInput
              v-model="playerName"
              placeholder="z.B. Christian"
              autocomplete="off"
              class="w-full sm:w-64"
              @keyup.enter="saveScore"
            />
          </UFormField>

          <div class="flex flex-wrap gap-2">
            <UButton
              :loading="savingScore"
              :disabled="!playerName.trim()"
              icon="i-lucide-save"
              size="sm"
              @click="saveScore"
            >
              Speichern
            </UButton>
            <UButton
              variant="ghost"
              color="neutral"
              size="sm"
              @click="scoreDismissed = true"
            >
              Nicht speichern
            </UButton>
          </div>

          <p class="text-xs text-muted">
            Ohne Namen wird nichts gespeichert.
          </p>

          <UAlert
            v-if="saveError"
            color="error"
            variant="subtle"
            :title="saveError"
          />
        </template>

        <div
          v-else
          class="flex items-center gap-2 text-sm text-primary"
        >
          <UIcon name="i-lucide-check" />
          Gespeichert als {{ playerName.trim() }}.
        </div>
      </div>

      <div
        v-if="scores.length"
        class="rounded-lg border border-default px-4 py-3"
      >
        <div class="text-sm font-medium mb-2">
          Bisherige Ergebnisse
        </div>
        <ol class="flex flex-col gap-1">
          <li
            v-for="(s, i) in scores"
            :key="s.id"
            class="flex items-baseline gap-2 text-sm"
          >
            <span class="text-muted tabular-nums w-5">{{ i + 1 }}.</span>
            <span class="font-medium">{{ s.playerName }}</span>
            <span
              v-if="s.voiceName"
              class="text-xs text-muted"
            >({{ s.voiceName }})</span>
            <span class="ml-auto tabular-nums">{{ s.percentage }}%</span>
            <span class="text-xs text-muted tabular-nums">Streak {{ s.bestCombo }}</span>
          </li>
        </ol>
      </div>

      <UAlert
        v-if="lyricsError"
        color="error"
        variant="subtle"
        title="Lyrics konnten nicht geladen werden"
        :description="lyricsError"
      />

      <template v-else-if="lines">
        <SyncedLyrics
          :lines="lines"
          :current-time="mixer.currentTime.value"
        />
        <NoteHighway
          :lines="lines"
          :current-time="mixer.currentTime.value"
          :current-hz="currentHz"
          :is-mic-active="isMicActive"
        />
      </template>
    </template>
  </div>
</template>
