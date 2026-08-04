<template>
  <VModal
    :modelValue="props.showCreateProject"
    @update:modelValue="props.closeCreateProject"
    title="New Project"
    size="md"
  >
    <template #header>
      <VModalHeader title="New Project" @close="props.closeCreateProject" />
    </template>

    <div class="v-form-grid v-modal-stack">
      <input
        :value="props.newProjectTitle"
        placeholder="Project Title"
        class="v-input"
        @input="emit('update:newProjectTitle', $event.target.value)"
      />
      <textarea
        :value="props.newProjectDesc"
        placeholder="Description (optional)"
        class="v-input modal-textarea"
        @input="emit('update:newProjectDesc', $event.target.value)"
      ></textarea>
      <input
        :value="props.newProjectDue"
        type="date"
        placeholder="Due Date"
        class="v-input"
        @input="emit('update:newProjectDue', $event.target.value)"
      />

      <section class="v-modal-section create-project-storage">
        <div class="v-modal-section-head">
          <h3 class="v-modal-section-title">Working project folder</h3>
          <p class="v-modal-section-copy">Choose where Vue should create the new project folder.</p>
        </div>
        <StorageFolderPicker
          v-if="props.projectStorageRoots.length"
          :roots="props.projectStorageRoots"
          :model-root="props.newProjectStorageRoot"
          :model-path="props.newProjectStoragePath"
          allow-create
          @update:model-root="emit('update:newProjectStorageRoot', $event)"
          @update:model-path="emit('update:newProjectStoragePath', $event)"
        />
        <p v-else class="v-inline-note create-project-storage__unavailable">{{ workingProjectStorageIssue }}</p>
        <p v-if="props.projectStorageRoots.length && !workingProjectStorageAvailable" class="v-inline-note create-project-storage__unavailable">
          {{ workingProjectStorageIssue }}
        </p>
      </section>
    </div>

    <template #footer>
      <button class="v-btn v-btn-secondary" @click="props.closeCreateProject">Cancel</button>
      <button class="v-btn v-btn-primary" @click="props.createProject" :disabled="!canCreateProject">Create</button>
    </template>
  </VModal>

  <VModal
    :modelValue="props.showCreatePage"
    @update:modelValue="props.closeCreatePage"
    title="Create Vue Dashboard"
    size="md"
  >
    <template #header>
      <VModalHeader title="Create Vue Dashboard" @close="props.closeCreatePage" />
    </template>

    <div class="v-form-grid v-modal-stack">
      <input
        :value="props.newPageTitle"
        placeholder="Vue Dashboard title"
        class="v-input"
        @input="emit('update:newPageTitle', $event.target.value)"
        @keydown.enter="props.createPage"
      />
      <textarea
        :value="props.newPageDesc"
        placeholder="Description (optional)"
        class="v-input modal-textarea"
        @input="emit('update:newPageDesc', $event.target.value)"
      ></textarea>
    </div>

    <template #footer>
      <button class="v-btn v-btn-secondary" @click="props.closeCreatePage">Cancel</button>
      <button class="v-btn v-btn-primary" @click="props.createPage" :disabled="!props.newPageTitle?.trim()">Create Vue Dashboard</button>
    </template>
  </VModal>

  <VModal
    :modelValue="props.showCreateTracker"
    @update:modelValue="props.closeCreateTracker"
    title="Create Vue Tracker"
    size="md"
  >
    <template #header>
      <VModalHeader title="Create Vue Tracker" @close="props.closeCreateTracker" />
    </template>

    <input
      :value="props.newTrackerName"
      placeholder="Vue Tracker name (e.g., VFX Shots)"
      class="v-input"
      @input="emit('update:newTrackerName', $event.target.value)"
      @keydown.enter="props.createTracker"
    />

    <template #footer>
      <button class="v-btn v-btn-secondary" @click="props.closeCreateTracker">Cancel</button>
      <button class="v-btn v-btn-primary" @click="props.createTracker" :disabled="!props.newTrackerName?.trim()">Create</button>
    </template>
  </VModal>

  <VModal
    :modelValue="props.showCreateFolder"
    @update:modelValue="props.closeCreateFolder"
    title="Create Folder"
    size="md"
  >
    <template #header>
      <VModalHeader title="Create Folder" @close="props.closeCreateFolder" />
    </template>

    <input
      :value="props.newFolderName"
      placeholder="Folder name"
      class="v-input"
      @input="emit('update:newFolderName', $event.target.value)"
      @keydown.enter="props.createProjectFolder"
    />

    <template #footer>
      <button class="v-btn v-btn-secondary" @click="props.closeCreateFolder">Cancel</button>
      <button class="v-btn v-btn-primary" @click="props.createProjectFolder" :disabled="!props.newFolderName?.trim()">Create</button>
    </template>
  </VModal>

  <VModal
    :modelValue="props.showRenameModal"
    @update:modelValue="props.closeRenameModal"
    :title="`Rename ${renameTargetLabel}`"
    size="md"
  >
    <template #header>
      <VModalHeader :title="`Rename ${renameTargetLabel}`" @close="props.closeRenameModal" />
    </template>

    <input
      :value="props.renameNewName"
      class="v-input"
      placeholder="New name"
      autofocus
      @input="emit('update:renameNewName', $event.target.value)"
      @keydown.enter="props.confirmRename"
    />

    <template #footer>
      <button class="v-btn v-btn-secondary" @click="props.closeRenameModal">Cancel</button>
      <button class="v-btn v-btn-primary" @click="props.confirmRename" :disabled="!props.renameNewName?.trim()">Rename</button>
    </template>
  </VModal>


  <VModal
    :modelValue="!!props.showThumbUpload"
    @update:modelValue="props.closeThumbUpload"
    :title="thumbUploadTitle"
    size="md"
  >
    <template #header>
      <VModalHeader :title="thumbUploadTitle" @close="props.closeThumbUpload" />
    </template>

    <div class="v-modal-stack thumb-modal-body">
      <p class="v-inline-note">Choose from NAS or upload an image directly. NAS videos use their generated thumbnail.</p>

      <div class="v-modal-choice-grid thumb-upload-options">
        <button class="v-btn v-btn-secondary thumb-source-btn" @click="props.openThumbFromNas">
          <svg class="icon"><use href="#icon-folder"/></svg>
          <span>Choose from NAS</span>
        </button>
        <label class="v-modal-upload-zone upload-zone">
          <input type="file" accept="image/*" hidden @change="props.handleThumbUpload"/>
          <svg class="icon"><use href="#icon-upload"/></svg>
          <span class="v-modal-upload-zone-title">Upload image directly</span>
          <span class="v-modal-upload-zone-hint">Drag one in or browse your device.</span>
        </label>
      </div>

      <div v-if="props.thumbUploadPreview" class="v-modal-card-soft thumb-preview">
        <img :src="props.thumbUploadPreview" />
        <span class="v-text-muted">{{ props.thumbUploadData?.name || 'Preview ready' }}</span>
      </div>
    </div>

    <template #footer>
      <button class="v-btn v-btn-secondary" @click="props.closeThumbUpload">Cancel</button>
      <button class="v-btn v-btn-primary" @click="props.confirmThumbUpload" :disabled="!props.thumbUploadData">Set Thumbnail</button>
    </template>
  </VModal>
</template>

<script setup>
import { computed } from 'vue'
import { VModal, VModalHeader } from '../primitives'
import StorageFolderPicker from '../files/StorageFolderPicker.vue'

const props = defineProps({
  showCreateProject: { type: Boolean, default: false },
  newProjectTitle: { type: String, default: '' },
  newProjectDesc: { type: String, default: '' },
  newProjectDue: { type: String, default: '' },
  projectStorageRoots: { type: Array, default: () => [] },
  newProjectStorageRoot: { type: String, default: '' },
  newProjectStoragePath: { type: String, default: null },
  closeCreateProject: { type: Function, required: true },
  createProject: { type: Function, required: true },

  showCreatePage: { type: Boolean, default: false },
  newPageTitle: { type: String, default: '' },
  newPageDesc: { type: String, default: '' },
  closeCreatePage: { type: Function, required: true },
  createPage: { type: Function, required: true },

  showCreateTracker: { type: Boolean, default: false },
  newTrackerName: { type: String, default: '' },
  closeCreateTracker: { type: Function, required: true },
  createTracker: { type: Function, required: true },

  showCreateFolder: { type: Boolean, default: false },
  newFolderName: { type: String, default: '' },
  closeCreateFolder: { type: Function, required: true },
  createProjectFolder: { type: Function, required: true },

  showRenameModal: { type: Boolean, default: false },
  renameTarget: { type: Object, default: null },
  renameNewName: { type: String, default: '' },
  closeRenameModal: { type: Function, required: true },
  confirmRename: { type: Function, required: true },

  currentProject: { type: Object, default: null },

  showThumbUpload: { default: null },
  thumbUploadMode: { type: String, default: 'browser-folder' },
  thumbUploadPreview: { default: null },
  thumbUploadData: { default: null },
  closeThumbUpload: { type: Function, required: true },
  handleThumbUpload: { type: Function, required: true },
  openThumbFromNas: { type: Function, required: true },
  confirmThumbUpload: { type: Function, required: true }
})

const emit = defineEmits([
  'update:newProjectTitle',
  'update:newProjectDesc',
  'update:newProjectDue',
  'update:newProjectStorageRoot',
  'update:newProjectStoragePath',
  'update:newPageTitle',
  'update:newPageDesc',
  'update:newTrackerName',
  'update:newFolderName',
  'update:renameNewName'
])

const workingProjectRoot = computed(() => props.projectStorageRoots.find(root => root.id === props.newProjectStorageRoot) || null)
const workingProjectStorageAvailable = computed(() => (
  !!workingProjectRoot.value?.available && !workingProjectRoot.value?.read_only
))
const workingProjectStorageIssue = computed(() => {
  if (workingProjectRoot.value?.read_only) return 'This storage location is read-only. Choose a writable location.'
  if (workingProjectRoot.value && !workingProjectRoot.value.available) return 'This storage location is unavailable. Choose another location.'
  return 'No project storage locations are available. Check the storage configuration before creating a project.'
})
const canCreateProject = computed(() => (
  !!props.newProjectTitle?.trim()
  && workingProjectStorageAvailable.value
  && props.newProjectStoragePath !== null
))

const renameTargetLabel = computed(() => {
  if (props.renameTarget?.type === 'page') return 'Vue Dashboard'
  if (props.renameTarget?.type === 'folder') return 'Folder'
  if (props.renameTarget?.type === 'tracker') return 'Vue Tracker'
  return 'File'
})

const thumbUploadTitle = computed(() => {
  if (props.thumbUploadMode === 'project') return 'Set Project Thumbnail'
  if (props.thumbUploadMode === 'project-folder') return 'Set Folder Thumbnail'
  if (props.thumbUploadMode === 'browser-folder') return 'Set Folder Thumbnail'
  return 'Choose Thumbnail'
})
</script>

<style scoped>
.modal-textarea {
  min-height: 80px;
  resize: vertical;
}

.create-project-storage { margin-top: 2px; padding-top: 14px; border-top: 1px solid var(--v-modal-divider); }
.create-project-storage__unavailable { margin: 0; }

.thumb-modal-body {
  gap: var(--v-space-3);
}

.upload-zone {
  min-height: 116px;
}

.thumb-source-btn {
  flex: 1;
  height: auto;
  flex-direction: column;
  gap: var(--v-space-2);
  padding: var(--v-space-4);
}

.thumb-preview {
  align-items: flex-start;
  gap: var(--v-space-2);
}

.thumb-preview img {
  width: min(220px, 100%);
  max-width: 100%;
  border-radius: var(--v-radius-md);
}

</style>
