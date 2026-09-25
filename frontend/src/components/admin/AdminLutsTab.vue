<template>
  <section class="admin-section settings-stack">
    <AdminSettingsHeader
      title="Preview LUTs"
      description="Color looks that your team and share visitors can apply while they review. Source files and downloads do not change."
      icon="#icon-color"
    >
      <button class="v-btn v-btn-primary v-btn-sm" type="button" :disabled="busy || loading" aria-describedby="luts-file-hint" @click="fileInput?.click()">
        <svg class="icon"><use href="#icon-upload" /></svg>
        {{ uploading ? 'Uploading…' : 'Upload LUTs' }}
      </button>
    </AdminSettingsHeader>
    <input ref="fileInput" type="file" accept=".cube" multiple hidden @change="uploadFiles" />

    <section class="settings-card">
      <header class="settings-card-head">
        <div>
          <h3>Saved LUTs <span v-if="luts.length" class="settings-count-pill">{{ luts.length }}</span></h3>
          <p id="luts-file-hint">3D .cube files with 2 to 65 points, up to 32 MiB each. A LUT loaded in a viewer is temporary.</p>
        </div>
        <div class="settings-card-head-actions">
          <button class="v-btn v-btn-ghost v-btn-sm" type="button" :disabled="busy || loading" @click="loadLuts">
            <svg class="icon" :class="{ spinning: loading }"><use href="#icon-refresh" /></svg>
            Refresh
          </button>
        </div>
      </header>

      <div v-if="loadError || failures.length || removeError" class="settings-card-body luts-alerts" role="alert">
        <p v-if="loadError">{{ loadError }}</p>
        <div v-if="failures.length">
          <p>These files could not be uploaded:</p>
          <ul><li v-for="(failure, index) in failures" :key="index"><strong>{{ failure.name }}</strong>: {{ failure.reason }}</li></ul>
        </div>
        <p v-if="removeError">{{ removeError }}</p>
      </div>

      <p v-if="loading && !luts.length" class="settings-empty" role="status">Loading saved LUTs…</p>
      <div v-else-if="!luts.length && !loadError" class="settings-empty">
        <strong>No LUTs yet</strong>
        <span>Upload .cube files to make them available in Color preview.</span>
      </div>
      <ul v-if="luts.length" class="settings-list" aria-label="Saved LUTs">
        <li v-for="lut in luts" :key="lut.id" class="settings-list-row">
          <span class="settings-list-mark" aria-hidden="true"><svg class="icon"><use href="#icon-color" /></svg></span>
          <div class="settings-list-main">
            <div class="settings-list-title"><span>{{ lut.name }}</span></div>
            <div class="settings-list-meta">
              <span>{{ lut.size }}-point 3D LUT</span>
              <span>{{ formatSizeBytes(lut.byte_size) }}</span>
            </div>
          </div>
          <div class="settings-list-actions">
            <button class="v-btn v-btn-ghost v-btn-sm luts-remove" type="button" :disabled="busy || loading" :aria-label="`Remove ${lut.name}`" @click="removeLut(lut)">
              {{ removingId === lut.id ? 'Removing…' : 'Remove' }}
            </button>
          </div>
        </li>
      </ul>

      <footer v-if="uploadProgress || message" class="settings-card-foot">
        <p role="status">{{ uploadProgress || message }}</p>
      </footer>
    </section>
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
.luts-alerts {
  gap: var(--v-space-2);
  border-bottom: 1px solid var(--v-divider-subtle);
  color: var(--v-warning);
  font-size: var(--v-text-sm);
  overflow-wrap: anywhere;
}

.luts-alerts p {
  margin: 0;
  line-height: 1.5;
}

.luts-alerts ul {
  margin: var(--v-space-2) 0 0;
  padding-left: var(--v-space-4);
  list-style: disc;
}

.luts-remove {
  color: var(--v-danger-text);
}

.icon.spinning {
  animation: v-spin 0.8s linear infinite;
}
</style>
