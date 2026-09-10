<template>
  <section class="processing-panel v-surface-panel" aria-labelledby="processing-title">
    <header class="processing-heading">
      <div>
        <h3 id="processing-title">Preview processing</h3>
        <p>Choose how Vueio creates video previews and thumbnails. Original files stay unchanged.</p>
      </div>
      <button type="button" class="v-btn v-btn-secondary v-btn-sm" :disabled="busy || loading" @click="checkHardware">
        <svg class="icon" :class="{ spinning: checking }" aria-hidden="true"><use href="#icon-refresh" /></svg>
        {{ checking ? 'Checking hardware…' : 'Check hardware' }}
      </button>
    </header>

    <p v-if="loading" role="status">Loading processing settings…</p>
    <template v-else-if="status">
      <fieldset class="processing-options" :disabled="busy">
        <legend class="v-sr-only">Processing mode</legend>
        <label class="processing-option" :class="{ selected: mode === 'cpu' }">
          <input v-model="mode" type="radio" name="media-processing" value="cpu" />
          <span><strong>CPU <small>Default</small></strong><span>Use the processor. No graphics setup needed.</span></span>
        </label>
        <label class="processing-option" :class="{ selected: mode === 'gpu', unavailable: !workingDevices.length }">
          <input v-model="mode" type="radio" name="media-processing" value="gpu" :disabled="!workingDevices.length" />
          <span><strong>GPU <small>CPU fallback</small></strong><span>Use verified video hardware. Retry on CPU if a job fails.</span></span>
        </label>
      </fieldset>

      <VField v-if="mode === 'gpu' && workingDevices.length > 1" label="Graphics device">
        <select v-model="device" class="v-input" :disabled="busy"><option v-for="item in workingDevices" :key="item.id" :value="item.id">{{ item.name }}</option></select>
      </VField>

      <div class="processing-hardware" aria-live="polite">
        <template v-if="status.devices.length">
          <article v-for="item in status.devices" :key="item.id" class="processing-device">
            <div><strong>{{ item.name }}</strong><span class="processing-result" :class="{ passed: item.encoding }">{{ item.encoding ? 'Encoding verified' : 'Not available' }}</span></div>
            <p>{{ item.message }}</p>
          </article>
        </template>
        <p v-else-if="status.checked_at">No usable graphics device was found inside Vueio. CPU processing is available. Check the graphics drivers and container access on this computer.</p>
        <p v-else>Check hardware to detect your graphics device and test a short encode. CPU stays selected unless you change it.</p>
        <p v-if="mode === 'gpu'" class="processing-note">Video encoding uses the GPU. Video decoding and scaling can still use CPU. Unsupported thumbnail formats also use CPU.</p>
      </div>

      <footer class="processing-actions">
        <button type="button" class="v-btn v-btn-primary v-btn-sm" :disabled="busy || !changed || (mode === 'gpu' && !workingDevices.some(item => item.id === device))" @click="save">{{ saving ? 'Saving…' : 'Save processing' }}</button>
        <span>New jobs only. Existing previews and running jobs stay unchanged.</span>
      </footer>

      <div v-if="status.activity.length" class="processing-activity">
        <h4>Recent processing <span>This session</span></h4>
        <div v-for="job in status.activity.slice(0, 3)" :key="job.id" class="processing-job">
          <span>{{ job.kind === 'thumbnail' ? 'Thumbnail' : 'Video preview' }}</span>
          <strong>{{ job.device }}</strong>
          <span :class="{ 'processing-fallback': job.fallback }">{{ job.fallback ? 'CPU fallback · ' : '' }}{{ job.state }}</span>
        </div>
      </div>
    </template>
    <p v-if="error" class="processing-error" role="alert">{{ error }}</p>
    <p v-if="message" role="status">{{ message }}</p>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import api, { getApiErrorMessage } from '../../lib/api'
import VField from '../primitives/VField.vue'

const status = ref(null)
const mode = ref('cpu')
const device = ref('')
const loading = ref(true)
const checking = ref(false)
const saving = ref(false)
const error = ref('')
const message = ref('')
const busy = computed(() => checking.value || saving.value)
const workingDevices = computed(() => (status.value?.devices || []).filter(item => item.encoding))
const changed = computed(() => status.value && (mode.value !== status.value.mode || (mode.value === 'gpu' && device.value !== status.value.device)))
let timer
let disposed = false

function scheduleRefresh() {
  timer = setTimeout(() => {
    if (disposed) return
    if (busy.value || document.hidden) scheduleRefresh()
    else void load()
  }, 5000)
}

function accept(data, reset = false) {
  status.value = data
  if (reset) { mode.value = data.mode; device.value = data.device }
  if (!device.value && workingDevices.value.length) device.value = workingDevices.value[0].id
}

async function load() {
  try {
    const { data } = await api.get('/api/admin/media-processing')
    if (!disposed) accept(data, loading.value)
  } catch (cause) {
    if (!disposed) error.value = getApiErrorMessage(cause, 'Processing settings could not be loaded.')
  } finally {
    loading.value = false
    if (!disposed) scheduleRefresh()
  }
}

async function checkHardware() {
  checking.value = true; error.value = ''; message.value = ''
  try {
    const { data } = await api.post('/api/admin/media-processing/check', {}, { timeout: 60000 })
    if (!disposed) accept(data)
  } catch (cause) {
    error.value = getApiErrorMessage(cause, 'Hardware could not be checked. CPU processing is still available.')
  } finally { checking.value = false }
}

async function save() {
  saving.value = true; error.value = ''; message.value = ''
  try {
    const { data } = await api.put('/api/admin/media-processing', { mode: mode.value, device: device.value })
    if (!disposed) { accept(data, true); message.value = 'Processing preference saved.' }
  } catch (cause) {
    error.value = getApiErrorMessage(cause, 'Processing preference could not be saved.')
  } finally { saving.value = false }
}

onMounted(load)
onBeforeUnmount(() => { disposed = true; clearTimeout(timer) })
</script>

<style scoped>
.processing-panel { display: grid; gap: var(--v-space-4); padding: var(--v-space-5); }
.processing-heading { display: flex; align-items: start; justify-content: space-between; gap: var(--v-space-4); }
.processing-heading h3, .processing-activity h4 { margin: 0; font-size: var(--v-text-lg); }
.processing-panel p { margin: var(--v-space-2) 0 0; color: var(--v-text-secondary); line-height: 1.5; }
.processing-heading .v-btn { flex-shrink: 0; }
.processing-options { display: grid; grid-template-columns: 1fr 1fr; gap: var(--v-space-3); margin: 0; padding: 0; border: 0; min-width: 0; }
.processing-option { display: flex; align-items: start; gap: var(--v-space-3); padding: var(--v-space-4); border: 1px solid var(--v-control-border); border-radius: var(--v-radius-lg); background: var(--v-control-bg); cursor: pointer; }
.processing-option.selected { border-color: var(--v-accent); background: var(--v-accent-subtle); }
.processing-option:focus-within { outline: 2px solid var(--v-accent); outline-offset: 2px; }
.processing-option.unavailable { cursor: not-allowed; }
.processing-option input { accent-color: var(--v-accent); margin-top: 3px; }
.processing-option > span { display: grid; gap: var(--v-space-2); }
.processing-option strong { display: flex; flex-wrap: wrap; align-items: center; gap: var(--v-space-2); }
.processing-option small { font-weight: 400; color: var(--v-text-secondary); }
.processing-option span span { color: var(--v-text-secondary); line-height: 1.5; }
.processing-hardware { border-top: 1px solid var(--v-border); padding-top: var(--v-space-3); }
.processing-device + .processing-device { margin-top: var(--v-space-4); }
.processing-device > div { display: flex; align-items: center; justify-content: space-between; gap: var(--v-space-3); flex-wrap: wrap; }
.processing-result { color: var(--v-text-secondary); font-size: var(--v-text-sm); }
.processing-result.passed { color: var(--v-accent); }
.processing-note { font-size: var(--v-text-sm); }
.processing-actions { display: flex; align-items: center; gap: var(--v-space-3); }
.processing-actions span { color: var(--v-text-secondary); font-size: var(--v-text-sm); }
.processing-activity { border-top: 1px solid var(--v-border); padding-top: var(--v-space-4); }
.processing-activity h4 span { color: var(--v-text-secondary); font-size: var(--v-text-sm); font-weight: 400; margin-left: var(--v-space-2); }
.processing-job { display: grid; grid-template-columns: 1fr 1fr auto; gap: var(--v-space-3); padding-top: var(--v-space-3); font-size: var(--v-text-sm); }
.processing-job strong { font-weight: 500; overflow-wrap: anywhere; }
.processing-fallback { color: var(--v-warning); }
.processing-panel .processing-error { color: var(--v-danger); }
@media (max-width: 600px) {
  .processing-heading, .processing-actions { flex-direction: column; align-items: stretch; }
  .processing-options { grid-template-columns: 1fr; }
  .processing-job { grid-template-columns: 1fr 1fr; }
  .processing-job > span:last-child { grid-column: 1 / -1; }
}
</style>
