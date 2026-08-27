<template>
  <div class="player-main media-compare-surface">
    <header class="media-compare-header">
      <div class="media-compare-rail">
        <span class="media-compare-kicker">Compare</span>

        <div v-if="canSelectPair" class="media-compare-pair" aria-label="Compare pair">
          <label class="media-compare-slot is-primary">
            <span class="media-compare-slot-pill">
              <span class="media-compare-slot-key">A</span>
              <select
                class="media-compare-slot-select"
                :value="primaryVersionKey"
                aria-label="Primary version"
                @change="$emit('update-primary-version', $event.target.value)"
              >
                <option
                  v-for="option in versionOptions"
                  :key="`primary-${option.value}`"
                  :value="option.value"
                  :disabled="option.value === secondaryVersionKey"
                >
                  {{ option.label }}
                </option>
              </select>
              <svg class="icon media-compare-slot-chevron" aria-hidden="true"><use href="#icon-chevron-down" /></svg>
            </span>
          </label>

          <span class="media-compare-divider" aria-hidden="true">vs</span>

          <label class="media-compare-slot is-secondary">
            <span class="media-compare-slot-pill">
              <span class="media-compare-slot-key">B</span>
              <select
                class="media-compare-slot-select"
                :value="secondaryVersionKey"
                aria-label="Secondary version"
                @change="$emit('update-secondary-version', $event.target.value)"
              >
                <option
                  v-for="option in versionOptions"
                  :key="`secondary-${option.value}`"
                  :value="option.value"
                  :disabled="option.value === primaryVersionKey"
                >
                  {{ option.label }}
                </option>
              </select>
              <svg class="icon media-compare-slot-chevron" aria-hidden="true"><use href="#icon-chevron-down" /></svg>
            </span>
          </label>
        </div>

        <p v-else class="media-compare-headline">
          <strong>{{ primaryLabel }}</strong>
          <span>vs</span>
          <strong>{{ secondaryLabel }}</strong>
        </p>

        <span class="media-compare-rail-divider" aria-hidden="true"></span>

        <div class="v-view-toggle media-compare-layout" role="group" aria-label="Compare layout">
          <button
            type="button"
            class="v-view-toggle-btn"
            :class="{ active: mode === 'side-by-side' }"
            @click="$emit('update:mode', 'side-by-side')"
          >
            Side by side
          </button>
          <button
            type="button"
            class="v-view-toggle-btn"
            :class="{ active: mode === 'wipe' }"
            @click="$emit('update:mode', 'wipe')"
          >
            Wipe
          </button>
        </div>

        <button type="button" class="v-btn v-btn-ghost v-btn-sm media-compare-done" @click="$emit('exit')">
          <svg class="icon"><use href="#icon-close" /></svg>
          <span>Done</span>
        </button>
      </div>
    </header>

    <div v-if="isUnsupportedPair" class="media-compare-empty">
      <strong>Compare is not available for this pair.</strong>
      <span>Choose two videos or two images from the same shot.</span>
    </div>

    <div
      v-else-if="mode === 'wipe'"
      ref="wipeStageRef"
      class="media-compare-stage media-compare-wipe"
      @pointerdown="startWipeDrag"
    >
      <div class="media-compare-wipe-layer is-secondary">
        <ComparePane
          side="secondary"
          :family="mediaFamily"
          :media-url="secondaryState.mediaUrl"
          :ready="secondaryState.ready"
          :loading="secondaryState.loading"
          :error="secondaryState.error"
          :progress="secondaryState.progress"
          :label="secondaryLabel"
          :video-ref="setSecondaryVideoRef"
          muted
          @loadedmetadata="handleSecondaryLoadedMetadata"
          @timeupdate="handlePlaybackTimeUpdate"
          @waiting="handlePlaybackWaiting"
        />
      </div>
      <div class="media-compare-wipe-layer is-primary" :style="{ clipPath: `inset(0 ${100 - wipePercent}% 0 0)` }">
        <ComparePane
          side="primary"
          :family="mediaFamily"
          :media-url="primaryState.mediaUrl"
          :ready="primaryState.ready"
          :loading="primaryState.loading"
          :error="primaryState.error"
          :progress="primaryState.progress"
          :label="primaryLabel"
          :video-ref="setPrimaryVideoRef"
          @loadedmetadata="handlePrimaryLoadedMetadata"
          @timeupdate="handlePlaybackTimeUpdate"
          @waiting="handlePlaybackWaiting"
        />
      </div>
      <div class="media-compare-wipe-divider" :style="{ left: `${wipePercent}%` }" aria-hidden="true">
        <span></span>
      </div>
    </div>

    <div v-else class="media-compare-stage media-compare-split">
      <ComparePane
        side="primary"
        :family="mediaFamily"
        :media-url="primaryState.mediaUrl"
        :ready="primaryState.ready"
        :loading="primaryState.loading"
        :error="primaryState.error"
        :progress="primaryState.progress"
        :label="primaryLabel"
        :video-ref="setPrimaryVideoRef"
        @loadedmetadata="handlePrimaryLoadedMetadata"
        @timeupdate="handlePlaybackTimeUpdate"
        @waiting="handlePlaybackWaiting"
      />
      <ComparePane
        side="secondary"
        :family="mediaFamily"
        :media-url="secondaryState.mediaUrl"
        :ready="secondaryState.ready"
        :loading="secondaryState.loading"
        :error="secondaryState.error"
        :progress="secondaryState.progress"
        :label="secondaryLabel"
        :video-ref="setSecondaryVideoRef"
        muted
        @loadedmetadata="handleSecondaryLoadedMetadata"
        @timeupdate="handlePlaybackTimeUpdate"
        @waiting="handlePlaybackWaiting"
      />
    </div>

    <footer v-if="mediaFamily === 'video' && !isUnsupportedPair" class="media-viewer-toolbar media-compare-controls">
      <div class="timeline-row">
        <div
          ref="timelineRef"
          class="timeline media-compare-timeline"
          :class="{ 'is-scrubbing': timelineDragging }"
          role="slider"
          tabindex="0"
          :aria-valuemin="0"
          :aria-valuemax="Math.round(clampedDuration)"
          :aria-valuenow="Math.round(currentTime)"
          aria-label="Compare timeline"
          @mousedown.stop.prevent="startTimelineDrag"
          @touchstart.stop.prevent="startTimelineTouch"
          @keydown.left.prevent="nudgeTimeline($event.shiftKey ? -1 : -frameStepSeconds)"
          @keydown.right.prevent="nudgeTimeline($event.shiftKey ? 1 : frameStepSeconds)"
        >
          <div class="timeline-bg" />
          <div class="timeline-progress" :style="{ width: `${timelinePercent}%` }" />
          <div class="timeline-handle" :style="{ left: `${timelinePercent}%` }" />
        </div>
      </div>

      <div class="controls-row">
        <div class="controls-bar" role="group" aria-label="Compare playback controls">
          <div class="controls-bar__segment controls-bar__segment--play">
            <button
              type="button"
              class="control-btn control-btn--play"
              :disabled="!canPlayVideoPair"
              :aria-label="isPlaying ? 'Pause comparison' : 'Play comparison'"
              @click="togglePlayback"
            >
              <span class="play-pause-morph" :class="{ 'is-playing': isPlaying }" aria-hidden="true">
                <svg class="play-pause-morph__glyph play-pause-morph__glyph--play"><use href="#icon-play" /></svg>
                <svg class="play-pause-morph__glyph play-pause-morph__glyph--pause"><use href="#icon-pause" /></svg>
              </span>
            </button>
          </div>

          <div class="controls-bar__segment controls-bar__segment--main">
            <div class="controls-bar__times">
              <span class="time-current">{{ formatSeconds(currentTime) }}</span>
              <span class="time-sep">/</span>
              <span class="time-duration">{{ formatSeconds(clampedDuration) }}</span>
            </div>
            <div class="controls-bar__spacer" />
            <div class="controls-bar__actions">
              <button
                type="button"
                class="control-btn control-btn--icon loop-btn"
                :class="{ active: loopEnabled }"
                :aria-label="loopEnabled ? 'Disable loop' : 'Enable loop'"
                @click="loopEnabled = !loopEnabled"
              >
                <svg class="icon"><use href="#icon-refresh" /></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useDocumentVisible } from '../../composables/useDocumentVisible'
import api from '../../lib/api'
import { clamp } from '../../utils/math'

const PREFERRED_START_QUALITY_HEIGHT = 1080
const HAVE_FUTURE_DATA = 3
const PLAYBACK_READY_TIMEOUT_MS = 8000
const STREAM_POLL_DELAYS_MS = [1000, 2000, 5000]

const props = defineProps({
  primaryMedia: { type: Object, required: true },
  secondaryMedia: { type: Object, required: true },
  primaryLabel: { type: String, default: 'A' },
  secondaryLabel: { type: String, default: 'B' },
  versionOptions: { type: Array, default: () => [] },
  primaryVersionKey: { type: String, default: '' },
  secondaryVersionKey: { type: String, default: '' },
  mode: { type: String, default: 'side-by-side' },
  resolveMediaRoutes: { type: Function, required: true },
  formatTimecode: { type: Function, default: null },
  frameRate: { type: Number, default: 24 },
})

defineEmits(['exit', 'update:mode', 'update-primary-version', 'update-secondary-version'])

const ComparePane = defineComponent({
  name: 'ComparePane',
  props: {
    side: { type: String, required: true },
    family: { type: String, required: true },
    mediaUrl: { type: String, default: '' },
    ready: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
    error: { type: String, default: '' },
    progress: { type: Number, default: 0 },
    label: { type: String, default: '' },
    muted: { type: Boolean, default: false },
    videoRef: { type: Function, default: null },
  },
  emits: ['loadedmetadata', 'timeupdate', 'waiting'],
  setup(paneProps, { emit }) {
    return () => h('div', { class: ['media-compare-pane', `is-${paneProps.side}`] }, [
      h('div', { class: 'media-compare-pane-label' }, paneProps.label),
      paneProps.family === 'image'
        ? h('img', {
          src: paneProps.mediaUrl,
          alt: paneProps.label,
          class: 'media-compare-media',
        })
        : h('video', {
          ref: paneProps.videoRef,
          class: 'media-compare-media',
          playsinline: true,
          webkitplaysinline: '',
          preload: 'auto',
          muted: paneProps.muted,
          onLoadedmetadata: event => emit('loadedmetadata', event),
          onTimeupdate: event => emit('timeupdate', event),
          onWaiting: event => emit('waiting', event),
        }),
      paneProps.family === 'video' && paneProps.error
        ? h('div', { class: 'media-compare-preparing is-error', role: 'alert' }, [
          h('span', 'Stream unavailable'),
          h('strong', paneProps.error),
        ])
        : paneProps.family === 'video' && !paneProps.ready
        ? h('div', { class: 'media-compare-preparing' }, [
          h('span', paneProps.loading ? 'Preparing stream' : 'Loading stream'),
          h('strong', `${Math.round(paneProps.progress || 0)}%`),
        ])
        : null,
    ])
  },
})

const primaryVideoRef = ref(null)
const secondaryVideoRef = ref(null)
const wipeStageRef = ref(null)
const timelineRef = ref(null)
const wipePercent = ref(50)
const isPlaying = ref(false)
const currentTime = ref(0)
const loopEnabled = ref(true)
const timelineDragging = ref(false)

const primaryState = reactive(createPaneState())
const secondaryState = reactive(createPaneState())
const documentVisible = useDocumentVisible()

let primaryHls = null
let secondaryHls = null
let primaryAttachRequestId = 0
let secondaryAttachRequestId = 0
let primaryPoll = null
let secondaryPoll = null
const pollAttempts = { primary: 0, secondary: 0 }
let setupToken = 0
let draggingWipe = false
let playbackRequestToken = 0
let stallRecoveryQueued = false
let resumeAfterTimelineDrag = false
let timelineDragRect = null
let pendingTimelineClientX = null
let timelineSeekFrame = 0
let timelineSeekTimer = 0
let lastTimelineSeekAt = 0
let wipeDragRect = null
let pendingWipeClientX = null
let wipeMoveFrame = 0
const COMPARE_TIMELINE_SEEK_INTERVAL_MS = 80

const primaryFamily = computed(() => getMediaFamily(props.primaryMedia))
const secondaryFamily = computed(() => getMediaFamily(props.secondaryMedia))
const mediaFamily = computed(() => (primaryFamily.value === secondaryFamily.value ? primaryFamily.value : 'unsupported'))
const isUnsupportedPair = computed(() => mediaFamily.value === 'unsupported')
const canSelectPair = computed(() => props.versionOptions.length > 2)
const canPlayVideoPair = computed(() => mediaFamily.value === 'video' && primaryState.ready && secondaryState.ready)
const clampedDuration = computed(() => {
  if (mediaFamily.value !== 'video') return 0
  const primaryDuration = Number(primaryState.duration || 0)
  const secondaryDuration = Number(secondaryState.duration || 0)
  if (!primaryDuration) return secondaryDuration || 0
  if (!secondaryDuration) return primaryDuration || 0
  return Math.max(primaryDuration, secondaryDuration)
})
const timelineValue = computed(() => {
  if (!clampedDuration.value) return 0
  return Math.round((currentTime.value / clampedDuration.value) * 1000)
})
const timelinePercent = computed(() => clamp(timelineValue.value / 10, 0, 100))
const frameStepSeconds = computed(() => 1 / (Number(props.frameRate) || 24))

watch(
  () => [props.primaryMedia, props.secondaryMedia],
  () => setupComparison(),
  { immediate: true },
)

watch(() => props.mode, () => {
  nextTick(() => {
    attachReadyVideo('primary')
    attachReadyVideo('secondary')
  })
})

watch(documentVisible, (visible) => {
  if (!visible) {
    clearPanePoll('primary', { resetBackoff: false })
    clearPanePoll('secondary', { resetBackoff: false })
    return
  }

  const token = setupToken
  if (primaryState.loading) void setupPane('primary', props.primaryMedia, primaryState, token)
  if (secondaryState.loading) void setupPane('secondary', props.secondaryMedia, secondaryState, token)
})

onMounted(() => {
  window.addEventListener('keydown', handleCompareKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleCompareKeydown)
  playbackRequestToken += 1
  cleanupPane('primary')
  cleanupPane('secondary')
  removeWipeListeners()
  removeTimelineListeners()
})

function createPaneState() {
  return {
    mediaUrl: '',
    loading: false,
    ready: false,
    error: '',
    progress: 0,
    duration: 0,
    attachedUrl: '',
    attachedVideo: null,
  }
}

function getMediaFamily(media) {
  if (!media) return 'unsupported'
  if (media.is_image) return 'image'
  if (media.is_pdf) return 'unsupported'
  return 'video'
}

function resetPaneState(state) {
  state.mediaUrl = ''
  state.loading = false
  state.ready = false
  state.error = ''
  state.progress = 0
  state.duration = 0
  state.attachedUrl = ''
  state.attachedVideo = null
}

function setupComparison() {
  setupToken += 1
  const token = setupToken
  playbackRequestToken += 1
  stallRecoveryQueued = false
  resumeAfterTimelineDrag = false
  cleanupPane('primary')
  cleanupPane('secondary')
  resetPaneState(primaryState)
  resetPaneState(secondaryState)
  currentTime.value = 0
  isPlaying.value = false

  if (isUnsupportedPair.value) return
  setupPane('primary', props.primaryMedia, primaryState, token)
  setupPane('secondary', props.secondaryMedia, secondaryState, token)
}

async function setupPane(side, media, state, token) {
  const routes = props.resolveMediaRoutes(media)
  if (!routes?.fileUrl) return

  if (mediaFamily.value === 'image') {
    state.mediaUrl = routes.fileUrl
    state.ready = true
    return
  }

  state.loading = true
  state.error = ''
  state.mediaUrl = routes.manifestUrl

  try {
    const { data } = await api.get(routes.statusUrl)
    if (token !== setupToken) return
    handleStatus(side, media, state, routes, data, token, { resetBackoff: true })
  } catch (error) {
    if (token === setupToken) {
      state.loading = false
      state.progress = 0
      state.error = 'Could not load'
    }
  }
}

function handleStatus(side, media, state, routes, data, token, { schedulePoll = true, resetBackoff = false } = {}) {
  const status = String(data?.status || '').toLowerCase()
  if (status === 'complete') {
    clearPanePoll(side)
    state.loading = false
    state.ready = true
    state.progress = data?.progress || 100
    nextTick(() => attachReadyVideo(side))
    return
  }

  if (status === 'error') {
    clearPanePoll(side)
    state.loading = false
    state.progress = 0
    state.error = 'Encoding failed'
    return
  }

  state.loading = true
  state.progress = data?.progress || 0
  if (schedulePoll) startPolling(side, media, state, routes, token, { resetBackoff })
}

function startPolling(side, media, state, routes, token, { resetBackoff = false } = {}) {
  clearPanePoll(side, { resetBackoff })
  if (!documentVisible.value) return

  const delay = STREAM_POLL_DELAYS_MS[pollAttempts[side]]
  const poll = setTimeout(async () => {
    try {
      const { data } = await api.get(routes.statusUrl)
      if (token !== setupToken) return
      const status = String(data?.status || '').toLowerCase()
      handleStatus(side, media, state, routes, data, token, { schedulePoll: false })
      if (status !== 'complete' && status !== 'error') {
        pollAttempts[side] = Math.min(pollAttempts[side] + 1, STREAM_POLL_DELAYS_MS.length - 1)
        startPolling(side, media, state, routes, token)
      }
    } catch {
      if (token === setupToken) {
        state.progress = 0
        pollAttempts[side] = Math.min(pollAttempts[side] + 1, STREAM_POLL_DELAYS_MS.length - 1)
        startPolling(side, media, state, routes, token)
      }
    }
  }, delay)

  if (side === 'primary') primaryPoll = poll
  else secondaryPoll = poll
}

function clearPanePoll(side, { resetBackoff = true } = {}) {
  if (side === 'primary' && primaryPoll) {
    clearTimeout(primaryPoll)
    primaryPoll = null
  }
  if (side === 'secondary' && secondaryPoll) {
    clearTimeout(secondaryPoll)
    secondaryPoll = null
  }
  if (resetBackoff) pollAttempts[side] = 0
}

function cleanupPane(side) {
  clearPanePoll(side)
  if (side === 'primary') primaryAttachRequestId += 1
  else secondaryAttachRequestId += 1
  if (side === 'primary' && primaryHls) {
    primaryHls.destroy()
    primaryHls = null
  }
  if (side === 'secondary' && secondaryHls) {
    secondaryHls.destroy()
    secondaryHls = null
  }
}

function setPrimaryVideoRef(el) {
  if (!el) cleanupPane('primary')
  primaryVideoRef.value = el
  void attachReadyVideo('primary')
}

function setSecondaryVideoRef(el) {
  if (!el) cleanupPane('secondary')
  secondaryVideoRef.value = el
  void attachReadyVideo('secondary')
}

async function attachReadyVideo(side) {
  const state = side === 'primary' ? primaryState : secondaryState
  const video = side === 'primary' ? primaryVideoRef.value : secondaryVideoRef.value
  if (mediaFamily.value !== 'video' || !state.ready || !state.mediaUrl || !video) return
  if (state.attachedUrl === state.mediaUrl && state.attachedVideo === video) return

  cleanupPane(side)
  const requestId = side === 'primary' ? primaryAttachRequestId : secondaryAttachRequestId
  state.attachedUrl = state.mediaUrl
  state.attachedVideo = video

  let Hls
  try {
    const hlsModule = await import('hls.js')
    Hls = hlsModule.default
  } catch {
    Hls = null
  }
  const currentRequestId = side === 'primary' ? primaryAttachRequestId : secondaryAttachRequestId
  if (
    requestId !== currentRequestId
    || state.attachedUrl !== state.mediaUrl
    || state.attachedVideo !== video
  ) return

  if (Hls?.isSupported()) {
    const hls = new Hls({
      enableWorker: true,
      lowLatencyMode: false,
      // Two panes run side by side, so each gets half the solo player's caps.
      maxBufferLength: 15,
      maxMaxBufferLength: 45,
      maxBufferSize: 10 * 1000 * 1000,
      backBufferLength: 15,
      autoStartLoad: false,
      startFragPrefetch: true,
    })
    hls.loadSource(state.mediaUrl)
    hls.attachMedia(video)
    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      const startLevel = chooseStartLevel(hls.levels || [])
      if (startLevel >= 0) {
        hls.startLevel = startLevel
        hls.currentLevel = startLevel
        hls.nextLevel = startLevel
      }
      hls.startLoad(0)
    })
    if (side === 'primary') primaryHls = hls
    else secondaryHls = hls
    return
  }

  if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = state.mediaUrl
  }
}

function chooseStartLevel(levels) {
  if (!Array.isArray(levels) || !levels.length) return -1
  const candidates = levels
    .map((level, index) => ({ index, height: Number(level?.height || 0), bitrate: Number(level?.bitrate || 0) }))
    .sort((a, b) => b.height - a.height || b.bitrate - a.bitrate)
  return (
    candidates.find(level => level.height && level.height <= PREFERRED_START_QUALITY_HEIGHT)
    || candidates[candidates.length - 1]
  )?.index ?? -1
}

function handlePrimaryLoadedMetadata(event) {
  primaryState.duration = Number(event?.target?.duration || 0)
}

function handleSecondaryLoadedMetadata(event) {
  secondaryState.duration = Number(event?.target?.duration || 0)
}

function handlePlaybackTimeUpdate() {
  const nextTime = Math.max(
    Number(primaryVideoRef.value?.currentTime || 0),
    Number(secondaryVideoRef.value?.currentTime || 0),
  )
  const maxTime = clampedDuration.value
  if (maxTime && nextTime >= maxTime) {
    if (loopEnabled.value) {
      void playBoth(0)
    } else {
      pauseBoth()
    }
    return
  }
  currentTime.value = nextTime
}

function handlePlaybackWaiting() {
  if (!isPlaying.value || stallRecoveryQueued) return
  const primary = primaryVideoRef.value
  const secondary = secondaryVideoRef.value
  if (!primary || !secondary) return

  const activeVideos = [primary, secondary].filter(video => canVideoPlayAt(video, video.currentTime))
  if (!activeVideos.length) return

  const recoveryTime = Math.min(...activeVideos.map(video => Number(video.currentTime || 0)))
  stallRecoveryQueued = true
  playbackRequestToken += 1
  pauseVideoElements()
  queueMicrotask(() => {
    stallRecoveryQueued = false
    if (isPlaying.value) void playBoth(recoveryTime)
  })
}

function setVideoCurrentTime(video, time) {
  if (!video) return false
  const nextTime = Number(time || 0)
  if (Math.abs(Number(video.currentTime || 0) - nextTime) <= frameStepSeconds.value / 2) {
    return false
  }
  try {
    video.currentTime = nextTime
    return true
  } catch {
    // Seek can fail while the element is still loading.
    return false
  }
}

function waitForPlaybackReady(video) {
  if (!video.seeking && video.readyState >= HAVE_FUTURE_DATA) return Promise.resolve(true)

  return new Promise(resolve => {
    const readyEvents = ['loadeddata', 'seeked', 'canplay']
    const finish = ready => {
      clearTimeout(timeout)
      readyEvents.forEach(eventName => video.removeEventListener(eventName, checkReady))
      video.removeEventListener('error', handleError)
      resolve(ready)
    }
    const checkReady = () => {
      if (!video.seeking && video.readyState >= HAVE_FUTURE_DATA) finish(true)
    }
    const handleError = () => finish(false)
    const timeout = setTimeout(() => finish(false), PLAYBACK_READY_TIMEOUT_MS)

    readyEvents.forEach(eventName => video.addEventListener(eventName, checkReady))
    video.addEventListener('error', handleError, { once: true })
    checkReady()
  })
}

function canVideoPlayAt(video, time) {
  const duration = Number(video?.duration || 0)
  return Boolean(video) && (!duration || Number(time || 0) < duration - frameStepSeconds.value / 2)
}

function pauseVideoElements() {
  if (primaryVideoRef.value && !primaryVideoRef.value.paused) primaryVideoRef.value.pause()
  if (secondaryVideoRef.value && !secondaryVideoRef.value.paused) secondaryVideoRef.value.pause()
}

function togglePlayback() {
  if (!canPlayVideoPair.value) return
  if (isPlaying.value) {
    pauseBoth()
  } else {
    void playBoth()
  }
}

async function playBoth(requestedTime = null) {
  const primary = primaryVideoRef.value
  const secondary = secondaryVideoRef.value
  if (!primary || !secondary || !canPlayVideoPair.value) return

  const requestToken = ++playbackRequestToken
  isPlaying.value = true
  let time = boundPlaybackTime(requestedTime == null
    ? Math.max(
      Number(currentTime.value || 0),
      Number(primary.currentTime || 0),
      Number(secondary.currentTime || 0),
    )
    : requestedTime)
  if (clampedDuration.value && time >= clampedDuration.value) time = 0

  pauseVideoElements()
  setVideoCurrentTime(primary, time)
  setVideoCurrentTime(secondary, time)
  currentTime.value = time
  secondary.playbackRate = primary.playbackRate || 1

  const playableVideos = [primary, secondary].filter(video => canVideoPlayAt(video, time))
  const ready = await Promise.all(playableVideos.map(waitForPlaybackReady))
  if (requestToken !== playbackRequestToken || !isPlaying.value) return
  if (!ready.every(Boolean)) {
    isPlaying.value = false
    return
  }

  const results = await Promise.allSettled(playableVideos.map(video => video.play()))
  if (requestToken !== playbackRequestToken) return
  isPlaying.value = results.some((result, index) => result.status === 'fulfilled' && !playableVideos[index].paused)
}

function pauseBoth() {
  playbackRequestToken += 1
  stallRecoveryQueued = false
  pauseVideoElements()
  isPlaying.value = false
}

function seekBoth(time) {
  const boundedTime = boundPlaybackTime(time)
  const resumePlayback = isPlaying.value && !timelineDragging.value
  if (resumePlayback) pauseBoth()
  setVideoCurrentTime(primaryVideoRef.value, boundedTime)
  setVideoCurrentTime(secondaryVideoRef.value, boundedTime)
  currentTime.value = boundedTime
  if (resumePlayback) void playBoth(boundedTime)
}

function boundPlaybackTime(time) {
  const numericTime = Number(time || 0)
  if (!clampedDuration.value) return Math.max(0, numericTime)
  return clamp(numericTime, 0, clampedDuration.value)
}

function startTimelineDrag(event) {
  if (!canPlayVideoPair.value || !clampedDuration.value) return
  resumeAfterTimelineDrag = isPlaying.value
  timelineDragging.value = true
  timelineDragRect = timelineRef.value?.getBoundingClientRect?.() || null
  if (resumeAfterTimelineDrag) pauseBoth()
  seekFromTimelineClientX(event.clientX, timelineDragRect)
  window.addEventListener('mousemove', handleTimelineMouseMove)
  window.addEventListener('mouseup', stopTimelineDrag, { once: true })
}

function handleTimelineMouseMove(event) {
  if (!timelineDragging.value) return
  scheduleTimelineSeek(event.clientX)
}

function startTimelineTouch(event) {
  if (!canPlayVideoPair.value || !clampedDuration.value) return
  resumeAfterTimelineDrag = isPlaying.value
  timelineDragging.value = true
  timelineDragRect = timelineRef.value?.getBoundingClientRect?.() || null
  if (resumeAfterTimelineDrag) pauseBoth()
  seekFromTimelineClientX(event.touches?.[0]?.clientX, timelineDragRect)
  window.addEventListener('touchmove', handleTimelineTouchMove, { passive: false })
  window.addEventListener('touchend', stopTimelineDrag, { once: true })
  window.addEventListener('touchcancel', stopTimelineDrag, { once: true })
}

function handleTimelineTouchMove(event) {
  if (!timelineDragging.value) return
  event.preventDefault()
  scheduleTimelineSeek(event.touches?.[0]?.clientX)
}

function stopTimelineDrag() {
  flushPendingTimelineSeek()
  timelineDragging.value = false
  timelineDragRect = null
  removeTimelineListeners()
  if (!resumeAfterTimelineDrag) return
  resumeAfterTimelineDrag = false
  void playBoth(currentTime.value)
}

function removeTimelineListeners() {
  window.removeEventListener('mousemove', handleTimelineMouseMove)
  window.removeEventListener('mouseup', stopTimelineDrag)
  window.removeEventListener('touchmove', handleTimelineTouchMove)
  window.removeEventListener('touchend', stopTimelineDrag)
  window.removeEventListener('touchcancel', stopTimelineDrag)
  if (timelineSeekFrame) window.cancelAnimationFrame(timelineSeekFrame)
  if (timelineSeekTimer) window.clearTimeout(timelineSeekTimer)
  timelineSeekFrame = 0
  timelineSeekTimer = 0
}

function seekFromTimelineClientX(clientX, cachedRect = null) {
  if (!timelineRef.value || !clampedDuration.value || Number.isNaN(Number(clientX))) return
  const rect = cachedRect || timelineRef.value.getBoundingClientRect()
  if (!rect.width) return
  const ratio = clamp((Number(clientX) - rect.left) / rect.width, 0, 1)
  seekBoth(clampedDuration.value * ratio)
  lastTimelineSeekAt = Date.now()
}

function flushPendingTimelineSeek() {
  if (pendingTimelineClientX == null) return
  const clientX = pendingTimelineClientX
  pendingTimelineClientX = null
  seekFromTimelineClientX(clientX, timelineDragRect)
}

function scheduleTimelineSeek(clientX) {
  if (Number.isNaN(Number(clientX))) return
  pendingTimelineClientX = clientX
  if (timelineSeekFrame || timelineSeekTimer) return

  const remaining = Math.max(0, COMPARE_TIMELINE_SEEK_INTERVAL_MS - (Date.now() - lastTimelineSeekAt))
  const requestFlush = () => {
    timelineSeekTimer = 0
    timelineSeekFrame = window.requestAnimationFrame(() => {
      timelineSeekFrame = 0
      flushPendingTimelineSeek()
    })
  }
  if (remaining) timelineSeekTimer = window.setTimeout(requestFlush, remaining)
  else requestFlush()
}

function nudgeTimeline(deltaSeconds) {
  if (!canPlayVideoPair.value || !clampedDuration.value) return
  seekBoth(currentTime.value + Number(deltaSeconds || 0))
}

function handleCompareKeydown(event) {
  if (event.defaultPrevented || mediaFamily.value !== 'video') return
  const target = event.target
  const tagName = String(target?.tagName || '').toUpperCase()
  if (tagName === 'INPUT' || tagName === 'TEXTAREA' || tagName === 'SELECT' || target?.isContentEditable) return

  switch (event.code) {
    case 'Space':
      event.preventDefault()
      togglePlayback()
      break
    case 'ArrowLeft':
      event.preventDefault()
      nudgeTimeline(event.shiftKey ? -1 : -frameStepSeconds.value)
      break
    case 'ArrowRight':
      event.preventDefault()
      nudgeTimeline(event.shiftKey ? 1 : frameStepSeconds.value)
      break
    default:
      break
  }
}

function formatSeconds(seconds) {
  if (typeof props.formatTimecode === 'function') return props.formatTimecode(Number(seconds || 0))
  const total = Math.max(0, Math.floor(Number(seconds || 0)))
  const minutes = Math.floor(total / 60)
  const remaining = total % 60
  return `${minutes}:${String(remaining).padStart(2, '0')}`
}

function startWipeDrag(event) {
  if (props.mode !== 'wipe' || !wipeStageRef.value) return
  draggingWipe = true
  wipeDragRect = wipeStageRef.value.getBoundingClientRect()
  updateWipeFromClientX(event.clientX)
  window.addEventListener('pointermove', updateWipeFromEvent)
  window.addEventListener('pointerup', stopWipeDrag, { once: true })
}

function updateWipeFromEvent(event) {
  if (!draggingWipe || !wipeDragRect) return
  pendingWipeClientX = event.clientX
  if (wipeMoveFrame) return
  wipeMoveFrame = window.requestAnimationFrame(() => {
    wipeMoveFrame = 0
    if (pendingWipeClientX == null) return
    const clientX = pendingWipeClientX
    pendingWipeClientX = null
    updateWipeFromClientX(clientX)
  })
}

function updateWipeFromClientX(clientX) {
  const rect = wipeDragRect
  if (!rect?.width) return
  const next = ((clientX - rect.left) / rect.width) * 100
  wipePercent.value = clamp(next, 5, 95)
}

function stopWipeDrag() {
  if (wipeMoveFrame) window.cancelAnimationFrame(wipeMoveFrame)
  wipeMoveFrame = 0
  if (pendingWipeClientX != null) updateWipeFromClientX(pendingWipeClientX)
  pendingWipeClientX = null
  wipeDragRect = null
  draggingWipe = false
  removeWipeListeners()
}

function removeWipeListeners() {
  window.removeEventListener('pointermove', updateWipeFromEvent)
  if (wipeMoveFrame) window.cancelAnimationFrame(wipeMoveFrame)
  wipeMoveFrame = 0
  pendingWipeClientX = null
  wipeDragRect = null
}
</script>
