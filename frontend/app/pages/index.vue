<script setup lang="ts">
interface Song {
  id: number
  title: string
  createdAt: string
  instrumentalUrl: string
  lyricsUrl: string
  tracks: { voiceName: string, audioUrl: string, lyricsUrl: string | null }[]
}

const config = useRuntimeConfig()
const apiBase = config.public.apiBase as string

const { data: songs, refresh, pending: loadingSongs, error: songsError } = await useFetch<Song[]>(`${apiBase}/api/songs`)

/* -------------------- Geraete-Bibliothek (offline, .ksong) ------------------- */

const { songs: localSongs, refresh: refreshLibrary, importKsong, remove: removeFromLibrary } = useSongLibrary()
const importing = ref(false)
const importError = ref('')
const importedTitle = ref('')

// Optionaler Heim-Server: einmal die IP des Rechners eingeben (gemerkt im
// localStorage), dann fuehrt der Link auf dessen .ksong-Liste (GET /songs).
// Direktes Laden aus der App geht nicht (HTTPS-Seite -> HTTP-LAN = Mixed
// Content), daher nur ein Link zum manuellen Download + anschliessendem Import.
const SHARE_HOST_KEY = 'karaoke:shareHost'
const shareHost = ref('')
const shareUrl = computed(() => {
  const h = shareHost.value.trim().replace(/^https?:\/\//, '').replace(/\/.*$/, '')
  if (!h) return ''
  return `http://${h.includes(':') ? h : `${h}:8080`}/songs`
})

onMounted(() => {
  refreshLibrary()
  try {
    shareHost.value = localStorage.getItem(SHARE_HOST_KEY) ?? ''
  } catch {
    // localStorage nicht verfuegbar - dann halt kein Merken
  }
})
watch(shareHost, (v) => {
  try {
    localStorage.setItem(SHARE_HOST_KEY, v.trim())
  } catch {
    // s.o.
  }
})

async function onKsongChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  importing.value = true
  importError.value = ''
  importedTitle.value = ''
  try {
    const s = await importKsong(file)
    importedTitle.value = s.title
  } catch (err) {
    importError.value = err instanceof Error ? err.message : 'Import fehlgeschlagen'
  } finally {
    importing.value = false
  }
}

async function removeLocal(id: string, title: string) {
  if (!confirm(`"${title}" von diesem Gerät entfernen?`)) return
  await removeFromLibrary(id)
}

function formatSize(bytes: number): string {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.round(bytes / 1024)} KB`
}

// Titel wird von beiden Formularen geteilt
const title = ref('')

// Umschalten zwischen den zwei Registrierungswegen (siehe SongController):
// - 'single'  -> POST /api/songs           (instrumental.wav + lyrics.json)
// - 'multi'   -> POST /api/songs/multitrack (Chorlied: je Stimme Audio + optional Lyrics)
const mode = ref<'single' | 'multi'>('single')

/* ----------------------------- einstimmig ----------------------------- */

const instrumentalFile = ref<File | null>(null)
const lyricsFile = ref<File | null>(null)
const submitting = ref(false)
const errorMessage = ref('')

function onInstrumentalChange(e: Event) {
  instrumentalFile.value = (e.target as HTMLInputElement).files?.[0] ?? null
}

function onLyricsChange(e: Event) {
  lyricsFile.value = (e.target as HTMLInputElement).files?.[0] ?? null
}

async function registerSong() {
  errorMessage.value = ''

  if (!title.value.trim()) {
    errorMessage.value = 'Bitte einen Titel eingeben.'
    return
  }
  if (!instrumentalFile.value) {
    errorMessage.value = 'Bitte instrumental.wav auswählen (Ergebnis aus convert.py).'
    return
  }
  if (!lyricsFile.value) {
    errorMessage.value = 'Bitte lyrics.json auswählen (Ergebnis aus convert.py).'
    return
  }

  submitting.value = true
  try {
    const formData = new FormData()
    formData.append('title', title.value.trim())
    formData.append('instrumental', instrumentalFile.value)
    formData.append('lyrics', lyricsFile.value)

    await $fetch(`${apiBase}/api/songs`, {
      method: 'POST',
      body: formData
    })

    title.value = ''
    instrumentalFile.value = null
    lyricsFile.value = null
    // Datei-Inputs im DOM zuruecksetzen
    ;(document.getElementById('instrumental-input') as HTMLInputElement | null)!.value = ''
    ;(document.getElementById('lyrics-input') as HTMLInputElement | null)!.value = ''

    await refresh()
  } catch (err: unknown) {
    const data = (err as { data?: { message?: string } })?.data
    errorMessage.value = data?.message ?? 'Song konnte nicht registriert werden.'
  } finally {
    submitting.value = false
  }
}

/* ----------------------------- mehrstimmig ---------------------------- */

interface VoiceRow {
  name: string
  fixed: boolean // true = eine der Standard-Stimmen, Name nicht editierbar
  enabled: boolean
  audio: File | null
  lyrics: File | null
}

// Klassisches SATB + Klavier (siehe Architektur-Doku). Klavier ist als
// Begleit-Basis vorausgewaehlt, der Rest wird nach Bedarf angehakt.
function defaultVoiceRows(): VoiceRow[] {
  return [
    { name: 'Klavier', fixed: true, enabled: true, audio: null, lyrics: null },
    { name: 'Sopran', fixed: true, enabled: false, audio: null, lyrics: null },
    { name: 'Alt', fixed: true, enabled: false, audio: null, lyrics: null },
    { name: 'Tenor', fixed: true, enabled: false, audio: null, lyrics: null },
    { name: 'Bass', fixed: true, enabled: false, audio: null, lyrics: null }
  ]
}

const voiceRows = ref<VoiceRow[]>(defaultVoiceRows())
const submittingMulti = ref(false)
const multiError = ref('')
// Erhoehen erzwingt ueber :key ein Neu-Rendern der Datei-Inputs -> Anzeige leert sich
const resetNonce = ref(0)

const namePattern = /^[A-Za-z0-9_-]+$/

function addCustomVoice() {
  voiceRows.value.push({ name: '', fixed: false, enabled: true, audio: null, lyrics: null })
}

function removeVoice(index: number) {
  voiceRows.value.splice(index, 1)
}

function onVoiceFile(row: VoiceRow, kind: 'audio' | 'lyrics', e: Event) {
  row[kind] = (e.target as HTMLInputElement).files?.[0] ?? null
}

async function registerMultitrack() {
  multiError.value = ''

  const t = title.value.trim()
  if (!t) {
    multiError.value = 'Bitte einen Titel eingeben.'
    return
  }

  const active = voiceRows.value.filter(r => r.enabled)
  if (!active.length) {
    multiError.value = 'Mindestens eine Stimme auswählen.'
    return
  }
  for (const r of active) {
    const name = r.name.trim()
    if (!namePattern.test(name)) {
      multiError.value = `Ungültiger Stimmname "${r.name || '(leer)'}" – nur Buchstaben, Zahlen, - und _.`
      return
    }
    if (!r.audio) {
      multiError.value = `Für "${name}" fehlt die Audio-Datei.`
      return
    }
  }
  const names = active.map(r => r.name.trim())
  if (new Set(names.map(n => n.toLowerCase())).size !== names.length) {
    multiError.value = 'Stimmnamen müssen eindeutig sein.'
    return
  }
  if (!active.some(r => r.lyrics)) {
    multiError.value = 'Mindestens eine Stimme braucht eine lyrics.json – sonst gibt es nichts zum Mitsingen.'
    return
  }

  submittingMulti.value = true
  try {
    const fd = new FormData()
    fd.append('title', t)
    fd.append('voiceNames', names.join(','))
    for (const r of active) {
      const name = r.name.trim()
      fd.append(`audio_${name}`, r.audio as File)
      if (r.lyrics) fd.append(`lyrics_${name}`, r.lyrics)
    }

    await $fetch(`${apiBase}/api/songs/multitrack`, {
      method: 'POST',
      body: fd
    })

    title.value = ''
    voiceRows.value = defaultVoiceRows()
    resetNonce.value++
    await refresh()
  } catch (err: unknown) {
    const data = (err as { data?: { message?: string } })?.data
    multiError.value = data?.message ?? 'Song konnte nicht registriert werden.'
  } finally {
    submittingMulti.value = false
  }
}
</script>

<template>
  <div class="flex flex-col gap-8">
    <div>
      <h1 class="text-2xl font-bold mb-1">
        Song registrieren
      </h1>
      <p class="text-sm text-muted mb-4">
        Fertige Artefakte aus dem Konvertierungs-Workflow hochladen –
        einstimmig aus <code>convert.py</code> oder mehrstimmig (Chor) aus
        <code>convert_choir.py</code>.
      </p>

      <div class="flex gap-2 mb-4">
        <UButton
          size="sm"
          :variant="mode === 'single' ? 'solid' : 'subtle'"
          :color="mode === 'single' ? 'primary' : 'neutral'"
          @click="mode = 'single'"
        >
          Einstimmig
        </UButton>
        <UButton
          size="sm"
          :variant="mode === 'multi' ? 'solid' : 'subtle'"
          :color="mode === 'multi' ? 'primary' : 'neutral'"
          @click="mode = 'multi'"
        >
          Mehrstimmig (Chor)
        </UButton>
      </div>

      <UCard v-if="mode === 'single'">
        <form
          class="flex flex-col gap-4"
          @submit.prevent="registerSong"
        >
          <UFormField label="Titel">
            <UInput
              v-model="title"
              placeholder="z.B. We Will Rock You"
              class="w-full"
            />
          </UFormField>

          <UFormField label="instrumental.wav">
            <input
              id="instrumental-input"
              type="file"
              accept="audio/wav,.wav"
              class="block w-full text-sm file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:bg-primary file:text-inverted"
              @change="onInstrumentalChange"
            >
          </UFormField>

          <UFormField label="lyrics.json">
            <input
              id="lyrics-input"
              type="file"
              accept="application/json,.json"
              class="block w-full text-sm file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:bg-primary file:text-inverted"
              @change="onLyricsChange"
            >
          </UFormField>

          <UAlert
            v-if="errorMessage"
            color="error"
            variant="subtle"
            :title="errorMessage"
          />

          <UButton
            type="submit"
            :loading="submitting"
            class="self-start"
          >
            Song registrieren
          </UButton>
        </form>
      </UCard>

      <UCard v-else>
        <form
          class="flex flex-col gap-5"
          @submit.prevent="registerMultitrack"
        >
          <UFormField label="Titel">
            <UInput
              v-model="title"
              placeholder="z.B. Irish Blessing (Chorsatz)"
              class="w-full"
            />
          </UFormField>

          <div class="flex flex-col gap-1">
            <div class="text-sm font-medium">
              Stimmen
            </div>
            <p class="text-xs text-muted">
              Pro Stimme eine Audiodatei (Export aus der Notensatz-Software).
              <code>lyrics.json</code> nur für singbare Stimmen – reine Begleitung
              (z.B. Klavier) bleibt ohne. Mindestens eine Stimme braucht Lyrics.
            </p>
          </div>

          <div class="flex flex-col gap-3">
            <div
              v-for="(row, i) in voiceRows"
              :key="row.fixed ? row.name : `custom-${i}`"
              class="rounded-lg border px-3 py-3 flex flex-col gap-2.5 transition-colors"
              :class="row.enabled ? 'border-primary/50 bg-elevated' : 'border-default'"
            >
              <div class="flex items-center gap-2">
                <input
                  :id="`voice-enabled-${i}`"
                  type="checkbox"
                  :checked="row.enabled"
                  class="size-4"
                  @change="row.enabled = ($event.target as HTMLInputElement).checked"
                >
                <label
                  v-if="row.fixed"
                  :for="`voice-enabled-${i}`"
                  class="text-sm font-medium select-none"
                >
                  {{ row.name }}
                </label>
                <UInput
                  v-else
                  v-model="row.name"
                  size="xs"
                  placeholder="Stimmname (z.B. Tenor-2)"
                  class="w-44"
                />
                <UButton
                  v-if="!row.fixed"
                  size="xs"
                  variant="ghost"
                  color="neutral"
                  icon="i-lucide-x"
                  class="ml-auto"
                  @click="removeVoice(i)"
                />
              </div>

              <div
                v-if="row.enabled"
                class="grid gap-2 sm:grid-cols-2 pl-6"
              >
                <label class="flex flex-col gap-1 text-xs text-muted">
                  Audio (Pflicht)
                  <input
                    :key="`audio-${row.name}-${resetNonce}`"
                    type="file"
                    accept="audio/*"
                    class="block w-full text-sm file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-primary file:text-inverted"
                    @change="onVoiceFile(row, 'audio', $event)"
                  >
                </label>
                <label class="flex flex-col gap-1 text-xs text-muted">
                  lyrics.json (optional)
                  <input
                    :key="`lyrics-${row.name}-${resetNonce}`"
                    type="file"
                    accept="application/json,.json"
                    class="block w-full text-sm file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-elevated file:text-default file:border file:border-default"
                    @change="onVoiceFile(row, 'lyrics', $event)"
                  >
                </label>
              </div>
            </div>
          </div>

          <UButton
            size="xs"
            variant="subtle"
            color="neutral"
            icon="i-lucide-plus"
            class="self-start"
            @click="addCustomVoice"
          >
            Weitere Stimme
          </UButton>

          <UAlert
            v-if="multiError"
            color="error"
            variant="subtle"
            :title="multiError"
          />

          <UButton
            type="submit"
            :loading="submittingMulti"
            class="self-start"
          >
            Chorlied registrieren
          </UButton>
        </form>
      </UCard>
    </div>

    <div>
      <h2 class="text-xl font-bold mb-1">
        Auf diesem Gerät
      </h2>
      <p class="text-sm text-muted mb-3">
        <code>.ksong</code>-Bundles aus dem Konvertierungs-Workflow importieren –
        danach offline spielbar, ganz ohne Server. Ideal fürs Handy.
      </p>

      <div class="flex flex-col gap-3 rounded-lg border border-default bg-elevated px-4 py-3 mb-4">
        <label class="flex flex-col gap-1 text-xs text-muted">
          .ksong-Datei importieren
          <input
            type="file"
            accept=".ksong,application/zip,application/octet-stream"
            :disabled="importing"
            class="block w-full text-sm file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:bg-primary file:text-inverted"
            @change="onKsongChange"
          >
        </label>
        <p
          v-if="importing"
          class="text-sm text-muted"
        >
          Importiere ...
        </p>
        <UAlert
          v-if="importedTitle"
          color="success"
          variant="subtle"
          :title="`„${importedTitle}“ importiert.`"
        />
        <UAlert
          v-if="importError"
          color="error"
          variant="subtle"
          :title="importError"
        />

        <div class="border-t border-default pt-3 flex flex-col gap-1.5">
          <span class="text-xs text-muted">
            Songs vom Heim-Server holen: IP des Rechners eingeben, Liste öffnen,
            Datei herunterladen, dann oben importieren.
          </span>
          <div class="flex flex-wrap items-center gap-2">
            <UInput
              v-model="shareHost"
              placeholder="192.168.178.102"
              size="xs"
              class="w-40"
            />
            <UButton
              v-if="shareUrl"
              :to="shareUrl"
              target="_blank"
              external
              size="xs"
              variant="subtle"
              color="neutral"
              icon="i-lucide-external-link"
            >
              Song-Liste öffnen
            </UButton>
          </div>
        </div>
      </div>

      <p
        v-if="!localSongs.length"
        class="text-sm text-muted mb-6"
      >
        Noch keine Songs auf diesem Gerät.
      </p>
      <div
        v-else
        class="flex flex-col gap-3 mb-6"
      >
        <UCard
          v-for="s in localSongs"
          :key="s.id"
        >
          <div class="flex items-center justify-between gap-4">
            <div>
              <div class="font-semibold">
                {{ s.title }}
              </div>
              <div class="text-xs text-muted">
                importiert {{ new Date(s.importedAt).toLocaleString('de-DE') }} · {{ formatSize(s.sizeBytes) }} · offline
              </div>
              <div
                v-if="s.tracks.length > 1"
                class="text-xs text-primary mt-0.5"
              >
                Chor · {{ s.tracks.map(t => t.voiceName).join(', ') }}
              </div>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <UButton
                :to="`/songs/local:${s.id}`"
                trailing-icon="i-lucide-mic"
                size="sm"
              >
                Singen
              </UButton>
              <UButton
                icon="i-lucide-trash-2"
                variant="ghost"
                color="neutral"
                size="sm"
                @click="removeLocal(s.id, s.title)"
              />
            </div>
          </div>
        </UCard>
      </div>

      <h2 class="text-xl font-bold mb-3">
        Auf dem Server
      </h2>

      <p
        v-if="loadingSongs"
        class="text-sm text-muted"
      >
        Lade...
      </p>
      <p
        v-else-if="songsError"
        class="text-sm text-muted"
      >
        Server nicht erreichbar – nur Geräte-Songs verfügbar.
      </p>
      <p
        v-else-if="!songs?.length"
        class="text-sm text-muted"
      >
        Noch keine Songs registriert.
      </p>

      <div
        v-else
        class="flex flex-col gap-3"
      >
        <UCard
          v-for="song in songs"
          :key="song.id"
        >
          <div class="flex items-center justify-between gap-4">
            <div>
              <div class="font-semibold">
                {{ song.title }}
              </div>
              <div class="text-xs text-muted">
                registriert {{ new Date(song.createdAt).toLocaleString('de-DE') }}
              </div>
              <div
                v-if="song.tracks.length > 1"
                class="text-xs text-primary mt-0.5"
              >
                Chor · {{ song.tracks.map(t => t.voiceName).join(', ') }}
              </div>
            </div>
            <UButton
              :to="`/songs/${song.id}`"
              trailing-icon="i-lucide-mic"
              size="sm"
            >
              Singen
            </UButton>
          </div>
        </UCard>
      </div>
    </div>
  </div>
</template>
