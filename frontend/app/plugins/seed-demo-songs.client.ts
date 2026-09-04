/**
 * Fuellt die Geraete-Bibliothek beim allerersten Start mit ein paar
 * gemeinfreien Beispiel-Songs (siehe frontend/public/seed-songs/), damit
 * neue Nutzer nicht erst manuell etwas importieren muessen, um die App
 * auszuprobieren.
 *
 * Laeuft nur einmal (Merker in localStorage) und nur, wenn die Bibliothek
 * zu dem Zeitpunkt wirklich leer ist - so wird weder ein bewusst geleertes
 * Geraet erneut befuellt, noch mischt sich das hier in eine schon bestehende
 * Bibliothek ein.
 */

const SEEDED_KEY = 'karaoke:demoSongsSeeded'

const DEMO_SONGS = [
  { file: 'amazing-grace.ksong' },
  { file: 'bruder-jakob.ksong' }
]

export default defineNuxtPlugin(async () => {
  let alreadySeeded = true
  try {
    alreadySeeded = localStorage.getItem(SEEDED_KEY) === '1'
  } catch {
    return // kein localStorage -> lieber nichts automatisch importieren
  }
  if (alreadySeeded) return

  const { songs, refresh, importKsong } = useSongLibrary()
  await refresh()

  if (songs.value.length === 0) {
    const config = useRuntimeConfig()
    const base = config.app.baseURL.endsWith('/') ? config.app.baseURL : `${config.app.baseURL}/`

    for (const demo of DEMO_SONGS) {
      try {
        const res = await fetch(`${base}seed-songs/${demo.file}`)
        if (!res.ok) continue
        const blob = await res.blob()
        await importKsong(new File([blob], demo.file, { type: 'application/zip' }))
      } catch {
        // ein einzelner Demo-Song darf fehlschlagen, ohne die App zu blockieren
      }
    }
  }

  try {
    localStorage.setItem(SEEDED_KEY, '1')
  } catch {
    // s.o. - dann halt kein Merker, im schlimmsten Fall laeuft's naechstes Mal nochmal
  }
})
