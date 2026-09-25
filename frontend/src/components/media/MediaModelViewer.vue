<template>
  <section ref="review" class="model-review" :class="{ 'is-fullscreen': fullscreen }" aria-label="3D model review">
    <div ref="stage" class="model-stage">
      <div ref="viewport" class="model-viewport" :class="{ 'is-framed': lockedAspect }" :style="viewportStyle">
        <canvas ref="canvas" class="model-canvas" tabindex="0" aria-label="3D model. Drag to orbit. Scroll to zoom. Use arrow keys to orbit, plus and minus to zoom, and F to fit. For animation, left and right step frames; hold Shift to orbit." @keydown="handleKey" @webglcontextlost.prevent="contextLost" @webglcontextrestored="contextRestored" />
        <canvas :ref="setAnnotationCanvasRef" class="annotation-canvas" :class="{ 'drawing-mode': isDrawingMode }" aria-label="Draw on this 3D view" @pointerdown="startPointerDrawing" @pointermove="movePointerDrawing" @pointerup="finishPointerDrawing" @pointercancel="finishPointerDrawing" />
        <canvas :ref="setPreviewCanvasRef" class="annotation-preview-canvas" :class="{ visible: showAnnotationPreview }" aria-hidden="true" />
      </div>
      <div v-if="error || !ready" class="model-message" role="status" aria-live="polite">
        <template v-if="error">
          <span class="model-message__icon is-error"><svg class="icon"><use href="#icon-alert" /></svg></span>
          <h3>Preview unavailable</h3>
          <p>{{ error }}</p>
          <button class="v-btn v-btn-secondary" type="button" @click="retry"><svg class="icon"><use href="#icon-refresh" /></svg><span>Try again</span></button>
        </template>
        <template v-else>
          <span class="model-message__icon"><svg class="icon"><use href="#icon-model" /></svg></span>
          <h3>{{ preparation ? 'Preparing 3D preview' : 'Opening model' }}</h3>
          <div class="model-progress" :class="{ 'is-indeterminate': progress == null }" role="progressbar" aria-label="Model loading progress" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="progress == null ? undefined : Math.round(progress)"><span :style="progress == null ? null : { width: `${progress}%` }" /></div>
          <p>{{ preparation ? 'The first frame opens when it is ready.' : 'Loading geometry and materials.' }}</p>
        </template>
      </div>
      <div v-if="ready" class="model-overlay">
        <div class="model-overlay__start">
          <button v-if="lockedAspect && !isDrawingMode" class="model-chip is-action" type="button" @click="leaveCommentView"><svg class="icon"><use href="#icon-undo" /></svg><span>Return to orbit</span></button>
          <span v-else-if="isDrawingMode" class="model-chip is-accent"><svg class="icon"><use href="#icon-lock" /></svg><span>View locked for drawing</span></span>
          <Transition name="model-fade"><span v-if="!interacted && !lockedAspect && !isDrawingMode" class="model-chip">{{ orbitHint }}</span></Transition>
        </div>
        <div class="model-overlay__end">
          <span v-if="preparation" class="model-chip" role="status"><svg class="icon model-spin"><use href="#icon-loader" /></svg><span>Preparing frames · {{ Math.round(progress || 0) }}%</span></span>
          <span v-if="warning" class="model-chip is-warning" role="status"><svg class="icon"><use href="#icon-alert" /></svg><span>{{ warning }}</span><button type="button" class="model-chip__dismiss" aria-label="Dismiss message" @click="warning = ''"><svg class="icon"><use href="#icon-close" /></svg></button></span>
        </div>
      </div>
      <span v-if="buffering && ready" class="model-chip model-buffering" role="status"><svg class="icon model-spin"><use href="#icon-loader" /></svg><span>Loading frame…</span></span>
    </div>

    <div v-if="!error" class="media-viewer-toolbar model-toolbar" :class="{ 'is-static': !animated }" :aria-busy="!ready">
      <div v-if="animated" class="timeline-row">
        <div class="model-timeline">
          <input class="model-scrubber" aria-label="Animation frame" :aria-valuetext="`${formatTimecodeWithFrames(frame / fps, fps)}, frame ${frame}`" type="range" min="0" :max="frameCount - 1" step="1" :value="frame" :style="{ '--progress': frame / Math.max(1, frameCount - 1) }" :disabled="!ready || isDrawingMode" @input="scrub" />
          <div class="model-comment-markers">
            <button v-for="comment in timedComments" :key="comment.id" type="button" class="comment-marker" :class="{ resolved: comment.resolved, 'has-annotation': comment.annotation_data }" :style="{ left: `${Math.min(100, Number(comment.timestamp) / (duration || 1) * 100)}%` }" :title="comment.text || 'Drawing annotation'" :aria-label="`Review comment at ${formatTimecodeWithFrames(comment.timestamp, fps)}`" :disabled="isDrawingMode" @click="focusComment(comment)" />
          </div>
        </div>
      </div>
      <div class="controls-bar" role="group" aria-label="3D view controls">
        <div class="controls-zone controls-zone--left">
          <template v-if="animated">
            <button type="button" class="v-btn v-btn-quiet v-btn-icon control-btn control-btn--play" :aria-label="playing ? 'Pause animation' : 'Play animation'" :disabled="!ready || isDrawingMode" @click="togglePlay">
              <span class="play-pause-morph" :class="{ 'is-playing': playing }" aria-hidden="true">
                <svg class="icon play-pause-morph__glyph play-pause-morph__glyph--play"><use href="#icon-play" /></svg>
                <svg class="icon play-pause-morph__glyph play-pause-morph__glyph--pause"><use href="#icon-pause" /></svg>
              </span>
            </button>
            <button type="button" class="v-btn v-btn-quiet v-btn-icon control-btn control-btn--icon model-step" aria-label="Previous frame" title="Previous frame (←)" :disabled="!ready || isDrawingMode || frame === 0" @click="step(-1)"><svg class="icon model-step__back"><use href="#icon-chevron-right" /></svg></button>
            <button type="button" class="v-btn v-btn-quiet v-btn-icon control-btn control-btn--icon model-step" aria-label="Next frame" title="Next frame (→)" :disabled="!ready || isDrawingMode || frame >= frameCount - 1" @click="step(1)"><svg class="icon"><use href="#icon-chevron-right" /></svg></button>
          </template>
          <span v-else-if="ready" class="model-stats">
            <span class="model-stats__format">{{ formatLabel }}</span>
            <span v-if="triangleLabel" class="model-stats__detail">{{ triangleLabel }}</span>
          </span>
        </div>
        <div class="controls-zone controls-zone--center">
          <div v-if="animated" class="controls-timecode">
            <span class="time-current">{{ formatTimecodeWithFrames(frame / fps, fps) }}</span>
            <span class="time-sep">/</span>
            <span class="time-duration">{{ formatTimecodeWithFrames(duration, fps) }}</span>
            <span class="frame-counter" title="Current frame">
              <span class="frame-counter__prefix">F</span>
              <span class="frame-counter__value">{{ frame }}</span>
            </span>
          </div>
        </div>
        <div class="controls-zone controls-zone--right">
          <VMenu v-if="clips.length > 1" :key="`clips-${fullscreen}`" v-model:open="clipMenuOpen" class="model-clip-menu" align="end" :min-width="200" :teleport="true" :teleport-to="menuTarget" panel-class="viewer-settings-menu" panel-label="Animation clip">
            <template #trigger="{ triggerProps }">
              <button type="button" class="v-btn v-btn-quiet control-btn control-btn--icon model-clip-trigger" :class="{ active: clipMenuOpen }" v-bind="triggerProps" :aria-label="`Animation clip: ${clipName}`" :title="clipName" :disabled="!ready || isDrawingMode" @click.stop="clipMenuOpen = !clipMenuOpen">
                <svg class="icon model-clip-trigger__icon"><use href="#icon-layout" /></svg>
                <span class="model-clip-trigger__label">{{ clipName }}</span>
                <svg class="icon model-clip-trigger__chevron"><use href="#icon-chevron-down" /></svg>
              </button>
            </template>
            <div class="viewer-settings-panel">
              <div class="viewer-settings-heading v-section-label">Animation</div>
              <button v-for="(clip, index) in clips" :key="index" type="button" class="v-dropdown-item viewer-settings-option" :class="{ active: index === clipIndex }" role="menuitemradio" :aria-checked="index === clipIndex ? 'true' : 'false'" @click="chooseClip(index)">
                <span class="viewer-settings-option__label model-clip-name">{{ clip.name || `Animation ${index + 1}` }}</span>
                <svg v-if="index === clipIndex" class="icon viewer-settings-option__check"><use href="#icon-check" /></svg>
              </button>
            </div>
          </VMenu>
          <VMenu :key="`lighting-${fullscreen}`" v-model:open="lightingOpen" align="end" :close-on-select="false" :teleport="true" :teleport-to="menuTarget" panel-role="dialog" panel-label="Lighting" panel-class="model-lighting-menu" :min-width="268">
            <template #trigger="{ triggerProps }">
              <button type="button" class="v-btn v-btn-quiet v-btn-icon control-btn control-btn--icon model-tool" :class="{ active: lightingOpen || !defaultLighting }" v-bind="triggerProps" aria-label="Lighting" title="Lighting" :disabled="!ready || isDrawingMode" @click.stop="lightingOpen = !lightingOpen">
                <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="2" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" /></svg>
              </button>
            </template>
            <div class="model-lighting">
              <div class="model-lighting__head">
                <span class="v-section-label">Lighting</span>
                <button type="button" class="model-lighting__reset" :disabled="defaultLighting" @click="resetLighting">Reset</button>
              </div>
              <div class="model-segmented" role="group" aria-label="Environment">
                <button v-for="option in lightingPresets" :key="option.value" type="button" class="model-segmented__option" :class="{ active: lighting.preset === option.value }" :aria-pressed="lighting.preset === option.value ? 'true' : 'false'" @click="lighting.preset = option.value; changeLighting()">{{ option.label }}</button>
              </div>
              <label class="model-slider">
                <span class="model-slider__label">Intensity<output>{{ lighting.intensity.toFixed(1) }}×</output></span>
                <input v-model.number="lighting.intensity" type="range" min="0" max="3" step="0.1" :style="{ '--progress': lighting.intensity / 3 }" @input="changeLighting" />
              </label>
              <label class="model-slider">
                <span class="model-slider__label">Rotation<output>{{ lighting.rotation }}°</output></span>
                <input v-model.number="lighting.rotation" type="range" min="0" max="360" step="1" :style="{ '--progress': lighting.rotation / 360 }" @input="changeLighting" />
              </label>
            </div>
          </VMenu>
          <button type="button" class="v-btn v-btn-quiet v-btn-icon control-btn control-btn--icon model-tool" aria-label="Fit model to view" title="Fit model (F)" :disabled="!ready || isDrawingMode" @click="fitModel"><svg class="icon"><use href="#icon-target" /></svg></button>
          <button v-if="canFullscreen" type="button" class="v-btn v-btn-quiet v-btn-icon control-btn control-btn--icon model-tool" :class="{ active: fullscreen }" :aria-label="fullscreen ? 'Exit full screen' : 'Full screen'" :title="fullscreen ? 'Exit full screen' : 'Full screen'" :disabled="isDrawingMode" @click="toggleFullscreen"><svg class="icon"><use href="#icon-fullscreen" /></svg></button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, reactive, ref, shallowRef, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { VMenu } from '../primitives'
import { createModelEnvironment, decodeModelFrame, disposeModel, fetchModelBytes, loadModel } from '../../lib/modelPreview'
import { ContactShadow, captureThumbnail, clipCamera, createModelRenderer, frameModel, modelBackdrop } from '../../lib/modelStage'
import { announceModelThumbnail, holdModelThumbnails, modelPreviewUrl, uploadModelThumbnail } from '../../lib/modelThumbnails'
import { getModelAnnotationTarget } from '../../lib/annotations'
import { formatTimecodeWithFrames } from '../../utils/formatters'

const props = defineProps({
  sourceUrl: { type: String, required: true },
  isDrawingMode: { type: Boolean, default: false },
  showAnnotationPreview: { type: Boolean, default: false },
  comments: { type: Array, default: () => [] },
  startPointerDrawing: { type: Function, required: true },
  movePointerDrawing: { type: Function, required: true },
  finishPointerDrawing: { type: Function, required: true },
  setAnnotationCanvasRef: { type: Function, required: true },
  setPreviewCanvasRef: { type: Function, required: true },
})
const emit = defineEmits(['loaded', 'time', 'annotation'])
const review = ref(null), stage = ref(null), viewport = ref(null), canvas = ref(null)
const ready = ref(false), error = ref(''), warning = ref(''), progress = ref(null), preparation = ref(false)
const playing = ref(false), buffering = ref(false), frame = ref(0), fps = ref(30), frameCount = ref(1)
const clips = shallowRef([]), clipIndex = ref(0), lightingOpen = ref(false), clipMenuOpen = ref(false)
const DEFAULT_LIGHTING = Object.freeze({ preset: 'studio', intensity: 1, rotation: 0 })
const lightingPresets = [{ value: 'studio', label: 'Studio' }, { value: 'daylight', label: 'Daylight' }, { value: 'night', label: 'Night' }]
const lighting = reactive({ ...DEFAULT_LIGHTING })
const lockedAspect = ref(null), stageSize = reactive({ width: 1, height: 1 })
const interacted = ref(false), fullscreen = ref(false), triangles = ref(0), format = ref('')
const canFullscreen = typeof document !== 'undefined' && Boolean(document.fullscreenEnabled)
const orbitHint = typeof matchMedia === 'function' && matchMedia('(pointer: coarse)').matches
  ? 'Drag to orbit · Pinch to zoom'
  : 'Drag to orbit · Right-drag to pan · Scroll to zoom'
const animated = computed(() => frameCount.value > 1)
const duration = computed(() => (frameCount.value - 1) / fps.value)
const clipName = computed(() => clips.value[clipIndex.value]?.name || `Animation ${clipIndex.value + 1}`)
const defaultLighting = computed(() => Object.keys(DEFAULT_LIGHTING).every(key => lighting[key] === DEFAULT_LIGHTING[key]))
const formatLabel = computed(() => format.value ? `${format.value.toUpperCase()} model` : '3D model')
const triangleLabel = computed(() => triangles.value ? `${new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(triangles.value)} triangles` : '')
// Menus teleport to the body, which is hidden while the review is full screen.
// Menus re-mount on this change because a mounted Teleport keeps its first target.
const menuTarget = computed(() => fullscreen.value ? '.model-review' : 'body')
const timedComments = computed(() => props.comments.filter(comment => Number.isFinite(comment.timestamp) && (getModelAnnotationTarget(comment)?.clip ?? clipIndex.value) === clipIndex.value))
const viewportStyle = computed(() => {
  const aspect = lockedAspect.value
  if (!aspect) return {}
  const width = Math.min(stageSize.width, stageSize.height * aspect)
  return { width: `${width}px`, height: `${width / aspect}px`, flex: 'none' }
})
let renderer, scene, camera, controls, root, mixer, action, environment, shadow, observer, contextLossExtension
let animationFrame = 0, pollTimer = 0, lastTick = 0
let pendingSeek = null, loadingFrame = false, polling = false, shadowDirty = true
const controller = new AbortController()
let manifest = null, disposed = false, pendingFocus = null
let center = new THREE.Vector3(), radius = 1
const frameCache = new Map()

function requestRender() {
  if (!animationFrame && !disposed && !document.hidden) animationFrame = requestAnimationFrame(render)
}
function render(now) {
  animationFrame = 0
  if (disposed || !renderer) return
  if (playing.value && ready.value && !buffering.value) {
    const next = Math.min(frameCount.value - 1, Math.floor((now - lastTick) / 1000 * fps.value))
    if (next !== frame.value) void seek(next, false)
    if (frame.value === frameCount.value - 1) playing.value = false
  }
  controls?.update()
  // The contact shadow follows the pose, not the camera.
  if (shadowDirty && root) { shadow.render(renderer, scene); shadowDirty = false }
  clipCamera(camera, center, radius)
  renderer.render(scene, camera)
  if (playing.value && !buffering.value && !document.hidden) requestRender()
}
function pause() { playing.value = false }
async function togglePlay() {
  if (!ready.value || props.isDrawingMode) return
  if (playing.value) { pause(); return }
  leaveCommentView()
  if (frame.value >= frameCount.value - 1) await seek(0)
  if (disposed) return
  playing.value = true
  lastTick = performance.now() - frame.value / fps.value * 1000
  void pumpFrames()
  requestRender()
}
function resize() {
  if (!renderer || disposed) return
  stageSize.width = stage.value.clientWidth
  stageSize.height = stage.value.clientHeight
  const rect = viewport.value.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  renderer.setSize(rect.width, rect.height, false)
  camera.aspect = rect.width / rect.height
  camera.updateProjectionMatrix()
  requestRender()
}
function applyLighting() {
  if (!renderer) return
  if (environment?.preset !== lighting.preset) {
    environment?.dispose()
    environment = createModelEnvironment(renderer, lighting.preset)
    environment.preset = lighting.preset
    scene.environment = environment.texture
  }
  scene.environmentIntensity = lighting.intensity
  scene.environmentRotation.y = THREE.MathUtils.degToRad(lighting.rotation)
  requestRender()
}
function changeLighting() { leaveCommentView(); applyLighting() }
function resetLighting() { Object.assign(lighting, DEFAULT_LIGHTING); changeLighting() }
function chooseClip(index) { clipIndex.value = index; selectClip() }
function toggleFullscreen() {
  if (document.fullscreenElement) void document.exitFullscreen()
  else void review.value?.requestFullscreen().catch(() => {})
}
function fullscreenChanged() {
  lightingOpen.value = false
  clipMenuOpen.value = false
  fullscreen.value = document.fullscreenElement === review.value
}
function leaveCommentView() {
  if (props.isDrawingMode) return
  lockedAspect.value = null
  emit('annotation', null)
  void nextTick(resize)
}
function frameView() {
  const view = frameModel(root, camera, 0.8)
  center.copy(view.center)
  radius = view.radius
  controls.target.copy(view.target)
  controls.minDistance = radius * 0.02
  controls.maxDistance = radius * 100
  controls.update()
  requestRender()
  return view
}
function fitModel() {
  if (!root || props.isDrawingMode) return
  leaveCommentView()
  frameView()
}
async function publishThumbnail(generation) {
  try {
    const capture = captureThumbnail(renderer, scene, root, shadow)
    requestRender()
    if (await uploadModelThumbnail(props.sourceUrl, generation, await capture)) announceModelThumbnail()
  } catch { /* A thumbnail is optional. Review still works. */ }
}
function captureView() {
  if (!ready.value) return null
  pause()
  return { kind: 'model-view', version: 1, position: camera.position.toArray(), target: controls.target.toArray(), up: camera.up.toArray(), fov: camera.fov, aspect: camera.aspect, lighting: { ...lighting }, clip: clipIndex.value, time: animated.value ? frame.value / fps.value : null }
}
async function focusComment(comment) {
  if (!ready.value) { pendingFocus = comment; return }
  if (props.isDrawingMode) return
  const target = getModelAnnotationTarget(comment)
  if (!target) { leaveCommentView(); return }
  pause()
  if (target.clip >= clips.value.length && clips.value.length) { warning.value = 'This note refers to an animation clip that is no longer available.'; return }
  clipIndex.value = target.clip
  selectClip()
  lockedAspect.value = target.aspect
  await nextTick()
  resize()
  camera.position.fromArray(target.position)
  camera.up.fromArray(target.up)
  camera.fov = target.fov
  camera.updateProjectionMatrix()
  controls.target.fromArray(target.target)
  controls.update()
  Object.assign(lighting, target.lighting)
  applyLighting()
  if (await seek(Math.round((target.time || 0) * fps.value))) emit('annotation', comment.annotation_data || null)
  requestRender()
}
function selectClip() {
  pause()
  leaveCommentView()
  action?.stop()
  if (mixer && clips.value[clipIndex.value]) {
    const clip = clips.value[clipIndex.value]
    action = mixer.clipAction(clip)
    action.setLoop(THREE.LoopOnce, 1)
    action.clampWhenFinished = true
    action.play()
    frameCount.value = Math.max(1, Math.ceil(clip.duration * fps.value) + 1)
  }
  frame.value = 0
  mixer?.setTime(0)
  shadowDirty = true
  emitInfo()
  emit('time', 0)
  requestRender()
}
function emitInfo() {
  emit('loaded', { fps: fps.value, frames: frameCount.value, duration: duration.value, extension: manifest?.format, triangles: triangles.value, codec: '', resolution: '' })
}
async function frameAt(index) {
  if (frameCache.has(index)) return frameCache.get(index)
  const buffer = await fetchModelBytes(modelPreviewUrl(props.sourceUrl, 'frame', { frame: index, generation: manifest.generation }), controller.signal)
  const model = decodeModelFrame(buffer)
  if (disposed) { disposeModel(model); throw new DOMException('Closed', 'AbortError') }
  frameCache.set(index, model)
  return model
}
function trimFrames() {
  for (const [index, model] of frameCache) {
    if (frameCache.size <= 4) break
    if (model !== root && index !== pendingSeek?.index) {
      frameCache.delete(index)
      disposeModel(model)
    }
  }
}
// One fetch at a time. Scrubbing replaces the queued target; playback keeps
// only the current frame and a small look-ahead window in memory.
async function pumpFrames() {
  if (loadingFrame || disposed || manifest?.format !== 'abc') return
  loadingFrame = true
  try {
    while (!disposed) {
      const command = pendingSeek
      const next = command?.index ?? (playing.value
        ? [frame.value + 1, frame.value + 2].find(index => index < manifest.ready_frames && !frameCache.has(index))
        : undefined)
      if (next === undefined || next >= manifest.ready_frames) break
      const model = await frameAt(next)
      if (command && command === pendingSeek) {
        scene.remove(root)
        root = model
        scene.add(root)
        shadowDirty = true
        frame.value = next
        if (buffering.value) lastTick = performance.now() - next / fps.value * 1000
        buffering.value = false
        pendingSeek = null
        emit('time', next / fps.value)
        command.resolve(true)
        requestRender()
      }
      trimFrames()
    }
  } catch (failure) {
    if (failure.name !== 'AbortError') { pause(); warning.value = failure.message }
    pendingSeek?.resolve(false)
    pendingSeek = null
    buffering.value = false
  } finally { loadingFrame = false }
}
async function seek(index, user = true) {
  if (props.isDrawingMode || !ready.value) return false
  const wanted = Math.max(0, Math.min(frameCount.value - 1, index))
  if (user) pause()
  if (manifest?.format === 'abc') {
    pendingSeek?.resolve(false)
    buffering.value = !frameCache.has(wanted)
    return new Promise(resolve => {
      pendingSeek = { index: wanted, resolve }
      void pumpFrames()
    })
  }
  mixer?.setTime(wanted / fps.value)
  shadowDirty = true
  frame.value = wanted
  emit('time', wanted / fps.value)
  requestRender()
  return true
}
function scrub(event) { leaveCommentView(); void seek(Number(event.target.value)) }
function step(delta) { leaveCommentView(); void seek(frame.value + delta) }
function handleKey(event) {
  if (props.isDrawingMode) return
  if (event.code === 'Space' && animated.value) { event.preventDefault(); togglePlay(); return }
  if (event.key.toLowerCase() === 'f') { event.preventDefault(); fitModel(); return }
  if (animated.value && !event.shiftKey && ['ArrowLeft', 'ArrowRight'].includes(event.key)) {
    event.preventDefault(); step(event.key === 'ArrowLeft' ? -1 : 1); return
  }
  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '-', '='].includes(event.key)) return
  event.preventDefault()
  interacted.value = true
  leaveCommentView()
  const offset = camera.position.clone().sub(controls.target)
  const spherical = new THREE.Spherical().setFromVector3(offset)
  if (event.key === 'ArrowLeft') spherical.theta -= 0.12
  if (event.key === 'ArrowRight') spherical.theta += 0.12
  if (event.key === 'ArrowUp') spherical.phi -= 0.12
  if (event.key === 'ArrowDown') spherical.phi += 0.12
  if (event.key === '+' || event.key === '=') spherical.radius *= 0.9
  if (event.key === '-') spherical.radius *= 1.1
  spherical.makeSafe()
  spherical.radius = Math.max(controls.minDistance, Math.min(controls.maxDistance, spherical.radius))
  camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(spherical))
  controls.update()
  requestRender()
}
function contextLost() { pause(); error.value = 'The browser lost its 3D graphics context. Close other graphics-heavy tabs, then try again.' }
async function contextRestored() {
  // Wait until every context-restored listener has run before creating GPU resources.
  await new Promise(requestAnimationFrame)
  if (disposed) return
  environment?.dispose()
  environment = null
  applyLighting()
  shadowDirty = true
  error.value = ''
  resize()
  if (!ready.value) void pollManifest()
}
function visibilityChanged() { pause(); if (document.hidden) cancelAnimationFrame(animationFrame); animationFrame = 0; if (!document.hidden) { requestRender(); if (preparation.value) void pollManifest() } }
async function pollManifest(retry = false) {
  if (polling || disposed) return
  polling = true
  clearTimeout(pollTimer)
  try {
    const response = await fetch(modelPreviewUrl(props.sourceUrl, 'manifest'), { method: retry ? 'POST' : 'GET', credentials: 'same-origin', signal: controller.signal })
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'The preview could not be opened.')
    if (data.status === 'error') throw new Error(data.error)
    manifest = data
    preparation.value = data.format === 'abc' && data.status !== 'complete'
    progress.value = data.progress ?? null
    if (!ready.value && (data.format !== 'abc' || data.ready_frames > 0)) {
      if (data.format === 'abc') {
        root = await frameAt(0)
        triangles.value = root.geometry.attributes.position.count / 3
        fps.value = data.fps
        frameCount.value = data.frame_count
      } else {
        const loaded = await loadModel(props.sourceUrl, data, renderer, controller.signal, value => { progress.value = value })
        root = loaded.root
        triangles.value = Math.round(loaded.triangles)
        clips.value = loaded.animations
        warning.value = [...loaded.warnings].join(' ')
        if (clips.value.length) mixer = new THREE.AnimationMixer(root)
      }
      if (disposed) { disposeModel(root); return }
      format.value = data.format || ''
      scene.add(root)
      ready.value = true
      selectClip()
      shadow.place(frameView().bounds)
      if (data.needs_thumbnail) void publishThumbnail(data.thumbnail_generation)
      if (pendingFocus) { const comment = pendingFocus; pendingFocus = null; await focusComment(comment) }
    }
    void pumpFrames()
    if (preparation.value && !document.hidden) pollTimer = setTimeout(() => { void pollManifest() }, 1500)
  } catch (failure) {
    if (failure.name !== 'AbortError') {
      preparation.value = false
      pendingSeek?.resolve(false)
      pendingSeek = null
      buffering.value = false
      pause()
      if (ready.value) warning.value = failure.message
      else error.value = failure.message
    }
  } finally { polling = false }
}
function retry() {
  // Restored contexts re-upload Three.js resources on the next render.
  if (!renderer) { location.reload(); return }
  if (polling) return
  if (renderer.getContext().isContextLost()) {
    if (contextLossExtension) contextLossExtension.restoreContext()
    else location.reload()
    return
  }
  error.value = ''
  warning.value = ''
  void pollManifest(true)
}
watch(() => props.isDrawingMode, async drawing => {
  pause()
  if (controls) controls.enabled = !drawing
  if (drawing) { lockedAspect.value = camera?.aspect || null; lightingOpen.value = false; clipMenuOpen.value = false }
  else leaveCommentView()
  await nextTick()
  resize()
})
// Background thumbnails wait while this viewer loads and shows its model.
const releaseThumbnails = holdModelThumbnails()
onMounted(() => {
  try {
    renderer = createModelRenderer(canvas.value)
    contextLossExtension = renderer.getContext().getExtension('WEBGL_lose_context')
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2))
    scene = new THREE.Scene()
    shadow = new ContactShadow()
    scene.add(shadow.group)
    camera = new THREE.PerspectiveCamera(40, 1, 0.001, 1000)
    controls = new OrbitControls(camera, canvas.value)
    controls.addEventListener('change', requestRender)
    controls.addEventListener('start', () => { interacted.value = true; leaveCommentView() })
    observer = new ResizeObserver(resize)
    observer.observe(stage.value)
    observer.observe(viewport.value)
    document.addEventListener('visibilitychange', visibilityChanged)
    document.addEventListener('fullscreenchange', fullscreenChanged)
    resize()
    applyLighting()
    void pollManifest()
  } catch { error.value = '3D review needs a browser with WebGL 2 enabled.' }
})
onBeforeUnmount(() => {
  disposed = true
  releaseThumbnails()
  controller.abort()
  pendingSeek?.resolve(false)
  pendingSeek = null
  clearTimeout(pollTimer)
  cancelAnimationFrame(animationFrame)
  observer?.disconnect()
  document.removeEventListener('visibilitychange', visibilityChanged)
  document.removeEventListener('fullscreenchange', fullscreenChanged)
  if (fullscreen.value) void document.exitFullscreen().catch(() => {})
  mixer?.stopAllAction()
  if (root) mixer?.uncacheRoot(root)
  controls?.dispose()
  if (!frameCache.size) disposeModel(root)
  for (const value of frameCache.values()) disposeModel(value)
  frameCache.clear()
  environment?.dispose()
  shadow?.dispose()
  renderer?.dispose()
  renderer?.forceContextLoss()
})
defineExpose({ captureView, focusComment, pause, getViewportRect: () => viewport.value?.getBoundingClientRect() })
</script>

<style scoped>
.model-review { display: flex; flex-direction: column; width: 100%; height: 100%; min-width: 0; min-height: 0; background: var(--v-bg-black); }
.model-stage { flex: 1; min-height: 180px; position: relative; display: flex; align-items: center; justify-content: center; overflow: hidden; background: var(--v-bg-black); }
.model-viewport { position: relative; width: 100%; height: 100%; min-width: 0; background: v-bind(modelBackdrop); transition: box-shadow var(--v-duration-normal) var(--v-ease-emphasized); }
/* A saved comment view keeps its framing. The outline shows that frame. */
.model-viewport.is-framed { box-shadow: 0 0 0 1px color-mix(in srgb, var(--v-accent) 30%, transparent); }
.model-canvas { display: block; width: 100%; height: 100%; touch-action: none; cursor: grab; outline: none; }
.model-canvas:active { cursor: grabbing; }
.model-canvas:focus-visible { box-shadow: inset 0 0 0 2px var(--v-accent-muted); }

.model-message { position: absolute; inset: 0; z-index: 4; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--v-space-3); padding: var(--v-space-6); text-align: center; }
.model-message h3, .model-message p { margin: 0; }
.model-message h3 { color: var(--v-text); font-size: var(--v-text-md); font-weight: 650; }
.model-message p { max-width: 40ch; color: var(--v-text-secondary); font-size: var(--v-text-sm); line-height: 1.5; }
.model-message .v-btn { margin-top: var(--v-space-1); }
.model-message__icon { display: grid; place-items: center; width: 44px; height: 44px; border: 1px solid color-mix(in srgb, var(--v-text) 10%, transparent); border-radius: var(--v-radius-md); background: color-mix(in srgb, var(--v-text) 4%, transparent); color: var(--v-text-secondary); }
.model-message__icon .icon { width: 20px; height: 20px; }
.model-message__icon.is-error { border-color: color-mix(in srgb, var(--v-danger) 24%, transparent); background: color-mix(in srgb, var(--v-danger) 10%, transparent); color: var(--v-danger); }
.model-progress { width: min(220px, 70%); height: 3px; overflow: hidden; border-radius: var(--v-radius-full); background: color-mix(in srgb, var(--v-text) 12%, transparent); }
.model-progress span { display: block; width: 0; height: 100%; border-radius: inherit; background: var(--v-accent); transition: width var(--v-duration-fast) linear; }
.model-progress.is-indeterminate span { width: 36%; animation: model-progress-slide 1.2s var(--v-ease-emphasized) infinite; }
@keyframes model-progress-slide { from { transform: translateX(-100%); } to { transform: translateX(280%); } }

.model-overlay { position: absolute; top: var(--v-space-3); left: var(--v-space-3); right: var(--v-space-3); z-index: 3; display: flex; align-items: flex-start; justify-content: space-between; gap: var(--v-space-2); pointer-events: none; }
.model-overlay__start, .model-overlay__end { display: flex; flex-wrap: wrap; gap: var(--v-space-2); min-width: 0; }
.model-overlay__end { justify-content: flex-end; }
.model-chip { display: inline-flex; align-items: center; gap: 6px; min-height: 28px; max-width: 100%; padding: 4px 11px; border: 1px solid color-mix(in srgb, var(--v-text) 10%, transparent); border-radius: var(--v-radius-full); background: color-mix(in srgb, var(--v-bg-black) 74%, transparent); color: var(--v-text-secondary); font-size: var(--v-text-sm); font-weight: 500; line-height: 1.3; box-shadow: 0 8px 22px rgba(0, 0, 0, 0.3); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); }
.model-chip .icon { flex: 0 0 auto; width: 13px; height: 13px; }
.model-chip.is-action { color: var(--v-text); font-weight: 600; cursor: pointer; pointer-events: auto; transition: border-color var(--v-transition-fast), background var(--v-transition-fast); }
.model-chip.is-action:hover { border-color: color-mix(in srgb, var(--v-text) 20%, transparent); background: color-mix(in srgb, var(--v-bg-black) 58%, var(--v-surface-panel)); }
.model-chip.is-action:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--v-accent-muted); }
.model-chip.is-accent { border-color: color-mix(in srgb, var(--v-accent) 32%, transparent); color: var(--v-accent); }
.model-chip.is-warning { max-width: min(420px, 100%); padding: 4px 4px 4px 11px; border-color: color-mix(in srgb, var(--v-warning) 30%, transparent); color: var(--v-warning); pointer-events: auto; }
.model-chip__dismiss { display: grid; place-items: center; flex: 0 0 auto; width: 22px; height: 22px; padding: 0; border: 0; border-radius: var(--v-radius-full); background: transparent; color: inherit; cursor: pointer; }
.model-chip__dismiss:hover { background: color-mix(in srgb, var(--v-warning) 14%, transparent); }
.model-chip__dismiss .icon { width: 12px; height: 12px; }
.model-buffering { white-space: nowrap; position: absolute; bottom: var(--v-space-3); left: 50%; z-index: 3; transform: translateX(-50%); }
.model-spin { animation: model-spin 0.8s linear infinite; }
@keyframes model-spin { to { transform: rotate(360deg); } }
.model-fade-leave-active { transition: opacity var(--v-duration-normal) var(--v-ease-emphasized); }
.model-fade-leave-to { opacity: 0; }

/* Layout comes from the shared video toolbar. Only model-specific parts live here. */
.model-toolbar { container-type: inline-size; }
.model-toolbar.is-static { padding-top: 10px; }
.model-timeline { position: relative; height: 20px; }
.model-scrubber { --thumb: 12px; --fill: calc(var(--thumb) / 2 + (100% - var(--thumb)) * var(--progress, 0)); display: block; width: 100%; height: 20px; margin: 0; background: transparent; cursor: pointer; -webkit-appearance: none; appearance: none; touch-action: none; }
.model-scrubber:focus { outline: none; }
.model-scrubber:focus-visible { border-radius: var(--v-radius-full); box-shadow: 0 0 0 3px var(--v-accent-muted); }
.model-scrubber:disabled { cursor: default; }
.model-scrubber::-webkit-slider-runnable-track { height: 3px; border-radius: var(--v-radius-full); background: linear-gradient(to right, var(--v-accent) 0 var(--fill), color-mix(in srgb, var(--v-text) 14%, transparent) var(--fill) 100%); }
.model-scrubber::-moz-range-track { height: 3px; border-radius: var(--v-radius-full); background: linear-gradient(to right, var(--v-accent) 0 var(--fill), color-mix(in srgb, var(--v-text) 14%, transparent) var(--fill) 100%); }
.model-scrubber:hover::-webkit-slider-runnable-track, .model-scrubber:active::-webkit-slider-runnable-track { height: 4px; }
.model-scrubber:hover::-moz-range-track, .model-scrubber:active::-moz-range-track { height: 4px; }
.model-scrubber::-webkit-slider-thumb { width: var(--thumb); height: var(--thumb); margin-top: -4.5px; border: 0; border-radius: 50%; background: var(--v-accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--v-accent) 24%, transparent); opacity: 0; transition: opacity var(--v-duration-fast) var(--v-ease-emphasized); -webkit-appearance: none; appearance: none; }
.model-scrubber::-moz-range-thumb { width: var(--thumb); height: var(--thumb); border: 0; border-radius: 50%; background: var(--v-accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--v-accent) 24%, transparent); opacity: 0; transition: opacity var(--v-duration-fast) var(--v-ease-emphasized); }
.model-scrubber:hover::-webkit-slider-thumb { margin-top: -4px; }
.model-scrubber:is(:hover, :active, :focus-visible)::-webkit-slider-thumb { opacity: 1; }
.model-scrubber:is(:hover, :active, :focus-visible)::-moz-range-thumb { opacity: 1; }
.model-comment-markers { position: absolute; inset: 0 6px; pointer-events: none; }
.model-comment-markers .comment-marker { padding: 0; border: 0; pointer-events: auto; -webkit-appearance: none; appearance: none; }
.model-comment-markers .comment-marker:disabled { cursor: default; opacity: 0.5; }

.model-step__back { transform: scaleX(-1); }
.control-btn:disabled { cursor: default; opacity: 0.4; }
.control-btn:disabled:hover { background: transparent; color: var(--v-text-muted); }
.model-tool.active { color: var(--v-accent); background: color-mix(in srgb, var(--v-accent) 11%, transparent); }
.model-clip-menu, .model-clip-menu :deep(.v-menu-trigger) { display: flex; min-width: 0; }
.model-clip-trigger { width: auto; min-width: 0; max-width: 180px; flex: 0 1 auto; gap: 6px; padding: 0 8px 0 9px; }
.model-clip-trigger.active { color: var(--v-text); background: var(--v-bg-hover); }
.model-clip-trigger__label { overflow: hidden; font-size: var(--v-text-sm); font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.model-clip-trigger .model-clip-trigger__icon { width: 14px; height: 14px; }
.model-clip-trigger .model-clip-trigger__chevron { width: 12px; height: 12px; opacity: 0.7; transition: transform var(--v-transition-fast); }
.model-clip-trigger.active .model-clip-trigger__chevron { transform: rotate(180deg); }
.model-clip-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.model-stats { display: flex; align-items: center; gap: 8px; min-width: 0; overflow: hidden; color: var(--v-text-muted); font-size: var(--v-text-sm); white-space: nowrap; }
.model-stats__format { padding: 3px 7px; border: 1px solid color-mix(in srgb, var(--v-text) 10%, transparent); border-radius: var(--v-radius-sm); background: color-mix(in srgb, var(--v-text) 4%, transparent); color: var(--v-text-secondary); font-size: var(--v-text-2xs); font-weight: 700; letter-spacing: 0.04em; }
.model-stats__detail { overflow: hidden; font-variant-numeric: tabular-nums; text-overflow: ellipsis; }

.model-lighting { display: grid; gap: 14px; padding: 6px 6px 8px; }
.model-lighting__head { display: flex; align-items: center; justify-content: space-between; min-height: 22px; padding: 0 4px; }
.model-lighting__reset { padding: 2px 6px; border: 0; border-radius: var(--v-radius-sm); background: transparent; color: var(--v-accent); font-size: var(--v-text-sm); font-weight: 600; cursor: pointer; }
.model-lighting__reset:hover:not(:disabled) { background: var(--v-accent-muted); }
.model-lighting__reset:disabled { color: var(--v-text-muted); cursor: default; opacity: 0.6; }
.model-segmented { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px; padding: 2px; border: 1px solid color-mix(in srgb, var(--v-text) 8%, transparent); border-radius: var(--v-button-radius); background: color-mix(in srgb, var(--v-text) 4%, transparent); }
.model-segmented__option { min-height: 30px; padding: 0 8px; border: 0; border-radius: calc(var(--v-button-radius) - 2px); background: transparent; color: var(--v-text-secondary); font-size: var(--v-text-sm); font-weight: 600; cursor: pointer; transition: background var(--v-transition-fast), color var(--v-transition-fast); }
.model-segmented__option:hover { color: var(--v-text); }
.model-segmented__option.active { background: var(--v-surface-inline-strong); color: var(--v-text); box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3); }
.model-segmented__option:focus-visible { outline: none; box-shadow: 0 0 0 2px var(--v-accent-muted); }
.model-slider { display: grid; gap: 6px; padding: 0 4px; }
.model-slider__label { display: flex; justify-content: space-between; color: var(--v-text-secondary); font-size: var(--v-text-sm); font-weight: 600; }
.model-slider__label output { color: var(--v-text); font-variant-numeric: tabular-nums; }
.model-slider input { --thumb: 13px; --fill: calc(var(--thumb) / 2 + (100% - var(--thumb)) * var(--progress, 0)); width: 100%; height: 20px; margin: 0; background: transparent; cursor: pointer; -webkit-appearance: none; appearance: none; }
.model-slider input:focus { outline: none; }
.model-slider input::-webkit-slider-runnable-track { height: 4px; border-radius: var(--v-radius-full); background: linear-gradient(to right, var(--v-accent) 0 var(--fill), var(--v-surface-inline-strong) var(--fill) 100%); }
.model-slider input::-moz-range-track { height: 4px; border-radius: var(--v-radius-full); background: linear-gradient(to right, var(--v-accent) 0 var(--fill), var(--v-surface-inline-strong) var(--fill) 100%); }
.model-slider input::-webkit-slider-thumb { width: var(--thumb); height: var(--thumb); margin-top: -4.5px; border: 0; border-radius: 50%; background: var(--v-text); box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-bg-base) 80%, transparent); -webkit-appearance: none; appearance: none; transition: box-shadow var(--v-duration-fast) var(--v-ease-emphasized); }
.model-slider input::-moz-range-thumb { width: var(--thumb); height: var(--thumb); border: 0; border-radius: 50%; background: var(--v-text); box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-bg-base) 80%, transparent); }
.model-slider input:is(:hover, :active, :focus-visible)::-webkit-slider-thumb { box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-bg-base) 82%, transparent), 0 0 0 5px color-mix(in srgb, var(--v-accent) 22%, transparent); }
.model-slider input:is(:hover, :active, :focus-visible)::-moz-range-thumb { box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-bg-base) 82%, transparent), 0 0 0 5px color-mix(in srgb, var(--v-accent) 22%, transparent); }

@media (max-width: 768px) {
  .model-overlay { top: var(--v-space-2); left: var(--v-space-2); right: var(--v-space-2); }
  .model-toolbar.is-static { padding-top: 8px; }
  .model-timeline, .model-scrubber { height: 24px; }
  .model-scrubber::-webkit-slider-runnable-track { height: 4px; }
  .model-scrubber::-moz-range-track { height: 4px; }
  .model-scrubber::-webkit-slider-thumb { margin-top: -4px; opacity: 1; }
  .model-scrubber::-moz-range-thumb { opacity: 1; }
  .model-segmented__option { min-height: 40px; }
  .model-slider input { height: 32px; }
}
/* The clip name shows only when the toolbar has room for it. */
@container (max-width: 768px) {
  .model-clip-trigger { width: var(--viewer-control-size); max-width: none; padding: 0; justify-content: center; }
  .model-clip-trigger__label, .model-clip-trigger .model-clip-trigger__chevron { display: none; }
  .model-clip-trigger .model-clip-trigger__icon { width: var(--viewer-control-glyph); height: var(--viewer-control-glyph); }
}
@media (max-width: 480px) {
  .model-step { display: none; }
  .model-chip { min-height: 26px; padding: 4px 9px; font-size: var(--v-text-xs); }
}
@media (max-width: 360px) {
  .model-toolbar .time-sep, .model-toolbar .time-duration { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .model-spin, .model-progress.is-indeterminate span { animation-duration: 2.4s; }
  .model-fade-leave-active, .model-viewport { transition: none; }
}
</style>
