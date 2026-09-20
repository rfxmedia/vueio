<template>
  <aside class="comparison-export" aria-labelledby="comparison-export-title">
    <header class="export-heading">
      <h2 id="comparison-export-title">Export comparison</h2>
    </header>
    <form class="export-form" novalidate @submit.prevent="start">
      <fieldset class="export-fields" :disabled="busy">
        <section class="export-section">
          <div class="export-pair">
            <div><span>Before</span><strong :title="beforeLabel">{{ beforeLabel }}</strong></div>
            <button type="button" class="v-btn v-btn-ghost v-btn-sm" aria-label="Swap before and after" @click="options.swapped = !options.swapped">Swap</button>
            <div><span>After</span><strong :title="afterLabel">{{ afterLabel }}</strong></div>
          </div>
        </section>
        <section class="export-section">
          <h3>Footage</h3>
          <div class="v-view-toggle export-layout" role="group" aria-label="Footage motion">
            <button ref="firstControl" type="button" class="v-view-toggle-btn" :class="{ active: !frozen }" :aria-pressed="!frozen" @click="setFrozen(false)">Moving footage</button>
            <button type="button" class="v-view-toggle-btn" :class="{ active: frozen }" :aria-pressed="frozen" @click="setFrozen(true)">Freeze frame</button>
          </div>
          <template v-if="frozen">
            <label class="export-frame-choice">
              <span>Frame to freeze</span><span class="export-unit">of {{ maxFrames }}</span>
              <input class="v-input" type="number" min="1" :max="maxFrames" step="1" :value="options.freeze_frame + 1" @change="setFrame('freeze_frame', $event)" />
            </label>
            <input class="export-size" type="range" min="1" :max="maxFrames" step="1" :value="options.freeze_frame + 1" aria-label="Choose frame to freeze" @input="setFrame('freeze_frame', $event)" />
            <p class="export-note">Both versions stay on this frame.</p>
            <label class="export-length"><span>Export length</span><span class="export-unit">{{ durationLabel }}</span>
              <span class="export-number-unit"><input class="v-input" type="number" min="2" :max="maxExportFrames" step="1" :value="options.freeze_frames" @change="setFrame('freeze_frames', $event)" /><span>frames</span></span>
            </label>
          </template>
          <template v-else>
            <div class="export-field-grid">
              <label>First frame<input class="v-input" type="number" min="1" :max="Math.max(1, maxFrames - 1)" step="1" :value="options.start_frame + 1" @change="setFrame('start_frame', $event)" /></label>
              <label>Last frame<input class="v-input" type="number" :min="Math.min(2, maxFrames)" :max="maxFrames" step="1" :value="options.end_frame" @change="setFrame('end_frame', $event)" /></label>
            </div>
            <p class="export-note">{{ frameCount }} frames · {{ durationLabel }}<template
v-if="info.end_frames[0] !== info.end_frames[1]"> · Ends with the shorter version</template></p>
          </template>
          <p v-if="info.different_frame_rates" class="export-note">These versions have different frame rates. Frame numbers use the {{ Number(info.fps.toFixed(2)) }} fps comparison timeline.</p>
          <p v-if="validation" class="export-error" role="status">{{ validation }}</p>
        </section>
        <section class="export-section">
          <label class="export-aspect"><span>Aspect ratio</span><select v-model="options.aspect" class="v-input" aria-label="Aspect ratio">
            <option value="source">Original</option>
            <option value="3:4">3:4 · Portrait</option>
            <option value="1:1">1:1 · Square</option>
            <option value="16:9">16:9 · Landscape</option>
          </select></label>
          <div class="v-view-toggle export-layout" role="group" aria-label="Export layout">
            <button
v-for="layout in layouts" :key="layout.value" type="button" class="v-view-toggle-btn"
              :class="{ active: options.mode === layout.value }" :aria-pressed="options.mode === layout.value"
              @click="options.mode = layout.value">{{ layout.label }}</button>
          </div>
          <p v-if="options.mode === 'side-by-side'" class="export-note">{{ geometry.stacked ? 'Stacked' : 'Side by side' }} · Both images shown in full</p>
          <template v-if="options.mode === 'wipe' && frameCount >= 2">
            <div class="export-wipe-map" aria-hidden="true">
              <div class="export-wipe-track"><span :style="{ left: `${timing.start / frameCount * 100}%`, width: `${timing.duration / frameCount * 100}%` }" /></div>
              <div><span>Before</span><span>Wipe</span><span>After</span></div>
            </div>
            <div class="export-field-grid">
              <label>Wipe start frame<input class="v-input" type="number" min="1" :max="frameCount - 1" step="1" :value="timing.start + 1" @change="setWipe('start', $event)" /></label>
              <label>Wipe end frame<input class="v-input" type="number" min="2" :max="frameCount" step="1" :value="timing.start + timing.duration" @change="setWipe('end', $event)" /></label>
            </div>
            <p class="export-note">Frame numbers in the exported video.</p>
          </template>
        </section>
        <details class="export-section export-details" :open="branding.labels || !!logoData">
          <summary>Labels &amp; logo<svg class="icon" aria-hidden="true"><use href="#icon-chevron-down" /></svg></summary>
          <div class="export-branding">
          <VSwitch v-model="branding.labels" label="Before / after labels" />
          <div v-if="branding.labels" class="export-field-grid">
            <label>Before<input v-model="branding.before" class="v-input" maxlength="40" /></label>
            <label>After<input v-model="branding.after" class="v-input" maxlength="40" /></label>
          </div>
          <div class="export-section-heading export-logo-heading"><h3>Logo</h3><span>Optional</span></div>
          <div class="export-logo-row">
            <img v-if="logoData" :src="logoData" alt="Selected logo" class="export-logo" />
            <button type="button" class="v-btn v-btn-secondary" @click="logoInput.click()">{{ logoData ? 'Replace logo' : 'Add logo' }}</button>
            <button v-if="logoData" type="button" class="v-btn v-btn-ghost" @click="removeLogo">Remove</button>
            <input ref="logoInput" class="export-file-input" type="file" accept="image/png,image/jpeg,image/webp" aria-label="Choose a logo" tabindex="-1" @change="chooseLogo" />
          </div>
          <p v-if="logoError" class="export-error" role="alert">{{ logoError }}</p>
          <template v-if="logoData">
            <div class="export-field-grid">
              <label>Position<select v-model="branding.corner" class="v-input">
                <option v-for="corner in corners" :key="corner.value" :value="corner.value">{{ corner.label }}</option>
              </select></label>
              <label>Size <span class="export-unit">{{ branding.size }}%</span><input v-model.number="branding.size" type="range" min="5" max="25" step="1" class="export-size" /></label>
            </div>
          </template>
          </div>
        </details>
      </fieldset>
    </form>
    <footer class="export-footer">
      <div class="export-output"><strong>MP4</strong><span>{{ geometry.width }} × {{ geometry.height }} · {{ Number(info.fps.toFixed(2)) }} fps · No audio</span></div>
      <div v-if="busy" class="export-progress" role="status" aria-live="polite">
        <div><span>{{ status === 'processing' ? 'Rendering your video' : 'Preparing export' }}</span><span>{{ Math.round(progress) }}%</span></div>
        <progress :value="progress" max="100" aria-label="Export progress" />
        <button type="button" class="v-btn v-btn-secondary" @click="cancel">Cancel export</button>
      </div>
      <template v-else>
        <p v-if="error" class="export-error" role="alert">{{ error }}</p>
        <p v-if="notice" class="export-note" role="status">{{ notice }}</p>
        <a v-if="status === 'complete'" :href="`${jobUrl}/file`" download="comparison.mp4" class="v-btn v-btn-primary export-submit" :aria-disabled="downloading" @click.prevent="download">{{ downloading ? 'Starting download…' : 'Download MP4' }}</a>
        <button v-else type="button" class="v-btn v-btn-primary export-submit" :disabled="!!validation || logoLoading" @click="start">{{ error ? 'Try again' : 'Export MP4' }}</button>
        <p v-if="status === 'complete'" class="export-note">Ready. This download link expires in 24 hours.</p>
      </template>
    </footer>
  </aside>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import api, { getApiErrorMessage } from '../../lib/api'
import { createExportArtwork, exportFrameCount, exportGeometry, exportTiming, loadLogo } from '../../lib/comparisonExport'
import { useSessionAuthStore } from '../../ownership/sessionAuth'
import VSwitch from '../primitives/VSwitch.vue'

const props = defineProps({ info: { type: Object, required: true }, pairUrl: { type: String, required: true }, labels: { type: Array, required: true }, sourceFrame: { type: Number, default: 0 } })
const emit = defineEmits(['preview', 'busy'])
const { currentUser } = useSessionAuthStore()
const maxFrames = Math.min(...props.info.end_frames), maxExportFrames = Math.floor(props.info.fps * 300)
const options = reactive({ mode: 'wipe', aspect: 'source', start_frame: 0, end_frame: maxFrames, freeze_frame: null, freeze_frames: Math.round(props.info.fps * 5), wipe_start: .4, wipe_duration: .2, swapped: false })
const branding = reactive({ labels: false, before: 'Before', after: 'After', corner: 'bottom-right', size: 12 })
const logoData = ref(''), logoInput = ref(null), logoError = ref(''), logoLoading = ref(false), firstControl = ref(null), downloading = ref(false)
const status = ref('idle'), progress = ref(0), error = ref(''), notice = ref(''), jobUrl = ref('')
const busy = computed(() => ['starting', 'queued', 'processing'].includes(status.value))
const geometry = computed(() => exportGeometry(props.info, options))
const frozen = computed(() => options.freeze_frame != null)
const frameCount = computed(() => exportFrameCount(options))
const duration = computed(() => Math.max(0, frameCount.value) / props.info.fps)
const durationLabel = computed(() => `${Number(duration.value.toFixed(2))} s`)
const timing = computed(() => exportTiming(options))
const beforeLabel = computed(() => props.labels[Number(options.swapped)])
const afterLabel = computed(() => props.labels[Number(!options.swapped)])
const validation = computed(() => frameCount.value < 2 ? 'This shot has one frame. Use Freeze frame to export it.'
  : duration.value > 300 ? 'Choose a clip of five minutes or less.' : '')
const layouts = [{ value: 'wipe', label: 'Wipe' }, { value: 'side-by-side', label: 'Split view' }]
const corners = ['top-left', 'top-right', 'bottom-left', 'bottom-right'].map(value => ({ value, label: value.replace('-', ' ').replace(/^./, c => c.toUpperCase()) }))
const userKey = currentUser.value?.id
const preferenceKey = userKey ? `vueio:comparison-export:${userKey}` : null
// Keep the composition open if this job's request fails. Its own retry/cancel
// controls handle recovery instead of reloading the whole media viewer.
const requestConfig = { skipConnectionRecovery: true }
let logo = null, artwork = null, timer, preferenceTimer, previewRaf = 0, attempt = 0, logoAttempt = 0, disposed = false

function setFrozen(value) {
  if (value === frozen.value) return
  options.freeze_frame = value ? Math.max(0, Math.min(maxFrames - 1, props.sourceFrame)) : null
}
function clampFrame(n, min, max) { return Math.max(min, Math.min(max, Math.round(n))) }
function setFrame(key, event) {
  const n = event.target.value === '' ? NaN : Number(event.target.value)
  if (Number.isFinite(n)) {
    if (key === 'freeze_frame') options.freeze_frame = clampFrame(n, 1, maxFrames) - 1
    else if (key === 'freeze_frames') options.freeze_frames = clampFrame(n, 2, maxExportFrames)
    else if (key === 'start_frame') {
      options.start_frame = clampFrame(n, 1, Math.max(1, maxFrames - 1)) - 1
      options.end_frame = Math.min(maxFrames, Math.max(options.end_frame, options.start_frame + 2))
    } else {
      options.end_frame = clampFrame(n, Math.min(2, maxFrames), maxFrames)
      options.start_frame = Math.max(0, Math.min(options.start_frame, options.end_frame - 2))
    }
  }
  event.target.value = options[key] + (['start_frame', 'freeze_frame'].includes(key) ? 1 : 0)
}
function setWipe(key, event) {
  const n = event.target.value === '' ? NaN : Number(event.target.value), frames = frameCount.value
  let start = timing.value.start, end = start + timing.value.duration
  if (Number.isFinite(n) && frames >= 2) {
    if (key === 'start') { start = clampFrame(n, 1, frames - 1) - 1; end = Math.max(end, start + 2) }
    else { end = clampFrame(n, 2, frames); start = Math.min(start, end - 2) }
    options.wipe_start = start / frames; options.wipe_duration = (end - start) / frames
  }
  event.target.value = key === 'start' ? start + 1 : end
}
function preview() {
  cancelAnimationFrame(previewRaf)
  previewRaf = requestAnimationFrame(() => {
    artwork = createExportArtwork(props.info, options, branding, logo, artwork)
    emit('preview', { options: { ...options }, artwork })
  })
}
function savePreferences() {
  if (!preferenceKey) return
  try {
    localStorage.setItem(preferenceKey, JSON.stringify({ mode: options.mode, aspect: options.aspect, wipe_start: options.wipe_start, wipe_duration: options.wipe_duration, branding: { ...branding }, logo: logoData.value }))
  } catch { /* A full or unavailable local store does not block export. */ }
}
function removeLogo() { logoAttempt++; logoLoading.value = false; logo = null; logoData.value = ''; logoError.value = ''; preview() }
async function chooseLogo(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  const current = ++logoAttempt
  logoError.value = ''; logoLoading.value = true
  let url
  try {
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) throw new Error('Choose a PNG, JPEG, or WebP file smaller than 5 MB.')
    url = URL.createObjectURL(file)
    const image = await loadLogo(url)
    if (image.width * image.height > 32_000_000 || Math.max(image.width, image.height) > 8192) throw new Error('Use a logo no larger than 8,192 pixels per side.')
    const canvas = document.createElement('canvas'), scale = Math.min(1, 1024 / Math.max(image.width, image.height))
    canvas.width = Math.max(1, Math.round(image.width * scale)); canvas.height = Math.max(1, Math.round(image.height * scale))
    canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height)
    const data = canvas.toDataURL('image/png'), resized = await loadLogo(data)
    if (current !== logoAttempt || disposed) return
    logo = resized; logoData.value = data; preview()
  } catch (exception) { if (current === logoAttempt) logoError.value = exception.message }
  finally { if (url) URL.revokeObjectURL(url); if (current === logoAttempt) logoLoading.value = false }
}
async function poll(current) {
  try {
    const { data } = await api.get(jobUrl.value, requestConfig)
    if (current !== attempt || disposed) return
    status.value = data.status; progress.value = data.progress || 0
    if (data.status === 'error') { jobUrl.value = ''; error.value = data.error || 'The video could not be rendered. Try again.'; return }
    if (data.status !== 'complete') timer = setTimeout(() => poll(current), 1500)
  } catch (exception) {
    if (current === attempt && !disposed) {
      if ([400, 401, 403, 404, 410, 422].includes(exception.response?.status)) jobUrl.value = ''
      status.value = 'error'; error.value = exception.response ? getApiErrorMessage(exception) : 'The export status could not load. Try again to reconnect.'
    }
  }
}
async function download() {
  if (downloading.value) return
  downloading.value = true; error.value = ''
  const url = `${jobUrl.value}/file`
  try {
    await api.head(url, requestConfig)
    if (disposed) return
    const link = document.createElement('a')
    link.href = url; link.download = 'comparison.mp4'
    document.body.append(link); link.click(); link.remove()
  } catch (exception) {
    if (exception.response?.status === 404) { jobUrl.value = ''; status.value = 'idle' }
    error.value = exception.response?.status === 403 ? 'Download access is no longer available.'
      : exception.response?.status === 404 ? 'This export is no longer available. Export it again.' : 'The download could not start. Try again.'
  } finally { downloading.value = false }
}
async function start() {
  if (busy.value || validation.value || logoLoading.value) return
  // If polling lost its connection, recheck the same job instead of making another.
  if (jobUrl.value && status.value === 'error') { status.value = 'queued'; error.value = ''; void poll(++attempt); return }
  const current = ++attempt, base = props.pairUrl
  status.value = 'starting'; error.value = ''; notice.value = ''; progress.value = 0
  try {
    artwork = createExportArtwork(props.info, options, branding, logo, artwork)
    const pixels = artwork?.toDataURL('image/png').split(',')[1] || null
    const { data } = await api.post(`${base}/export`, { options: { ...options }, artwork: pixels }, requestConfig)
    const url = `${base}/export/${encodeURIComponent(data.token)}`
    if (current !== attempt || disposed) { void api.delete(url, requestConfig).catch(() => {}); return }
    jobUrl.value = url; status.value = data.status
    void poll(current)
  } catch (exception) {
    if (current === attempt && !disposed) { status.value = 'error'; error.value = exception.response ? getApiErrorMessage(exception) : 'The server could not be reached. Your settings are kept. Try again.' }
  }
}
async function cancel() {
  attempt++; clearTimeout(timer)
  const url = jobUrl.value
  jobUrl.value = ''; status.value = 'idle'; error.value = ''; notice.value = 'Export cancelled.'
  if (url) {
    try { await api.delete(url, requestConfig) }
    catch { if (!disposed) notice.value = 'The cancel request could not reach the server. The render may finish there.' }
  }
}
watch(busy, value => emit('busy', value))
watch([options, branding, logoData], () => {
  if (!busy.value) {
    if (jobUrl.value && status.value === 'error') void api.delete(jobUrl.value, requestConfig).catch(() => {})
    jobUrl.value = ''; status.value = 'idle'; error.value = ''; notice.value = ''
  }
  preview(); clearTimeout(preferenceTimer); preferenceTimer = setTimeout(savePreferences, 400)
}, { deep: true })
onMounted(async () => {
  firstControl.value?.focus({ preventScroll: true })
  if (preferenceKey) {
    try {
      const saved = JSON.parse(localStorage.getItem(preferenceKey) || 'null')
      if (saved) {
        if (layouts.some(item => item.value === saved.mode)) options.mode = saved.mode
        if (['source', '3:4', '1:1', '16:9'].includes(saved.aspect)) options.aspect = saved.aspect
        if ([saved.wipe_start, saved.wipe_duration].every(Number.isFinite) && saved.wipe_start >= 0 && saved.wipe_duration > 0 && saved.wipe_start + saved.wipe_duration <= 1) {
          options.wipe_start = saved.wipe_start; options.wipe_duration = saved.wipe_duration
        }
        const b = saved.branding || {}
        branding.labels = b.labels === true
        for (const key of ['before', 'after']) if (typeof b[key] === 'string') branding[key] = b[key].slice(0, 40)
        if (corners.some(c => c.value === b.corner)) branding.corner = b.corner
        if (Number.isFinite(b.size)) branding.size = Math.max(5, Math.min(25, b.size))
        if (typeof saved.logo === 'string' && saved.logo.startsWith('data:image/png;base64,') && saved.logo.length < 3_000_000) {
          logoLoading.value = true
          const restored = await loadLogo(saved.logo)
          if (!disposed && logoAttempt === 0) { logo = restored; logoData.value = saved.logo }
        }
      }
    } catch { /* Ignore invalid preferences. */ }
    finally { logoLoading.value = false }
  }
  if (!disposed) preview()
})
onBeforeUnmount(() => {
  disposed = true; logoAttempt++; cancelAnimationFrame(previewRaf); clearTimeout(timer); clearTimeout(preferenceTimer); savePreferences()
  if (busy.value || status.value === 'error') void cancel()
})
</script>

<style scoped>
.comparison-export { width: clamp(280px, 38%, 344px); flex: 0 0 clamp(280px, 38%, 344px); min-height: 0; display: flex; flex-direction: column; background: var(--v-surface-panel); border-left: 1px solid var(--v-border); }
.export-heading { display: grid; gap: var(--v-space-2); padding: var(--v-space-5); }
.export-heading h2 { margin: 0; font-size: 18px; font-weight: 650; letter-spacing: -.02em; }
.export-note, .export-output, .export-section-heading > span, .export-unit { color: var(--v-text-secondary); font-size: 12px; }
.export-form { min-height: 0; overflow-y: auto; overscroll-behavior: contain; flex: 1; }
.export-fields { border: 0; padding: 0; margin: 0; min-width: 0; }
.export-section { display: grid; gap: var(--v-space-2); padding: var(--v-space-4) var(--v-space-5); border-top: 1px solid var(--v-border); }
.export-pair { display: grid; grid-template-columns: 1fr auto 1fr; gap: var(--v-space-3); align-items: center; }
.export-pair > div { display: grid; gap: var(--v-space-1); min-width: 0; }
.export-pair > div:last-child { text-align: right; }
.export-pair span { font-size: 12px; color: var(--v-text-secondary); }
.export-pair strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 550; }
.export-layout { display: flex; }
.export-layout > button { flex: 1; white-space: nowrap; font-weight: 550; }
.export-layout > button.active { color: var(--v-accent); background: var(--v-control-bg-active); border-color: var(--v-control-border-hover); box-shadow: none; }
.export-section-heading, .export-progress > div { display: flex; align-items: baseline; justify-content: space-between; gap: var(--v-space-2); }
.export-section h3 { margin: 0; font-size: 13px; font-weight: 600; }
.export-field-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: var(--v-space-3); }
.export-field-grid label { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--v-space-2); font-size: 12px; }
.export-field-grid .v-input { width: 100%; min-width: 0; }
.comparison-export .v-input { font-variant-numeric: tabular-nums; }
.export-frame-choice { display: grid; grid-template-columns: 1fr auto auto; gap: var(--v-space-2); align-items: center; font-size: 12px; }
.export-frame-choice .v-input { width: 76px; text-align: center; grid-column: 2; grid-row: 1; }
.export-frame-choice .export-unit { grid-column: 3; grid-row: 1; }
.export-length { display: grid; grid-template-columns: 1fr auto; gap: var(--v-space-2); font-size: 12px; }
.export-aspect { display: flex; justify-content: space-between; align-items: center; gap: var(--v-space-3); font-size: 13px; }
.export-aspect .v-input { width: auto; min-width: 0; max-width: 65%; }
.export-number-unit { position: relative; grid-column: 1 / -1; }
.export-number-unit .v-input { width: 100%; padding-right: 76px; }
.export-number-unit > span { position: absolute; right: var(--v-space-5); top: 50%; transform: translateY(-50%); color: var(--v-text-secondary); pointer-events: none; }
.export-wipe-map { display: grid; gap: var(--v-space-2); margin-top: var(--v-space-1); }
.export-wipe-track { height: 6px; position: relative; background: var(--v-control-bg); border-radius: var(--v-radius-sm); overflow: hidden; }
.export-wipe-track > span { height: 100%; position: absolute; background: var(--v-accent); border-radius: inherit; }
.export-wipe-map > div:last-child { display: flex; justify-content: space-between; color: var(--v-text-secondary); font-size: 12px; }
.export-details summary { display: flex; align-items: center; justify-content: space-between; list-style: none; cursor: pointer; font-size: 13px; font-weight: 600; }
.export-details summary::-webkit-details-marker { display: none; }
.export-details summary .icon { width: 16px; height: 16px; color: var(--v-text-secondary); }
.export-details[open] summary .icon { transform: rotate(180deg); }
.export-branding { display: grid; gap: var(--v-space-3); margin-top: var(--v-space-4); }
.export-note, .export-error { margin: 0; line-height: 1.5; }
.export-error { color: var(--v-danger); font-size: 12px; }
.export-logo-heading { margin-top: var(--v-space-3); }
.export-logo-row { display: flex; align-items: center; flex-wrap: wrap; gap: var(--v-space-2); }
.export-logo { width: 40px; height: 40px; object-fit: contain; border-radius: var(--v-radius-sm); background: var(--v-surface-inset); }
.export-file-input { display: none; }
.export-size { width: 100%; height: 24px; margin: 0; appearance: none; background: transparent; cursor: pointer; }
.export-size::-webkit-slider-runnable-track { height: 4px; border-radius: var(--v-radius-full); background: var(--v-text-muted); }
.export-size::-moz-range-track { height: 4px; border-radius: var(--v-radius-full); background: var(--v-text-muted); }
.export-size::-webkit-slider-thumb { appearance: none; width: 14px; height: 14px; margin-top: -5px; border-radius: var(--v-radius-full); background: var(--v-accent); }
.export-size::-moz-range-thumb { width: 14px; height: 14px; border: 0; border-radius: var(--v-radius-full); background: var(--v-accent); }
.export-size:disabled { opacity: .45; cursor: default; }
.export-footer { display: grid; gap: var(--v-space-3); padding: var(--v-space-5); padding-bottom: max(var(--v-space-5), env(safe-area-inset-bottom)); border-top: 1px solid var(--v-border); }
.export-output { display: flex; flex-wrap: wrap; gap: var(--v-space-2); align-items: center; }
.export-output strong { color: var(--v-text-primary); font-weight: 600; }
.export-progress { display: grid; gap: var(--v-space-3); font-size: 12px; }
.export-progress progress { width: 100%; height: 4px; accent-color: var(--v-accent); }
.export-submit { width: 100%; min-height: 40px; text-decoration: none; }
@media (max-height: 560px) and (min-width: 769px) {
  .export-heading { display: none; }
  .export-section, .export-footer { padding: var(--v-space-3) var(--v-space-4); }
}
@media (max-width: 768px) {
  .comparison-export { width: 100%; flex: 1 1 0; border-left: 0; border-top: 1px solid var(--v-border); overflow: hidden; }
  .export-heading { display: none; }
  .export-section { padding: var(--v-space-4); }
  .export-section:first-child { border-top: 0; }
  .export-footer { padding: var(--v-space-3) var(--v-space-4); padding-bottom: max(var(--v-space-3), env(safe-area-inset-bottom)); }
  .comparison-export .v-input { min-height: 44px; font-size: 16px; }
  .export-size { height: 44px; }
  .export-section .v-btn, .export-layout .v-view-toggle-btn, .export-submit, .export-progress .v-btn, .export-details summary { min-height: 44px; }
}
</style>
