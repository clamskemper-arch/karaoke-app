/**
 * Erfasst Mikrofon-Audio und schaetzt in Echtzeit die Grundfrequenz der
 * Stimme per Autokorrelation (klassischer ACF2+-Ansatz, siehe autoCorrelate
 * in app/utils/pitch.ts). Gedacht fuer eine einzelne singende Stimme (monophon).
 */
export function usePitchDetector() {
  const currentHz = ref<number | null>(null)
  const isActive = ref(false)
  const errorMessage = ref('')
  // Nur fuers Debug-Overlay: aktueller Eingangspegel (RMS) und der Name des
  // vom Browser gewaehlten Mikrofons - damit man "zu leise" von "falsches
  // Geraet"/"kein Signal" unterscheiden kann.
  const level = ref(0)
  const deviceLabel = ref('')

  let audioContext: AudioContext | null = null
  let analyser: AnalyserNode | null = null
  let source: MediaStreamAudioSourceNode | null = null
  let stream: MediaStream | null = null
  let rafId: number | null = null
  let buffer: Float32Array<ArrayBuffer> | null = null

  function loop() {
    if (!analyser || !audioContext || !buffer) return
    analyser.getFloatTimeDomainData(buffer)
    let sum = 0
    for (let i = 0; i < buffer.length; i++) sum += buffer[i]! * buffer[i]!
    level.value = Math.sqrt(sum / buffer.length)
    const hz = autoCorrelate(buffer, audioContext.sampleRate)
    currentHz.value = hz > 0 ? hz : null
    rafId = requestAnimationFrame(loop)
  }

  async function start() {
    if (isActive.value) return
    errorMessage.value = ''
    try {
      // autoGainControl AN: ein eingebautes Laptop-Mikro liefert ohne AGC oft
      // einen so leisen Pegel, dass die Pitch-Erkennung nie anspringt.
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: true
        }
      })
      deviceLabel.value = stream.getAudioTracks()[0]?.label ?? ''
      const AudioContextCtor = window.AudioContext
        ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      audioContext = new AudioContextCtor()
      await audioContext.resume()
      source = audioContext.createMediaStreamSource(stream)
      analyser = audioContext.createAnalyser()
      analyser.fftSize = 2048
      buffer = new Float32Array(analyser.fftSize)
      source.connect(analyser)
      isActive.value = true
      loop()
    } catch {
      errorMessage.value = 'Mikrofon konnte nicht aktiviert werden (Zugriff verweigert oder kein Mikrofon gefunden).'
      stop()
    }
  }

  function stop() {
    if (rafId !== null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
    stream?.getTracks().forEach(track => track.stop())
    if (audioContext && audioContext.state !== 'closed') audioContext.close()
    audioContext = null
    analyser = null
    source = null
    stream = null
    buffer = null
    isActive.value = false
    currentHz.value = null
    level.value = 0
    deviceLabel.value = ''
  }

  onBeforeUnmount(stop)

  return { currentHz, isActive, errorMessage, level, deviceLabel, start, stop }
}

// autoCorrelate() liegt bei den Pitch-Utils (app/utils/pitch.ts) und wird hier
// per Nuxt-Auto-Import verwendet - reine Funktion, dort unit-getestet.
