/**
 * Haelt den Bildschirm wach, solange die App offen und sichtbar ist (Screen
 * Wake Lock API) - sonst sperrt sich das Handy waehrend des Singens/
 * Einsingens, wenn man es ja gerade nicht beruehrt. Global in app.vue
 * eingehaengt, nicht nur auf der Player-/Einsingen-Seite: ein eingeschalteter
 * Bildschirm in der Songliste ist harmlos, ein gesperrter mitten im Lied
 * nicht. Der Browser gibt das Lock automatisch frei, sobald der Tab in den
 * Hintergrund geht - das holen wir uns beim Wiedersichtbarwerden zurueck.
 *
 * Nicht ueberall unterstuetzt (u.a. Safari < 16.4) - dann einfach ein No-Op,
 * kein Fehler fuer den Nutzer noetig (Bildschirm sperrt sich dann halt wie
 * gewohnt, kein Regressionsrisiko).
 */
export function useWakeLock() {
  const supported = typeof navigator !== 'undefined' && 'wakeLock' in navigator
  let sentinel: WakeLockSentinel | null = null

  async function request() {
    if (!supported || sentinel || document.visibilityState !== 'visible') return
    try {
      sentinel = await navigator.wakeLock.request('screen')
      sentinel.addEventListener('release', () => {
        sentinel = null
      })
    } catch {
      // z.B. Energiesparmodus oder Tab gerade nicht aktiv - einfach weglassen
    }
  }

  function release() {
    void sentinel?.release()
    sentinel = null
  }

  function handleVisibilityChange() {
    if (document.visibilityState === 'visible') void request()
  }

  onMounted(() => {
    void request()
    document.addEventListener('visibilitychange', handleVisibilityChange)
  })

  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    release()
  })

  return { supported }
}
