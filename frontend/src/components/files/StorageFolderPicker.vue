<template>
  <div class="storage-picker">
    <div v-if="roots.length > 1" class="storage-picker__roots" role="tablist" aria-label="Storage root">
      <button
        v-for="root in roots"
        :key="root.id"
        type="button"
        class="v-control-pill storage-picker__root"
        :class="{ 'is-active': root.id === modelRoot }"
        :title="root.read_only ? `${root.label} is read-only` : root.label"
        @click="chooseRoot(root.id)"
      >
        <svg class="icon"><use :href="root.read_only ? '#icon-lock' : '#icon-folder'" /></svg>
        {{ root.label }}
      </button>
    </div>

    <div class="storage-picker__browser v-modal-card-soft">
      <div class="storage-picker__toolbar">
        <button
          type="button"
          class="v-icon-btn v-icon-btn-sm"
          :disabled="!canGoUp || loading"
          aria-label="Go to parent folder"
          @click="goUp"
        >
          <svg class="icon"><use href="#icon-back" /></svg>
        </button>
        <div class="storage-picker__location">
          <span>{{ activeRoot?.label || 'Storage' }}</span>
          <strong>/{{ browsePath }}</strong>
        </div>
        <button
          type="button"
          class="v-btn v-btn-secondary v-btn-sm storage-picker__select-current"
          :class="{ 'is-selected': modelPath === browsePath }"
          :aria-pressed="modelPath === browsePath"
          :disabled="!canSelectCurrentFolder"
          :title="canSelectCurrentFolder ? 'Use this folder' : 'Choose or create a folder first'"
          @click="selectFolder(browsePath)"
        >
          <svg class="icon"><use href="#icon-check" /></svg>
          {{ modelPath === browsePath ? 'Selected' : 'Select' }}
        </button>
        <button
          v-if="canCreate"
          type="button"
          class="v-btn v-btn-secondary v-btn-sm"
          @click="creating = !creating"
        >
          <svg class="icon"><use href="#icon-plus" /></svg>
          New folder
        </button>
      </div>

      <form v-if="creating" class="storage-picker__create" @submit.prevent="createFolder">
        <input v-model="newFolderName" class="v-input" placeholder="Folder name" autofocus />
        <button class="v-btn v-btn-primary v-btn-sm" :disabled="!newFolderName.trim() || creatingFolder">
          {{ creatingFolder ? 'Creating…' : 'Create' }}
        </button>
      </form>

      <div v-if="error" class="v-inline-note storage-picker__error">{{ error }}</div>
      <div v-else-if="loading" class="storage-picker__empty">Loading folders…</div>
      <div v-else-if="!folders.length" class="storage-picker__empty">This folder has no subfolders.</div>
      <div v-else class="storage-picker__folders">
        <div
          v-for="folder in folders"
          :key="folder.path"
          class="storage-picker__folder-row"
          :class="{ 'is-selected': modelPath === folder.path }"
        >
          <button type="button" class="storage-picker__folder" @click="openFolder(folder.path)">
            <span class="storage-picker__folder-icon"><svg class="icon"><use href="#icon-folder" /></svg></span>
            <span>{{ folder.name }}</span>
            <svg class="icon storage-picker__chevron"><use href="#icon-chevron-down" /></svg>
          </button>
          <button
            type="button"
            class="storage-picker__folder-select"
            :class="{ 'is-selected': modelPath === folder.path }"
            :aria-label="`${modelPath === folder.path ? 'Selected' : 'Select'} ${folder.name}`"
            :aria-pressed="modelPath === folder.path"
            @click="selectFolder(folder.path)"
          >
            <svg class="icon"><use :href="modelPath === folder.path ? '#icon-check' : '#icon-circle'" /></svg>
          </button>
        </div>
      </div>
    </div>

    <p v-if="modelPath !== null" class="storage-picker__selection">
      <svg class="icon"><use href="#icon-check" /></svg>
      Selected: <strong>{{ activeRoot?.label || modelRoot }} / {{ modelPath || 'Root' }}</strong>
    </p>
    <p v-else class="storage-picker__selection is-empty">
      <svg class="icon"><use href="#icon-circle" /></svg>
      Choose a folder to continue.
    </p>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import api, { getApiErrorMessage } from '../../lib/api'

const props = defineProps({
  roots: { type: Array, default: () => [] },
  modelRoot: { type: String, default: '' },
  modelPath: { type: String, default: null },
  allowCreate: { type: Boolean, default: false },
  allowRootSelection: { type: Boolean, default: true },
  basePath: { type: String, default: '' },
})

const emit = defineEmits(['update:modelRoot', 'update:modelPath'])
const folders = ref([])
const loading = ref(false)
const error = ref('')
const creating = ref(false)
const creatingFolder = ref(false)
const newFolderName = ref('')

function normalizePath(path) {
  return String(path || '').split('/').filter(Boolean).join('/')
}

const browsePath = ref(normalizePath(props.modelPath ?? props.basePath))
const normalizedBasePath = computed(() => normalizePath(props.basePath))

const activeRoot = computed(() => props.roots.find(root => root.id === props.modelRoot) || props.roots[0] || null)
const canCreate = computed(() => props.allowCreate && activeRoot.value?.available !== false && !activeRoot.value?.read_only)
const canSelectCurrentFolder = computed(() => props.allowRootSelection || Boolean(browsePath.value))
const canGoUp = computed(() => {
  const base = normalizedBasePath.value
  return Boolean(browsePath.value && browsePath.value !== base)
})

async function loadFolders() {
  if (!props.modelRoot) {
    folders.value = []
    return
  }
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/storage/browse', { params: { root: props.modelRoot, path: browsePath.value } })
    folders.value = data.folders || []
  } catch (requestError) {
    folders.value = []
    error.value = getApiErrorMessage(requestError, 'Unable to browse this storage location.')
  } finally {
    loading.value = false
  }
}

function chooseRoot(root) {
  browsePath.value = normalizedBasePath.value
  emit('update:modelRoot', root)
  emit('update:modelPath', null)
}

function openFolder(path) {
  browsePath.value = path
}

function selectFolder(path) {
  const normalized = normalizePath(path)
  if (!props.allowRootSelection && !normalized) return
  emit('update:modelPath', normalized)
}

function goUp() {
  const parts = browsePath.value.split('/').filter(Boolean)
  const baseParts = normalizedBasePath.value.split('/').filter(Boolean)
  if (parts.length <= baseParts.length) return
  parts.pop()
  browsePath.value = parts.join('/')
}

async function createFolder() {
  if (!newFolderName.value.trim() || !canCreate.value) return
  creatingFolder.value = true
  error.value = ''
  try {
    const { data } = await api.post('/api/storage/folders', {
      root: props.modelRoot,
      path: browsePath.value,
      name: newFolderName.value.trim(),
    })
    newFolderName.value = ''
    creating.value = false
    browsePath.value = data.path
    emit('update:modelPath', data.path)
  } catch (requestError) {
    error.value = getApiErrorMessage(requestError, 'Unable to create the folder.')
  } finally {
    creatingFolder.value = false
  }
}

watch(() => [props.modelRoot, browsePath.value], loadFolders, { immediate: true })
watch(() => props.modelPath, (path, previousPath) => {
  if (path === null && previousPath !== null) browsePath.value = normalizedBasePath.value
})
watch(normalizedBasePath, (path) => {
  const withinBase = !path || browsePath.value === path || browsePath.value.startsWith(`${path}/`)
  if (!withinBase) browsePath.value = path
})
</script>

<style scoped>
.storage-picker { display: grid; gap: 10px; }
.storage-picker__roots { display: flex; flex-wrap: wrap; gap: var(--v-space-2); }
.storage-picker__root.is-active { color: var(--v-accent); border-color: color-mix(in srgb, var(--v-accent) 36%, var(--v-control-border)); background: var(--v-control-bg-active); }
.storage-picker__browser { overflow: hidden; padding: 0; }
.storage-picker__toolbar { min-height: 48px; padding: 8px 10px; display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; align-items: center; gap: var(--v-space-2); border-bottom: 1px solid var(--v-modal-divider); }
.storage-picker__location { min-width: 0; display: flex; align-items: baseline; gap: 5px; color: var(--v-text-muted); font-size: var(--v-text-xs); }
.storage-picker__location strong { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--v-text); font-size: var(--v-text-sm); }
.storage-picker__select-current.is-selected { color: var(--v-accent); border-color: color-mix(in srgb, var(--v-accent) 32%, var(--v-control-border)); background: var(--v-control-bg-active); }
.storage-picker__folders { display: grid; max-height: 260px; overflow-y: auto; padding: 6px; }
.storage-picker__folder-row { display: grid; grid-template-columns: minmax(0, 1fr) 34px; align-items: center; border-radius: var(--v-radius-md); }
.storage-picker__folder-row:hover,
.storage-picker__folder-row.is-selected { background: var(--v-surface-raised-strong); }
.storage-picker__folder-row.is-selected { box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-accent) 22%, transparent); }
.storage-picker__folder { width: 100%; min-height: 44px; display: grid; grid-template-columns: 30px minmax(0, 1fr) 16px; align-items: center; gap: 9px; padding: 6px 5px 6px 9px; border: 0; border-radius: var(--v-button-radius); background: transparent; color: var(--v-text); text-align: left; font: inherit; cursor: pointer; }
.storage-picker__folder:focus-visible { outline: 2px solid var(--v-accent); outline-offset: -2px; }
.storage-picker__folder-select { width: 30px; height: 30px; display: grid; place-items: center; padding: 0; border: 0; border-radius: var(--v-button-radius); background: transparent; color: var(--v-text-muted); cursor: pointer; }
.storage-picker__folder-select:hover { color: var(--v-text); background: var(--v-control-bg-hover); }
.storage-picker__folder-select:focus-visible { outline: 2px solid var(--v-accent); outline-offset: -2px; }
.storage-picker__folder-select.is-selected { color: var(--v-accent); }
.storage-picker__folder-select .icon { width: 15px; height: 15px; }
.storage-picker__folder-icon { width: 30px; height: 30px; display: grid; place-items: center; border-radius: var(--v-radius-sm); color: var(--v-accent); background: color-mix(in srgb, var(--v-accent) 8%, var(--v-surface-inset)); }
.storage-picker__folder-icon .icon { width: 15px; height: 15px; }
.storage-picker__chevron { width: 13px; height: 13px; color: var(--v-text-muted); transform: rotate(-90deg); }
.storage-picker__empty { min-height: 92px; display: grid; place-items: center; padding: 18px; color: var(--v-text-muted); font-size: var(--v-text-sm); }
.storage-picker__create { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--v-space-2); padding: 10px; border-bottom: 1px solid var(--v-modal-divider); background: var(--v-surface-inset); }
.storage-picker__error { margin: 8px 10px; color: var(--v-danger); }
.storage-picker__selection { display: flex; align-items: center; gap: 6px; margin: 0; color: var(--v-text-muted); font-size: var(--v-text-xs); }
.storage-picker__selection .icon { width: 13px; height: 13px; color: var(--v-accent); }
.storage-picker__selection strong { color: var(--v-text); font-weight: 650; }
.storage-picker__selection.is-empty .icon { color: var(--v-text-muted); }
@media (max-width: 548px) {
  .storage-picker__toolbar { grid-template-columns: auto minmax(0, 1fr) auto; }
  .storage-picker__toolbar > .v-btn:not(.storage-picker__select-current) { grid-column: 1 / -1; width: 100%; }
  .storage-picker__folders { max-height: 220px; }
}
</style>
