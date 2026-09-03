import { unzipSync, strFromU8 } from 'fflate'

/**
 * Geraete-lokale Song-Bibliothek: importierte .ksong-Bundles (siehe
 * konverter/ksong.py) landen in IndexedDB und sind danach offline abspielbar,
 * ganz ohne Backend. Gedacht fuer die mobile Nutzung ("Songs vorher am Rechner
 * konvertieren, dann aufs Handy importieren").
 *
 * Ein .ksong ist ein ZIP:
 *   manifest.json                {ksongVersion, title, createdAt, tracks:[...]}
 *   tracks/<Stimme>/audio.m4a    AAC (oder .wav als Fallback)
 *   tracks/<Stimme>/lyrics.json  nur bei singbaren Stimmen
 *
 * Die Refs sind bewusst auf Modulebene (Singleton) - Songliste und Song-Seite
 * teilen sich denselben Zustand, ohne extra Store.
 */

export interface KLyricWord { word: string, start: number, end: number, midi: number | null, note: string | null }
export interface KLyricLine { line: string, start: number, end: number, words: KLyricWord[] }

export interface LibraryTrack {
  voiceName: string
  audioKey: string
  audioType: string
  lyricsKey: string | null
}

export interface LibrarySong {
  id: string
  title: string
  createdAt: string
  importedAt: string
  sizeBytes: number
  tracks: LibraryTrack[]
}

interface AssetRecord { key: string, blob: Blob }

const DB_NAME = 'karaoke-library'
const DB_VERSION = 1
const STORE_SONGS = 'songs'
const STORE_ASSETS = 'assets'

const songs = ref<LibrarySong[]>([])
const loaded = ref(false)
const error = ref('')

// assetKey -> Object-URL, damit dieselbe Datei nicht mehrfach URL-Objekte belegt
const urlCache = new Map<string, string>()

let dbPromise: Promise<IDBDatabase> | null = null

function openDb(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE_SONGS)) db.createObjectStore(STORE_SONGS, { keyPath: 'id' })
      if (!db.objectStoreNames.contains(STORE_ASSETS)) db.createObjectStore(STORE_ASSETS, { keyPath: 'key' })
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
  return dbPromise
}

function getAllSongs(): Promise<LibrarySong[]> {
  return openDb().then(db => new Promise<LibrarySong[]>((resolve, reject) => {
    const req = db.transaction(STORE_SONGS, 'readonly').objectStore(STORE_SONGS).getAll()
    req.onsuccess = () => resolve(req.result as LibrarySong[])
    req.onerror = () => reject(req.error)
  }))
}

function getAsset(key: string): Promise<AssetRecord | undefined> {
  return openDb().then(db => new Promise<AssetRecord | undefined>((resolve, reject) => {
    const req = db.transaction(STORE_ASSETS, 'readonly').objectStore(STORE_ASSETS).get(key)
    req.onsuccess = () => resolve(req.result as AssetRecord | undefined)
    req.onerror = () => reject(req.error)
  }))
}

function putSongWithAssets(song: LibrarySong, assets: AssetRecord[]): Promise<void> {
  return openDb().then(db => new Promise<void>((resolve, reject) => {
    const t = db.transaction([STORE_SONGS, STORE_ASSETS], 'readwrite')
    t.oncomplete = () => resolve()
    t.onerror = () => reject(t.error)
    t.objectStore(STORE_SONGS).put(song)
    const store = t.objectStore(STORE_ASSETS)
    for (const a of assets) store.put(a)
  }))
}

function deleteSongWithAssets(id: string, keys: string[]): Promise<void> {
  return openDb().then(db => new Promise<void>((resolve, reject) => {
    const t = db.transaction([STORE_SONGS, STORE_ASSETS], 'readwrite')
    t.oncomplete = () => resolve()
    t.onerror = () => reject(t.error)
    t.objectStore(STORE_SONGS).delete(id)
    const store = t.objectStore(STORE_ASSETS)
    for (const k of keys) store.delete(k)
  }))
}

function uuid(): string {
  return globalThis.crypto?.randomUUID?.()
    ?? `k-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

/** Kopiert die fflate-Ausgabe in einen frischen Uint8Array (garantiert
 *  ArrayBuffer-basiert, nicht SharedArrayBuffer) und packt sie in ein Blob. */
function bytesToBlob(bytes: Uint8Array, type: string): Blob {
  return new Blob([new Uint8Array(bytes)], { type })
}

function mimeForPath(p: string): string {
  const ext = p.slice(p.lastIndexOf('.') + 1).toLowerCase()
  const map: Record<string, string> = {
    m4a: 'audio/mp4', mp4: 'audio/mp4', aac: 'audio/aac', mp3: 'audio/mpeg',
    wav: 'audio/wav', ogg: 'audio/ogg', opus: 'audio/ogg', flac: 'audio/flac'
  }
  return map[ext] ?? 'application/octet-stream'
}

function assetKeysOf(song: LibrarySong): string[] {
  const keys: string[] = []
  for (const t of song.tracks) {
    keys.push(t.audioKey)
    if (t.lyricsKey) keys.push(t.lyricsKey)
  }
  return keys
}

async function refresh(): Promise<void> {
  if (!import.meta.client) return
  try {
    const all = await getAllSongs()
    all.sort((a, b) => b.importedAt.localeCompare(a.importedAt))
    songs.value = all
    loaded.value = true
    error.value = ''
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Bibliothek konnte nicht geladen werden'
  }
}

interface KsongManifest {
  ksongVersion: number
  title: string
  createdAt?: string
  tracks: { voiceName: string, audio: string, lyrics: string | null }[]
}

async function importKsong(file: File): Promise<LibrarySong> {
  const raw = new Uint8Array(await file.arrayBuffer())

  let entries: Record<string, Uint8Array>
  try {
    entries = unzipSync(raw)
  } catch {
    throw new Error('Datei ist kein gültiges .ksong (ZIP nicht lesbar).')
  }

  const manifestBytes = entries['manifest.json']
  if (!manifestBytes) throw new Error('.ksong ohne manifest.json.')

  let manifest: KsongManifest
  try {
    manifest = JSON.parse(strFromU8(manifestBytes))
  } catch {
    throw new Error('manifest.json im .ksong ist kein gültiges JSON.')
  }
  if (manifest.ksongVersion !== 1) {
    throw new Error(`.ksong-Version ${manifest.ksongVersion} wird von dieser App-Version nicht unterstützt.`)
  }
  if (!manifest.title || !Array.isArray(manifest.tracks) || manifest.tracks.length === 0) {
    throw new Error('.ksong-Manifest unvollständig (Titel oder Stimmen fehlen).')
  }

  const id = uuid()
  const assets: AssetRecord[] = []
  const tracks: LibraryTrack[] = []

  for (const t of manifest.tracks) {
    const audioBytes = entries[t.audio]
    if (!audioBytes) throw new Error(`Audio fehlt im Bundle: ${t.audio}`)
    const audioType = mimeForPath(t.audio)
    const audioKey = `${id}::${t.audio}`
    assets.push({ key: audioKey, blob: bytesToBlob(audioBytes, audioType) })

    let lyricsKey: string | null = null
    if (t.lyrics) {
      const lyricsBytes = entries[t.lyrics]
      if (!lyricsBytes) throw new Error(`Lyrics fehlen im Bundle: ${t.lyrics}`)
      try {
        JSON.parse(strFromU8(lyricsBytes))
      } catch {
        throw new Error(`Lyrics im Bundle sind kein gültiges JSON: ${t.lyrics}`)
      }
      lyricsKey = `${id}::${t.lyrics}`
      assets.push({ key: lyricsKey, blob: bytesToBlob(lyricsBytes, 'application/json') })
    }

    tracks.push({ voiceName: t.voiceName, audioKey, audioType, lyricsKey })
  }

  const song: LibrarySong = {
    id,
    title: manifest.title,
    createdAt: manifest.createdAt ?? new Date().toISOString(),
    importedAt: new Date().toISOString(),
    sizeBytes: file.size,
    tracks
  }

  await putSongWithAssets(song, assets)
  songs.value = [song, ...songs.value]
  return song
}

async function remove(id: string): Promise<void> {
  const song = songs.value.find(s => s.id === id) ?? (await getAllSongs()).find(s => s.id === id)
  const keys = song ? assetKeysOf(song) : []
  await deleteSongWithAssets(id, keys)
  for (const k of keys) {
    const url = urlCache.get(k)
    if (url) {
      URL.revokeObjectURL(url)
      urlCache.delete(k)
    }
  }
  songs.value = songs.value.filter(s => s.id !== id)
}

/** Object-URL fuer eine Asset-Datei (Audio) - fuer <audio>/fetch/decodeAudioData. */
async function assetUrl(key: string): Promise<string> {
  const cached = urlCache.get(key)
  if (cached) return cached
  const rec = await getAsset(key)
  if (!rec) throw new Error(`Asset nicht in der Bibliothek: ${key}`)
  const url = URL.createObjectURL(rec.blob)
  urlCache.set(key, url)
  return url
}

async function getLyricsByKey(key: string): Promise<KLyricLine[]> {
  const rec = await getAsset(key)
  if (!rec) throw new Error(`Lyrics nicht in der Bibliothek: ${key}`)
  return JSON.parse(await rec.blob.text()) as KLyricLine[]
}

function findSong(id: string): LibrarySong | undefined {
  return songs.value.find(s => s.id === id)
}

export function useSongLibrary() {
  return {
    songs: readonly(songs),
    loaded: readonly(loaded),
    error: readonly(error),
    refresh,
    importKsong,
    remove,
    assetUrl,
    getLyricsByKey,
    findSong
  }
}
