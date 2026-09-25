<template>
  <div class="settings-stack">
    <section class="settings-card" aria-labelledby="processing-title">
      <header class="settings-card-head">
        <div>
          <h3 id="processing-title">Media processing</h3>
          <p>One choice for thumbnails, video previews, comparisons, and exports. Originals stay unchanged.</p>
        </div>
        <div class="settings-card-head-actions">
          <button type="button" class="v-btn v-btn-secondary v-btn-sm" :disabled="busy || loading" @click="checkHardware">
            <svg class="icon" :class="{ spinning: hardwareChecking }" aria-hidden="true"><use href="#icon-refresh" /></svg>
            {{ hardwareChecking ? 'Checking hardware…' : 'Check again' }}
          </button>
        </div>
      </header>

      <div v-if="loading" class="settings-card-body"><p class="processing-muted" role="status">Loading processing settings…</p></div>
      <div v-else-if="status" class="settings-card-body">
        <fieldset class="processing-options" :disabled="busy">
          <legend class="v-sr-only">Processing mode</legend>
          <label class="processing-option" :class="{ selected: mode === 'cpu' }">
            <input v-model="mode" type="radio" name="media-processing" value="cpu" />
            <span><strong>CPU <small>Default</small></strong><span>Use the processor. No graphics setup needed.</span></span>
          </label>
          <label class="processing-option" :class="{ selected: mode === 'gpu', unavailable: !workingDevices.length }">
            <input v-model="mode" type="radio" name="media-processing" value="gpu" :disabled="!workingDevices.length" />
            <span><strong>GPU <small>CPU fallback</small></strong><span>{{ selectedDevice?.name || 'Use your graphics hardware where supported.' }}</span></span>
          </label>
        </fieldset>

        <VField v-if="mode === 'gpu' && workingDevices.length > 1" label="Graphics device">
          <select v-model="device" class="v-input" :disabled="busy"><option v-for="item in workingDevices" :key="item.id" :value="item.id">{{ item.name }}</option></select>
        </VField>

        <div class="processing-hardware" aria-live="polite">
          <p v-if="hardwareChecking" role="status">Checking each preview task. You can leave this page while the check runs.</p>
          <p v-else-if="status.check_error" class="processing-error" role="alert">{{ status.check_error }}</p>
          <template v-if="status.devices.length">
            <article v-for="item in status.devices" :key="item.id" class="processing-device">
              <div><strong>{{ item.name }}</strong><span class="processing-result" :class="{ passed: item.encoding }">{{ deviceState(item) }}</span></div>
              <p v-if="status.devices.length > 1 && item.location" class="processing-location">Device {{ item.location }}</p>
              <p>{{ item.message }}</p>
              <dl v-if="item.id === device && item.encoding && item.capabilities" class="processing-capabilities" :aria-label="`${item.name} task checks`">
                <div v-for="task in tasks" :key="task.kind">
                  <dt>{{ task.label }}</dt>
                  <dd :class="{ passed: item.capabilities[task.kind] }">{{ item.capabilities[task.kind] ? 'GPU ready' : 'Uses CPU' }}</dd>
                </div>
              </dl>
            </article>
          </template>
          <p v-else-if="status.checked_at && !hardwareChecking">No graphics device is available to Vueio. CPU processing still works. Check the host driver and container GPU access.</p>
          <p v-if="mode === 'gpu' && !selectedDevice && !hardwareChecking" class="processing-fallback">Your saved GPU is unavailable. New jobs use CPU until it is available again.</p>
          <p v-if="mode === 'gpu'" class="processing-note">The GPU handles supported video tasks. Audio, some source formats, and image processing still need CPU. Failed GPU jobs retry on CPU.</p>
        </div>

        <div v-if="status.activity.length" class="processing-activity">
          <h4>Recent processing <span>This session</span></h4>
          <div v-for="job in status.activity.slice(0, 3)" :key="job.id" class="processing-job">
            <span>{{ tasks.find(task => task.kind === job.kind)?.label || 'Video preview' }}</span>
            <strong>{{ job.device }}</strong>
            <span :class="{ 'processing-fallback': job.fallback }">{{ job.fallback ? 'CPU fallback · ' : '' }}{{ job.state }}</span>
          </div>
        </div>
      </div>
      <footer v-if="status && !loading" class="settings-card-foot">
        <p v-if="error" class="is-error" role="alert">{{ error }}</p>
        <p v-else-if="message" role="status">{{ message }}</p>
        <p v-else>Applies to new jobs only. Existing previews and running jobs do not change.</p>
        <button type="button" class="v-btn v-btn-primary v-btn-sm" :disabled="busy || !changed || (mode === 'gpu' && !workingDevices.some(item => item.id === device))" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
      </footer>
      <p v-else-if="error" class="settings-card-body processing-error" role="alert">{{ error }}</p>
    </section>

    <section class="settings-card" aria-labelledby="preview-cache-title">
      <header class="settings-card-head">
        <div>
          <h3 id="preview-cache-title">Preview cache</h3>
          <p>Previews use disk space. Vueio rebuilds a preview from the original file when someone opens it.</p>
        </div>
      </header>
      <VSwitch
        v-if="status && typeof status.auto_cleanup_previews === 'boolean'"
        class="settings-switch-row"
        :model-value="cleanupEnabled"
        :disabled="busy"
        label="Clear unused previews"
        :hint="cleanupSaving ? 'Saving…' : cleanupError || cleanupMessage || 'Remove video previews after 30 days without a view. Thumbnails stay. The cache size limit still applies.'"
        @update:modelValue="saveCleanup"
      />
      <slot name="cache" />
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import api, { getApiErrorMessage } from '../../lib/api'
import VField from '../primitives/VField.vue'
import VSwitch from '../primitives/VSwitch.vue'

const status = ref(null)
const mode = ref('cpu')
const device = ref('')
const loading = ref(true)
const checking = ref(false)
const saving = ref(false)
const cleanupSaving = ref(false)
const cleanupEnabled = ref(true)
const cleanupMessage = ref('')
const cleanupError = ref('')
const error = ref('')
const message = ref('')
const hardwareChecking = computed(() => checking.value || status.value?.checking)
const busy = computed(() => hardwareChecking.value || saving.value || cleanupSaving.value)
const workingDevices = computed(() => (status.value?.devices || []).filter(item => item.encoding))
const selectedDevice = computed(() => workingDevices.value.find(item => item.id === device.value))
const changed = computed(() => status.value && (mode.value !== status.value.mode || (mode.value === 'gpu' && device.value !== status.value.device)))
const tasks = [
  { kind: 'thumbnail', label: 'Thumbnails' },
  { kind: 'mp4', label: 'Video previews' },
  { kind: 'hls', label: 'Streaming previews' },
  { kind: 'comparison', label: 'Comparisons' },
  { kind: 'comparison_export', label: 'Comparison exports' },
]
let timer
let disposed = false
let requestGeneration = 0
let requestedCheck = false

function deviceState(item) {
  if (!item.encoding) return 'Setup needed'
  return item.capabilities && tasks.every(task => item.capabilities[task.kind]) ? 'Ready' : 'Partly ready'
}

function scheduleRefresh() {
  clearTimeout(timer)
  timer = setTimeout(() => {
    if (disposed) return
    if (checking.value || saving.value || cleanupSaving.value || document.hidden) scheduleRefresh()
    else void load()
  }, status.value?.checking ? 1000 : 5000)
}

function accept(data, reset = false) {
  status.value = data
  if (!cleanupSaving.value) cleanupEnabled.value = data.auto_cleanup_previews === true
  if (reset) { mode.value = data.mode; device.value = data.device }
  if (!device.value && workingDevices.value.length) device.value = workingDevices.value[0].id
}

async function load() {
  const generation = requestGeneration
  try {
    const { data } = await api.get('/api/admin/media-processing')
    if (!disposed && generation === requestGeneration) {
      accept(data, !status.value || !changed.value)
      if (!requestedCheck && !data.checked_at && !data.checking && !data.check_error) void checkHardware()
    }
  } catch (cause) {
    if (!disposed) error.value = getApiErrorMessage(cause, 'Processing settings could not be loaded.')
  } finally {
    loading.value = false
    if (!disposed) scheduleRefresh()
  }
}

async function checkHardware() {
  if (hardwareChecking.value || disposed) return
  requestedCheck = true
  requestGeneration++
  checking.value = true; error.value = ''; message.value = ''
  try {
    const { data } = await api.post('/api/admin/media-processing/check', {}, { timeout: 60000 })
    if (!disposed) accept(data, !status.value)
  } catch (cause) {
    error.value = getApiErrorMessage(cause, 'Hardware could not be checked. CPU processing is still available.')
  } finally { checking.value = false; if (!disposed) scheduleRefresh() }
}

async function save() {
  requestGeneration++
  saving.value = true; error.value = ''; message.value = ''
  try {
    const { data } = await api.put('/api/admin/media-processing', { mode: mode.value, device: device.value })
    if (!disposed) { accept(data, true); message.value = 'Processing preference saved.' }
  } catch (cause) {
    error.value = getApiErrorMessage(cause, 'Processing preference could not be saved.')
  } finally { saving.value = false }
}

async function saveCleanup(enabled) {
  requestGeneration++
  cleanupEnabled.value = enabled
  cleanupSaving.value = true; cleanupError.value = ''; cleanupMessage.value = ''
  try {
    const { data } = await api.put('/api/admin/media-processing', { auto_cleanup_previews: enabled })
    if (!disposed) {
      accept(data)
      cleanupMessage.value = enabled ? 'Automatic cleanup is on.' : 'Automatic cleanup is off.'
    }
  } catch (cause) {
    cleanupError.value = getApiErrorMessage(cause, 'Cleanup preference could not be saved. Try again.')
  } finally {
    cleanupSaving.value = false
    if (!disposed) cleanupEnabled.value = status.value.auto_cleanup_previews
  }
}

onMounted(load)
onBeforeUnmount(() => { disposed = true; clearTimeout(timer) })
</script>

<style scoped>
.processing-muted { margin: 0; color: var(--v-text-muted); }
.processing-options { display: grid; grid-template-columns: 1fr 1fr; gap: var(--v-space-3); min-width: 0; margin: 0; padding: 0; border: 0; }
.processing-option { display: flex; align-items: start; gap: var(--v-space-3); padding: 14px; border: 1px solid var(--v-control-border); border-radius: var(--v-radius-md); background: var(--v-control-bg); cursor: pointer; transition: border-color var(--v-transition-fast), background-color var(--v-transition-fast); }
.processing-option:hover { border-color: var(--v-control-border-hover); }
.processing-option.selected { border-color: color-mix(in srgb, var(--v-accent) 55%, transparent); background: var(--v-accent-subtle); }
.processing-option:focus-within { outline: 2px solid var(--v-border-focus); outline-offset: 2px; }
.processing-option.unavailable { cursor: not-allowed; opacity: 0.6; }
.processing-option input { margin-top: 2px; accent-color: var(--v-accent); }
.processing-option > span { display: grid; gap: 4px; }
.processing-option strong { display: flex; flex-wrap: wrap; align-items: center; gap: var(--v-space-2); color: var(--v-text); font-size: var(--v-text-base); font-weight: 600; }
.processing-option small { padding: 1px 7px; border-radius: var(--v-radius-full); background: color-mix(in srgb, var(--v-text) 6%, transparent); color: var(--v-text-muted); font-size: var(--v-text-xs); font-weight: 500; }
.processing-option span span { color: var(--v-text-muted); font-size: var(--v-text-sm); line-height: 1.45; }
.processing-hardware p, .processing-device p { margin: 4px 0 0; color: var(--v-text-muted); font-size: var(--v-text-sm); line-height: 1.5; }
.processing-hardware > p:first-child { margin-top: 0; }
.processing-device + .processing-device { margin-top: var(--v-space-3); }
.processing-device > div { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: var(--v-space-3); }
.processing-device strong { color: var(--v-text); font-size: var(--v-text-base); font-weight: 600; }
.processing-device { overflow-wrap: anywhere; }
.processing-capabilities { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--v-space-2) var(--v-space-4); margin: var(--v-space-3) 0 0; }
.processing-capabilities > div { display: flex; align-items: baseline; justify-content: space-between; gap: var(--v-space-2); padding-block: var(--v-space-2); border-bottom: 1px solid var(--v-divider-subtle); font-size: var(--v-text-sm); }
.processing-capabilities dt { color: var(--v-text-secondary); }
.processing-capabilities dd { margin: 0; flex-shrink: 0; color: var(--v-text-muted); }
.processing-capabilities dd.passed { color: var(--v-accent); }
.processing-result { color: var(--v-text-muted); font-size: var(--v-text-sm); }
.processing-result.passed { color: var(--v-accent); }
.processing-activity { padding-top: var(--v-space-3); border-top: 1px solid var(--v-divider-subtle); }
.processing-activity h4 { margin: 0; color: var(--v-text); font-size: var(--v-text-base); font-weight: 600; }
.processing-activity h4 span { margin-left: var(--v-space-2); color: var(--v-text-muted); font-size: var(--v-text-sm); font-weight: 400; }
.processing-job { display: grid; grid-template-columns: 1fr 1fr auto; gap: var(--v-space-3); padding-top: var(--v-space-2); color: var(--v-text-secondary); font-size: var(--v-text-sm); }
.processing-job strong { font-weight: 500; overflow-wrap: anywhere; }
.processing-fallback { color: var(--v-warning); }
.processing-error { margin: 0; color: var(--v-danger-text); }
@media (max-width: 600px) {
  .processing-options { grid-template-columns: 1fr; }
  .processing-capabilities { grid-template-columns: 1fr; }
  .processing-job { grid-template-columns: 1fr 1fr; }
  .processing-job > span:last-child { grid-column: 1 / -1; }
}
</style>
