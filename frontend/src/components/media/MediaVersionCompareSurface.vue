<template>
  <div class="player-main media-compare-surface">
    <header class="media-compare-header">
      <div class="media-compare-rail">
        <span class="media-compare-kicker">Compare</span>
        <div v-if="versionOptions.length > 1" class="media-compare-pair" aria-label="Compare pair">
          <template v-for="(key, index) in [primaryVersionKey, secondaryVersionKey]" :key="index">
            <span v-if="index" class="media-compare-divider" aria-hidden="true">vs</span>
            <label class="media-compare-slot" :class="index ? 'is-secondary' : 'is-primary'">
              <span class="media-compare-slot-pill">
                <span class="media-compare-slot-key">{{ index ? 'B' : 'A' }}</span>
                <select
class="media-compare-slot-select" :value="key" :aria-label="index ? 'Secondary version' : 'Primary version'"
                  @change="$emit(index ? 'update-secondary-version' : 'update-primary-version', $event.target.value)">
                  <option
v-for="option in versionOptions" :key="option.value" :value="option.value"
                    :disabled="option.value === (index ? primaryVersionKey : secondaryVersionKey)">{{ option.label }}</option>
                </select>
                <svg class="icon media-compare-slot-chevron" aria-hidden="true"><use href="#icon-chevron-down" /></svg>
              </span>
            </label>
          </template>
        </div>
        <p v-else class="media-compare-headline"><strong>{{ primaryLabel }}</strong><span>vs</span><strong>{{ secondaryLabel }}</strong></p>
        <span class="media-compare-rail-divider" aria-hidden="true" />
        <div class="v-view-toggle media-compare-layout" role="group" aria-label="Compare layout">
          <button
v-for="layout in [{ value: 'side-by-side', label: 'Side by side' }, { value: 'wipe', label: 'Wipe' }]"
            :key="layout.value" type="button" class="v-view-toggle-btn" :class="{ active: mode === layout.value }"
            :aria-pressed="mode === layout.value" @click="$emit('update:mode', layout.value)">{{ layout.label }}</button>
        </div>
        <button type="button" class="v-btn v-btn-ghost v-btn-sm media-compare-done" aria-label="Exit comparison" @click="$emit('exit')">
          <svg class="icon" aria-hidden="true"><use href="#icon-close" /></svg><span>Done</span>
        </button>
      </div>
    </header>

    <div
ref="stage" class="media-compare-stage" :class="[
      mode === 'wipe' ? 'media-compare-wipe' : 'media-compare-split',
      { 'is-packed': family === 'video', 'is-stacked': stacked },
    ]" @pointerdown="startWipe">
      <template v-if="family === 'video'">
        <video
ref="video" class="media-compare-decoder" playsinline preload="auto" :loop="loopEnabled" :muted="muted"
          aria-hidden="true" @loadeddata="loaded" @seeked="seeked" @play="playing = true; observeFrames()"
          @pause="playing = false" @ended="playing = false" @waiting="buffering = true" @playing="buffering = false"
          @error="mediaError" />
        <canvas ref="canvas" class="media-compare-media" role="img" :aria-label="`${primaryLabel} compared with ${secondaryLabel}`" />
        <div v-if="ready" class="media-compare-labels" aria-hidden="true">
          <span v-for="(label, index) in labels" :key="index" class="media-compare-pane-label">{{ label }}</span>
        </div>
        <div v-if="ready" class="media-compare-end-markers">
          <div v-for="(end, index) in info.end_frames" :key="index" class="media-compare-end-slot">
            <span v-if="frame >= end" class="media-compare-ended">{{ labels[index] }} ends here</span>
          </div>
        </div>
      </template>
      <template v-else-if="family === 'image'">
        <div
v-for="(url, index) in imageUrls" :key="index" class="media-compare-pane" :class="index ? 'is-secondary' : 'is-primary'"
          :style="mode === 'wipe' && !index ? { clipPath: `inset(0 ${100 - wipePercent}% 0 0)` } : undefined">
          <img :src="url" :alt="labels[index]" class="media-compare-media" @error="error = 'This image could not load.'" />
          <div class="media-compare-pane-label">{{ labels[index] }}</div>
        </div>
      </template>
      <div v-else class="media-compare-empty"><strong>Choose two videos or two images from the same shot.</strong></div>

      <template v-if="family && mode === 'wipe' && !error && (family === 'image' || ready)">
        <input
v-model.number="wipePercent" type="range" min="0" max="100" class="media-compare-wipe-input"
          aria-label="Wipe position" @pointerdown.stop />
        <div class="media-compare-wipe-divider" :style="{ transform: `translateX(${wipeLeft}px)` }" aria-hidden="true"><span /></div>
      </template>
      <div v-if="error || (family === 'video' && !ready)" class="media-compare-preparing" :class="{ 'is-error': error }" role="status">
        <template v-if="error">
          <strong>{{ error }}</strong>
          <button type="button" class="v-btn v-btn-secondary v-btn-sm" @pointerdown.stop @click="loadPair(true)">Try again</button>
        </template>
        <template v-else>
          <strong>{{ state === 'queued' ? 'Waiting to prepare comparison' : state === 'processing' ? 'Preparing comparison' : 'Loading comparison' }}</strong>
          <progress v-if="state === 'processing'" :value="progress" max="100" aria-label="Comparison preparation" />
          <span v-if="state === 'processing'">{{ Math.round(progress) }}%</span>
        </template>
      </div>
      <div v-else-if="buffering && playing" class="media-compare-status" role="status">Buffering…</div>
    </div>

    <footer v-if="family === 'video'" class="media-viewer-toolbar media-compare-controls">
      <div class="timeline-row">
        <div class="timeline media-compare-timeline" :class="{ 'is-scrubbing': scrubbing }">
          <div class="timeline-bg" />
          <div class="timeline-progress" :style="{ transform: `translateY(-50%) scaleX(${timelineFraction})` }" />
          <div class="timeline-handle" :style="{ left: `${timelineFraction * 100}%` }" />
          <input
type="range" min="0" :max="Math.max(0, info.frame_count - 1)" step="1" :value="requestedFrame" :disabled="!ready"
            class="media-compare-seek" aria-label="Compare timeline" :aria-valuetext="`Frame ${requestedFrame + 1} of ${info.frame_count}`"
            @pointerdown="beginScrub" @input="seek(Number($event.target.value))" @change="endScrub" @keydown="keydown" />
        </div>
      </div>
      <div class="controls-row">
        <div class="controls-bar" role="group" aria-label="Compare playback controls">
          <div class="controls-zone controls-zone--left">
            <button
type="button" class="v-btn v-btn-quiet v-btn-icon control-btn control-btn--play" :disabled="!ready"
              :aria-label="playing ? 'Pause comparison' : 'Play comparison'" @click="toggle">
              <svg class="icon" aria-hidden="true"><use :href="playing ? '#icon-pause' : '#icon-play'" /></svg>
            </button>
            <button
type="button" class="v-btn v-btn-quiet v-btn-icon control-btn loop-btn" :class="{ active: loopEnabled }"
              :aria-pressed="loopEnabled" aria-label="Loop comparison" @click="loopEnabled = !loopEnabled">
              <svg class="icon" aria-hidden="true"><use href="#icon-refresh" /></svg>
            </button>
            <button
type="button" class="v-btn v-btn-quiet v-btn-sm" :aria-pressed="!muted" :disabled="!ready"
              :title="`Audio from ${info.primary_is_left ? primaryLabel : secondaryLabel}`" @click="muted = !muted">
              {{ muted ? 'Sound off' : `Sound: ${info.primary_is_left ? primaryLabel : secondaryLabel}` }}
            </button>
          </div>
          <div class="controls-zone controls-zone--center">
            <div class="controls-timecode"><span class="time-current">{{ formatSeconds(frame / info.fps) }}</span>
              <span class="time-sep">/</span><span class="time-duration">{{ formatSeconds(info.frame_count / info.fps) }}</span></div>
          </div>
          <div class="controls-zone controls-zone--right media-compare-rate-note">
            <span v-if="info.different_frame_rates">Aligned by time · </span>Frame {{ ready ? frame + 1 : '—' }} / {{ info.frame_count || '—' }}
          </div>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import api from '../../lib/api'
import { getCanonicalMediaRefs, getMediaKind } from '../../lib/mediaEntity'
import { formatTimecodeWithFrames } from '../../utils/formatters'

const props = defineProps({
  primaryMedia: { type: Object, required: true }, secondaryMedia: { type: Object, required: true },
  primaryLabel: { type: String, default: 'A' }, secondaryLabel: { type: String, default: 'B' },
  versionOptions: { type: Array, default: () => [] }, primaryVersionKey: { type: String, default: '' },
  secondaryVersionKey: { type: String, default: '' }, mode: { type: String, default: 'side-by-side' },
  resolveMediaRoutes: { type: Function, required: true }, formatTimecode: { type: Function, default: null },
  frameRate: { type: Number, default: 24 },
})
defineEmits(['exit', 'update:mode', 'update-primary-version', 'update-secondary-version'])

const video = ref(null), canvas = ref(null), stage = ref(null)
const ready = ref(false), playing = ref(false), buffering = ref(false), error = ref('')
const state = ref('loading'), progress = ref(0), info = ref({ fps: 24, frame_count: 0, end_frames: [] })
const frame = ref(0), requestedFrame = ref(0), wipePercent = ref(50), loopEnabled = ref(true), muted = ref(true)
const scrubbing = ref(false), compact = ref(false), stageWidth = ref(0), stageHeight = ref(0)
const labels = computed(() => [props.primaryLabel, props.secondaryLabel])
const family = computed(() => {
  const first = getMediaKind(props.primaryMedia), second = getMediaKind(props.secondaryMedia)
  return first === second && ['video', 'image'].includes(first) ? first : ''
})
const routes = computed(() => [props.resolveMediaRoutes(props.primaryMedia), props.resolveMediaRoutes(props.secondaryMedia)])
const imageUrls = computed(() => routes.value.map(route => route.fileUrl))
const pairUrl = computed(() => {
  const otherId = getCanonicalMediaRefs(props.secondaryMedia).shotVersionId
  const base = routes.value[0]?.comparisonBaseUrl
  return base && otherId ? `${base}/${encodeURIComponent(otherId)}` : ''
})
const stacked = computed(() => compact.value && props.mode === 'side-by-side')
const timelineFraction = computed(() => requestedFrame.value / Math.max(1, info.value.frame_count - 1))
const wipeWidth = computed(() => family.value === 'video' ? Math.min(stageWidth.value, stageHeight.value * 16 / 9) : stageWidth.value)
const wipeLeft = computed(() => (stageWidth.value - wipeWidth.value) / 2 + wipeWidth.value * wipePercent.value / 100)
let generation = 0, controller, pollTimer, frameCallback = 0, paintRaf = 0, seekRaf = 0, observer, resume = false

function stopFrames() {
  if (frameCallback && video.value?.cancelVideoFrameCallback) video.value.cancelVideoFrameCallback(frameCallback)
  else cancelAnimationFrame(frameCallback)
  frameCallback = 0
  cancelAnimationFrame(paintRaf)
  cancelAnimationFrame(seekRaf)
  paintRaf = seekRaf = 0
}

function requestPaint() {
  if (!paintRaf && !document.hidden) paintRaf = requestAnimationFrame(paint)
}

function paint() {
  // A new video frame can satisfy a pending drag redraw on the same display tick.
  cancelAnimationFrame(paintRaf)
  paintRaf = 0
  const source = video.value, target = canvas.value
  if (!target || !source || source.readyState < 2 || source.seeking || document.hidden) return
  const w = source.videoWidth / 2, h = source.videoHeight
  if (!w || !h) return
  const width = props.mode === 'side-by-side' && !stacked.value ? w * 2 : w
  const height = stacked.value ? h * 2 : h
  if (target.width !== width) target.width = width
  if (target.height !== height) target.height = height
  const context = target.getContext('2d', { alpha: false })
  if (!context) return
  const a = info.value.primary_is_left ? 0 : w, b = w - a
  if (props.mode === 'wipe') {
    const cut = Math.round(w * wipePercent.value / 100)
    context.drawImage(source, b, 0, w, h, 0, 0, w, h)
    if (cut) context.drawImage(source, a, 0, cut, h, 0, 0, cut, h)
  } else {
    context.drawImage(source, a, 0, w, h, 0, 0, w, h)
    context.drawImage(source, b, 0, w, h, stacked.value ? 0 : w, stacked.value ? h : 0, w, h)
  }
}

function showFrame(time) {
  frame.value = Math.max(0, Math.min(info.value.frame_count - 1, Math.floor(time * info.value.fps + .001)))
  if (!scrubbing.value) requestedFrame.value = frame.value
}

function observeFrames() {
  const source = video.value
  if (!source || frameCallback || document.hidden) return
  const callback = (_now, metadata) => {
    frameCallback = 0
    if (!source.seeking) { paint(); showFrame(metadata?.mediaTime ?? source.currentTime) }
    if (!source.paused) observeFrames()
  }
  frameCallback = source.requestVideoFrameCallback ? source.requestVideoFrameCallback(callback) : requestAnimationFrame(callback)
}

function loaded() { ready.value = true; buffering.value = false; paint(); showFrame(video.value.currentTime) }
function mediaError() { if (video.value?.getAttribute('src')) error.value = 'The comparison could not load. Try again.' }
async function play() {
  if (!ready.value || !video.value) return
  const current = generation
  if (video.value.ended) video.value.currentTime = 0
  observeFrames()
  try { await video.value.play() }
  catch { if (current === generation) error.value = 'Playback could not start. Try again.' }
}
function pause() { video.value?.pause(); resume = false }
function toggle() { if (video.value?.paused) void play(); else pause() }
function seek(value) {
  if (!ready.value || !video.value) return
  video.value.pause()
  requestedFrame.value = Math.max(0, Math.min(info.value.frame_count - 1, Math.round(value)))
  // Seek inside the frame, not on a floating-point boundary between frames.
  video.value.currentTime = (requestedFrame.value + .25) / info.value.fps
}
function beginScrub() { resume = playing.value; scrubbing.value = true }
function endScrub() {
  scrubbing.value = false
  if (!video.value?.seeking && resume) { resume = false; void play() }
}
function seeked() {
  cancelAnimationFrame(seekRaf)
  // Safari makes the newly decoded picture drawable on the next render tick.
  seekRaf = requestAnimationFrame(() => {
    seekRaf = 0
    if (!video.value || video.value.seeking) return
    paint(); showFrame(video.value.currentTime)
    if (!scrubbing.value && resume) { resume = false; void play() }
  })
}
function startWipe(event) {
  if (props.mode !== 'wipe' || error.value || (family.value === 'video' && !ready.value) || event.button !== 0) return
  if (event.target.closest('button, input, select')) return
  const element = stage.value
  const bounds = element.getBoundingClientRect()
  const scale = bounds.width / element.offsetWidth
  const width = wipeWidth.value * scale
  if (!width) return
  const left = bounds.left + (element.clientLeft + (stageWidth.value - wipeWidth.value) / 2) * scale
  element.setPointerCapture(event.pointerId)
  const move = e => {
    wipePercent.value = Math.max(0, Math.min(100, (e.clientX - left) / width * 100))
  }
  element.onpointermove = move
  element.onlostpointercapture = () => { element.onpointermove = null; element.onlostpointercapture = null }
  move(event)
}
function keydown(event) {
  if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || !ready.value || family.value !== 'video') return
  const target = event.target
  const timeline = target?.classList?.contains('media-compare-seek')
  if (!timeline && target?.closest?.('input, textarea, select, button, [contenteditable="true"], [role="dialog"]')) return
  if (event.code === 'Space') { event.preventDefault(); toggle() }
  else if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
    event.preventDefault(); resume = false
    seek(event.key === 'Home' ? 0 : event.key === 'End' ? info.value.frame_count - 1
      : requestedFrame.value + (event.key === 'ArrowRight' ? 1 : -1) * (event.shiftKey ? 10 : 1))
  }
}
function formatSeconds(seconds) { return formatTimecodeWithFrames(seconds + 1e-7, info.value.fps) }

async function loadPair(retry = false) {
  const current = ++generation
  clearTimeout(pollTimer); controller?.abort(); stopFrames(); pause()
  ready.value = false; error.value = ''; state.value = 'loading'; buffering.value = false
  frame.value = requestedFrame.value = 0; progress.value = 0; scrubbing.value = false
  info.value = { fps: 24, frame_count: 0, end_frames: [] }
  if (video.value) { video.value.removeAttribute('src'); video.value.load() }
  await nextTick()
  if (current !== generation || family.value !== 'video') return
  if (!pairUrl.value) { error.value = 'Choose two video versions from this tracker.'; return }
  const url = pairUrl.value
  controller = new AbortController()
  const signal = controller.signal
  let polls = 0
  const poll = async () => {
    try {
      const response = await api.request({ url: `${url}/status`, method: retry && polls === 0 ? 'POST' : 'GET', signal })
      if (current !== generation) return
      const data = response.data
      info.value = data; state.value = data.status; progress.value = data.progress || 0
      if (data.status === 'error') { error.value = data.error || 'The comparison could not be prepared.'; return }
      if (data.status === 'complete') {
        video.value.src = `${url}/file`
        video.value.load()
        return
      }
      pollTimer = setTimeout(poll, [1000, 2000, 5000][Math.min(polls++, 2)])
    } catch (exception) {
      if (current === generation && !signal.aborted) {
        const status = exception.response?.status
        const detail = exception.response?.data?.detail
        error.value = status === 403 || status === 401 ? 'Comparison is not available for these versions.'
          : status === 404 && detail === 'Not Found' ? 'This server needs the new comparison update.'
            : status === 404 ? 'One of these versions is unavailable.'
              : status === 422 ? 'Video timing could not be read. Choose another version.'
                : 'The comparison could not be prepared. Try again.'
      }
    }
  }
  void poll()
}

function visibilityChanged() {
  if (document.hidden) { pause(); stopFrames() }
  else paint()
}
watch([pairUrl, family, imageUrls], () => { void loadPair() })
watch([() => props.mode, wipePercent, stacked], requestPaint)
onMounted(() => {
  observer = new ResizeObserver(entries => {
    const box = entries[0].contentRect
    stageWidth.value = box.width; stageHeight.value = box.height
    compact.value = box.width <= 600
    paint()
  })
  observer.observe(stage.value)
  window.addEventListener('keydown', keydown)
  window.addEventListener('pointerup', endScrub)
  window.addEventListener('pointercancel', endScrub)
  document.addEventListener('visibilitychange', visibilityChanged)
  void loadPair()
})
onBeforeUnmount(() => {
  generation++; controller?.abort(); clearTimeout(pollTimer); stopFrames(); pause(); observer?.disconnect()
  if (video.value) { video.value.removeAttribute('src'); video.value.load() }
  window.removeEventListener('keydown', keydown)
  window.removeEventListener('pointerup', endScrub)
  window.removeEventListener('pointercancel', endScrub)
  document.removeEventListener('visibilitychange', visibilityChanged)
})
</script>
