<template>
  <section class="admin-section luts-settings-section">
    <AdminSettingsHeader
      title="Preview LUTs"
      description="Shared preview LUTs for your team and share visitors."
      icon="#icon-color"
    >
      <button class="v-btn v-btn-ghost v-btn-sm" type="button" :disabled="busy || loading" @click="loadLuts">Refresh</button>
      <button class="v-btn v-btn-primary v-btn-sm" type="button" :disabled="busy || loading" aria-describedby="luts-file-hint" @click="fileInput?.click()">
        {{ uploading ? 'Uploading…' : 'Upload LUTs' }}
      </button>
    </AdminSettingsHeader>
    <input ref="fileInput" type="file" accept=".cube" multiple hidden @change="uploadFiles" />

    <div class="luts-body">
      <div class="luts-help">
        <p id="luts-file-hint">32 MiB per file · 3D .cube, 2–65 points</p>
        <p>Source downloads stay unchanged. LUTs loaded directly in a viewer are temporary.</p>
      </div>
      <p v-if="uploadProgress || message" class="luts-message" role="status">{{ uploadProgress || message }}</p>
      <p v-if="loadError" class="luts-error" role="alert">{{ loadError }}</p>
      <div v-if="failures.length" class="luts-errors" role="alert">
        <p>These files could not be uploaded:</p>
        <ul><li v-for="(failure, index) in failures" :key="index"><strong>{{ failure.name }}</strong>: {{ failure.reason }}</li></ul>
      </div>
      <p v-if="removeError" class="luts-error" role="alert">{{ removeError }}</p>
      <p v-if="loading && !luts.length" class="luts-empty" role="status">Loading saved LUTs…</p>
      <p v-else-if="!luts.length && !loadError" class="luts-empty">No saved LUTs yet. Upload .cube files to make them available in Color preview.</p>
      <ul v-if="luts.length" class="luts-list" aria-label="Saved LUTs">
        <li v-for="lut in luts" :key="lut.id" class="luts-row">
          <div class="luts-copy">
            <strong>{{ lut.name }}</strong>
            <span>{{ lut.size }}-point 3D LUT · {{ formatSizeBytes(lut.byte_size) }}</span>
          </div>
          <button class="v-btn v-btn-ghost v-btn-sm luts-remove" type="button" :disabled="busy || loading" :aria-label="`Remove ${lut.name}`" @click="removeLut(lut)">
            {{ removingId === lut.id ? 'Removing…' : 'Remove' }}
          </button>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import AdminSettingsHeader from './AdminSettingsHeader.vue'
import api, { getApiErrorMessage } from '../../lib/api'
import { formatSizeBytes } from '../../utils/formatters'

const luts = ref([])
const fileInput = ref(null)
const loading = ref(false)
const uploading = ref(false)
const removingId = ref(null)
const loadError = ref('')
const removeError = ref('')
const failures = ref([])
const message = ref('')
const uploadProgress = ref('')
const busy = computed(() => uploading.value || removingId.value !== null)
const controller = new AbortController()

async function loadLuts() {
  if (loading.value) return
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await api.get('/api/luts', { signal: controller.signal })
    luts.value = data.luts
  } catch (error) {
    if (!controller.signal.aborted) loadError.value = `Could not load saved LUTs: ${getApiErrorMessage(error)}`
  } finally {
    loading.value = false
  }
}

async function uploadFiles(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length || busy.value || loading.value) return
  uploading.value = true
  failures.value = []
  removeError.value = ''
  message.value = ''
  let saved = 0
  try {
    for (const [index, file] of files.entries()) {
      if (controller.signal.aborted) break
      uploadProgress.value = `Uploading ${index + 1} of ${files.length}: ${file.name}`
      try {
        if (!file.name.toLowerCase().endsWith('.cube')) throw new Error('Choose a .cube file.')
        if (file.size > 32 * 1024 * 1024) throw new Error('File exceeds 32 MiB.')
        const form = new FormData()
        form.append('file', file)
        const { data } = await api.post('/api/admin/luts', form, { signal: controller.signal })
        luts.value = [...luts.value.filter(lut => lut.id !== data.id), data]
        saved += 1
      } catch (error) {
        if (!controller.signal.aborted) failures.value.push({ name: file.name, reason: getApiErrorMessage(error) })
      }
    }
    if (!controller.signal.aborted) {
      message.value = `Uploaded ${saved} of ${files.length} LUT files.`
      await loadLuts()
    }
  } finally {
    uploadProgress.value = ''
    uploading.value = false
  }
}

async function removeLut(lut) {
  if (busy.value || loading.value) return
  removingId.value = lut.id
  removeError.value = ''
  message.value = ''
  try {
    await api.delete(`/api/admin/luts/${encodeURIComponent(lut.id)}`, { signal: controller.signal })
    luts.value = luts.value.filter(item => item.id !== lut.id)
    message.value = `Removed ${lut.name}.`
  } catch (error) {
    if (!controller.signal.aborted) removeError.value = `Could not remove ${lut.name}: ${getApiErrorMessage(error)}`
  } finally {
    removingId.value = null
  }
}

onMounted(loadLuts)
onUnmounted(() => controller.abort())
</script>

<style scoped>
.luts-body { display: grid; gap: var(--v-space-4); padding-top: var(--v-space-4); min-width: 0; }
.luts-help { display: grid; gap: var(--v-space-1); color: var(--v-text-muted); font-size: var(--v-text-sm); }
.luts-body p { margin: 0; line-height: 1.5; }
.luts-message { color: var(--v-text-secondary); overflow-wrap: anywhere; }
.luts-error,
.luts-errors { color: var(--v-warning); font-size: var(--v-text-sm); overflow-wrap: anywhere; }
.luts-errors ul { margin: var(--v-space-2) 0 0; padding-left: var(--v-space-4); list-style: disc; }
.luts-empty { padding: var(--v-space-6) var(--v-space-4); background: var(--v-surface-canvas); border: 1px solid var(--v-surface-border-soft); border-radius: var(--v-radius-md); color: var(--v-text-muted); }
.luts-list { margin: 0; padding: 0; list-style: none; }
.luts-row { display: flex; align-items: center; gap: var(--v-space-4); padding: var(--v-space-4) 0; border-bottom: 1px solid var(--v-surface-border-soft); }
.luts-row:first-child { padding-top: 0; }
.luts-copy { display: grid; gap: var(--v-space-1); min-width: 0; flex: 1; }
.luts-copy strong { font-size: var(--v-text-base); overflow-wrap: anywhere; }
.luts-copy span { color: var(--v-text-muted); font-size: var(--v-text-sm); }
.luts-remove { flex: none; color: var(--v-danger-text); }
@media (max-width: 548px) {
  .luts-row { gap: var(--v-space-2); }
  .luts-remove { min-height: var(--v-btn-height-lg); }
}
</style>
