<template>
  <div class="storage-connect">
    <div class="storage-connect-actions">
      <button type="button" class="v-btn" :class="secondary ? 'v-btn-secondary' : 'v-btn-primary'" :disabled="busy" @click="openPicker">
        <svg class="icon" aria-hidden="true"><use href="#icon-plus" /></svg>
        {{ busy ? 'Connecting storage…' : 'Add storage' }}
      </button>
      <button v-if="hasOffline && supported" type="button" class="v-btn v-btn-secondary" :disabled="busy || loading" @click="showReconnect = true">
        Reconnect drives
      </button>
    </div>
    <p v-if="message" class="v-inline-note" role="status">{{ message }}</p>
    <p v-if="error" class="v-field-help is-error" role="alert">{{ error }}</p>

    <VModal :model-value="open" size="md" aria-label="Add storage" @update:model-value="open = $event">
      <template #header>
        <VModalHeader title="Add storage" subtitle="Choose a drive connected to the computer running Vueio—not the device browsing this page." @close="open = false" />
      </template>
      <div class="v-modal-stack">
        <div class="drive-heading">
          <h3 class="v-modal-section-title">Connected to your computer</h3>
          <button class="v-btn v-btn-ghost v-btn-sm" type="button" :disabled="loading || busy" @click="refresh">
            {{ loading ? 'Checking…' : 'Check again' }}
          </button>
        </div>
        <p v-if="loading && !drives.length" class="v-inline-note" role="status">Looking for connected drives…</p>
        <div v-else-if="!supported" class="v-modal-section">
          <h3 class="v-modal-section-title">Connect storage on the Vueio computer</h3>
          <p class="v-modal-section-copy">{{ hostMessage }}</p>
          <template v-if="hostReason !== 'custom_mounts'">
            <p class="v-modal-section-copy">Registered locations still work. On a managed Linux installation, install the latest release and enable its host helper:</p>
            <code class="drive-command">sudo vueioctl updater enable</code>
            <p class="v-modal-section-copy">On the Mac preview, run the command without sudo and keep Docker Desktop open. Windows installation is not available yet. Docker only exposes folders that you explicitly share with it.</p>
          </template>
        </div>
        <p v-else-if="!drives.length" class="v-inline-note">No additional drives found. Plug in and unlock your drive on the Vueio computer, then check again. Storage already connected to Vueio is shown in Settings.</p>
        <div v-else class="drive-options" role="radiogroup" aria-label="Available drives">
          <label v-for="drive in drives" :key="drive.id" class="drive-option" :class="{ selected: selectedId === drive.id }">
            <input v-model="selectedId" type="radio" name="storage-drive" :value="drive.id" :disabled="busy || (drive.read_only && !drive.reconnect_label)" @change="choose(drive)" />
            <span class="drive-option-copy">
              <strong>{{ drive.label }}</strong>
              <span>{{ drive.path }}</span>
              <span>{{ formatSizeBytes(drive.free_bytes) }} free of {{ formatSizeBytes(drive.total_bytes) }}</span>
              <span v-if="drive.reconnect_label">Reconnect {{ drive.reconnect_label }} · original drive recognized</span>
              <span v-else-if="drive.read_only">Unlock write access on the computer to connect this drive.</span>
            </span>
            <svg class="icon" aria-hidden="true"><use href="#icon-folder" /></svg>
          </label>
        </div>
        <form v-if="selected" id="storage-connect-form" class="v-modal-section" @submit.prevent="connect({ action: 'add', id: selected.id, label: label.trim(), mode })">
          <VField label="Name in Vueio" hint="Letters, numbers, spaces, dots, dashes and underscores.">
            <input v-model="label" class="v-input" required maxlength="80" pattern="[A-Za-z0-9][A-Za-z0-9 ._\-]*" :disabled="busy || Boolean(selected.reconnect_label)" />
          </VField>
          <VField v-if="!selected.reconnect_label" label="File access" :hint="mode === 'rw' ? 'Allow uploads and new project folders.' : 'Review and download existing files. No uploads or file changes.'">
            <select v-model="mode" class="v-input" :disabled="busy">
              <option value="rw">Read and write</option>
              <option value="ro">Read only</option>
            </select>
          </VField>
          <p class="v-modal-section-copy">{{ selected.reconnect_label ? 'Your storage name, projects and access mode are kept.' : 'Vueio saves a small identity file on the drive. Existing files stay in place.' }} Connecting storage briefly restarts Vueio, so finish any uploads first.</p>
        </form>
        <p v-if="error" class="v-field-help is-error" role="alert">{{ error }}</p>
      </div>
      <template #footer>
        <button class="v-btn v-btn-secondary" type="button" @click="open = false">Close</button>
        <button v-if="selected" class="v-btn v-btn-primary" type="submit" form="storage-connect-form" :disabled="busy || loading || !label.trim()">
          {{ selected.reconnect_label ? 'Reconnect drive' : 'Connect drive' }}
        </button>
      </template>
    </VModal>

    <VModal :model-value="showReconnect" size="sm" aria-label="Reconnect storage" @update:model-value="showReconnect = $event">
      <template #header><VModalHeader title="Reconnect storage" @close="showReconnect = false" /></template>
      <p class="v-modal-section-copy">Connect the original drives to the Vueio computer first. Vueio will verify their identities and restart briefly. Missing drives stay offline; projects and files are not deleted.</p>
      <p class="v-modal-section-copy">Finish any uploads before continuing.</p>
      <template #footer>
        <button class="v-btn v-btn-secondary" type="button" @click="showReconnect = false">Cancel</button>
        <button class="v-btn v-btn-primary" type="button" :disabled="busy" @click="connect({ action: 'reconnect' })">Reconnect</button>
      </template>
    </VModal>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { VField, VModal, VModalHeader } from '../primitives'
import api, { getApiErrorMessage } from '../../lib/api'
import { formatSizeBytes } from '../../utils/formatters'

defineProps({ hasOffline: Boolean, secondary: Boolean })
const emit = defineEmits(['changed'])
const open = ref(false)
const showReconnect = ref(false)
const loading = ref(false)
const busy = ref(false)
const supported = ref(false)
const hostMessage = ref('')
const hostReason = ref('')
const drives = ref([])
const selectedId = ref('')
const selected = computed(() => drives.value.find(drive => drive.id === selectedId.value))
const label = ref('')
const mode = ref('rw')
const message = ref('')
const error = ref('')
const controller = new AbortController()
let timer
let operationStarted = 0

function choose(drive) {
  label.value = drive.reconnect_label || drive.label.replace(/[^A-Za-z0-9 ._-]/g, '').replace(/^[^A-Za-z0-9]+/, '').slice(0, 80) || 'Media drive'
  error.value = ''
}

async function refresh() {
  if (loading.value || controller.signal.aborted) return
  clearTimeout(timer)
  loading.value = true
  try {
    const { data } = await api.get('/api/admin/storage/devices', { signal: controller.signal })
    supported.value = data.supported === true
    hostMessage.value = data.message
    hostReason.value = data.reason || ''
    drives.value = Array.isArray(data.drives) ? data.drives : []
    const state = data.operation?.state
    if (state === 'running') {
      busy.value = true
      operationStarted ||= Date.now()
      message.value = data.operation.message
    } else if (supported.value && (busy.value || state === 'failed')) {
      busy.value = false
      if (state === 'failed') {
        message.value = ''
        error.value = data.operation.message
      } else {
        message.value = data.operation?.message || 'Storage was checked. Review the connected locations below.'
      }
      emit('changed')
    }
  } catch (reason) {
    if (!controller.signal.aborted && !busy.value) error.value = getApiErrorMessage(reason, 'Could not check for drives.')
  } finally {
    loading.value = false
    if (busy.value && !controller.signal.aborted) {
      if (Date.now() - operationStarted < 120000) timer = setTimeout(refresh, 2500)
      else {
        busy.value = false
        error.value = 'Vueio has not finished reconnecting. Check the Vueio computer before trying again. No request was automatically repeated.'
        emit('changed')
      }
    }
  }
}

function openPicker() {
  selectedId.value = ''
  error.value = ''
  open.value = true
  refresh()
}

async function connect(payload) {
  if (busy.value) return
  busy.value = true
  operationStarted = Date.now()
  error.value = ''
  message.value = ''
  try {
    const { data } = await api.post('/api/admin/storage/devices', payload, { signal: controller.signal })
    message.value = data.message
    open.value = false
    showReconnect.value = false
    timer = setTimeout(refresh, 2500)
  } catch (reason) {
    busy.value = false
    if (!controller.signal.aborted) error.value = reason.response
      ? getApiErrorMessage(reason, 'The drive could not be connected.')
      : 'The connection could not be confirmed. Vueio may be restarting. Check the storage list before trying again.'
    emit('changed')
  }
}

defineExpose({ refresh })
onMounted(refresh)
onUnmounted(() => { controller.abort(); clearTimeout(timer) })
</script>

<style scoped>
.storage-connect, .drive-options { display: grid; gap: var(--v-space-3); }
.storage-connect-actions, .drive-heading { display: flex; align-items: center; justify-content: space-between; gap: var(--v-space-3); flex-wrap: wrap; }
.storage-connect-actions { justify-content: flex-start; }
.drive-option { display: flex; align-items: center; gap: var(--v-space-3); padding: var(--v-space-4); border: 1px solid var(--v-control-border); border-radius: var(--v-radius-md); background: var(--v-surface-raised); cursor: pointer; }
.drive-option.selected { border-color: var(--v-border-focus); background: var(--v-accent-subtle); }
.drive-option:focus-within { outline: 2px solid var(--v-accent); outline-offset: 2px; }
.drive-option input { accent-color: var(--v-accent); }
.drive-option-copy { display: grid; flex: 1; gap: var(--v-space-1); min-width: 0; overflow-wrap: anywhere; }
.drive-option-copy span { color: var(--v-text-muted); font-size: var(--v-text-sm); }
.drive-option-copy strong { font-size: var(--v-text-md); }
.drive-option > .icon { color: var(--v-accent); flex-shrink: 0; }
.drive-command { display: block; padding: var(--v-space-3); border-radius: var(--v-radius-md); background: var(--v-surface-inset); overflow-wrap: anywhere; }
@media (max-width: 548px) {
  .storage-connect-actions > .v-btn { width: 100%; min-height: var(--v-btn-height-lg); }
}
</style>
