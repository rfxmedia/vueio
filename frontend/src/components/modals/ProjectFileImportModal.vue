<template>
  <VModal
    :modelValue="show"
    @update:modelValue="closeUpload"
    :title="title"
    size="md"
  >
    <template #header>
      <VModalHeader :title="title" @close="closeUpload" />
    </template>

    <div class="v-modal-stack">
      <p v-if="description" class="v-inline-note">{{ description }}</p>
      <p v-if="uploadDisabledReason" class="v-inline-note v-text-danger">{{ uploadDisabledReason }}</p>
      <p v-if="uploadError" class="v-inline-note v-text-danger">{{ uploadError }}</p>
      <div v-if="requiresUploaderName" class="v-form-grid">
        <label class="v-field">
          <span class="v-field-label">Your name</span>
          <input
            type="text"
            :value="uploaderName"
            class="v-input"
            placeholder="Required for upload attribution"
            @input="setUploaderName($event.target.value)"
          />
        </label>
        <p v-if="uploaderNameError" class="v-inline-note v-text-danger">{{ uploaderNameError }}</p>
      </div>

      <label
        class="v-modal-upload-zone upload-zone"
        :class="{ 'v-upload-zone-active': canUpload && uploadModalDragActive, 'is-disabled': !canUpload }"
        :title="uploadDisabledReason || ''"
        @dragenter.prevent="canUpload && handleModalDragEnter($event)"
        @dragover.prevent="canUpload && handleModalDragOver($event)"
        @dragleave="canUpload && handleModalDragLeave($event)"
        @drop.prevent="canUpload && handleModalDrop($event)"
      >
        <input ref="fileInputRef" type="file" multiple @change="handleFileUpload" :disabled="!canUpload" hidden />
        <input ref="folderInputRef" type="file" multiple webkitdirectory directory @change="handleFileUpload" :disabled="!canUpload" hidden />
        <svg class="icon"><use href="#icon-upload" /></svg>
        <span class="v-modal-upload-zone-title">{{ canUpload ? activeTitle : 'Uploads unavailable in this folder' }}</span>
        <span class="v-modal-upload-zone-hint v-upload-zone-hint">{{ canUpload ? activeHint : (uploadDisabledReason || 'Uploads are currently disabled.') }}</span>
        <div v-if="canUpload" class="upload-zone-actions">
          <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click.prevent="openFilePicker">Choose files</button>
          <button type="button" class="v-btn v-btn-ghost v-btn-sm" @click.prevent="openFolderPicker">Choose folder</button>
        </div>
      </label>
    </div>

    <template #footer>
      <button class="v-btn v-btn-secondary" @click="closeUpload">Close</button>
    </template>
  </VModal>
</template>

<script setup>
import { computed, ref } from 'vue'
import { VModal, VModalHeader } from '../primitives'

const props = defineProps({
  show: { type: Boolean, required: true },
  title: { type: String, default: 'Upload files' },
  description: { type: String, default: 'Upload files or drop folders from your device into this folder.' },
  canUpload: { type: Boolean, required: true },
  uploadDisabledReason: { type: String, default: '' },
  uploadError: { type: String, default: '' },
  uploadModalDragActive: { type: Boolean, required: true },
  closeUpload: { type: Function, required: true },
  requiresUploaderName: { type: Boolean, default: false },
  uploaderName: { type: String, default: '' },
  uploaderNameError: { type: String, default: '' },
  setUploaderName: { type: Function, default: () => {} },
  handleModalDragEnter: { type: Function, required: true },
  handleModalDragOver: { type: Function, required: true },
  handleModalDragLeave: { type: Function, required: true },
  handleModalDrop: { type: Function, required: true },
  handleFileUpload: { type: Function, required: true },
})

const fileInputRef = ref(null)
const folderInputRef = ref(null)

const activeTitle = computed(() => props.requiresUploaderName
  ? 'Choose files or a folder, or drop them here'
  : 'Choose files or drop here'
)
const activeHint = computed(() => props.requiresUploaderName
  ? 'Folder layout is preserved. Your name is stored for upload attribution.'
  : 'Folders supported via drag & drop or folder picker.'
)

function openFilePicker() {
  fileInputRef.value?.click?.()
}

function openFolderPicker() {
  folderInputRef.value?.click?.()
}
</script>
<style scoped>
.upload-zone {
  padding: var(--v-space-6);
}

.upload-zone .icon {
  width: 32px;
  height: 32px;
}

.v-upload-zone-active {
  border-color: var(--v-info-border);
  background: var(--v-info-bg);
}

.v-upload-zone-hint {
  font-size: var(--v-text-xs);
}

.upload-zone-actions {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  margin-top: var(--v-space-3);
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .upload-zone-actions {
    width: 100%;
  }

  .upload-zone-actions .v-btn {
    flex: 1;
  }
}
</style>
