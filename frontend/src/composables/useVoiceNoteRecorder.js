import { computed, getCurrentScope, onScopeDispose, ref, shallowRef } from 'vue'

import { notify } from '../utils/toasts'

const MAX_DURATION_SECONDS = 300
const PEAK_COUNT = 64
const LEVEL_BAR_COUNT = 12

function selectRecordingMimeType() {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/mp4;codecs=mp4a.40.2',
    'audio/mp4',
    'audio/ogg;codecs=opus',
    'audio/webm',
  ]
  return candidates.find(type => MediaRecorder.isTypeSupported?.(type)) || ''
}

function filenameForMimeType(mimeType) {
  const normalized = String(mimeType || '').toLowerCase()
  const extension = normalized.includes('mp4') ? 'm4a' : normalized.includes('ogg') ? 'ogg' : 'weba'
  return `voice-note-${Date.now()}.${extension}`
}

function createMediaRecorder(stream, mimeType) {
  const options = {
    ...(mimeType ? { mimeType } : {}),
    audioBitsPerSecond: 64000,
  }
  try {
    return new MediaRecorder(stream, options)
  } catch {
    return new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
  }
}

function mixAudioBuffer(audioBuffer) {
  const mono = new Float32Array(audioBuffer.length)
  for (let channel = 0; channel < audioBuffer.numberOfChannels; channel += 1) {
    const channelData = audioBuffer.getChannelData(channel)
    for (let index = 0; index < mono.length; index += 1) {
      mono[index] += channelData[index] / audioBuffer.numberOfChannels
    }
  }
  return mono
}

function extractPeaks(samples, count = PEAK_COUNT) {
  if (!samples?.length) return Array.from({ length: count }, () => 0.08)
  const peaks = []
  const bucketSize = Math.max(1, Math.floor(samples.length / count))
  let maxPeak = 0
  for (let bucket = 0; bucket < count; bucket += 1) {
    const start = bucket * bucketSize
    const end = bucket === count - 1 ? samples.length : Math.min(samples.length, start + bucketSize)
    let sum = 0
    for (let index = start; index < end; index += 1) sum += samples[index] * samples[index]
    const peak = Math.sqrt(sum / Math.max(1, end - start))
    maxPeak = Math.max(maxPeak, peak)
    peaks.push(peak)
  }
  const scale = maxPeak > 0 ? maxPeak : 1
  return peaks.map(peak => Math.max(0.06, Math.min(1, peak / scale)))
}

async function decodeRecording(blob) {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext
  if (!AudioContextClass) throw new Error('Audio decoding is unavailable')
  const context = new AudioContextClass()
  try {
    const decoded = await context.decodeAudioData(await blob.arrayBuffer())
    const mono = mixAudioBuffer(decoded)
    return {
      duration: decoded.duration,
      peaks: extractPeaks(mono),
    }
  } finally {
    await context.close().catch(() => {})
  }
}

export function useVoiceNoteRecorder() {
  const isSupported = ref(Boolean(
    typeof window !== 'undefined'
    && typeof window.MediaRecorder !== 'undefined'
    && window.navigator?.mediaDevices?.getUserMedia,
  ))
  const state = ref('idle')
  const elapsedSeconds = ref(0)
  const levels = ref(Array.from({ length: LEVEL_BAR_COUNT }, () => 0.08))
  const pendingVoiceNote = shallowRef(null)

  let mediaRecorder = null
  let mediaStream = null
  let analyserContext = null
  let analyser = null
  let animationFrame = 0
  let timer = 0
  let startedAt = 0
  let chunks = []
  let stopResolver = null
  let stopRejecter = null
  let stopPromise = null
  let discardRecording = false
  let activeRecordingId = 0

  const isRecording = computed(() => state.value === 'recording')
  const hasPendingVoiceNote = computed(() => Boolean(pendingVoiceNote.value))

  function stopTracks() {
    mediaStream?.getTracks().forEach(track => track.stop())
    mediaStream = null
  }

  function stopMeters() {
    if (animationFrame) cancelAnimationFrame(animationFrame)
    animationFrame = 0
    if (timer) window.clearInterval(timer)
    timer = 0
    analyser?.disconnect?.()
    analyser = null
    analyserContext?.close?.().catch(() => {})
    analyserContext = null
    levels.value = Array.from({ length: LEVEL_BAR_COUNT }, () => 0.08)
  }

  function updateLevels() {
    if (!analyser || state.value !== 'recording') return
    const bins = new Uint8Array(analyser.frequencyBinCount)
    analyser.getByteFrequencyData(bins)
    levels.value = Array.from({ length: LEVEL_BAR_COUNT }, (_, bar) => {
      const start = Math.floor(bar * bins.length / LEVEL_BAR_COUNT)
      const end = Math.max(start + 1, Math.floor((bar + 1) * bins.length / LEVEL_BAR_COUNT))
      let sum = 0
      for (let index = start; index < end; index += 1) sum += bins[index]
      return Math.max(0.08, Math.min(1, sum / Math.max(1, end - start) / 160))
    })
    animationFrame = requestAnimationFrame(updateLevels)
  }

  async function finalizeRecording(recordingId) {
    if (recordingId !== activeRecordingId) return
    stopMeters()
    stopTracks()
    if (discardRecording) {
      discardRecording = false
      chunks = []
      mediaRecorder = null
      state.value = pendingVoiceNote.value ? 'ready' : 'idle'
      return
    }
    const mimeType = mediaRecorder?.mimeType || selectRecordingMimeType() || 'audio/webm'
    const blob = new Blob(chunks, { type: mimeType })
    const fallbackDuration = Math.min(MAX_DURATION_SECONDS, Math.max(0.1, (Date.now() - startedAt) / 1000))
    chunks = []
    mediaRecorder = null

    let decoded = null
    try {
      decoded = await decodeRecording(blob)
    } catch (error) {
      console.warn('Voice note waveform extraction unavailable')
    }
    if (recordingId !== activeRecordingId || discardRecording) {
      discardRecording = false
      state.value = pendingVoiceNote.value ? 'ready' : 'idle'
      return
    }
    const duration = Math.min(MAX_DURATION_SECONDS, Math.max(0.1, decoded?.duration || fallbackDuration))
    const note = {
      blob,
      file: blob,
      name: filenameForMimeType(mimeType),
      mime: mimeType,
      duration,
      peaks: decoded?.peaks || Array.from({ length: PEAK_COUNT }, () => 0.08),
      previewUrl: URL.createObjectURL(blob),
    }
    pendingVoiceNote.value = note
    state.value = 'ready'
    stopResolver?.(note)
    stopResolver = null
    stopRejecter = null
    stopPromise = null
  }

  async function startRecording() {
    if (!isSupported.value || state.value === 'recording') return false
    if (pendingVoiceNote.value) removeVoiceNote()
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          autoGainControl: true,
          noiseSuppression: true,
        },
      })
      const mimeType = selectRecordingMimeType()
      discardRecording = false
      const recordingId = ++activeRecordingId
      mediaRecorder = createMediaRecorder(mediaStream, mimeType)
      chunks = []
      mediaRecorder.addEventListener('dataavailable', event => {
        if (event.data?.size) chunks.push(event.data)
      })
      mediaRecorder.addEventListener('stop', () => { void finalizeRecording(recordingId) }, { once: true })
      mediaRecorder.addEventListener('error', event => {
        if (recordingId !== activeRecordingId) return
        activeRecordingId += 1
        stopRejecter?.(event.error || new Error('Recording failed'))
        stopResolver = null
        stopRejecter = null
        stopPromise = null
        stopMeters()
        stopTracks()
        mediaRecorder = null
        state.value = 'idle'
        notify('Voice recording failed. Please try again.')
      })

      const AudioContextClass = window.AudioContext || window.webkitAudioContext
      if (AudioContextClass) {
        analyserContext = new AudioContextClass()
        const source = analyserContext.createMediaStreamSource(mediaStream)
        analyser = analyserContext.createAnalyser()
        analyser.fftSize = 64
        analyser.smoothingTimeConstant = 0.72
        source.connect(analyser)
      }

      elapsedSeconds.value = 0
      startedAt = Date.now()
      state.value = 'recording'
      mediaRecorder.start(1000)
      updateLevels()
      timer = window.setInterval(() => {
        elapsedSeconds.value = Math.min(MAX_DURATION_SECONDS, (Date.now() - startedAt) / 1000)
        if (elapsedSeconds.value >= MAX_DURATION_SECONDS) void stopRecording()
      }, 100)
      return true
    } catch (error) {
      activeRecordingId += 1
      stopMeters()
      stopTracks()
      mediaRecorder = null
      state.value = 'idle'
      const denied = error?.name === 'NotAllowedError' || error?.name === 'SecurityError'
      notify(denied ? 'Microphone access was denied.' : 'Microphone access is unavailable.')
      return false
    }
  }

  function stopRecording() {
    if (state.value !== 'recording' || !mediaRecorder) return Promise.resolve(pendingVoiceNote.value)
    if (stopPromise) return stopPromise
    const pendingStop = new Promise((resolve, reject) => {
      stopResolver = resolve
      stopRejecter = reject
    })
    stopPromise = pendingStop
    try {
      mediaRecorder.stop()
    } catch (error) {
      const reject = stopRejecter
      stopResolver = null
      stopRejecter = null
      stopPromise = null
      reject?.(error)
    }
    return pendingStop
  }

  function cancelRecording() {
    if (mediaRecorder && state.value === 'recording') {
      discardRecording = true
      activeRecordingId += 1
      try {
        mediaRecorder.stop()
      } catch {
        // Recorder may already be stopping.
      }
    }
    stopResolver?.(null)
    stopResolver = null
    stopRejecter = null
    stopPromise = null
    chunks = []
    mediaRecorder = null
    stopMeters()
    stopTracks()
    elapsedSeconds.value = 0
    state.value = pendingVoiceNote.value ? 'ready' : 'idle'
  }

  function removeVoiceNote() {
    cancelRecording()
    if (pendingVoiceNote.value?.previewUrl) URL.revokeObjectURL(pendingVoiceNote.value.previewUrl)
    pendingVoiceNote.value = null
    state.value = 'idle'
  }

  if (getCurrentScope()) onScopeDispose(removeVoiceNote)

  return {
    isSupported,
    state,
    isRecording,
    hasPendingVoiceNote,
    elapsedSeconds,
    levels,
    pendingVoiceNote,
    startRecording,
    stopRecording,
    cancelRecording,
    removeVoiceNote,
  }
}
