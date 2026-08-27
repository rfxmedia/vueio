<template>
  <div
    class="player-main"
    :class="[playerMainClass, { 'is-stream-preparing': isViewingVideo && showStreamPreparingOverlay }]"
  >
    <div v-if="isViewingVideo && showStreamPreparingOverlay" class="stream-overlay">
      <div class="stream-box">
        <div class="progress-ring"><svg viewBox="0 0 100 100"><circle class="bg" cx="50" cy="50" r="45"/><circle class="fg" cx="50" cy="50" r="45" :style="`stroke-dashoffset: ${283 - (283 * streamProgress / 100)}`"/></svg><span class="progress-text">{{ Math.round(streamProgress) }}%</span></div>
        <h3>Preparing stream...</h3><p>This version is being packaged for adaptive playback and cached for future views.</p>
      </div>
    </div>

    <div v-else class="video-container" :ref="setVideoContainerRef" @click="handleVideoContainerClick">
      <div v-if="mediaUnavailable" class="media-unavailable" role="status">
        <svg class="icon"><use href="#icon-file" /></svg>
        <h3>Version unavailable</h3>
        <p>The source file was deleted or replaced. Its tracker notes and comments remain available.</p>
      </div>
      <MediaPdfViewer
        v-else-if="isViewingPdf"
        :source-url="mediaStreamUrl"
        :file-name="currentMedia?.name || currentMedia?.path?.split('/').pop() || ''"
        :comments="comments"
        :is-drawing-mode="isDrawingMode"
        :focus-request="pdfFocusRequest"
        :start-pointer-drawing="startPointerDrawing"
        :move-pointer-drawing="movePointerDrawing"
        :finish-pointer-drawing="finishPointerDrawing"
        :on-activate-annotation-canvas="onActivateAnnotationCanvas"
        :on-annotation-target-change="onPdfAnnotationTargetChange"
        :on-loaded="onPdfLoaded"
        :on-download="onDownloadCurrentMedia"
        :on-comment-select="onPdfCommentSelect"
      />
      <div
        v-else-if="isViewingImage"
        ref="imageShellRef"
        class="viewer-image-shell"
        :class="imageShellClass"
        @wheel.stop="handleImageWheel"
        @mousedown.stop="handleImagePointerDown"
        @dblclick.stop="handleImageDoubleClick"
        @gesturestart.prevent="handleImageGestureStart"
        @gesturechange.prevent="handleImageGestureChange"
        @gestureend.prevent="handleImageGestureEnd"
      >
        <div
          :ref="setImageStageElement"
          class="viewer-image-stage"
          :style="imageStageStyle"
        >
          <img
            :src="mediaStreamUrl"
            :alt="currentMedia?.name || ''"
            class="viewer-image"
            draggable="false"
            @dragstart.prevent
            @load="handleImageLoad"
          />

          <canvas
            :ref="setAnnotationCanvasRef"
            class="annotation-canvas"
            :class="{ 'drawing-mode': isDrawingMode }"
            @pointerdown="startPointerDrawing"
            @pointermove="movePointerDrawing"
            @pointerup="finishPointerDrawing"
            @pointercancel="finishPointerDrawing"
          ></canvas>

          <canvas
            :ref="setPreviewCanvasRef"
            class="annotation-preview-canvas"
            :class="{ visible: showAnnotationPreview }"
          ></canvas>
        </div>
      </div>
      <template v-else>
        <video :ref="setVideoElRef" :muted="playerMuted" :loop="nativeVideoLoop" :poster="videoPosterUrl || undefined" @timeupdate="onTimeUpdate" @loadedmetadata="onLoaded" @canplay="onVideoCanPlay" @ended="onVideoEnded" @play="onVideoPlay" @pause="onVideoPause" @seeked="onVideoSeeked" playsinline webkit-playsinline preload="metadata"></video>

        <canvas
          :ref="setAnnotationCanvasRef"
          class="annotation-canvas"
          :class="{ 'drawing-mode': isDrawingMode }"
          @pointerdown="startPointerDrawing"
          @pointermove="movePointerDrawing"
          @pointerup="finishPointerDrawing"
          @pointercancel="finishPointerDrawing"
        ></canvas>

        <canvas
          :ref="setPreviewCanvasRef"
          class="annotation-preview-canvas"
          :class="{ visible: showAnnotationPreview }"
        ></canvas>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from 'vue'
import { clamp } from '../../utils/math'

const MediaPdfViewer = defineAsyncComponent(() => import('./MediaPdfViewer.vue'))

const props = defineProps({
  playerMainClass: { type: [String, Array, Object], default: '' },
  isViewingImage: { type: Boolean, default: false },
  isViewingPdf: { type: Boolean, default: false },
  isViewingVideo: { type: Boolean, default: false },
  enableImageDesktopNavigation: { type: Boolean, default: false },
  streamPreparing: { type: Boolean, default: false },
  showStreamPreparingOverlay: { type: Boolean, default: false },
  streamProgress: { type: Number, default: 0 },
  mediaStreamUrl: { type: String, default: '' },
  videoPosterUrl: { type: String, default: '' },
  mediaUnavailable: { type: Boolean, default: false },
  currentMedia: { type: Object, default: null },
  comments: { type: Array, default: () => [] },
  playerMuted: { type: Boolean, default: false },
  nativeVideoLoop: { type: Boolean, default: false },
  isDrawingMode: { type: Boolean, default: false },
  showAnnotationPreview: { type: Boolean, default: false },
  pdfFocusRequest: { type: Object, default: null },
  onPdfLoaded: { type: Function, default: null },
  onPdfAnnotationTargetChange: { type: Function, default: null },
  onActivateAnnotationCanvas: { type: Function, default: null },
  onDownloadCurrentMedia: { type: Function, default: null },
  onPdfCommentSelect: { type: Function, default: null },
  handleVideoContainerClick: { type: Function, required: true },
  onImageLoaded: { type: Function, required: true },
  onTimeUpdate: { type: Function, required: true },
  onLoaded: { type: Function, required: true },
  onVideoCanPlay: { type: Function, required: true },
  onVideoEnded: { type: Function, required: true },
  onVideoPlay: { type: Function, required: true },
  onVideoPause: { type: Function, required: true },
  onVideoSeeked: { type: Function, required: true },
  startPointerDrawing: { type: Function, required: true },
  movePointerDrawing: { type: Function, required: true },
  finishPointerDrawing: { type: Function, required: true },
  setVideoContainerRef: { type: Function, required: true },
  setVideoElRef: { type: Function, required: true },
  setImageStageRef: { type: Function, required: true },
  setAnnotationCanvasRef: { type: Function, required: true },
  setPreviewCanvasRef: { type: Function, required: true }
})

const imageShellRef = ref(null)
const imageStageRef = ref(null)
const imageScale = ref(1)
const imagePanX = ref(0)
const imagePanY = ref(0)
const isImageDragging = ref(false)

let dragStartX = 0
let dragStartY = 0
let dragOriginX = 0
let dragOriginY = 0
let gestureScaleOrigin = 1
let dragBounds = null
let pendingDragPoint = null
let imageDragFrame = 0
let imageResizeFrame = 0

const canUseImageDesktopNavigation = computed(() => (
  props.enableImageDesktopNavigation &&
  props.isViewingImage
))

const imageShellClass = computed(() => ({
  'is-interactive': canUseImageDesktopNavigation.value,
  'is-zoomed': imageScale.value > 1.001,
  'is-dragging': isImageDragging.value,
  'is-drawing': props.isDrawingMode,
}))

const imageStageStyle = computed(() => ({
  transform: `translate3d(${imagePanX.value}px, ${imagePanY.value}px, 0) scale(${imageScale.value})`,
}))

function setImageStageElement(el) {
  imageStageRef.value = el
  props.setImageStageRef(el)
}

function resetImageTransform() {
  imageScale.value = 1
  imagePanX.value = 0
  imagePanY.value = 0
  stopImageDrag()
}

function readImagePanBounds() {
  const shell = imageShellRef.value
  const stage = imageStageRef.value
  if (!shell || !stage) return null
  return {
    shellWidth: Number(shell.clientWidth || 0),
    shellHeight: Number(shell.clientHeight || 0),
    stageWidth: Number(stage.offsetWidth || 0),
    stageHeight: Number(stage.offsetHeight || 0),
  }
}

function clampImagePan(nextX, nextY, nextScale = imageScale.value, bounds = null) {
  if (nextScale <= 1.001) return { x: 0, y: 0 }

  const {
    shellWidth = 0,
    shellHeight = 0,
    stageWidth = 0,
    stageHeight = 0,
  } = bounds || readImagePanBounds() || {}
  if (!shellWidth || !shellHeight || !stageWidth || !stageHeight) {
    return { x: nextX, y: nextY }
  }

  const maxPanX = Math.max(0, ((stageWidth * nextScale) - shellWidth) / 2)
  const maxPanY = Math.max(0, ((stageHeight * nextScale) - shellHeight) / 2)

  return {
    x: clamp(nextX, -maxPanX, maxPanX),
    y: clamp(nextY, -maxPanY, maxPanY),
  }
}

function applyImagePan(nextX, nextY, nextScale = imageScale.value, bounds = null) {
  const clamped = clampImagePan(nextX, nextY, nextScale, bounds)
  imagePanX.value = clamped.x
  imagePanY.value = clamped.y
}

function getImageFocusPoint(clientX, clientY) {
  const shell = imageShellRef.value
  if (!shell) return null
  const rect = shell.getBoundingClientRect()
  return {
    x: clientX - (rect.left + rect.width / 2),
    y: clientY - (rect.top + rect.height / 2),
  }
}

function setImageScaleAtPoint(nextScale, clientX, clientY) {
  const clampedScale = clamp(nextScale, 1, 6)
  const focusPoint = getImageFocusPoint(clientX, clientY)
  if (!focusPoint) {
    imageScale.value = clampedScale
    applyImagePan(imagePanX.value, imagePanY.value, clampedScale)
    return
  }

  const previousScale = imageScale.value
  const localX = (focusPoint.x - imagePanX.value) / previousScale
  const localY = (focusPoint.y - imagePanY.value) / previousScale
  const nextPanX = focusPoint.x - (localX * clampedScale)
  const nextPanY = focusPoint.y - (localY * clampedScale)

  imageScale.value = clampedScale
  applyImagePan(nextPanX, nextPanY, clampedScale)
}

function isLikelyTrackpadPan(event) {
  return event.deltaMode === 0 && Math.abs(event.deltaX) < 48 && Math.abs(event.deltaY) < 48
}

function handleImageWheel(event) {
  if (!canUseImageDesktopNavigation.value || props.isDrawingMode) return

  const modifierZoom = event.ctrlKey || event.metaKey
  const trackpadLike = isLikelyTrackpadPan(event)

  if (!modifierZoom && trackpadLike) {
    if (imageScale.value <= 1.001) return
    event.preventDefault()
    applyImagePan(imagePanX.value - event.deltaX, imagePanY.value - event.deltaY)
    return
  }

  event.preventDefault()
  const primaryDelta = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX
  const zoomFactor = Math.exp(-primaryDelta * 0.002)
  setImageScaleAtPoint(imageScale.value * zoomFactor, event.clientX, event.clientY)
}

function handleImageDoubleClick(event) {
  if (!canUseImageDesktopNavigation.value || props.isDrawingMode) return
  event.preventDefault()
  if (imageScale.value > 1.001) {
    resetImageTransform()
    return
  }
  setImageScaleAtPoint(2, event.clientX, event.clientY)
}

function handleImagePointerDown(event) {
  if (!canUseImageDesktopNavigation.value || props.isDrawingMode) return
  if (event.button !== 0 || imageScale.value <= 1.001) return

  event.preventDefault()
  isImageDragging.value = true
  dragStartX = event.clientX
  dragStartY = event.clientY
  dragOriginX = imagePanX.value
  dragOriginY = imagePanY.value
  dragBounds = readImagePanBounds()
  window.addEventListener('mousemove', handleWindowImageDrag)
  window.addEventListener('mouseup', stopImageDrag)
}

function handleWindowImageDrag(event) {
  if (!isImageDragging.value) return
  event.preventDefault()
  pendingDragPoint = { x: event.clientX, y: event.clientY }
  if (imageDragFrame) return
  imageDragFrame = window.requestAnimationFrame(flushImageDrag)
}

function flushImageDrag() {
  imageDragFrame = 0
  if (!pendingDragPoint) return
  const point = pendingDragPoint
  pendingDragPoint = null
  applyImagePan(
    dragOriginX + (point.x - dragStartX),
    dragOriginY + (point.y - dragStartY),
    imageScale.value,
    dragBounds,
  )
}

function stopImageDrag() {
  if (imageDragFrame) {
    window.cancelAnimationFrame(imageDragFrame)
    imageDragFrame = 0
  }
  flushImageDrag()
  dragBounds = null
  if (isImageDragging.value) {
    isImageDragging.value = false
  }
  window.removeEventListener('mousemove', handleWindowImageDrag)
  window.removeEventListener('mouseup', stopImageDrag)
}

function handleImageGestureStart(event) {
  if (!canUseImageDesktopNavigation.value || props.isDrawingMode) return
  event.preventDefault()
  gestureScaleOrigin = imageScale.value
}

function handleImageGestureChange(event) {
  if (!canUseImageDesktopNavigation.value || props.isDrawingMode) return
  event.preventDefault()
  const shell = imageShellRef.value
  if (!shell) return
  const rect = shell.getBoundingClientRect()
  const clientX = Number(event.clientX || rect.left + rect.width / 2)
  const clientY = Number(event.clientY || rect.top + rect.height / 2)
  setImageScaleAtPoint(gestureScaleOrigin * Number(event.scale || 1), clientX, clientY)
}

function handleImageGestureEnd() {
  gestureScaleOrigin = imageScale.value
}

function handleImageLoad(event) {
  resetImageTransform()
  props.onImageLoaded(event)
}

function clampImagePanToBounds() {
  applyImagePan(imagePanX.value, imagePanY.value, imageScale.value)
}

function scheduleImagePanClamp() {
  if (imageResizeFrame) return
  imageResizeFrame = window.requestAnimationFrame(() => {
    imageResizeFrame = 0
    dragBounds = isImageDragging.value ? readImagePanBounds() : null
    clampImagePanToBounds()
  })
}

watch(() => props.currentMedia?.path, () => {
  resetImageTransform()
})

watch(() => props.isViewingImage, (isViewingImage) => {
  if (!isViewingImage) {
    resetImageTransform()
  }
})

onMounted(() => {
  window.addEventListener('resize', scheduleImagePanClamp)
})

onUnmounted(() => {
  stopImageDrag()
  if (imageResizeFrame) window.cancelAnimationFrame(imageResizeFrame)
  window.removeEventListener('resize', scheduleImagePanClamp)
})
</script>

<style>
.viewer-image,
.viewer-pdf,
.video-container video {
  display: block;
  max-width: 100%;
  max-height: 100%;
  min-width: 0;
  min-height: 0;
}

.media-unavailable {
  width: min(440px, calc(100% - 32px));
  margin: auto;
  text-align: center;
  color: var(--v-text-muted);
}

.media-unavailable .icon {
  width: 32px;
  height: 32px;
  margin-bottom: var(--v-space-3);
}

.media-unavailable h3 {
  margin: 0 0 var(--v-space-2);
  color: var(--v-text);
  font-size: var(--v-text-lg);
}

.media-unavailable p {
  margin: 0;
  line-height: 1.5;
}

.viewer-image {
  object-fit: contain;
}

.viewer-image-shell {
  position: relative;
  flex: 1;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.viewer-image-shell.is-interactive {
  user-select: none;
}

.viewer-image-shell.is-interactive:not(.is-zoomed):not(.is-drawing) {
  cursor: zoom-in;
}

.viewer-image-shell.is-interactive.is-zoomed:not(.is-drawing) {
  cursor: grab;
}

.viewer-image-shell.is-interactive.is-dragging:not(.is-drawing) {
  cursor: grabbing;
}

.viewer-image-stage {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  max-width: 100%;
  max-height: 100%;
  transform-origin: center center;
  transition: transform var(--v-duration-fast) var(--v-ease-emphasized);
  will-change: transform;
}

.viewer-image-shell.is-dragging .viewer-image-stage {
  transition: none;
}

.viewer-pdf {
  width: 100%;
  height: 100%;
  border: none;
  background: white;
}

.player-main {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: var(--v-viewer-player-main-padding);
  overflow: hidden;
  background: transparent;
}

.video-container {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: var(--v-viewer-video-border-width) solid var(--v-border);
  border-radius: var(--v-viewer-video-radius);
  box-shadow: none;
  background: var(--v-bg-black);
}

.video-container video {
  width: 100%;
  height: 100%;
  background: transparent;
  object-fit: contain;
  -webkit-transform: translateZ(0);
  transform: translateZ(0);
  -webkit-backface-visibility: hidden;
  backface-visibility: hidden;
}

.stream-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--v-surface-overlay);
}

.stream-box {
  text-align: center;
}

.progress-ring {
  position: relative;
  width: 90px;
  height: 90px;
  margin: 0 auto 20px;
}

.progress-ring svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.progress-ring circle {
  fill: none;
  stroke-width: 6;
}

.progress-ring .bg {
  stroke: var(--v-border);
}

.progress-ring .fg {
  stroke: var(--v-accent);
  stroke-dasharray: 283;
  transition: stroke-dashoffset var(--v-duration-normal) var(--v-ease-emphasized);
}

.progress-text {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--v-text-2xl);
  font-weight: 600;
}

.v-attachment-lightbox {
  --v-attachment-lightbox-padding: clamp(18px, 4vw, 52px);

  position: fixed;
  inset: 0;
  z-index: 5000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--v-attachment-lightbox-padding);
  background: color-mix(in srgb, var(--v-bg-base) 90%, transparent);
}

.v-attachment-lightbox-panel {
  width: min(1040px, 100%);
  height: min(760px, calc(100vh - (var(--v-attachment-lightbox-padding) * 2)));
  max-width: calc(100vw - (var(--v-attachment-lightbox-padding) * 2));
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--v-border-hover);
  border-radius: var(--v-radius-xl);
  background: var(--v-surface-panel);
  box-shadow: var(--v-shadow-lg);
}

.v-attachment-lightbox-header {
  position: relative;
  z-index: 2;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
  min-height: 52px;
  padding: 10px 12px 10px 16px;
  border-bottom: 1px solid var(--v-border);
}

.v-attachment-lightbox-title {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--v-text);
  font-size: var(--v-text-sm);
  font-weight: 650;
}

.v-attachment-lightbox-title .icon {
  width: 16px;
  height: 16px;
  color: var(--v-accent);
}

.v-attachment-lightbox-body {
  position: relative;
  z-index: 1;
  min-height: 0;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--v-space-4);
  overflow: hidden;
  background: var(--v-bg-black);
}

.v-attachment-lightbox-media {
  display: block;
  width: auto;
  height: auto;
  max-width: 100%;
  max-height: 100%;
  min-width: 0;
  min-height: 0;
  object-fit: contain;
  border-radius: var(--v-radius-md);
}

video.v-attachment-lightbox-media {
  width: 100%;
  height: 100%;
}

.v-attachment-lightbox-fade-enter-active,
.v-attachment-lightbox-fade-leave-active {
  transition: opacity var(--v-duration-fast) var(--v-ease-emphasized);
}

.v-attachment-lightbox-fade-enter-from,
.v-attachment-lightbox-fade-leave-to {
  opacity: 0;
}

.annotation-canvas,
.annotation-preview-canvas {
  position: absolute;
  top: 50%;
  left: 50%;
  opacity: 0;
  pointer-events: none;
  transform: translate(-50%, -50%);
  transition: opacity var(--v-duration-fast) var(--v-ease-emphasized);
}

.annotation-canvas.drawing-mode {
  z-index: 10;
  opacity: 1;
  cursor: crosshair;
  pointer-events: auto;
  touch-action: none;
}

.annotation-preview-canvas.visible {
  opacity: 1;
}

.annotation-preview-canvas {
  z-index: 5;
}

</style>
