<template>
  <div class="voice-note" :class="{ 'voice-note--compact': compact, 'is-playing': isPlaying }">
    <div class="voice-note__player">
      <button
        type="button"
        class="voice-note__play"
        :class="{ 'is-loading': isLoading }"
        :disabled="!url"
        :aria-label="isLoading ? 'Loading voice note' : isPlaying ? 'Pause voice note' : 'Play voice note'"
        :aria-busy="isLoading"
        @click.stop="togglePlayback"
      >
        <span v-if="isLoading" class="voice-note__loading" aria-hidden="true"></span>
        <svg v-else class="icon"><use :href="isPlaying ? '#icon-pause' : '#icon-play'" /></svg>
      </button>

      <div
        class="voice-note__waveform"
        role="slider"
        tabindex="0"
        aria-label="Voice note playback position"
        :aria-valuemin="0"
        :aria-valuemax="Math.round(displayDuration)"
        :aria-valuenow="Math.round(currentTime)"
        @pointerdown.stop.prevent="startSeeking"
        @pointermove.stop.prevent="moveSeeking"
        @pointerup.stop.prevent="finishSeeking"
        @pointercancel="finishSeeking"
        @keydown.left.prevent="seekBy(-5)"
        @keydown.right.prevent="seekBy(5)"
      >
        <span
          v-for="(peak, index) in displayPeaks"
          :key="index"
          class="voice-note__bar"
          :class="{ 'is-played': barProgress(index) <= progress }"
          :style="{ height: `${Math.max(14, peak * 100)}%` }"
        ></span>
      </div>

      <span class="voice-note__time">{{ timeLabel }}</span>
      <audio
        ref="audioEl"
        :src="url"
        preload="metadata"
        playsinline
        @loadedmetadata="handleMetadata"
        @timeupdate="handleTimeUpdate"
        @playing="handlePlaying"
        @pause="handlePause"
        @waiting="handleWaiting"
        @stalled="handleWaiting"
        @canplay="handleCanPlay"
        @ended="handleEnded"
        @error="handlePlaybackError"
      ></audio>
    </div>

    <div v-if="!compact && isTranscribing" class="voice-note__transcript-status is-loading">
      <span>Transcribing…</span>
    </div>
    <div v-else-if="!compact && transcriptionStatus === 'failed'" class="voice-note__transcript-status">
      Transcription unavailable
    </div>
    <div v-else-if="!compact && transcriptionStatus === 'complete' && !transcript" class="voice-note__transcript-status">
      No speech detected
    </div>

    <div v-if="!compact && transcript" class="voice-note__transcript-section">
      <button
        type="button"
        class="voice-note__transcript-toggle"
        :aria-expanded="transcriptOpen"
        @click.stop="transcriptOpen = !transcriptOpen"
      >
        <span class="voice-note__transcript-indicator" aria-hidden="true"></span>
        <span class="voice-note__transcript-label">Transcript</span>
        <span class="voice-note__transcript-action">{{ transcriptOpen ? 'Hide' : 'Show' }}</span>
        <svg class="icon"><use :href="transcriptOpen ? '#icon-chevron-up' : '#icon-chevron-down'" /></svg>
      </button>
      <Transition name="voice-transcript">
        <div v-if="transcriptOpen" class="voice-note__transcript-body">
          <p class="voice-note__transcript">{{ transcript }}</p>
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  attachment: { type: Object, required: true },
  url: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})

const audioEl = ref(null)
const isPlaying = ref(false)
const isLoading = ref(false)
const isSeeking = ref(false)
const currentTime = ref(0)
const mediaDuration = ref(0)
const transcriptOpen = ref(false)
let playIntent = false
let playbackRequest = 0
let readyCleanup = null

const peaks = computed(() => {
  const source = Array.isArray(props.attachment?.peaks) ? props.attachment.peaks : []
  if (source.length) return source.map(value => Math.max(0.05, Math.min(1, Number(value) || 0)))
  return Array.from({ length: 32 }, (_, index) => 0.2 + ((index * 7) % 11) / 18)
})

const displayPeaks = computed(() => {
  if (!props.compact || peaks.value.length <= 36) return peaks.value
  const step = peaks.value.length / 36
  return Array.from({ length: 36 }, (_, index) => peaks.value[Math.floor(index * step)])
})
const storedDuration = computed(() => Math.max(0, Number(props.attachment?.duration) || 0))
const displayDuration = computed(() => mediaDuration.value || storedDuration.value)
const progress = computed(() => displayDuration.value > 0 ? currentTime.value / displayDuration.value : 0)
const transcript = computed(() => props.attachment?.transcription || '')
const transcriptionStatus = computed(() => props.attachment?.transcription_status || '')
const isTranscribing = computed(() => ['queued', 'processing'].includes(transcriptionStatus.value))
const timeLabel = computed(() => {
  const elapsed = formatDuration(currentTime.value)
  const total = formatDuration(displayDuration.value)
  return props.compact && !currentTime.value ? total : `${elapsed} / ${total}`
})

function formatDuration(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0))
  const minutes = Math.floor(total / 60)
  return `${minutes}:${String(total % 60).padStart(2, '0')}`
}

function barProgress(index) {
  return (index + 1) / Math.max(1, displayPeaks.value.length)
}

function waitForPlayable(audio, timeoutMs = 6000) {
  if (audio.readyState >= 2) return Promise.resolve()
  readyCleanup?.()
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => finish(new Error('Voice note loading timed out')), timeoutMs)
    const finish = (error = null) => {
      window.clearTimeout(timeout)
      audio.removeEventListener('canplay', handleReady)
      audio.removeEventListener('loadeddata', handleReady)
      audio.removeEventListener('error', handleError)
      readyCleanup = null
      if (error) reject(error)
      else resolve()
    }
    const handleReady = () => finish()
    const handleError = () => finish(audio.error || new Error('Voice note could not be loaded'))
    readyCleanup = () => finish(new Error('Voice note loading was cancelled'))
    audio.addEventListener('canplay', handleReady, { once: true })
    audio.addEventListener('loadeddata', handleReady, { once: true })
    audio.addEventListener('error', handleError, { once: true })
    audio.load()
  })
}

async function requestPlayback(audio, allowRetry = true) {
  const requestId = ++playbackRequest
  isLoading.value = true
  try {
    if (audio.ended || (displayDuration.value > 0 && audio.currentTime >= displayDuration.value - 0.05)) {
      audio.currentTime = 0
    }
    if (audio.readyState === 0) audio.load()
    await audio.play()
    if (playIntent && requestId === playbackRequest && !audio.paused) {
      isPlaying.value = true
      isLoading.value = false
    }
  } catch (error) {
    if (!playIntent || requestId !== playbackRequest) return
    const recoverable = ['AbortError', 'NotSupportedError'].includes(error?.name) || audio.readyState === 0
    if (allowRetry && recoverable) {
      try {
        await waitForPlayable(audio)
        if (playIntent && requestId === playbackRequest) await requestPlayback(audio, false)
        return
      } catch {}
    }
    playIntent = false
    isLoading.value = false
    console.warn('Voice note playback failed')
  }
}

function togglePlayback() {
  const audio = audioEl.value
  if (!audio || !props.url) return
  if (!audio.paused || playIntent) {
    playIntent = false
    playbackRequest += 1
    readyCleanup?.()
    readyCleanup = null
    isLoading.value = false
    audio.pause()
    return
  }
  playIntent = true
  void requestPlayback(audio)
}

function handleMetadata() {
  const duration = Number(audioEl.value?.duration)
  if (Number.isFinite(duration) && duration > 0) mediaDuration.value = duration
}

function handlePlaying() {
  isPlaying.value = true
  isLoading.value = false
}

function handlePause() {
  isPlaying.value = false
  if (!isLoading.value) playIntent = false
  if (!playIntent) isLoading.value = false
}

function handleWaiting() {
  if (playIntent) isLoading.value = true
}

function handleCanPlay() {
  handleMetadata()
}

function handlePlaybackError() {
  if (!readyCleanup) {
    playIntent = false
    isLoading.value = false
    isPlaying.value = false
  }
}

function handleTimeUpdate() {
  if (!isSeeking.value) currentTime.value = Number(audioEl.value?.currentTime) || 0
}

function handleEnded() {
  playIntent = false
  isPlaying.value = false
  isLoading.value = false
  currentTime.value = 0
  if (audioEl.value) audioEl.value.currentTime = 0
}

function seekFromPointer(event) {
  const target = event.currentTarget
  const rect = target?.getBoundingClientRect?.()
  if (!rect?.width || !displayDuration.value) return
  const fraction = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
  currentTime.value = displayDuration.value * fraction
  if (audioEl.value) audioEl.value.currentTime = currentTime.value
}

function startSeeking(event) {
  isSeeking.value = true
  event.currentTarget?.setPointerCapture?.(event.pointerId)
  seekFromPointer(event)
}

function moveSeeking(event) {
  if (isSeeking.value) seekFromPointer(event)
}

function finishSeeking(event) {
  if (!isSeeking.value) return
  seekFromPointer(event)
  isSeeking.value = false
  event.currentTarget?.releasePointerCapture?.(event.pointerId)
}

function seekBy(delta) {
  const next = Math.max(0, Math.min(displayDuration.value, currentTime.value + delta))
  currentTime.value = next
  if (audioEl.value) audioEl.value.currentTime = next
}

watch(() => props.url, () => {
  playIntent = false
  playbackRequest += 1
  readyCleanup?.()
  readyCleanup = null
  isPlaying.value = false
  isLoading.value = false
  currentTime.value = 0
})

onBeforeUnmount(() => {
  playIntent = false
  playbackRequest += 1
  readyCleanup?.()
  readyCleanup = null
  audioEl.value?.pause?.()
})
</script>

<style scoped>
.voice-note {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  padding: 6px 7px;
  border: 1px solid color-mix(in srgb, var(--v-control-border) 68%, transparent);
  border-radius: var(--v-radius-sm);
  background: var(--v-surface-tint-hover);
  box-shadow: none;
}

.voice-note__player {
  display: grid;
  grid-template-columns: 26px minmax(56px, 1fr) auto;
  align-items: center;
  gap: 6px;
}

.voice-note__play {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border: 1px solid color-mix(in srgb, var(--v-control-border) 70%, transparent);
  border-radius: var(--v-button-radius);
  background: var(--v-surface-tint-strong);
  color: var(--v-text-secondary);
  cursor: pointer;
  transition: border-color var(--v-transition-fast), background var(--v-transition-fast), color var(--v-transition-fast);
}

.voice-note__play:hover:not(:disabled),
.voice-note.is-playing .voice-note__play,
.voice-note__play.is-loading {
  border-color: color-mix(in srgb, var(--v-accent) 45%, var(--v-control-border));
  background: var(--v-accent-muted);
  color: var(--v-accent);
}

.voice-note__play:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.voice-note__play .icon {
  width: 11px;
  height: 11px;
}

.voice-note__loading {
  width: 11px;
  height: 11px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: var(--v-radius-full);
  animation: voice-note-spin 700ms linear infinite;
}

.voice-note__waveform {
  display: flex;
  align-items: center;
  gap: 1.5px;
  height: 24px;
  min-width: 0;
  padding: 2px 0;
  cursor: pointer;
  touch-action: none;
}

.voice-note__waveform:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: 2px;
  border-radius: var(--v-radius-sm);
}

.voice-note__bar {
  flex: 1 1 1px;
  min-width: 1px;
  max-width: 3px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-text-muted) 52%, transparent);
  transition: background var(--v-duration-fast) var(--v-ease-emphasized);
}

.voice-note__bar.is-played {
  background: var(--v-accent);
}

.voice-note__time {
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.voice-note audio {
  display: none;
}

.voice-note__transcript-section {
  margin-top: 5px;
  padding-top: 5px;
  border-top: 1px solid color-mix(in srgb, var(--v-divider-subtle) 80%, transparent);
}

.voice-note__transcript-toggle {
  display: flex;
  align-items: center;
  gap: 5px;
  width: 100%;
  min-height: 18px;
  padding: 0 1px;
  border: 0;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text-muted);
  font-family: var(--v-font);
  font-size: var(--v-text-2xs);
  text-align: left;
  cursor: pointer;
  transition: color var(--v-transition-fast);
}

.voice-note__transcript-toggle:hover {
  background: transparent;
  color: var(--v-text-secondary);
}

.voice-note__transcript-toggle:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: 2px;
}

.voice-note__transcript-indicator {
  width: 5px;
  height: 5px;
  border-radius: var(--v-radius-full);
  background: var(--v-accent);
}

.voice-note__transcript-label {
  color: var(--v-text-secondary);
  font-weight: 650;
}

.voice-note__transcript-action {
  margin-left: auto;
  color: var(--v-text-muted);
  font-weight: 500;
}

.voice-note__transcript-toggle .icon {
  width: 10px;
  height: 10px;
}

.voice-note__transcript-body {
  margin-top: 4px;
  padding: 6px 8px;
  border: 1px solid color-mix(in srgb, var(--v-control-border) 68%, transparent);
  border-radius: var(--v-radius-sm);
  background: var(--v-surface-tint-strong);
}

.voice-note__transcript {
  margin: 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  line-height: 1.45;
  white-space: pre-wrap;
}

.voice-transcript-enter-active,
.voice-transcript-leave-active {
  transition: opacity var(--v-transition-fast);
}

.voice-transcript-enter-from,
.voice-transcript-leave-to {
  opacity: 0;
}

.voice-note--compact {
  flex: 1;
  max-width: none;
  padding: 2px 4px;
  border: 0;
  background: transparent;
  box-shadow: none;
}

.voice-note--compact .voice-note__player {
  grid-template-columns: 24px minmax(48px, 1fr) auto;
  gap: 5px;
}

.voice-note--compact .voice-note__play {
  width: 24px;
  height: 24px;
}

.voice-note--compact .voice-note__waveform {
  height: 22px;
}

.voice-note__transcript-status {
  margin: 2px 0 0 29px;
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
}

.voice-note__transcript-status.is-loading span {
  background: linear-gradient(90deg, var(--v-text-muted), var(--v-text-secondary), var(--v-text-muted));
  background-size: 180% 100%;
  background-clip: text;
  color: transparent;
  animation: voice-note-shimmer 1.5s linear infinite;
}

@keyframes voice-note-shimmer {
  to { background-position: -180% 0; }
}

@keyframes voice-note-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .voice-note__loading,
  .voice-note__transcript-status.is-loading span {
    animation: none;
  }

  .voice-note__transcript-status.is-loading span {
    color: var(--v-text-muted);
  }

  .voice-transcript-enter-active,
  .voice-transcript-leave-active {
    transition: none;
  }
}

@media (max-width: 430px) {
  .voice-note {
    max-width: 100%;
  }

  .voice-note__player {
    grid-template-columns: 26px minmax(48px, 1fr) auto;
  }

  .voice-note__time {
    grid-column: auto;
    margin-top: 0;
  }

  .voice-note--compact .voice-note__player {
    grid-template-columns: 24px minmax(42px, 1fr) auto;
  }
}
</style>
