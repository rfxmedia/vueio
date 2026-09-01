<template>
  <div class="media-viewer-toolbar">
    <div class="timeline-row">
      <div
        ref="timelineEl"
        class="timeline"
        :class="{ 'is-scrubbing': isTimelineDragging }"
        role="slider"
        tabindex="0"
        aria-label="Video timeline"
        aria-valuemin="0"
        :aria-valuemax="Math.max(0, duration)"
        @keydown="handleTimelineKeydown"
        @pointerdown.stop.prevent="handleStartTimelinePointer"
        @pointerup.stop.prevent="handleFinishTimelinePointer"
        @pointercancel.stop.prevent="handleCancelTimelinePointer"
        @mouseenter="handleTimelineEnter"
        @pointermove.stop.prevent="handleTimelineMove"
        @mouseleave="handleTimelineLeave"
      >
        <div class="timeline-bg"></div>
        <!-- Width/left are written imperatively by the playback clock so a
             frame tick never re-renders the component tree. -->
        <div ref="progressBarEl" class="timeline-progress"></div>
        <div ref="progressHandleEl" class="timeline-handle"></div>
        <div
          class="scrub-preview-popover"
          :class="{ 'is-visible': showScrubPreview, 'is-ready': scrubPreviewReady, 'is-loading': !scrubPreviewReady, 'has-comment': scrubPreviewComment }"
          :style="scrubPreviewStyle"
          aria-hidden="true"
        >
          <div class="scrub-preview-frame">
            <video
              ref="scrubPreviewVideoEl"
              class="scrub-preview-video"
              muted
              playsinline
              webkit-playsinline
              preload="metadata"
              @loadeddata="handleScrubPreviewReady"
              @canplay="handleScrubPreviewReady"
              @seeked="handleScrubPreviewReady"
              @error="handleScrubPreviewError"
            ></video>
          </div>
          <div class="scrub-preview-time">{{ formatTimecode(scrubPreviewTime) }}</div>
          <div v-if="scrubPreviewComment" class="scrub-preview-comment">
            <div class="scrub-preview-comment__meta">
              <span class="scrub-preview-comment__author">{{ scrubPreviewCommentAuthor }}</span>
              <span v-if="scrubPreviewCommentHasAnnotation" class="scrub-preview-comment__annotation">
                <svg class="icon"><use href="#icon-pen"/></svg>
              </span>
            </div>
            <p class="scrub-preview-comment__text">{{ scrubPreviewCommentText }}</p>
          </div>
        </div>
        <div
          v-for="comment in comments"
          :key="comment.id"
          class="comment-marker"
          :class="{ resolved: comment.resolved, 'has-annotation': comment.annotation_data }"
          :style="commentMarkerStyle(comment)"
          role="button"
          tabindex="0"
          :aria-label="commentMarkerLabel(comment)"
          @mouseenter.stop="handleCommentMarkerEnter(comment)"
          @mousemove.stop="handleCommentMarkerEnter(comment)"
          @mouseleave.stop="handleCommentMarkerLeave"
          @mousedown.stop.prevent
          @click.stop="handleSeekToComment(comment, $event)"
          @keydown.enter.prevent="handleSeekToComment(comment, $event)"
          @keydown.space.prevent="handleSeekToComment(comment, $event)"
        ></div>
      </div>
    </div>

    <div class="controls-row">
      <div class="controls-bar" role="group" aria-label="Playback controls">
        <div class="controls-zone controls-zone--left">
          <button
            type="button"
            class="v-btn v-btn-quiet v-btn-icon control-btn control-btn--play"
            :aria-label="isPlaying ? 'Pause' : 'Play'"
            @click="togglePlay"
          >
            <span class="play-pause-morph" :class="{ 'is-playing': isPlaying }" aria-hidden="true">
              <svg class="icon play-pause-morph__glyph play-pause-morph__glyph--play">
                <use href="#icon-play" />
              </svg>
              <svg class="icon play-pause-morph__glyph play-pause-morph__glyph--pause">
                <use href="#icon-pause" />
              </svg>
            </span>
          </button>
          <button
            type="button"
            class="v-btn v-btn-quiet v-btn-icon control-btn control-btn--icon loop-btn"
            :class="{ active: loopEnabled }"
            @click="toggleLoop"
            :aria-label="loopEnabled ? 'Disable loop playback' : 'Enable loop playback'"
          >
            <svg class="icon"><use href="#icon-refresh"/></svg>
          </button>
          <div class="volume-controls" :class="{ 'is-dragging': volumeSliderDragging }" @click.stop>
            <button
              type="button"
              class="v-btn v-btn-quiet v-btn-icon control-btn control-btn--icon"
              @click="toggleMute"
              :aria-label="isActuallyMuted ? 'Unmute' : 'Mute'"
            >
              <svg class="icon"><use :href="volumeIconHref"/></svg>
            </button>
            <input
              ref="volumeSliderEl"
              class="volume-slider"
              :class="{ 'is-dragging': volumeSliderDragging }"
              type="range"
              min="0"
              max="1"
              step="0.01"
              :value="playerVolume"
              @input="handleVolumeSliderInput"
              @change="handleVolumeSliderInput"
              @pointerdown="handleVolumePointerDown"
              @mousedown.stop
              @click.stop
              @touchstart.stop
              :style="{ '--vol-pct': volumePercent }"
              :aria-label="`Volume (${Math.round(playerVolume * 100)}%)`"
            />
          </div>
        </div>

        <div class="controls-zone controls-zone--center">
          <div class="controls-timecode">
            <span ref="timeCurrentEl" class="time-current"></span>
            <span class="time-sep">/</span>
            <span class="time-duration">{{ formatTimecode(duration) }}</span>
            <span class="frame-counter" title="Current frame">
              <span class="frame-counter__prefix">F</span>
              <span ref="frameValueEl" class="frame-counter__value"></span>
            </span>
          </div>
        </div>

        <div class="controls-zone controls-zone--right">
            <div class="frame-copy-control frame-capture-control">
              <VMenu
                :open="frameCaptureMenuOpen"
                align="end"
                min-width="256"
                :teleport="true"
                panel-role="dialog"
                panel-class="viewer-frame-capture-menu"
                @update:open="(open) => { if (!open) closeFrameCaptureMenu() }"
              >
                <template #trigger="{ triggerProps }">
                  <div class="frame-capture-split" :class="{ 'is-open': frameCaptureMenuOpen }">
                    <button
                      v-bind="triggerProps"
                      type="button"
                      class="v-btn v-btn-quiet v-btn-icon control-btn frame-copy-btn frame-capture-primary"
                      :class="{ 'is-busy': frameCaptureBusy, 'is-success': frameCaptureSucceeded, 'is-error': frameCopyState === 'error' }"
                      :disabled="!canCopyCurrentFrame || frameCaptureBusy"
                      :aria-label="frameCopyButtonTitle"
                      @click.stop="copyCurrentFrame"
                    >
                      <svg v-if="frameCaptureBusy" class="icon frame-copy-btn__spinner"><use href="#icon-loader"/></svg>
                      <svg v-else-if="frameCaptureSucceeded" class="icon"><use href="#icon-check"/></svg>
                      <svg v-else class="icon"><use href="#icon-camera"/></svg>
                    </button>
                    <button
                      type="button"
                      class="v-btn v-btn-quiet v-btn-icon control-btn control-btn--icon frame-capture-menu-btn"
                      :class="{ active: frameCaptureMenuOpen }"
                      aria-label="Screenshot options"
                      @click.stop="toggleFrameCaptureMenu"
                    >
                      <svg class="icon viewer-mobile-capture-icon"><use href="#icon-camera"/></svg>
                      <svg class="icon frame-capture-menu-btn__icon"><use href="#icon-chevron-down"/></svg>
                    </button>
                  </div>
                </template>
                <div class="viewer-frame-capture-panel">
                  <button
                    type="button"
                    class="v-dropdown-item viewer-frame-capture-option viewer-mobile-only"
                    :disabled="!canCopyCurrentFrame || frameCaptureBusy"
                    @click.stop="copyCurrentFrame"
                  >
                    <svg class="icon"><use href="#icon-camera"/></svg>
                    <span class="viewer-frame-capture-option__copy">
                      <span class="viewer-frame-capture-option__label">Copy Current Frame</span>
                      <span class="viewer-frame-capture-option__hint">Copy or share this frame</span>
                    </span>
                  </button>
                  <button
                    type="button"
                    class="v-dropdown-item viewer-frame-capture-option"
                    :disabled="!canDownloadCurrentFrame || frameCaptureBusy"
                    @click.stop="downloadCurrentFrame"
                  >
                    <svg class="icon"><use href="#icon-download"/></svg>
                    <span class="viewer-frame-capture-option__copy">
                      <span class="viewer-frame-capture-option__label">Download Current Frame</span>
                      <span class="viewer-frame-capture-option__hint">Save a PNG locally</span>
                    </span>
                  </button>
                  <button
                    type="button"
                    class="v-dropdown-item viewer-frame-capture-option"
                    :disabled="!canSetCurrentFrameAsThumbnail || frameCaptureBusy"
                    @click.stop="setCurrentFrameAsThumbnail"
                  >
                    <svg class="icon"><use href="#icon-image"/></svg>
                    <span class="viewer-frame-capture-option__copy">
                      <span class="viewer-frame-capture-option__label">Set Current Frame as Thumbnail</span>
                      <span class="viewer-frame-capture-option__hint">Replace media thumbnail</span>
                    </span>
                  </button>
                  <VSwitch
                    v-model="frameCaptureIncludeAnnotations"
                    class="viewer-frame-capture-switch"
                    label="Include annotations"
                    hint="Capture visible drawings and pending markups."
                  />
                  <VSwitch
                    v-model="frameCaptureIncludeComment"
                    class="viewer-frame-capture-switch"
                    label="Include selected comment"
                    :hint="frameCaptureCommentHint"
                    :disabled="!hasFrameCaptureComment"
                  />
                </div>
              </VMenu>
              <div
                v-if="frameCopyFeedbackVisible"
                class="frame-copy-feedback"
                :class="{ 'is-error': frameCopyState === 'error' }"
                role="status"
                aria-live="polite"
              >
                {{ frameCopyFeedbackLabel }}
              </div>
            </div>
            <VMenu
              :open="colorPreviewMenuOpen"
              align="end"
              min-width="278"
              :teleport="true"
              panel-class="viewer-color-preview-menu"
              panel-label="Color preview"
              @update:open="(open) => { if (!open) closeColorPreviewMenu() }"
            >
              <template #trigger="{ triggerProps }">
                <button
                  v-bind="triggerProps"
                  type="button"
                  class="v-btn v-btn-quiet v-btn-icon control-btn control-btn--icon viewer-color-preview-trigger"
                  :class="{ active: colorPreviewMenuOpen || colorPreviewMode !== 'source' }"
                  :aria-label="colorPreviewButtonLabel"
                  @click.stop="toggleColorPreviewMenu"
                >
                  <svg class="icon" aria-hidden="true"><use href="#icon-color"/></svg>
                </button>
              </template>
              <div class="viewer-color-preview-panel">
                <div class="viewer-color-preview-heading">
                  <span class="v-section-label">Color preview</span>
                  <span>Display only</span>
                </div>
                <button
                  v-for="option in colorPreviewOptions"
                  :key="option.value"
                  type="button"
                  class="v-dropdown-item viewer-color-preview-option"
                  :class="{ active: option.value === colorPreviewMode }"
                  :disabled="option.value !== 'source' && !colorPreviewAvailable"
                  role="menuitemradio"
                  :aria-checked="option.value === colorPreviewMode ? 'true' : 'false'"
                  @click.stop="selectColorPreview(option.value)"
                >
                  <span class="viewer-color-preview-option__mark" aria-hidden="true"></span>
                  <span class="viewer-color-preview-option__copy">
                    <span class="viewer-color-preview-option__label">{{ option.label }}</span>
                    <span class="viewer-color-preview-option__hint">{{ option.hint }}</span>
                  </span>
                  <svg v-if="option.value === colorPreviewMode" class="icon viewer-color-preview-option__check"><use href="#icon-check"/></svg>
                </button>
                <p class="viewer-color-preview-note">
                  {{ colorPreviewAvailable ? 'Viewer and screenshots only. Media stays unchanged.' : 'Color preview is unavailable in this browser.' }}
                </p>
              </div>
            </VMenu>
            <VMenu
              :open="qualityMenuOpen"
              align="end"
              min-width="176"
              :teleport="true"
              panel-class="viewer-settings-menu"
              @update:open="(open) => { if (!open) closeQualityMenu() }"
            >
              <template #trigger="{ triggerProps }">
                <button
                  v-bind="triggerProps"
                  type="button"
                  class="v-btn v-btn-quiet v-btn-icon control-btn control-btn--icon viewer-quality-trigger"
                  :class="{ active: qualityMenuOpen }"
                  :aria-label="`Playback settings. Quality: ${selectedQualityLabel}`"
                  @click.stop="toggleQualityMenu"
                >
                  <svg class="icon" aria-hidden="true"><use href="#icon-settings"/></svg>
                </button>
              </template>
              <div class="viewer-settings-panel">
                <div class="viewer-settings-section">
                  <div class="viewer-settings-heading v-section-label viewer-mobile-only">Playback</div>
                  <button
                    type="button"
                    class="v-dropdown-item viewer-settings-option viewer-mobile-only"
                    :class="{ active: loopEnabled }"
                    @click.stop="toggleLoopFromSettings"
                  >
                    <span class="viewer-settings-option__label">Loop playback</span>
                    <svg v-if="loopEnabled" class="icon viewer-settings-option__check"><use href="#icon-check"/></svg>
                  </button>
                  <div class="viewer-settings-heading v-section-label">Quality</div>
                  <button
                    v-for="option in qualityOptions"
                    :key="option.value"
                    type="button"
                    class="v-dropdown-item viewer-settings-option"
                    :class="{ active: option.value === selectedQuality }"
                    role="menuitemradio"
                    :aria-checked="option.value === selectedQuality ? 'true' : 'false'"
                    @click.stop="selectQuality(option.value)"
                  >
                    <span class="viewer-settings-option__label">{{ option.label }}</span>
                    <svg v-if="option.value === selectedQuality" class="icon viewer-settings-option__check"><use href="#icon-check"/></svg>
                  </button>
                </div>
              </div>
            </VMenu>
            <button
              type="button"
              class="v-btn v-btn-quiet v-btn-icon control-btn control-btn--icon fullscreen-btn"
              aria-label="Fullscreen"
              @click="toggleFullscreen"
            >
              <svg class="icon"><use href="#icon-fullscreen"/></svg>
            </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, toRefs, watch } from 'vue'
import { VMenu, VSwitch } from '../primitives'

const props = defineProps({
  comments: { type: Array, default: () => [] },
  duration: { type: Number, default: 0 },
  currentTimeRef: { type: Object, default: null },
  frameRate: { type: Number, default: 24 },
  streamPreparing: { type: Boolean, default: false },
  playerVolume: { type: Number, default: 0 },
  loopEnabled: { type: Boolean, default: false },
  isPlaying: { type: Boolean, default: false },
  isActuallyMuted: { type: Boolean, default: false },
  volumeIconHref: { type: String, default: '#icon-volume' },
  qualityOptions: { type: Array, default: () => [] },
  selectedQuality: { type: String, default: '' },
  selectedQualityLabel: { type: String, default: '' },
  scrubPreviewSourceUrl: { type: String, default: '' },
  formatTimecode: { type: Function, required: true },
  onSeekToTime: { type: Function, required: true },
  onStartTimelinePointer: { type: Function, required: true },
  onMoveTimelinePointer: { type: Function, required: true },
  onFinishTimelinePointer: { type: Function, required: true },
  onCancelTimelinePointer: { type: Function, required: true },
  onSeekToComment: { type: Function, required: true },
  onTogglePlay: { type: Function, required: true },
  onToggleMute: { type: Function, required: true },
  onVolumeSliderInput: { type: Function, required: true },
  onToggleLoop: { type: Function, required: true },
  onToggleFullscreen: { type: Function, required: true },
  onSetStreamQuality: { type: Function, required: true },
  onCopyCurrentFrame: { type: Function, default: null },
  onDownloadCurrentFrame: { type: Function, default: null },
  onSetCurrentFrameAsThumbnail: { type: Function, default: null },
  canSetCurrentFrameAsThumbnail: { type: Boolean, default: false },
  frameCaptureComment: { type: Object, default: null },
  colorPreviewOptions: { type: Array, default: () => [] },
  colorPreviewMode: { type: String, default: 'source' },
  colorPreviewAvailable: { type: Boolean, default: true },
  onSetColorPreviewMode: { type: Function, default: null },
})

const {
  comments,
  duration,
  playerVolume,
  loopEnabled,
  isPlaying,
  isActuallyMuted,
  volumeIconHref,
  qualityOptions,
  selectedQuality,
  selectedQualityLabel,
  formatTimecode
} = toRefs(props)

const timelineEl = ref(null)
const progressBarEl = ref(null)
const progressHandleEl = ref(null)
const timeCurrentEl = ref(null)
const frameValueEl = ref(null)

// ── Playback clock ───────────────────────────────────────────────────────────
// The transport updates `currentTimeRef` 60×/s while playing. Rendering that
// through the template would re-render this whole component per frame, so the
// clock-driven spots (progress bar, handle, timecode, frame counter, slider
// aria) are plain DOM writes instead. Everything else renders normally.

function clockTime() {
  const value = Number(props.currentTimeRef?.value)
  return Number.isFinite(value) ? value : 0
}

let lastAriaSecond = -1
let lastTimecodeText = ''
let lastFrameText = ''

function writeClockDom(time) {
  const pct = props.duration ? Math.max(0, Math.min(100, (time / props.duration) * 100)) : 0
  if (progressBarEl.value) progressBarEl.value.style.width = `${pct}%`
  if (progressHandleEl.value) progressHandleEl.value.style.left = `${pct}%`

  const timecode = props.formatTimecode?.(time) ?? ''
  if (timeCurrentEl.value && timecode !== lastTimecodeText) {
    lastTimecodeText = timecode
    timeCurrentEl.value.textContent = timecode
  }

  const frameText = String(Math.floor(time * (props.frameRate || 24)))
  if (frameValueEl.value && frameText !== lastFrameText) {
    lastFrameText = frameText
    frameValueEl.value.textContent = frameText
  }

  const second = Math.floor(time)
  if (timelineEl.value && second !== lastAriaSecond) {
    lastAriaSecond = second
    timelineEl.value.setAttribute('aria-valuenow', String(Math.max(0, Math.min(time, props.duration || time))))
    timelineEl.value.setAttribute('aria-valuetext', timecode)
  }
}

watch(
  [() => props.currentTimeRef?.value, timelineEl, () => props.duration, () => props.frameRate],
  () => writeClockDom(clockTime()),
  { immediate: true, flush: 'post' },
)
const scrubPreviewVideoEl = ref(null)
const volumeSliderEl = ref(null)
const qualityMenuOpen = ref(false)
const colorPreviewMenuOpen = ref(false)
const frameCaptureMenuOpen = ref(false)
const frameCaptureIncludeAnnotations = ref(true)
const frameCaptureIncludeComment = ref(true)
const isTimelineDragging = ref(false)
const volumeSliderDragging = ref(false)
const scrubPreviewVisible = ref(false)
const scrubPreviewTime = ref(0)
const scrubPreviewX = ref(0)
const scrubPreviewComment = ref(null)
const scrubPreviewReady = ref(false)
const scrubPreviewSupported = ref(true)
const frameCopyState = ref('idle')
const frameCopyError = ref('')
const volumePercent = computed(() => `${Math.round(props.playerVolume * 100)}%`)
const canUseScrubPreview = computed(() => Boolean(scrubPreviewSupported.value && props.scrubPreviewSourceUrl && props.duration > 0))
const showScrubPreview = computed(() => scrubPreviewVisible.value && (canUseScrubPreview.value || scrubPreviewComment.value))
const scrubPreviewStyle = computed(() => ({
  '--scrub-preview-x': `${scrubPreviewX.value}px`,
}))
const scrubPreviewCommentText = computed(() => {
  const comment = scrubPreviewComment.value
  const text = String(comment?.text || '').trim()
  if (text) return text
  return comment?.annotation_data ? 'Drawing annotation' : 'Comment'
})
const scrubPreviewCommentAuthor = computed(() => {
  const author = String(scrubPreviewComment.value?.user_name || '').trim()
  return author || 'Comment'
})
const scrubPreviewCommentHasAnnotation = computed(() => Boolean(scrubPreviewComment.value?.annotation_data))
const canCopyCurrentFrame = computed(() => typeof props.onCopyCurrentFrame === 'function')
const canDownloadCurrentFrame = computed(() => typeof props.onDownloadCurrentFrame === 'function')
const canSetCurrentFrameAsThumbnail = computed(() => props.canSetCurrentFrameAsThumbnail && typeof props.onSetCurrentFrameAsThumbnail === 'function')
const hasFrameCaptureComment = computed(() => Boolean(props.frameCaptureComment))
const frameCaptureCommentHint = computed(() => {
  const comment = props.frameCaptureComment
  if (!comment) return 'Select a comment at this frame to stamp it on screenshots.'
  const author = String(comment.user_name || 'Selected comment').trim()
  return `${author} at ${formatTimecode.value?.(Number(comment.timestamp || 0)) || 'this frame'}`
})
const frameCaptureBusy = computed(() => frameCopyState.value === 'copying' || frameCopyState.value === 'downloading' || frameCopyState.value === 'thumbnailing')
const frameCaptureSucceeded = computed(() => frameCopyState.value === 'copied' || frameCopyState.value === 'shared' || frameCopyState.value === 'downloaded' || frameCopyState.value === 'thumbnailed')
const frameCopyFeedbackVisible = computed(() => frameCaptureBusy.value || frameCaptureSucceeded.value || frameCopyState.value === 'error')
const frameCopyFeedbackLabel = computed(() => {
  if (frameCopyState.value === 'copying') return 'Saving screenshot'
  if (frameCopyState.value === 'copied') return 'Screenshot saved to clipboard.'
  if (frameCopyState.value === 'shared') return 'Screenshot ready to share.'
  if (frameCopyState.value === 'downloading') return 'Preparing download'
  if (frameCopyState.value === 'downloaded') return 'Frame downloaded'
  if (frameCopyState.value === 'thumbnailing') return 'Updating thumbnail'
  if (frameCopyState.value === 'thumbnailed') return 'Thumbnail updated'
  if (frameCopyState.value === 'error') return frameCopyError.value || 'Screenshot failed'
  return ''
})
const frameCopyButtonTitle = computed(() => {
  if (!canCopyCurrentFrame.value) return 'Screenshot unavailable'
  if (frameCopyState.value === 'copying') return 'Saving screenshot'
  if (frameCopyState.value === 'copied') return 'Screenshot saved to clipboard.'
  if (frameCopyState.value === 'shared') return 'Screenshot ready to share.'
  if (frameCopyState.value === 'thumbnailing') return 'Updating thumbnail'
  if (frameCopyState.value === 'thumbnailed') return 'Thumbnail updated'
  if (frameCopyState.value === 'error') return frameCopyError.value || 'Could not take screenshot'
  return 'Take Screenshot'
})
const selectedColorPreviewLabel = computed(() => (
  props.colorPreviewOptions.find(option => option.value === props.colorPreviewMode)?.label || 'Source'
))
const colorPreviewButtonLabel = computed(() => (
  props.colorPreviewAvailable
    ? `Color preview. ${selectedColorPreviewLabel.value}`
    : 'Color preview unavailable'
))
const frameCopyTooltipLabel = computed(() => {
  if (!canCopyCurrentFrame.value) return 'Screenshot unavailable'
  if (frameCopyState.value === 'copying') return 'Saving'
  if (frameCopyState.value === 'copied') return 'Saved to clipboard'
  if (frameCopyState.value === 'shared') return 'Ready to share'
  if (frameCopyState.value === 'downloading') return 'Preparing download'
  if (frameCopyState.value === 'downloaded') return 'Downloaded'
  if (frameCopyState.value === 'thumbnailing') return 'Updating thumbnail'
  if (frameCopyState.value === 'thumbnailed') return 'Thumbnail updated'
  if (frameCopyState.value === 'error') return 'Copy failed'
  return 'Take Screenshot'
})

let scrubPreviewHls = null
let scrubPreviewAttachRequestId = 0
let scrubPreviewHlsStarted = false
let scrubPreviewSeekFrame = 0
let scrubPreviewPendingTime = null
let scrubPreviewLastSeekAt = 0
let scrubPreviewHideTimer = 0
let frameCopyFeedbackTimer = 0
let timelinePointerRect = null
const SCRUB_PREVIEW_SEEK_INTERVAL_MS = 80

function commentMarkerStyle(comment) {
  const left = props.duration > 0 ? (comment.timestamp / props.duration) * 100 : 0
  return { left: `${Math.min(Math.max(left, 0), 100)}%` }
}

function commentMarkerLabel(comment) {
  const author = String(comment?.user_name || 'comment').trim()
  return `Open ${author} comment at ${props.formatTimecode?.(Number(comment?.timestamp || 0)) || 'this time'}`
}

function getCommentPreviewTime(comment) {
  const timestamp = Number(comment?.timestamp || 0)
  if (!Number.isFinite(timestamp)) return 0
  return Math.max(0, Math.min(props.duration || timestamp, timestamp))
}

function handleTimelineKeydown(event) {
  if (!props.duration) return
  const step = event.shiftKey ? 10 : 1
  const now = clockTime()
  let target = null
  if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') target = now - step
  if (event.key === 'ArrowRight' || event.key === 'ArrowUp') target = now + step
  if (event.key === 'Home') target = 0
  if (event.key === 'End') target = props.duration
  if (target === null) return
  event.preventDefault()
  props.onSeekToTime(Math.max(0, Math.min(props.duration, target)))
}

function handleStartTimelinePointer(event) {
  clearScrubPreviewHideTimer()
  cacheTimelinePointerRect()
  updateScrubPreviewFromPoint(event.clientX)
  isTimelineDragging.value = true
  props.onStartTimelinePointer(event, timelineEl.value)
}

function finishTimelinePointer(event, cancel = false) {
  if (!isTimelineDragging.value) return
  const handler = cancel ? props.onCancelTimelinePointer : props.onFinishTimelinePointer
  handler(event, timelineEl.value)
  isTimelineDragging.value = false
  timelinePointerRect = null
  suspendScrubPreviewLoading()
  hideScrubPreview({ delay: cancel ? 0 : 350 })
}

function handleFinishTimelinePointer(event) {
  finishTimelinePointer(event)
}

function handleCancelTimelinePointer(event) {
  finishTimelinePointer(event, true)
}

function releaseCommentMarkerFocus(event) {
  const target = event?.currentTarget
  if (target && typeof target.blur === 'function') target.blur()
}

function handleSeekToComment(comment, event = null) {
  scrubPreviewComment.value = comment || null
  props.onSeekToComment(comment)
  releaseCommentMarkerFocus(event)
}

function togglePlay() {
  props.onTogglePlay()
}

function toggleMute() {
  props.onToggleMute()
}

function handleVolumeSliderInput(event) {
  props.onVolumeSliderInput(event)
}

function getVolumeFromPointer(event) {
  const slider = volumeSliderEl.value
  const rect = slider?.getBoundingClientRect?.()
  if (!rect?.width) return props.playerVolume
  const clientX = Number(event?.clientX)
  if (!Number.isFinite(clientX)) return props.playerVolume
  const pct = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1)
  return Math.round(pct * 100) / 100
}

function applyVolumeFromPointer(event) {
  props.onVolumeSliderInput({ target: { value: String(getVolumeFromPointer(event)) } })
}

function stopVolumePointerDrag() {
  if (!volumeSliderDragging.value) return
  volumeSliderDragging.value = false
  window.removeEventListener('pointermove', handleWindowVolumePointerMove)
  window.removeEventListener('pointerup', handleWindowVolumePointerUp)
  window.removeEventListener('pointercancel', handleWindowVolumePointerUp)
}

function handleVolumePointerDown(event) {
  if (event?.pointerType === 'mouse' && event.button !== 0) return
  event.preventDefault()
  event.stopPropagation()
  volumeSliderDragging.value = true
  try { event.currentTarget?.focus?.({ preventScroll: true }) } catch {}
  try { event.currentTarget?.setPointerCapture?.(event.pointerId) } catch {}
  applyVolumeFromPointer(event)
  window.addEventListener('pointermove', handleWindowVolumePointerMove, { passive: false })
  window.addEventListener('pointerup', handleWindowVolumePointerUp)
  window.addEventListener('pointercancel', handleWindowVolumePointerUp)
}

function handleWindowVolumePointerMove(event) {
  if (!volumeSliderDragging.value) return
  event.preventDefault()
  applyVolumeFromPointer(event)
}

function handleWindowVolumePointerUp(event) {
  if (volumeSliderDragging.value) applyVolumeFromPointer(event)
  stopVolumePointerDrag()
}

function toggleLoop() {
  props.onToggleLoop()
}

function toggleLoopFromSettings() {
  toggleLoop()
  closeQualityMenu()
}

function clearFrameCopyFeedbackTimer() {
  if (!frameCopyFeedbackTimer) return
  window.clearTimeout(frameCopyFeedbackTimer)
  frameCopyFeedbackTimer = 0
}

function settleFrameCopyState(state, error = '') {
  clearFrameCopyFeedbackTimer()
  frameCopyState.value = state
  frameCopyError.value = error
  if (state === 'idle' || state === 'copying' || state === 'downloading' || state === 'thumbnailing') return
  frameCopyFeedbackTimer = window.setTimeout(() => {
    frameCopyState.value = 'idle'
    frameCopyError.value = ''
    frameCopyFeedbackTimer = 0
  }, 1800)
}

async function copyCurrentFrame() {
  if (!canCopyCurrentFrame.value || frameCaptureBusy.value) return
  frameCaptureMenuOpen.value = false
  settleFrameCopyState('copying')
  try {
    const result = await props.onCopyCurrentFrame({
      includeAnnotations: frameCaptureIncludeAnnotations.value,
      includeComment: frameCaptureIncludeComment.value,
    })
    const mode = result?.mode || 'clipboard'
    settleFrameCopyState(mode === 'download' ? 'downloaded' : mode === 'share' ? 'shared' : 'copied')
  } catch (error) {
    settleFrameCopyState('error', error?.message || 'Could not take screenshot')
  }
}

async function downloadCurrentFrame() {
  if (!canDownloadCurrentFrame.value || frameCaptureBusy.value) return
  frameCaptureMenuOpen.value = false
  settleFrameCopyState('downloading')
  try {
    await props.onDownloadCurrentFrame({
      includeAnnotations: frameCaptureIncludeAnnotations.value,
      includeComment: frameCaptureIncludeComment.value,
    })
    settleFrameCopyState('downloaded')
  } catch (error) {
    settleFrameCopyState('error', error?.message || 'Could not download current frame')
  }
}

async function setCurrentFrameAsThumbnail() {
  if (!canSetCurrentFrameAsThumbnail.value || frameCaptureBusy.value) return
  frameCaptureMenuOpen.value = false
  settleFrameCopyState('thumbnailing')
  try {
    await props.onSetCurrentFrameAsThumbnail()
    settleFrameCopyState('thumbnailed')
  } catch (error) {
    settleFrameCopyState('error', error?.message || 'Could not update thumbnail')
  }
}

function toggleFullscreen() {
  props.onToggleFullscreen()
}

function toggleQualityMenu() {
  frameCaptureMenuOpen.value = false
  colorPreviewMenuOpen.value = false
  qualityMenuOpen.value = !qualityMenuOpen.value
}

function toggleFrameCaptureMenu() {
  qualityMenuOpen.value = false
  colorPreviewMenuOpen.value = false
  frameCaptureMenuOpen.value = !frameCaptureMenuOpen.value
}

function toggleColorPreviewMenu() {
  qualityMenuOpen.value = false
  frameCaptureMenuOpen.value = false
  colorPreviewMenuOpen.value = !colorPreviewMenuOpen.value
}

function selectColorPreview(value) {
  if (value !== 'source' && !props.colorPreviewAvailable) return
  props.onSetColorPreviewMode?.(value)
  colorPreviewMenuOpen.value = false
}

function selectQuality(value) {
  props.onSetStreamQuality(value)
  qualityMenuOpen.value = false
}

function closeQualityMenu() {
  qualityMenuOpen.value = false
}

function closeFrameCaptureMenu() {
  frameCaptureMenuOpen.value = false
}

function closeColorPreviewMenu() {
  colorPreviewMenuOpen.value = false
}

function isHlsSource(source) {
  return /\.m3u8(?:$|[?#])/i.test(String(source || ''))
}

function clearScrubPreviewHideTimer() {
  if (!scrubPreviewHideTimer) return
  window.clearTimeout(scrubPreviewHideTimer)
  scrubPreviewHideTimer = 0
}

function destroyScrubPreviewEngine() {
  scrubPreviewAttachRequestId += 1
  if (scrubPreviewSeekFrame) {
    cancelAnimationFrame(scrubPreviewSeekFrame)
    scrubPreviewSeekFrame = 0
  }
  scrubPreviewPendingTime = null
  scrubPreviewLastSeekAt = 0
  if (scrubPreviewHls) {
    try { scrubPreviewHls.destroy() } catch {}
    scrubPreviewHls = null
  }
  scrubPreviewHlsStarted = false
  scrubPreviewReady.value = false
  const video = scrubPreviewVideoEl.value
  if (!video) return
  try { video.pause() } catch {}
  try {
    video.removeAttribute('src')
    video.load()
  } catch {}
}

function suspendScrubPreviewLoading() {
  if (scrubPreviewHls) {
    try { scrubPreviewHls.stopLoad() } catch {}
    scrubPreviewHlsStarted = false
  }
  try { scrubPreviewVideoEl.value?.pause() } catch {}
}

async function attachScrubPreviewSource() {
  destroyScrubPreviewEngine()
  const requestId = ++scrubPreviewAttachRequestId
  const video = scrubPreviewVideoEl.value
  const source = props.scrubPreviewSourceUrl
  scrubPreviewSupported.value = true
  scrubPreviewAttachedSource = source
  if (!video || !source) return

  video.muted = true
  video.playsInline = true

  if (!isHlsSource(source)) {
    video.src = source
    video.load()
    return
  }

  let Hls
  try {
    const hlsModule = await import('hls.js')
    Hls = hlsModule.default
  } catch {
    if (requestId === scrubPreviewAttachRequestId) scrubPreviewSupported.value = false
    return
  }
  if (
    requestId !== scrubPreviewAttachRequestId
    || video !== scrubPreviewVideoEl.value
    || source !== props.scrubPreviewSourceUrl
  ) return

  if (Hls.isSupported()) {
    scrubPreviewHls = new Hls({
      enableWorker: true,
      lowLatencyMode: false,
      autoStartLoad: false,
      startFragPrefetch: false,
      maxBufferLength: 6,
      backBufferLength: 0,
    })
    scrubPreviewHls.on(Hls.Events.ERROR, (_event, data) => {
      if (!data?.fatal) return
      scrubPreviewReady.value = false
      scrubPreviewSupported.value = false
      destroyScrubPreviewEngine()
    })
    scrubPreviewHls.attachMedia(video)
    scrubPreviewHls.on(Hls.Events.MEDIA_ATTACHED, () => {
      scrubPreviewHls?.loadSource(source)
    })
    return
  }

  // A second native HLS element can aggressively buffer after a timeline hover
  // and starve the primary player during long-video seeks. Hls.js previews are
  // bounded and explicitly suspended; native HLS skips the secondary player.
  scrubPreviewSupported.value = false
}

function handleScrubPreviewReady() {
  scrubPreviewReady.value = true
}

function handleScrubPreviewError() {
  scrubPreviewReady.value = false
}

function startScrubPreviewLoading(time) {
  if (scrubPreviewHls && !scrubPreviewHlsStarted) {
    scrubPreviewHlsStarted = true
    try { scrubPreviewHls.startLoad(Math.max(0, time - 0.25)) } catch {}
  }
}

function seekScrubPreview(time) {
  const video = scrubPreviewVideoEl.value
  if (!video || !props.scrubPreviewSourceUrl) return
  startScrubPreviewLoading(time)
  try { video.pause() } catch {}
  if (Math.abs(Number(video.currentTime || 0) - time) < 0.12) return
  if (video.readyState < 2) scrubPreviewReady.value = false
  try {
    video.currentTime = Math.max(0, Math.min(time, props.duration || time))
  } catch {}
}

function flushScrubPreviewSeek() {
  scrubPreviewSeekFrame = 0
  if (scrubPreviewPendingTime == null) return
  const elapsed = performance.now() - scrubPreviewLastSeekAt
  if (elapsed < SCRUB_PREVIEW_SEEK_INTERVAL_MS) {
    scrubPreviewSeekFrame = requestAnimationFrame(flushScrubPreviewSeek)
    return
  }
  const time = scrubPreviewPendingTime
  scrubPreviewPendingTime = null
  scrubPreviewLastSeekAt = performance.now()
  seekScrubPreview(time)
}

function scheduleScrubPreviewSeek(time) {
  scrubPreviewPendingTime = time
  if (!scrubPreviewSeekFrame) {
    scrubPreviewSeekFrame = requestAnimationFrame(flushScrubPreviewSeek)
  }
}

// The preview player is only attached on first timeline hover. Attaching on
// mount would open a second MediaSource and fetch its playlists at the exact
// moment the primary player is racing for its first segment.
let scrubPreviewAttachedSource = null

function ensureScrubPreviewAttached() {
  const video = scrubPreviewVideoEl.value
  const source = props.scrubPreviewSourceUrl
  if (!video || !source) return
  if (scrubPreviewAttachedSource === source) return
  void attachScrubPreviewSource()
}

watch(
  [() => props.scrubPreviewSourceUrl, scrubPreviewVideoEl],
  () => {
    destroyScrubPreviewEngine()
    scrubPreviewAttachedSource = null
    scrubPreviewSupported.value = true
  },
)

watch(showScrubPreview, (visible) => {
  if (visible) return
  if (scrubPreviewSeekFrame) {
    cancelAnimationFrame(scrubPreviewSeekFrame)
    scrubPreviewSeekFrame = 0
  }
  scrubPreviewPendingTime = null
  scrubPreviewComment.value = null
  suspendScrubPreviewLoading()
})

function cacheTimelinePointerRect(timelineNode = timelineEl.value) {
  timelinePointerRect = timelineNode?.getBoundingClientRect?.() || null
  return timelinePointerRect
}

function updateScrubPreviewFromPoint(clientX, timelineNode = timelineEl.value) {
  if (!timelineNode || !canUseScrubPreview.value) return
  ensureScrubPreviewAttached()
  const rect = timelinePointerRect || cacheTimelinePointerRect(timelineNode)
  if (!rect.width) return
  const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
  const time = Math.max(0, Math.min(props.duration, ratio * props.duration))
  scrubPreviewX.value = ratio * rect.width
  scrubPreviewTime.value = time
  scrubPreviewVisible.value = true
  scheduleScrubPreviewSeek(time)
}

function updateScrubPreviewFromComment(comment) {
  const timelineNode = timelineEl.value
  if (!timelineNode || !comment) return
  const rect = timelinePointerRect || cacheTimelinePointerRect(timelineNode)
  if (!rect.width) return
  const time = getCommentPreviewTime(comment)
  const ratio = props.duration > 0 ? Math.max(0, Math.min(1, time / props.duration)) : 0
  clearScrubPreviewHideTimer()
  if (canUseScrubPreview.value) ensureScrubPreviewAttached()
  scrubPreviewX.value = ratio * rect.width
  scrubPreviewTime.value = time
  scrubPreviewComment.value = comment
  scrubPreviewVisible.value = true
  if (canUseScrubPreview.value) scheduleScrubPreviewSeek(time)
}

function hideScrubPreview({ delay = 0 } = {}) {
  clearScrubPreviewHideTimer()
  if (!delay) {
    scrubPreviewVisible.value = false
    return
  }
  scrubPreviewHideTimer = window.setTimeout(() => {
    scrubPreviewVisible.value = false
    scrubPreviewHideTimer = 0
  }, delay)
}

function handleTimelineEnter(event) {
  clearScrubPreviewHideTimer()
  cacheTimelinePointerRect()
  updateScrubPreviewFromPoint(event.clientX)
}

function handleTimelineMove(event) {
  scrubPreviewComment.value = null
  updateScrubPreviewFromPoint(event.clientX)
  if (isTimelineDragging.value) {
    props.onMoveTimelinePointer(event, timelineEl.value)
  }
}

function handleCommentMarkerEnter(comment) {
  updateScrubPreviewFromComment(comment)
}

function handleCommentMarkerLeave() {
  scrubPreviewComment.value = null
}

function handleTimelineLeave() {
  if (isTimelineDragging.value) return
  timelinePointerRect = null
  hideScrubPreview()
}

watch(() => props.streamPreparing, (preparing) => {
  if (preparing) {
    closeQualityMenu()
    closeFrameCaptureMenu()
    closeColorPreviewMenu()
    isTimelineDragging.value = false
    hideScrubPreview()
  }
})

onUnmounted(() => {
  stopVolumePointerDrag()
  clearScrubPreviewHideTimer()
  clearFrameCopyFeedbackTimer()
  destroyScrubPreviewEngine()
})
</script>

<style>
.viewer-mobile-only,
.viewer-mobile-capture-icon {
  display: none !important;
}

.media-viewer-toolbar {
  margin: var(--v-viewer-toolbar-margin);
  padding: var(--v-viewer-toolbar-padding);
  background: var(--v-viewer-toolbar-bg);
  border: var(--v-viewer-toolbar-border-width) solid var(--v-border);
  border-radius: var(--v-viewer-toolbar-border-radius);
  border-top: none;
  flex-shrink: 0;
}

.timeline-row {
  position: relative;
  padding: var(--v-viewer-toolbar-timeline-padding);
}

.timeline {
  position: relative;
  height: 20px;
  cursor: pointer;
  touch-action: none;
  border-radius: var(--v-radius-full);
  overflow: visible;
}

.timeline:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.timeline-bg,
.timeline-progress {
  position: absolute;
  top: 50%;
  height: 3px;
  transform: translateY(-50%);
  border-radius: var(--v-radius-full);
  transition: height var(--v-duration-fast) var(--v-ease-emphasized);
}

.timeline-bg {
  left: 0;
  right: 0;
  background: color-mix(in srgb, var(--v-text) 14%, transparent);
}

.timeline-progress {
  left: 0;
  right: auto;
  background: var(--v-accent);
  transition: width var(--v-duration-fast) linear, height var(--v-duration-fast) var(--v-ease-emphasized);
}

.timeline:hover .timeline-bg,
.timeline:hover .timeline-progress,
.timeline.is-scrubbing .timeline-bg,
.timeline.is-scrubbing .timeline-progress {
  height: 4px;
}

.timeline-handle {
  position: absolute;
  top: 50%;
  width: 12px;
  height: 12px;
  background: var(--v-accent);
  border-radius: 50%;
  transform: translate(-50%, -50%);
  opacity: 0;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--v-accent) 24%, transparent);
  transition: opacity var(--v-duration-fast) var(--v-ease-emphasized);
}

.timeline:hover .timeline-handle {
  opacity: 1;
}

.timeline.is-scrubbing .timeline-handle {
  opacity: 1;
}

.scrub-preview-popover {
  --scrub-preview-width: 196px;
  --scrub-preview-half: calc(var(--scrub-preview-width) / 2);
  position: absolute;
  left: clamp(
    var(--scrub-preview-half),
    var(--scrub-preview-x, 0px),
    calc(100% - var(--scrub-preview-half))
  );
  bottom: calc(100% + 14px);
  width: var(--scrub-preview-width);
  pointer-events: none;
  z-index: 12;
  opacity: 0;
  visibility: hidden;
  transform: translateX(-50%) translateY(6px) scale(0.98);
  transform-origin: center bottom;
  transition:
    opacity var(--v-duration-fast) var(--v-ease-emphasized),
    transform var(--v-duration-fast) var(--v-ease-emphasized),
    visibility 0s linear var(--v-duration-fast);
  will-change: opacity, transform;
}

.scrub-preview-popover.is-visible {
  opacity: 1;
  visibility: visible;
  transform: translateX(-50%) translateY(0) scale(1);
  transition-delay: 0s;
}

.scrub-preview-popover.has-comment {
  --scrub-preview-width: 278px;
}

.scrub-preview-popover::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: -9px;
  width: 1px;
  height: 8px;
  background: color-mix(in srgb, var(--v-text) 40%, transparent);
  transform: translateX(-50%);
}

.scrub-preview-frame {
  position: relative;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--v-text) 18%, transparent);
  border-radius: var(--v-radius-md);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--v-text) 10%, transparent), transparent 42%),
    var(--v-surface-inline-strong);
  box-shadow:
    0 20px 52px rgba(0, 0, 0, 0.42),
    0 0 0 1px color-mix(in srgb, var(--v-accent) 10%, transparent);
}

.scrub-preview-frame::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent,
    color-mix(in srgb, var(--v-text) 8%, transparent),
    transparent
  );
  opacity: 0;
  transform: translateX(-65%);
}

.scrub-preview-popover.is-loading .scrub-preview-frame::before {
  opacity: 1;
  animation: scrub-preview-sheen 1.1s var(--v-ease-emphasized) infinite;
}

.scrub-preview-video {
  position: relative;
  z-index: 1;
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  transition: opacity var(--v-duration-fast) var(--v-ease-emphasized);
}

.scrub-preview-popover.is-ready .scrub-preview-video {
  opacity: 1;
}

.scrub-preview-time {
  width: max-content;
  min-width: 86px;
  margin: 7px auto 0;
  padding: 4px 8px;
  border: 1px solid color-mix(in srgb, var(--v-surface-border-strong) 78%, var(--v-bg-base));
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-bg-base) 88%, var(--v-surface-panel));
  color: var(--v-text);
  font-size: var(--v-text-sm);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  line-height: 1;
  text-align: center;
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.28);
}

.scrub-preview-comment {
  margin-top: 7px;
  padding: 10px 11px 11px;
  border: 1px solid color-mix(in srgb, var(--v-surface-border-strong) 76%, var(--v-bg-base));
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-bg-base) 86%, var(--v-surface-panel));
  box-shadow:
    0 18px 42px rgba(0, 0, 0, 0.52),
    0 0 0 1px color-mix(in srgb, var(--v-bg-base) 72%, transparent);
}

.scrub-preview-comment__meta {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  margin-bottom: 5px;
}

.scrub-preview-comment__author {
  min-width: 0;
  overflow: hidden;
  color: var(--v-text);
  font-size: var(--v-text-sm);
  font-weight: 700;
  line-height: 1.15;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scrub-preview-comment__annotation {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border: 1px solid color-mix(in srgb, var(--v-warning, #d4a548) 24%, transparent);
  border-radius: var(--v-radius-full);
  color: color-mix(in srgb, var(--v-warning, #d4a548) 86%, var(--v-text));
  background: color-mix(in srgb, var(--v-warning, #d4a548) 12%, transparent);
}

.scrub-preview-comment__annotation .icon {
  width: 10px;
  height: 10px;
}

.scrub-preview-comment__text {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  color: var(--v-text);
  font-size: var(--v-text-sm);
  font-weight: 500;
  line-height: 1.38;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

@keyframes scrub-preview-sheen {
  to {
    transform: translateX(65%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .scrub-preview-popover,
  .scrub-preview-video,
  .frame-copy-btn__spinner {
    transition-duration: 0.01ms;
    animation: none;
  }

  .scrub-preview-popover.is-loading .scrub-preview-frame::before {
    animation: none;
    opacity: 0.35;
    transform: none;
  }
}

.comment-marker {
  position: absolute;
  top: 50%;
  width: 6px;
  height: 14px;
  background: var(--v-annotation);
  border-radius: var(--v-radius-full);
  transform: translate(-50%, -50%);
  z-index: 2;
  cursor: pointer;
  transition:
    width var(--v-duration-fast) var(--v-ease-emphasized),
    height var(--v-duration-fast) var(--v-ease-emphasized),
    border-radius var(--v-duration-fast) var(--v-ease-emphasized),
    box-shadow var(--v-duration-fast) var(--v-ease-emphasized),
    background var(--v-duration-fast) var(--v-ease-emphasized),
    transform var(--v-duration-fast) var(--v-ease-emphasized),
    opacity var(--v-duration-fast) var(--v-ease-emphasized);
}

.comment-marker::before {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--v-bg-base) 78%, white);
  opacity: 0;
  transform: translate(-50%, -50%) scale(0.45);
  transition:
    opacity var(--v-duration-fast) var(--v-ease-emphasized),
    transform var(--v-duration-fast) var(--v-ease-emphasized);
}

.comment-marker:hover,
.comment-marker:focus-visible,
.comment-marker.has-annotation:hover,
.comment-marker.has-annotation:focus-visible {
  width: 18px;
  height: 18px;
  outline: none;
  border-radius: 50%;
  background: color-mix(in srgb, var(--v-annotation) 88%, white);
  box-shadow:
    0 0 0 4px color-mix(in srgb, var(--v-annotation) 24%, transparent),
    0 8px 18px rgba(0, 0, 0, 0.28);
  transform: translate(-50%, -50%) scale(1);
}

.comment-marker:hover::before,
.comment-marker:focus-visible::before {
  opacity: 0.86;
  transform: translate(-50%, -50%) scale(1);
}

.comment-marker.resolved {
  background: var(--v-status-done-text);
  opacity: 0.5;
}

.comment-marker.has-annotation {
  width: 8px;
}

.controls-row {
  padding: 0;
}

.controls-bar {
  --viewer-control-size: 32px;
  --viewer-control-glyph: 15px;
  --viewer-control-gap: 6px;
  --viewer-control-height: 32px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  height: var(--viewer-control-height);
  min-height: var(--viewer-control-height);
  gap: 14px;
  border: 0;
  background: transparent;
  line-height: 1;
  overflow: visible;
  box-shadow: none;
}

.controls-zone {
  display: flex;
  align-items: center;
  min-width: 0;
  height: var(--viewer-control-height);
  min-height: var(--viewer-control-height);
}

.controls-zone--left {
  justify-content: flex-start;
  gap: var(--viewer-control-gap);
}

.controls-zone--center {
  justify-content: center;
}

.controls-zone--right {
  justify-content: flex-end;
  gap: var(--viewer-control-gap);
}

.controls-timecode {
  display: flex;
  align-items: center;
  height: var(--viewer-control-height);
  min-height: var(--viewer-control-height);
  gap: 7px;
  padding: 0 11px;
  border: 1px solid color-mix(in srgb, var(--v-text) 10%, transparent);
  border-radius: var(--v-button-radius);
  background: color-mix(in srgb, var(--v-text) 4%, transparent);
  font-family: var(--v-font);
  font-size: var(--v-text-sm);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
  color: var(--v-text-muted);
  line-height: 1;
  white-space: nowrap;
  overflow: hidden;
  box-shadow: 0 1px 0 color-mix(in srgb, white 3%, transparent) inset;
}

.time-current,
.time-duration,
.time-sep {
  display: inline-flex;
  align-items: center;
  line-height: 1;
}

.time-current,
.time-duration {
  color: var(--v-text-secondary);
}

.time-current {
  font-weight: 500;
  color: var(--v-text);
}

.time-sep {
  opacity: 0.45;
  margin: 0 1px;
}

.frame-counter {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: var(--v-space-1);
  margin-left: 2px;
  line-height: 1;
}

.frame-counter__prefix {
  font-size: var(--v-text-2xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  line-height: 1;
  color: var(--v-text-muted);
}

.frame-counter__value {
  font-size: var(--v-text-xs);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1;
  color: var(--v-text);
  min-width: 1.25em;
  text-align: left;
}

.control-btn {
  position: relative;
  min-width: var(--viewer-control-size, var(--v-icon-btn-size));
  width: var(--viewer-control-size, var(--v-icon-btn-size));
  min-height: var(--viewer-control-size, var(--v-icon-btn-size));
  height: var(--viewer-control-size, var(--v-icon-btn-size));
  flex: 0 0 var(--viewer-control-size, var(--v-icon-btn-size));
  padding: 0;
  border: none;
  border-radius: var(--v-button-radius);
  overflow: hidden;
  color: var(--v-text-muted);
  line-height: 1;
  transition:
    background var(--v-transition-fast),
    color var(--v-transition-fast),
    box-shadow var(--v-transition-fast);
}

.control-btn:hover {
  background: var(--v-bg-hover);
  color: var(--v-text);
}

.control-btn .icon {
  width: var(--viewer-control-glyph, var(--v-icon-btn-glyph));
  height: var(--viewer-control-glyph, var(--v-icon-btn-glyph));
}

.control-btn--play {
  color: var(--v-text);
  -webkit-tap-highlight-color: transparent;
}

.control-btn--play:hover {
  background: var(--v-bg-hover);
  color: var(--v-text);
}

.control-btn--play:focus:not(:focus-visible) {
  outline: none;
}

/* Stacked play / pause with crossfade + scale (no abrupt symbol swap) */
.play-pause-morph {
  display: grid;
  place-items: center;
  width: var(--viewer-control-glyph);
  height: var(--viewer-control-glyph);
}

.play-pause-morph__glyph {
  grid-area: 1 / 1;
  width: var(--viewer-control-glyph);
  height: var(--viewer-control-glyph);
  transition:
    opacity var(--v-duration-normal) var(--v-ease-emphasized),
    transform var(--v-duration-normal) var(--v-ease-emphasized);
}

.play-pause-morph__glyph--play {
  opacity: 1;
  transform: scale(1);
}

.play-pause-morph__glyph--pause {
  opacity: 0;
  transform: scale(0.88);
}

.play-pause-morph.is-playing .play-pause-morph__glyph--play {
  opacity: 0;
  transform: scale(0.88);
}

.play-pause-morph.is-playing .play-pause-morph__glyph--pause {
  opacity: 1;
  transform: scale(1);
}

@media (prefers-reduced-motion: reduce) {
  .play-pause-morph__glyph {
    transition-duration: 0.01ms;
  }
}

.viewer-quality-trigger,
.viewer-color-preview-trigger {
  min-width: var(--viewer-control-size);
  width: var(--viewer-control-size);
  min-height: var(--viewer-control-height);
  height: var(--viewer-control-height);
  padding: 0;
}

.viewer-quality-trigger.active,
.viewer-color-preview-trigger.active {
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 11%, transparent);
}

@media (min-width: 769px) {
  .v-dropdown.viewer-settings-menu:not(.is-teleported),
  .v-menu-panel.viewer-settings-menu:not(.is-teleported) {
    top: auto !important;
    right: 0;
    bottom: calc(100% + 8px) !important;
    margin-top: 0 !important;
    margin-bottom: var(--v-space-1);
    max-height: min(280px, calc(100vh - 180px));
    overflow-y: auto;
  }
}

.v-dropdown.viewer-frame-capture-menu:not(.is-teleported),
.v-menu-panel.viewer-frame-capture-menu:not(.is-teleported) {
  top: auto !important;
  right: 0;
  bottom: calc(100% + 8px) !important;
  margin-top: 0 !important;
  margin-bottom: var(--v-space-1);
  max-height: min(320px, calc(100vh - 180px));
  overflow-y: auto;
}

.viewer-settings-menu {
  padding: 6px;
}

.viewer-color-preview-menu {
  max-height: min(70vh, 440px);
  padding: 7px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.viewer-color-preview-panel {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.viewer-color-preview-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
  padding: 3px 9px 6px;
}

.viewer-color-preview-heading > span:last-child {
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
}

.viewer-color-preview-option {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) 16px;
  min-height: 48px;
  padding: 6px 9px;
  gap: 9px;
  border-radius: var(--v-button-radius);
}

.viewer-color-preview-option.active {
  background: color-mix(in srgb, var(--v-accent) 8%, var(--v-bg-hover));
}

.viewer-color-preview-option__mark {
  width: 16px;
  height: 16px;
  align-self: center;
  border: 1px solid color-mix(in srgb, currentColor 22%, transparent);
  border-radius: var(--v-radius-full);
  background: linear-gradient(
    90deg,
    color-mix(in srgb, currentColor 28%, transparent) 0 33%,
    color-mix(in srgb, currentColor 54%, transparent) 33% 66%,
    color-mix(in srgb, currentColor 82%, transparent) 66% 100%
  );
}

.viewer-color-preview-option.active .viewer-color-preview-option__mark {
  color: var(--v-accent);
  border-color: color-mix(in srgb, var(--v-accent) 44%, transparent);
}

.viewer-color-preview-option__copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  text-align: left;
}

.viewer-color-preview-option__label {
  color: var(--v-text);
  font-size: var(--v-text-sm);
  font-weight: 600;
  line-height: 1.2;
}

.viewer-color-preview-option__hint {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.2;
}

.viewer-color-preview-option__check {
  width: 14px;
  height: 14px;
  align-self: center;
  color: var(--v-accent);
}

.viewer-color-preview-note {
  margin: 5px 3px 0;
  padding: 9px 7px 3px;
  border-top: 1px solid var(--v-border);
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.35;
}

.viewer-settings-panel {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-1);
}

.viewer-settings-section {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.viewer-settings-heading {
  padding: 4px 10px 6px;
}

.viewer-settings-option {
  justify-content: space-between;
  gap: var(--v-space-3);
  border-radius: var(--v-button-radius);
}

.viewer-settings-option.active {
  background: var(--v-bg-hover);
}

.viewer-settings-option__label {
  font-variant-numeric: tabular-nums;
}

.viewer-settings-option__check {
  width: 14px;
  height: 14px;
  color: var(--v-text);
}

.volume-controls {
  display: flex;
  align-items: center;
  height: var(--viewer-control-height);
  min-height: var(--viewer-control-height);
  gap: 3px;
  flex-shrink: 0;
  padding: 0 9px 0 2px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--v-text) 8%, transparent);
  border-radius: var(--v-button-radius);
  background: color-mix(in srgb, var(--v-text) 3%, transparent);
  transition:
    border-color var(--v-transition-fast),
    background var(--v-transition-fast),
    box-shadow var(--v-transition-fast);
}

.volume-controls:hover,
.volume-controls:focus-within,
.volume-controls.is-dragging {
  border-color: color-mix(in srgb, var(--v-text) 14%, transparent);
  background: color-mix(in srgb, var(--v-text) 5%, transparent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--v-accent) 10%, transparent) inset;
}

.volume-controls .control-btn {
  width: 28px;
  min-width: 28px;
  height: 100%;
  min-height: 0;
  flex: 0 0 28px;
  border-radius: 0;
}

.volume-controls .control-btn:hover:not(:disabled) {
  background: transparent;
}

.loop-btn.active {
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 11%, transparent);
}

.loop-btn.active:hover {
  background: var(--v-bg-hover);
}

.frame-copy-control {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.frame-capture-split {
  display: inline-flex;
  align-items: center;
  height: var(--viewer-control-height);
  min-height: var(--viewer-control-height);
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--v-text) 10%, transparent);
  border-radius: var(--v-button-radius);
  background: color-mix(in srgb, var(--v-text) 4%, transparent);
  transition:
    border-color var(--v-transition-fast),
    background var(--v-transition-fast);
}

.frame-capture-split:hover,
.frame-capture-split.is-open {
  border-color: color-mix(in srgb, var(--v-text) 16%, transparent);
}

.frame-capture-split .frame-capture-primary {
  width: 34px;
  min-width: 34px;
  flex: 0 0 34px;
  height: 100%;
  min-height: 0;
  padding: 0;
  border-radius: 0;
  color: var(--v-text);
}

.frame-capture-split .frame-capture-primary:hover:not(:disabled) {
  background: color-mix(in srgb, var(--v-text) 6%, transparent);
  color: var(--v-text);
}

.frame-capture-split .frame-capture-menu-btn {
  width: 28px;
  min-width: 28px;
  flex: 0 0 28px;
  height: 100%;
  min-height: 0;
  border-left: 1px solid color-mix(in srgb, var(--v-text) 9%, transparent);
  border-radius: 0;
}

.frame-capture-split .frame-capture-menu-btn:hover:not(:disabled),
.frame-capture-split .frame-capture-menu-btn.active {
  background: color-mix(in srgb, var(--v-text) 6%, transparent);
  color: var(--v-text);
}

.frame-capture-menu-btn__icon {
  width: 13px;
  height: 13px;
  transition: transform var(--v-transition-fast);
}

.frame-capture-menu-btn.active .frame-capture-menu-btn__icon {
  transform: rotate(180deg);
}

.viewer-frame-capture-menu {
  padding: 5px;
}

.viewer-frame-capture-panel {
  --frame-capture-menu-leading: 38px;
  --frame-capture-menu-gap: 9px;
  --frame-capture-menu-pad-x: 9px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.viewer-frame-capture-panel .viewer-frame-capture-option {
  display: grid;
  grid-template-columns: var(--frame-capture-menu-leading) minmax(0, 1fr);
  min-height: 42px;
  align-items: center;
  column-gap: var(--frame-capture-menu-gap);
  padding: 6px var(--frame-capture-menu-pad-x);
  border-radius: var(--v-button-radius);
  gap: var(--frame-capture-menu-gap);
}

.viewer-frame-capture-panel .viewer-frame-capture-option:disabled {
  cursor: default;
  opacity: 0.52;
}

.viewer-frame-capture-panel .viewer-frame-capture-option .icon {
  justify-self: center;
  width: 15px;
  height: 15px;
  color: var(--v-text-muted);
}

.viewer-frame-capture-option__copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 1px;
}

.viewer-frame-capture-option__label {
  color: var(--v-text);
  font-size: var(--v-text-sm);
  font-weight: 700;
  line-height: 1.1;
}

.viewer-frame-capture-option__hint {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 500;
  line-height: 1.16;
}

.viewer-frame-capture-panel .viewer-frame-capture-switch {
  display: grid;
  grid-template-columns: var(--frame-capture-menu-leading) minmax(0, 1fr);
  align-items: center;
  column-gap: var(--frame-capture-menu-gap);
  width: 100%;
  min-height: 50px;
  padding: 7px var(--frame-capture-menu-pad-x) 8px;
  border-radius: var(--v-button-radius);
  gap: var(--frame-capture-menu-gap);
}

.viewer-frame-capture-panel .viewer-frame-capture-switch:hover {
  background: var(--v-bg-hover);
}

.viewer-frame-capture-panel .viewer-frame-capture-switch .v-switch-label {
  font-size: var(--v-text-sm);
  line-height: 1.1;
}

.viewer-frame-capture-panel .viewer-frame-capture-switch .v-switch-track {
  justify-self: center;
  margin-top: 0;
}

.viewer-frame-capture-panel .viewer-frame-capture-switch .v-switch-copy {
  min-width: 0;
  gap: 2px;
}

.viewer-frame-capture-panel .viewer-frame-capture-switch .v-switch-hint {
  line-height: 1.18;
}

.frame-copy-btn.is-busy {
  color: var(--v-text);
}

.frame-copy-btn.is-success {
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 12%, transparent);
}

.frame-copy-btn.is-error {
  color: var(--v-danger);
  background: color-mix(in srgb, var(--v-danger) 10%, transparent);
}

.frame-copy-btn:disabled {
  cursor: default;
  opacity: 0.62;
}

.frame-copy-btn__spinner {
  animation: frame-copy-spin 0.8s linear infinite;
}

.frame-copy-feedback {
  position: absolute;
  right: 0;
  bottom: calc(100% + 8px);
  z-index: 18;
  width: max-content;
  max-width: 240px;
  padding: 5px 8px;
  border: 1px solid color-mix(in srgb, var(--v-accent) 18%, transparent);
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-bg-base) 90%, transparent);
  color: var(--v-text);
  font-size: var(--v-text-xs);
  font-weight: 700;
  line-height: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  box-shadow: 0 12px 26px rgba(0, 0, 0, 0.28);
  pointer-events: none;
  white-space: nowrap;
}

.frame-copy-feedback.is-error {
  border-color: color-mix(in srgb, var(--v-danger) 22%, transparent);
  color: var(--v-danger);
}

@keyframes frame-copy-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .frame-copy-btn__spinner {
    animation: none;
  }
}

.volume-slider {
  --vol-pct: 80%;
  width: 86px;
  height: 24px;
  margin: 0;
  padding: 0;
  flex: 0 0 86px;
  cursor: pointer;
  accent-color: var(--v-accent);
  border-radius: var(--v-radius-full);
  background: transparent;
  -webkit-appearance: none;
  appearance: none;
  touch-action: none;
  transition:
    opacity var(--v-duration-fast) var(--v-ease-emphasized);
}

.volume-slider:focus,
.volume-slider:focus-visible {
  outline: none;
}

.volume-slider::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: var(--v-radius-full);
  background: linear-gradient(
    to right,
    var(--v-accent) 0 var(--vol-pct),
    var(--v-surface-inline-strong) var(--vol-pct) 100%
  );
  transition: background var(--v-duration-fast) var(--v-ease-emphasized);
}

.volume-slider::-moz-range-track {
  height: 4px;
  border-radius: var(--v-radius-full);
  background: var(--v-surface-inline-strong);
  transition: background var(--v-duration-fast) var(--v-ease-emphasized);
}

.volume-slider::-moz-range-progress {
  height: 4px;
  border-radius: var(--v-radius-full);
  background: var(--v-accent);
  transition: background var(--v-duration-fast) var(--v-ease-emphasized);
}

.volume-slider::-webkit-slider-thumb {
  width: 13px;
  height: 13px;
  border: 1px solid color-mix(in srgb, var(--v-text) 97%, white);
  border-radius: 50%;
  background: var(--v-text);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-bg-base) 80%, transparent);
  transition:
    transform var(--v-duration-fast) var(--v-ease-emphasized),
    box-shadow var(--v-duration-fast) var(--v-ease-emphasized),
    background var(--v-duration-fast) var(--v-ease-emphasized);
}

.volume-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  margin-top: -4.5px;
}

.volume-slider::-moz-range-thumb {
  width: 13px;
  height: 13px;
  border: 1px solid color-mix(in srgb, var(--v-text) 97%, white);
  border-radius: 50%;
  background: var(--v-text);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-bg-base) 80%, transparent);
  transition:
    transform var(--v-duration-fast) var(--v-ease-emphasized),
    box-shadow var(--v-duration-fast) var(--v-ease-emphasized),
    background var(--v-duration-fast) var(--v-ease-emphasized);
}

.volume-controls:hover .volume-slider::-webkit-slider-thumb,
.volume-slider:focus-visible::-webkit-slider-thumb,
.volume-slider:active::-webkit-slider-thumb,
.volume-slider.is-dragging::-webkit-slider-thumb {
  background: var(--v-text);
  box-shadow:
    0 0 0 2px color-mix(in srgb, var(--v-bg-base) 82%, transparent),
    0 0 0 4px color-mix(in srgb, var(--v-accent) 18%, transparent);
}

.volume-controls:hover .volume-slider::-moz-range-thumb,
.volume-slider:focus-visible::-moz-range-thumb,
.volume-slider:active::-moz-range-thumb,
.volume-slider.is-dragging::-moz-range-thumb {
  background: var(--v-text);
  box-shadow:
    0 0 0 2px color-mix(in srgb, var(--v-bg-base) 82%, transparent),
    0 0 0 4px color-mix(in srgb, var(--v-accent) 18%, transparent);
}

@media (max-width: 768px) {
  .media-viewer-toolbar {
    padding: 8px var(--v-viewer-mobile-content-gutter) 8px;
    background: var(--v-bg-black);
  }

  .timeline-row {
    padding: 0 0 6px;
  }

  .timeline {
    height: 24px;
  }

  .timeline-bg,
  .timeline-progress {
    height: 4px;
  }

  .timeline-handle {
    width: 12px;
    height: 12px;
    opacity: 1;
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--v-accent) 20%, transparent);
  }

  .scrub-preview-popover {
    --scrub-preview-width: 156px;
    bottom: calc(100% + 10px);
  }

  .scrub-preview-popover.has-comment {
    --scrub-preview-width: 236px;
  }

  .scrub-preview-time {
    min-width: 76px;
    margin-top: 6px;
    padding: 3px 7px;
    font-size: var(--v-text-xs);
  }

  .scrub-preview-comment {
    margin-top: 6px;
    padding: 9px 10px 10px;
  }

  .scrub-preview-comment__author,
  .scrub-preview-comment__text {
    font-size: var(--v-text-xs);
  }

  .comment-marker {
    width: 6px;
    height: 14px;
  }

  .controls-bar {
    --viewer-control-size: 44px;
    --viewer-control-glyph: 17px;
    --viewer-control-gap: 0px;
    --viewer-control-height: 44px;
    grid-template-columns: auto minmax(0, 1fr) auto;
    height: var(--viewer-control-height);
    min-height: var(--viewer-control-height);
    gap: 3px;
    border: 0;
    border-radius: 0;
    background: transparent;
    overflow: visible;
  }

  .controls-zone--left {
    gap: var(--viewer-control-gap);
    padding: 0;
  }

  .controls-zone--center {
    min-width: 0;
    justify-content: center;
    padding: 0;
  }

  .controls-zone--right {
    gap: var(--viewer-control-gap);
  }

  .controls-timecode {
    min-width: 0;
    height: var(--viewer-control-height);
    min-height: var(--viewer-control-height);
    gap: 4px;
    padding: 0 5px;
    font-size: var(--v-text-sm);
    border-color: transparent;
    background: transparent;
    box-shadow: none;
  }

  .frame-counter {
    display: none;
  }

  .frame-counter__prefix,
  .frame-counter__value {
    font-size: var(--v-text-2xs);
  }

  .control-btn--play {
    width: var(--viewer-control-size);
    height: var(--viewer-control-size);
    flex: 0 0 var(--viewer-control-size);
    border-radius: var(--v-button-radius);
    background: var(--v-surface-tint);
    border: 0;
    color: var(--v-text);
  }

  .control-btn--play .icon,
  .control-btn--play .play-pause-morph,
  .control-btn--play .play-pause-morph__glyph {
    width: 18px;
    height: 18px;
  }

  .control-btn--icon {
    width: var(--viewer-control-size);
    height: var(--viewer-control-size);
    flex: 0 0 var(--viewer-control-size);
    border-radius: var(--v-button-radius);
    background: transparent;
  }

  .control-btn--icon .icon {
    width: var(--viewer-control-glyph);
    height: var(--viewer-control-glyph);
  }

  .frame-capture-split {
    width: var(--viewer-control-size);
    height: var(--viewer-control-height);
    border: 0;
    border-radius: var(--v-button-radius);
    background: transparent;
  }

  .frame-capture-split .frame-capture-primary {
    display: none;
  }

  .frame-capture-split .frame-capture-menu-btn {
    width: var(--viewer-control-size);
    min-width: var(--viewer-control-size);
    height: 100%;
    flex: 0 0 var(--viewer-control-size);
    border-left: 0;
  }

  .frame-capture-menu-btn__icon {
    display: none;
  }

  .viewer-mobile-capture-icon,
  .viewer-mobile-only {
    display: flex !important;
  }

  .loop-btn {
    display: none;
  }

  .volume-controls {
    display: flex;
    height: var(--viewer-control-height);
    min-height: var(--viewer-control-height);
    gap: 0;
    padding: 0;
    border: 0;
    background: transparent;
    margin-right: 0;
  }

  .volume-controls .control-btn {
    width: var(--viewer-control-size);
    height: var(--viewer-control-size);
    flex: 0 0 var(--viewer-control-size);
  }

  .volume-slider {
    display: none;
  }

  .frame-copy-feedback {
    right: 50%;
    transform: translateX(50%);
  }

  .viewer-settings-heading {
    padding: 4px 8px 6px;
    font-size: 8px;
  }

  .control-btn:hover,
  .control-btn--play:hover,
  .control-btn--icon:hover {
    background: var(--v-bg-hover);
  }

  .control-btn--icon {
    color: var(--v-text-secondary);
  }

  .control-btn--icon.loop-btn.active {
    color: var(--v-accent);
    background: transparent;
  }
}

@media (max-width: 390px) {
  .media-viewer-toolbar {
    padding-inline: var(--v-space-2);
  }

  .controls-bar {
    gap: 3px;
  }

  .controls-timecode {
    gap: 3px;
    padding: 0 2px;
    font-size: var(--v-text-xs);
  }
}
</style>
