/**
 * Erfasst Mikrofon-Audio und schaetzt in Echtzeit die Grundfrequenz der
 * Stimme per Autokorrelation (klassischer ACF2+-Ansatz, siehe autoCorrelate
 * unten). Gedacht fuer eine einzelne singende Stimme (monophon).
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

/**
 * Autokorrelations-basierte Grundfrequenzschaetzung (ACF2+). Liefert -1,
 * wenn das Signal zu leise ist oder keine klare Periodizitaet erkennbar ist.
 * Gleicher Grundansatz wie in aelteren Web-Audio-Pitch-Detector-Demos ueblich.
 */
function autoCorrelate(buf: Float32Array, sampleRate: number): number {
  const size = buf.length

  let rms = 0
  for (let i = 0; i < size; i++) rms += buf[i]! * buf[i]!
  rms = Math.sqrt(rms / size)
  if (rms < 0.005) return -1

  // Stille am Anfang/Ende abschneiden, damit sich die Autokorrelation auf
  // den eigentlichen Signalausschnitt konzentriert
  let start = 0
  let end = size - 1
  const threshold = 0.2
  for (let i = 0; i < size / 2; i++) {
    if (Math.abs(buf[i]!) >= threshold) {
      start = i
      break
    }
  }
  for (let i = 1; i < size / 2; i++) {
    if (Math.abs(buf[size - i]!) >= threshold) {
      end = size - i
      break
    }
  }

  const trimmed = buf.slice(start, end)
  const n = trimmed.length
  if (n < 2) return -1

  const correlations = new Float32Array(n)
  for (let lag = 0; lag < n; lag++) {
    let sum = 0
    for (let i = 0; i < n - lag; i++) sum += trimmed[i]! * trimmed[i + lag]!
    correlations[lag] = sum
  }

  // Erstes Abfallen ueberspringen (lag 0 ist immer das Maximum), dann das
  // naechste Maximum suchen - das entspricht der Grundperiode der Stimme
  let d = 0
  while (d < n - 1 && correlations[d]! > correlations[d + 1]!) d++

  let maxPos = -1
  let maxVal = -Infinity
  for (let i = d; i < n; i++) {
    if (correlations[i]! > maxVal) {
      maxVal = correlations[i]!
      maxPos = i
    }
  }
  if (maxPos <= 0) return -1

  // Parabolische Interpolation um den Peak fuer eine subsample-genaue
  // Periodenlaenge
  let period = maxPos
  const x1 = (maxPos > 0 ? correlations[maxPos - 1] : correlations[maxPos])!
  const x2 = correlations[maxPos]!
  const x3 = (maxPos < n - 1 ? correlations[maxPos + 1] : correlations[maxPos])!
  const a = (x1 + x3 - 2 * x2) / 2
  const b = (x3 - x1) / 2
  if (a !== 0) period = maxPos - b / (2 * a)

  if (period <= 0) return -1
  return sampleRate / period
}
