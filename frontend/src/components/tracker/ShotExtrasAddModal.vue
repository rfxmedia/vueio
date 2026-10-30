<template>
  <VModal :model-value="extrasDialog.open" :title="title" size="lg" @update:model-value="value => !value && closeExtrasDialog()">
    <template #header>
      <VModalHeader :title="title" :subtitle="subtitle" @close="closeExtrasDialog" />
    </template>

    <div v-if="extrasDialog.shot" class="v-modal-stack extras-add">
      <template v-if="extrasDialog.mode === 'ask'">
        <div class="extras-add-card">
          <div class="extras-add-label">What does the shot need?</div>
          <div class="extras-add-types" role="radiogroup" aria-label="Extra type">
            <button
              v-for="type in EXTRA_TYPES"
              :key="type.name"
              type="button"
              role="radio"
              class="extras-add-type"
              :class="{ 'is-on': sameName(ask.name, type.name) }"
              :aria-checked="sameName(ask.name, type.name) ? 'true' : 'false'"
              @click="chooseType(ask, type)"
            >{{ type.name }}</button>
          </div>
          <div class="extras-add-fields">
            <label class="v-field">
              <span class="v-field-label">Name</span>
              <input v-model="ask.name" class="v-input" maxlength="60" placeholder="Such as Alpha matte" @input="ask.clientVisible = defaultClientVisibility(ask.name)" />
            </label>
            <label class="v-field">
              <span class="v-field-label">Note <span class="v-field-optional">Optional</span></span>
              <input v-model="ask.note" class="v-input" maxlength="80" placeholder="Such as Window" />
            </label>
          </div>
          <VSwitch v-model="ask.clientVisible" label="Clients can see it" :hint="ask.clientVisible ? 'Clients get it with each published version.' : 'Only your team sees it.'" />
        </div>
        <p class="v-inline-note">
          {{ extrasDialog.shot.shot_id }} shows {{ ask.name.trim() || 'the extra' }} as needed on every version until it gets a file.
          Your artist can add it from the card.
        </p>
      </template>

      <template v-else>
        <div
          v-for="(entry, index) in extrasDialog.entries"
          :key="entry.key"
          class="extras-add-card extras-add-entry"
        >
          <div class="extras-add-file">
            <span class="extras-add-file-icon"><svg class="icon"><use :href="entry.file ? '#icon-upload' : '#icon-folder'" /></svg></span>
            <span class="extras-add-file-name" :title="entry.fileName">{{ entry.fileName }}</span>
            <span v-if="entry.size" class="extras-add-file-size">{{ formatSizeBytes(entry.size, { compact: true }) }}</span>
            <button type="button" class="extras-add-remove" :aria-label="`Remove ${entry.fileName}`" title="Remove" @click="extrasDialog.entries.splice(index, 1)">
              <svg class="icon"><use href="#icon-close" /></svg>
            </button>
          </div>
          <div class="extras-add-types" role="radiogroup" :aria-label="`What ${entry.fileName} is`">
            <button
              v-for="type in EXTRA_TYPES"
              :key="type.name"
              type="button"
              role="radio"
              class="extras-add-type"
              :class="{ 'is-on': sameName(entry.name, type.name) }"
              :aria-checked="sameName(entry.name, type.name) ? 'true' : 'false'"
              @click="chooseType(entry, type)"
            >{{ type.name }}</button>
          </div>
          <div class="extras-add-fields">
            <label class="v-field">
              <span class="v-field-label">Name</span>
              <input v-model="entry.name" class="v-input" maxlength="60" placeholder="Choose a type, or type a name" @input="entry.clientVisible = defaultClientVisibility(entry.name)" />
            </label>
            <label class="v-field">
              <span class="v-field-label">Note <span class="v-field-optional">Optional</span></span>
              <input v-model="entry.note" class="v-input" maxlength="80" placeholder="Such as Window" />
            </label>
          </div>
          <div class="extras-add-foot">
            <span class="extras-add-preview" :class="{ 'is-empty': !entry.name.trim() }">
              <svg class="icon" aria-hidden="true"><use href="#icon-download" /></svg>
              {{ entry.name.trim() ? previewName(entry) : 'Choose what this file is' }}
            </span>
            <VSwitch v-if="canManageExtras" v-model="entry.clientVisible" label="Clients can see it" />
          </div>
        </div>

        <p v-if="renumberNote" class="v-inline-note">{{ renumberNote }}</p>

        <div
          class="v-modal-upload-zone upload-zone extras-add-zone"
          :class="{ 'v-upload-zone-active': dragActive }"
          @dragenter.prevent="dragActive = true"
          @dragover.prevent="dragActive = true"
          @dragleave="dragActive = false"
          @drop.prevent="dropFiles"
        >
          <svg class="icon"><use href="#icon-upload" /></svg>
          <span class="v-modal-upload-zone-title">{{ extrasDialog.entries.length ? 'Add more files' : 'Drop the extra files here' }}</span>
          <span class="v-modal-upload-zone-hint v-upload-zone-hint">Mattes, clean plates, elements, references. Any type of file.</span>
          <div class="upload-zone-actions">
            <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click="fileInput?.click()">Upload from computer</button>
            <button type="button" class="v-btn v-btn-ghost v-btn-sm" @click="chooseProjectFiles">Choose project files</button>
          </div>
          <input ref="fileInput" type="file" multiple hidden @change="pickFiles" />
        </div>
      </template>
    </div>

    <template #footer>
      <button
        v-if="canManageExtras"
        type="button"
        class="v-btn v-btn-ghost extras-add-switch"
        @click="extrasDialog.mode = extrasDialog.mode === 'ask' ? 'files' : 'ask'"
      >
        {{ extrasDialog.mode === 'ask' ? 'Add files instead' : 'Ask for an extra instead' }}
      </button>
      <button type="button" class="v-btn v-btn-secondary" @click="closeExtrasDialog">Cancel</button>
      <button type="button" class="v-btn v-btn-primary" :disabled="!canSubmit || saving" @click="submit">{{ submitLabel }}</button>
    </template>
  </VModal>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useTrackerStore } from '../../ownership/tracker'
import { defaultClientVisibility, droppedExtraFiles, previewExtraFileName } from '../../composables/useTrackerExtrasController'
import { formatSizeBytes } from '../../utils/formatters'
import { VModal, VModalHeader, VSwitch } from '../primitives'

const {
  EXTRA_TYPES,
  addDialogFiles,
  addExtras,
  askForExtra,
  canManageExtras,
  chooseExtraProjectFiles,
  closeExtrasDialog,
  extrasDialog,
  formatVersionLabel,
} = useTrackerStore()

const fileInput = ref(null)
const dragActive = ref(false)
const saving = ref(false)

const ask = computed(() => extrasDialog.ask)
const versionLabel = computed(() => (extrasDialog.version ? formatVersionLabel(extrasDialog.version) : ''))
const title = computed(() => (
  extrasDialog.mode === 'ask'
    ? `Ask for an extra on ${extrasDialog.shot?.shot_id || 'this shot'}`
    : `Add extras to ${extrasDialog.shot?.shot_id || 'this shot'}`
))
const subtitle = computed(() => (
  extrasDialog.mode === 'ask'
    ? 'Every version shows it as needed until it gets a file.'
    : `The files go with ${versionLabel.value || 'the latest version'}. Clients get the ones they can see when it is published.`
))

function sameName(a, b) {
  return String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase()
}

function chooseType(target, type) {
  target.name = type.name
  target.clientVisible = type.clientVisible
}

// The shot's extras and the new ones, numbered as Vue.io will number them.
const numberedNames = computed(() => {
  const existing = (extrasDialog.shot?.extras || []).map(extra => ({ key: extra.id, name: extra.base_name || extra.name }))
  const added = extrasDialog.entries.map(entry => ({ key: entry.key, name: entry.name.trim() }))
  const all = [...existing, ...added].filter(item => item.name)
  const counts = new Map()
  for (const item of all) counts.set(item.name.toLowerCase(), (counts.get(item.name.toLowerCase()) || 0) + 1)
  const seen = new Map()
  const names = new Map()
  for (const item of all) {
    const key = item.name.toLowerCase()
    if (counts.get(key) > 1) {
      seen.set(key, (seen.get(key) || 0) + 1)
      names.set(item.key, `${item.name} ${seen.get(key)}`)
    } else {
      names.set(item.key, item.name)
    }
  }
  return names
})

function previewName(entry) {
  return previewExtraFileName(extrasDialog.version?.download_name, numberedNames.value.get(entry.key) || entry.name, entry.fileName)
}

const renumberNote = computed(() => {
  const renamed = (extrasDialog.shot?.extras || []).filter(extra => numberedNames.value.get(extra.id) && numberedNames.value.get(extra.id) !== extra.name)
  if (!renamed.length) return ''
  const [first] = renamed
  return `With more than one ${first.base_name || first.name}, Vue.io numbers them in list order. The current one becomes ${numberedNames.value.get(first.id)}.`
})

const canSubmit = computed(() => (
  extrasDialog.mode === 'ask'
    ? Boolean(ask.value.name.trim())
    : extrasDialog.entries.length > 0 && extrasDialog.entries.every(entry => entry.name.trim())
))

const submitLabel = computed(() => {
  if (saving.value) return 'Adding…'
  if (extrasDialog.mode === 'ask') return ask.value.name.trim() ? `Ask for ${ask.value.name.trim()}` : 'Ask for the extra'
  const count = extrasDialog.entries.length
  return count === 1 ? 'Add 1 extra' : `Add ${count || ''} extras`.replace('  ', ' ')
})

function pickFiles(event) {
  addDialogFiles([...(event.target.files || [])])
  event.target.value = ''
}

function dropFiles(event) {
  dragActive.value = false
  addDialogFiles(droppedExtraFiles(event.dataTransfer))
}

async function chooseProjectFiles() {
  const items = await chooseExtraProjectFiles({ multiple: true })
  if (items?.length) addDialogFiles([], items)
}

async function submit() {
  if (!canSubmit.value || saving.value) return
  const shot = extrasDialog.shot
  saving.value = true
  try {
    if (extrasDialog.mode === 'ask') {
      const ok = await askForExtra(shot, { name: ask.value.name.trim(), note: ask.value.note.trim() || null, clientVisible: ask.value.clientVisible })
      if (ok) closeExtrasDialog()
      return
    }
    const entries = extrasDialog.entries.map(entry => ({
      name: entry.name.trim(),
      note: entry.note.trim() || null,
      clientVisible: entry.clientVisible,
      ...(entry.file ? { file: entry.file } : { filePath: entry.filePath }),
    }))
    const version = extrasDialog.version
    // Uploads continue on the card; the dialog can close at once.
    closeExtrasDialog()
    await addExtras(shot, entries, version)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.extras-add-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--v-radius-md);
  background: var(--v-modal-card-bg, var(--v-surface-raised));
  box-shadow: inset 0 0 0 1px var(--v-surface-border-soft);
}

.extras-add-label {
  font-size: var(--v-text-sm);
  font-weight: 650;
}

.extras-add-file {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.extras-add-file-icon {
  width: 26px;
  height: 26px;
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: var(--v-surface-inline);
  color: var(--v-text-muted);
}

.extras-add-file-icon .icon {
  width: 13px;
  height: 13px;
}

.extras-add-file-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--v-text-sm);
  font-weight: 650;
}

.extras-add-file-size {
  flex: none;
  color: var(--v-text-dim);
  font-size: var(--v-text-xs);
}

.extras-add-remove {
  margin-left: auto;
  width: 26px;
  height: 26px;
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--v-text-muted);
  cursor: pointer;
}

.extras-add-remove:hover {
  background: var(--v-surface-inline);
  color: var(--v-text);
}

.extras-add-remove .icon {
  width: 14px;
  height: 14px;
}

.extras-add-types {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.extras-add-type {
  height: 28px;
  padding: 0 11px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  box-shadow: inset 0 0 0 1px var(--v-surface-border-soft);
  color: var(--v-text-muted);
  font: inherit;
  font-size: var(--v-text-xs);
  font-weight: 600;
  cursor: pointer;
}

.extras-add-type:hover {
  color: var(--v-text);
  box-shadow: inset 0 0 0 1px var(--v-border-hover);
}

.extras-add-type.is-on {
  background: var(--v-accent);
  box-shadow: none;
  color: var(--v-on-accent);
}

.extras-add-type:focus-visible {
  outline: 2px solid var(--v-accent-muted);
  outline-offset: 2px;
}

.extras-add-fields {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 10px;
}

.extras-add-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
}

.extras-add-preview {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  color: var(--v-text-secondary);
  font-family: var(--v-font-mono);
  font-size: var(--v-text-xs);
  overflow-wrap: anywhere;
}

.extras-add-preview.is-empty {
  color: var(--v-warning);
  font-family: var(--v-font);
  font-weight: 600;
}

.extras-add-preview .icon {
  width: 12px;
  height: 12px;
  flex: none;
}

.extras-add-switch {
  margin-right: auto;
}

@media (max-width: 640px) {
  .extras-add-fields {
    grid-template-columns: 1fr;
  }
}
</style>
