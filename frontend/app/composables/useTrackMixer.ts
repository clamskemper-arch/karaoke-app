export interface MixerTrackDef {
  voiceName: string
  audioUrl: string
}

/**
 * Spielt mehrere Audio-Spuren synchron ab (Web Audio API), mit einem GainNode
 * pro Spur zum live Stumm-/Lautschalten - Grundlage fuer den Mehrstimmen-Mixer
 * (Vertical Slice 5, Teil 3: Stimmwahl + "welche Stimmen zusaetzlich hoeren").
 * Ersetzt das bisherige einzelne <audio>-Element, das nur eine Spur konnte.
 *
 * AudioBufferSourceNode kann nur einmal gestartet werden (kein pause/resume
 * auf demselben Node) - deshalb wird bei play()/seek() ein neuer Node pro
 * Spur erzeugt und die Song-Position manuell ueber startContextTime/
 * startOffset nachgefuehrt, statt sich auf eine eingebaute currentTime zu
 * verlassen.
 */
export function useTrackMixer(trackDefs: Ref<MixerTrackDef[]>) {
  const isLoading = ref(false)
  const isReady = ref(false)
  const error = ref('')
  const isPlaying = ref(false)
  const currentTime = ref(0)
  const duration = ref(0)
  const enabled = reactive<Record<string, boolean>>({})

  let audioContext: AudioContext | null = null
  const buffers = new Map<string, AudioBuffer>()
  const gainNodes = new Map<string, GainNode>()
  const sourceNodes = new Map<string, AudioBufferSourceNode>()
  let startContextTime = 0
  let startOffset = 0
  let rafId: number | null = null

  function stopSources() {
    for (const src of sourceNodes.values()) {
      try {
        src.stop()
      } catch {
        // war schon gestoppt (z.B. natuerliches Songende) - ignorieren
      }
    }
    sourceNodes.clear()
  }

  function pause() {
    if (!isPlaying.value || !audioContext) return
    currentTime.value = startOffset + (audioContext.currentTime - startContextTime)
    stopSources()
    isPlaying.value = false
  }

  function tick() {
    if (isPlaying.value && audioContext) {
      const t = startOffset + (audioContext.currentTime - startContextTime)
      if (t >= duration.value) {
        currentTime.value = duration.value
        pause()
      } else {
        currentTime.value = t
      }
    }
    rafId = requestAnimationFrame(tick)
  }

  function teardown() {
    stopSources()
    for (const g of gainNodes.values()) g.disconnect()
    gainNodes.clear()
    buffers.clear()
    if (audioContext && audioContext.state !== 'closed') void audioContext.close()
    audioContext = null
    isReady.value = false
    isPlaying.value = false
    currentTime.value = 0
    duration.value = 0
    startOffset = 0
  }

  async function load() {
    // Bei lokalen Songs steht trackDefs beim Mount noch leer (wird erst aus der
    // IndexedDB-Bibliothek nachgeladen) - dann hier nichts tun, der Watcher
    // unten ruft load() erneut auf, sobald die Spuren da sind.
    if (trackDefs.value.length === 0) return
    isLoading.value = true
    error.value = ''
    try {
      const AudioContextCtor = window.AudioContext
        ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      audioContext = new AudioContextCtor()

      let maxDuration = 0
      for (const t of trackDefs.value) {
        const res = await fetch(t.audioUrl)
        if (!res.ok) throw new Error(`Audio fuer Stimme '${t.voiceName}' konnte nicht geladen werden`)
        const arrayBuffer = await res.arrayBuffer()
        const buffer = await audioContext.decodeAudioData(arrayBuffer)
        buffers.set(t.voiceName, buffer)
        maxDuration = Math.max(maxDuration, buffer.duration)

        const gain = audioContext.createGain()
        gain.gain.value = enabled[t.voiceName] ? 1 : 0
        gain.connect(audioContext.destination)
        gainNodes.set(t.voiceName, gain)
      }
      duration.value = maxDuration
      isReady.value = true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Audio konnte nicht geladen werden'
    } finally {
      isLoading.value = false
    }
  }

  // Wechseln die Spuren (anderer Song, oder lokale Spuren spaeter nachgeladen),
  // altes AudioContext abbauen und neu laden.
  const trackKey = computed(() => trackDefs.value.map(t => `${t.voiceName}|${t.audioUrl}`).join(','))
  watch(trackKey, (key, prev) => {
    if (key === prev) return
    teardown()
    void load()
  })

  function play() {
    if (!audioContext || !isReady.value || isPlaying.value) return
    if (audioContext.state === 'suspended') void audioContext.resume()

    startOffset = currentTime.value
    startContextTime = audioContext.currentTime
    for (const t of trackDefs.value) {
      const buffer = buffers.get(t.voiceName)
      const gain = gainNodes.get(t.voiceName)
      if (!buffer || !gain) continue
      const src = audioContext.createBufferSource()
      src.buffer = buffer
      src.connect(gain)
      src.start(0, Math.min(startOffset, buffer.duration))
      sourceNodes.set(t.voiceName, src)
    }
    isPlaying.value = true
  }

  function seek(time: number) {
    const clamped = Math.max(0, Math.min(time, duration.value))
    const wasPlaying = isPlaying.value
    if (wasPlaying) stopSources()
    currentTime.value = clamped
    startOffset = clamped
    isPlaying.value = false
    if (wasPlaying) play()
  }

  function setEnabled(voiceName: string, value: boolean) {
    enabled[voiceName] = value
    gainNodes.get(voiceName)?.gain.setValueAtTime(value ? 1 : 0, audioContext?.currentTime ?? 0)
  }

  function toggleEnabled(voiceName: string) {
    setEnabled(voiceName, !enabled[voiceName])
  }

  onMounted(() => {
    rafId = requestAnimationFrame(tick)
    void load()
  })

  onBeforeUnmount(() => {
    if (rafId !== null) cancelAnimationFrame(rafId)
    stopSources()
    if (audioContext && audioContext.state !== 'closed') void audioContext.close()
  })

  return {
    isLoading,
    isReady,
    error,
    isPlaying,
    currentTime,
    duration,
    enabled,
    play,
    pause,
    seek,
    setEnabled,
    toggleEnabled
  }
}
