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
      <p class="v-inline-note">{{ description }}</p>
      <p v-if="uploadDisabledReason" class="v-inline-note v-text-danger">{{ uploadDisabledReason }}</p>
      <p v-if="uploadError" class="v-inline-note v-text-danger">{{ uploadError }}</p>
      <div v-if="requiresUploaderName" class="v-form-grid">
        <label class="v-field">
          <span class="v-field-label">Your Name</span>
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
          <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click.prevent="openFilePicker">Choose Files</button>
          <button type="button" class="v-btn v-btn-ghost v-btn-sm" @click.prevent="openFolderPicker">Choose Folder</button>
        </div>
      </label>

      <div v-if="uploadQueue.length" class="v-upload-queue v-modal-card">
        <div class="v-upload-summary">
          <div class="v-upload-summary-left">
            <span>{{ uploadSummary.label }}</span>
            <span class="v-text-muted">{{ uploadSummary.size }}</span>
          </div>
          <div class="v-upload-summary-right">
            <span class="v-text-muted">{{ uploadSummary.progress }}</span>
            <span v-if="uploadSummary.speed" class="v-text-muted">{{ uploadSummary.speed }}</span>
            <span v-if="uploadSummary.eta" class="v-text-muted">{{ uploadSummary.eta }}</span>
          </div>
        </div>
        <div class="v-upload-list">
          <div v-for="item in uploadQueue" :key="item.id" class="v-upload-item" :class="`v-upload-${item.status}`">
            <div class="v-upload-main">
              <div class="v-upload-name v-truncate">{{ item.relPath || item.name }}</div>
              <div class="v-text-muted v-upload-meta">{{ item.uploadedLabel || formatSizeBytes(item.size || 0) }}</div>
            </div>
            <div v-if="item.speedLabel || item.etaLabel" class="v-text-muted v-upload-transfer">
              <span v-if="item.speedLabel">{{ item.speedLabel }}</span>
              <span v-if="item.speedLabel && item.etaLabel">·</span>
              <span v-if="item.etaLabel">{{ item.etaLabel }}</span>
            </div>
            <div class="v-upload-actions">
              <button v-if="item.status === 'error'" class="v-btn v-btn-ghost v-btn-xs" @click="retryUpload(item)">Retry</button>
              <button v-else-if="item.status === 'uploading' || item.status === 'pending' || item.status === 'retrying'" class="v-btn v-btn-ghost v-btn-xs" @click="cancelUpload(item)">Cancel</button>
              <span v-else-if="item.status === 'done'" class="v-text-secondary">Done</span>
              <span v-else-if="item.status === 'canceled'" class="v-text-muted">Canceled</span>
            </div>
            <div v-if="item.status === 'uploading' || item.status === 'retrying'" class="v-progress v-upload-progress">
              <div class="v-progress-fill" :style="{ width: `${item.progress || 0}%` }"></div>
            </div>
            <div v-if="item.status === 'error'" class="v-text-danger v-upload-error">{{ item.error }}</div>
          </div>
        </div>
        <div class="v-upload-footer">
          <button class="v-btn v-btn-secondary" @click="cancelAllUploads" :disabled="!uploadHasActive">Cancel All</button>
          <button class="v-btn v-btn-ghost" @click="clearCompletedUploads" :disabled="!uploadHasRemovable">Clear Completed</button>
        </div>
      </div>
    </div>

    <template #footer>
      <button class="v-btn v-btn-secondary" @click="closeUpload">Close</button>
    </template>
  </VModal>
</template>

<script setup>
import { computed, ref } from 'vue'
import { VModal, VModalHeader } from '../primitives'
import { formatSizeBytes } from '../../utils/formatters'

const props = defineProps({
  show: { type: Boolean, required: true },
  title: { type: String, default: 'Upload Files' },
  description: { type: String, default: 'Upload files or drop folders from your device into this folder.' },
  canUpload: { type: Boolean, required: true },
  uploadDisabledReason: { type: String, default: '' },
  uploadError: { type: String, default: '' },
  uploadModalDragActive: { type: Boolean, required: true },
  uploadQueue: { type: Array, required: true },
  uploadSummary: { type: Object, required: true },
  uploadHasActive: { type: Boolean, required: true },
  uploadHasRemovable: { type: Boolean, required: true },
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
  retryUpload: { type: Function, required: true },
  cancelUpload: { type: Function, required: true },
  cancelAllUploads: { type: Function, required: true },
  clearCompletedUploads: { type: Function, required: true }
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
  padding: 30px;
}

.upload-zone .icon {
  width: 32px;
  height: 32px;
}

.v-upload-zone-active {
  border-color: color-mix(in srgb, var(--v-accent-subtle) 97%, white);
  background: var(--v-accent-subtle);
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

.v-upload-queue {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-3);
}

.v-upload-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.v-upload-summary-left {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
}

.v-upload-summary-right {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  justify-content: flex-end;
  flex-wrap: wrap;
  text-align: right;
}

.v-upload-list {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-2);
  max-height: 260px;
  overflow-y: auto;
  padding-right: var(--v-space-1);
}

.v-upload-item {
  background: var(--v-modal-list-item-bg);
  border: 1px solid color-mix(in srgb, var(--v-modal-list-item-bg) 97%, white);
  border-radius: var(--v-radius-lg);
  padding: var(--v-space-3);
  display: flex;
  flex-direction: column;
  gap: var(--v-space-2);
}

.v-upload-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
}

.v-upload-name {
  font-weight: 600;
}

.v-upload-meta {
  font-size: var(--v-text-xs);
  white-space: nowrap;
}

.v-upload-transfer {
  display: flex;
  align-items: center;
  gap: var(--v-space-1);
  font-size: var(--v-text-xs);
  line-height: 1.35;
}

.v-upload-actions {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  justify-content: flex-end;
}

.v-upload-error {
  font-size: var(--v-text-xs);
}

.v-upload-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.v-upload-progress {
  margin-top: var(--v-space-2);
}

@media (max-width: 768px) {
  .upload-zone-actions {
    width: 100%;
  }

  .upload-zone-actions .v-btn {
    flex: 1;
  }

  .v-upload-summary {
    align-items: flex-start;
    flex-direction: column;
    gap: var(--v-space-1);
  }

  .v-upload-summary-right {
    justify-content: flex-start;
    text-align: left;
  }

  .v-upload-main {
    align-items: flex-start;
    flex-direction: column;
    gap: var(--v-space-1);
  }

  .v-upload-meta {
    white-space: normal;
  }
}
</style>
