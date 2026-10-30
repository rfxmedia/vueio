<template>
  <div v-if="visible" class="trc-extras" :class="{ 'is-open': managerOpen, 'is-shared': shareMode }" @click.stop>
    <span class="trc-extras-lead" aria-hidden="true">
      <span class="trc-extras-icon"><svg class="icon"><use href="#icon-layers" /></svg></span>
      <span v-if="filledCount" class="trc-extras-count">{{ filledCount }}</span>
    </span>
    <div class="trc-extras-main">
      <span class="trc-extras-tag">Extras</span>
      <div class="trc-extras-chips">
        <template v-for="slot in slots" :key="slot.id">
          <div
            v-if="slot.file"
            class="extra-chip"
            :class="{ 'is-offline': slot.file.exists === false, 'is-team-only': !shareMode && slot.client_visible === false }"
            @pointerenter="prefetchExtraPath(version, slot.file)"
          >
            <button
              type="button"
              class="extra-chip-main"
              :title="chipTitle(slot)"
              :aria-label="canView(slot) ? `Open ${slot.name}` : `Download ${slot.name}`"
              @click="activate(slot)"
            >
              <span class="extra-chip-thumb" :class="{ 'is-empty': !thumbnail(slot) }">
                <img v-if="thumbnail(slot)" :src="thumbnail(slot)" alt="" loading="lazy" @error="failedThumbs[slot.id] = true" />
                <svg v-else class="icon"><use :href="slot.file.is_image ? '#icon-image' : '#icon-file'" /></svg>
              </span>
              <span class="extra-chip-name">{{ slot.name }}</span>
              <span v-if="slot.note" class="extra-chip-note">{{ slot.note }}</span>
              <svg v-if="!shareMode && slot.client_visible === false" class="icon extra-chip-flag" aria-label="Only your team sees this"><use href="#icon-eye-off" /></svg>
            </button>
            <span class="extra-chip-actions">
              <button
                v-if="!shareMode && canCopyFilePaths"
                type="button"
                class="extra-chip-action"
                :aria-label="`Copy the path of ${slot.name}`"
                :title="`Copy the path of ${slot.name}`"
                @focus="prefetchExtraPath(version, slot.file)"
                @click="copyExtraPath(version, slot.file)"
              >
                <svg class="icon"><use href="#icon-copy" /></svg>
              </button>
              <button
                v-if="canDownload && slot.file.exists !== false"
                type="button"
                class="extra-chip-action"
                :aria-label="`Download ${slot.file.download_name}`"
                :title="`Download ${slot.file.download_name}`"
                @click="downloadExtra(version, slot.file)"
              >
                <svg class="icon"><use href="#icon-download" /></svg>
              </button>
            </span>
          </div>

          <span v-else-if="uploadFor(slot)" class="extra-chip is-uploading" :title="`Uploading ${uploadFor(slot).fileName}`">
            <span class="extra-chip-progress" :style="{ '--progress': `${Math.round(uploadFor(slot).progress * 100)}%` }" aria-hidden="true" />
            <span class="extra-chip-name">{{ slot.name }}</span>
            <span class="extra-chip-note">{{ Math.round(uploadFor(slot).progress * 100) }}%</span>
          </span>

          <VMenu
            v-else
            :open="openMenu === slot.id"
            align="start"
            teleport
            panel-label="Add a file to this extra"
            panel-class="extra-fill-menu"
            @update:open="value => setMenu(slot.id, value)"
          >
            <template #trigger="{ triggerProps }">
              <button
                v-bind="triggerProps"
                type="button"
                class="extra-chip is-needed"
                :class="{ 'is-actionable': canAddExtraFiles }"
                :disabled="!canAddExtraFiles"
                :title="canAddExtraFiles ? `Add ${slot.name} for ${versionLabel}` : `${slot.name} is needed for ${versionLabel}`"
                @click="canAddExtraFiles && setMenu(slot.id, openMenu !== slot.id)"
              >
                <svg class="icon"><use :href="canAddExtraFiles ? '#icon-plus' : '#icon-clock'" /></svg>
                <span class="extra-chip-name">{{ slot.name }}</span>
                <span class="extra-chip-note">Needed</span>
              </button>
            </template>
            <div class="v-dropdown-label v-section-label">{{ slot.name }} for {{ versionLabel }}</div>
            <button type="button" class="v-dropdown-item" role="menuitem" @click="pickUpload(slot)">
              <svg class="icon"><use href="#icon-upload" /></svg> Upload from computer
            </button>
            <button type="button" class="v-dropdown-item" role="menuitem" @click="pickProjectFile(slot)">
              <svg class="icon"><use href="#icon-folder" /></svg> Choose a project file
            </button>
            <button
              v-for="earlier in earlierFiles(slot)"
              :key="earlier.version.id"
              type="button"
              class="v-dropdown-item"
              role="menuitem"
              @click="fillExtra(shot, slot, { fromVersionId: earlier.version.id }, version)"
            >
              <svg class="icon"><use href="#icon-undo" /></svg> Use the file from {{ formatVersionLabel(earlier.version) }}
            </button>
            <template v-if="canManageExtras">
              <div class="v-dropdown-divider"></div>
              <button type="button" class="v-dropdown-item v-dropdown-item-danger" role="menuitem" @click="confirmRemove(slot)">
                <svg class="icon"><use href="#icon-close" /></svg> No longer needed
              </button>
            </template>
          </VMenu>
        </template>

        <span v-for="upload in newUploads" :key="upload.key" class="extra-chip is-uploading" :title="`Uploading ${upload.fileName}`">
          <span class="extra-chip-progress" :style="{ '--progress': `${Math.round(upload.progress * 100)}%` }" aria-hidden="true" />
          <span class="extra-chip-name">{{ upload.name }}</span>
          <span class="extra-chip-note">{{ Math.round(upload.progress * 100) }}%</span>
        </span>

        <VMenu
          v-if="canAddExtraFiles"
          :open="openMenu === 'add'"
          align="start"
          teleport
          panel-label="Add an extra"
          panel-class="extra-fill-menu"
          @update:open="value => setMenu('add', value)"
        >
          <template #trigger="{ triggerProps }">
            <button
              v-bind="triggerProps"
              type="button"
              class="extra-add"
              :aria-label="`Add an extra to ${shot.shot_id}`"
              @click="canManageExtras ? setMenu('add', openMenu !== 'add') : openAddExtras(shot)"
            >
              <svg class="icon"><use href="#icon-plus" /></svg>
              <span>Add</span>
            </button>
          </template>
          <button type="button" class="v-dropdown-item" role="menuitem" @click="openAddExtras(shot)">
            <svg class="icon"><use href="#icon-upload" /></svg> Add files
          </button>
          <button type="button" class="v-dropdown-item" role="menuitem" @click="openAddExtras(shot, { mode: 'ask' })">
            <svg class="icon"><use href="#icon-clock" /></svg> Ask for an extra
          </button>
        </VMenu>
      </div>
    </div>
    <VMenu
      v-if="!shareMode && slots.length"
      :open="managerOpen"
      align="end"
      teleport
      :close-on-select="false"
      panel-role="dialog"
      :panel-label="`Extras of ${shot.shot_id}`"
      panel-class="extras-panel-menu"
      @update:open="value => { managerOpen = value }"
    >
      <template #trigger="{ triggerProps }">
        <button
          v-bind="triggerProps"
          type="button"
          class="trc-extras-manage"
          :aria-expanded="managerOpen ? 'true' : 'false'"
          :aria-label="`Manage the extras of ${shot.shot_id}`"
          title="Manage extras"
          @click="managerOpen = !managerOpen"
        >
          <svg class="icon"><use :href="managerOpen ? '#icon-chevron-up' : '#icon-chevron-down'" /></svg>
        </button>
      </template>
      <ShotExtrasPanel :shot="shot" :version="version" @close="managerOpen = false" />
    </VMenu>
    <input ref="fileInput" type="file" hidden @change="uploadPicked" />
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useTrackerStore } from '../../ownership/tracker'
import { VMenu } from '../primitives'
import ShotExtrasPanel from './ShotExtrasPanel.vue'

const props = defineProps({
  shot: { type: Object, required: true },
})

const {
  canAddExtraFiles,
  canCopyFilePaths,
  canManageExtras,
  canViewShotExtra,
  chooseExtraProjectFiles,
  copyExtraPath,
  downloadExtra,
  fillExtra,
  formatVersionLabel,
  getEarlierExtraFiles,
  getExtraSlots,
  getExtraThumbnailUrl,
  getUploadsFor,
  openAddExtras,
  openShotExtra,
  prefetchExtraPath,
  removeExtra,
  shareMode,
  showShotDownloads,
} = useTrackerStore()

const openMenu = ref('')
const managerOpen = ref(false)
const fileInput = ref(null)
const pendingFill = ref(null)
const failedThumbs = reactive({})

const version = computed(() => props.shot?.versions?.at(-1) || null)
const versionLabel = computed(() => (version.value ? formatVersionLabel(version.value) : 'this version'))
const slots = computed(() => getExtraSlots(props.shot, version.value))
const uploads = computed(() => getUploadsFor(props.shot, version.value))
const newUploads = computed(() => uploads.value.filter(upload => !upload.extraId))
const filledCount = computed(() => slots.value.filter(slot => slot.file).length)
const canDownload = computed(() => !shareMode.value || showShotDownloads.value)
const visible = computed(() => slots.value.length > 0 || newUploads.value.length > 0)

function uploadFor(slot) {
  return uploads.value.find(upload => upload.extraId === slot.id) || null
}

function thumbnail(slot) {
  return failedThumbs[slot.id] ? '' : getExtraThumbnailUrl(version.value, slot.file)
}

function canView(slot) {
  return canViewShotExtra(slot.file)
}

function chipTitle(slot) {
  if (slot.file.exists === false) return `${slot.name} is offline`
  const action = canView(slot) ? 'Open' : 'Download'
  return `${action} ${slot.file.download_name}`
}

function activate(slot) {
  if (canView(slot)) void openShotExtra(props.shot, version.value, slot.file)
  else if (canDownload.value) downloadExtra(version.value, slot.file)
}

function earlierFiles(slot) {
  return getEarlierExtraFiles(props.shot, slot.id, version.value).slice(0, 3)
}

function setMenu(key, open) {
  openMenu.value = open ? key : ''
}

function pickUpload(slot) {
  openMenu.value = ''
  pendingFill.value = slot
  fileInput.value?.click()
}

function uploadPicked(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  const slot = pendingFill.value
  pendingFill.value = null
  if (file && slot) void fillExtra(props.shot, slot, { file }, version.value)
}

async function pickProjectFile(slot) {
  openMenu.value = ''
  const [item] = await chooseExtraProjectFiles({ multiple: false })
  if (item?.file_path) await fillExtra(props.shot, slot, { filePath: item.file_path }, version.value)
}

function confirmRemove(slot) {
  openMenu.value = ''
  if (confirm(`Remove ${slot.name} from ${props.shot.shot_id}? Earlier versions lose this extra too. The files stay in the project.`)) {
    void removeExtra(props.shot, slot)
  }
}
</script>

<style scoped>
.trc-extras {
  position: relative;
  display: grid;
  grid-template-columns: var(--trc-lead-width, 36px) minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 5px 8px 6px 10px;
}

.trc-extras::before {
  content: '';
  position: absolute;
  inset: 0 10px auto;
  height: 1px;
  background: rgba(255, 255, 255, 0.045);
  pointer-events: none;
}

.trc-extras.is-open {
  background: color-mix(in srgb, var(--v-bg-hover) 55%, transparent);
}

.trc-extras-lead {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  width: var(--trc-lead-width, 36px);
}

.trc-extras-icon {
  width: 20px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: color-mix(in srgb, var(--v-text-dim) 88%, transparent);
}

.trc-extras-icon .icon {
  width: 15px;
  height: 15px;
}

.trc-extras-count {
  font-size: 10px;
  font-weight: 700;
  color: var(--v-text-muted);
  font-variant-numeric: tabular-nums;
}

.trc-extras-main {
  display: grid;
  grid-template-columns: var(--trc-label-width, 76px) minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.trc-extras-tag {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 600;
  white-space: nowrap;
}

.trc-extras-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.extra-chip {
  position: relative;
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  height: 26px;
  border-radius: var(--v-radius-sm);
  background: var(--v-surface-inline);
  box-shadow: inset 0 0 0 1px var(--v-surface-border-soft);
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  transition: background var(--v-transition-fast), box-shadow var(--v-transition-fast), color var(--v-transition-fast);
}

.extra-chip:hover,
.extra-chip:focus-within {
  background: var(--v-bg-hover);
  box-shadow: inset 0 0 0 1px var(--v-border-hover);
  color: var(--v-text);
}

.extra-chip-main {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  height: 100%;
  padding: 0 9px 0 3px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.extra-chip-main:focus-visible,
.extra-chip-action:focus-visible,
.extra-add:focus-visible,
.trc-extras-manage:focus-visible,
.extra-chip.is-needed:focus-visible {
  outline: 2px solid var(--v-accent-muted);
  outline-offset: 1px;
}

.extra-chip-thumb {
  width: 34px;
  height: 20px;
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 3px;
  overflow: hidden;
  background: #000;
  color: var(--v-text-dim);
}

.extra-chip-thumb.is-empty {
  background: var(--v-surface-inline-strong);
}

.extra-chip-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.extra-chip-thumb .icon {
  width: 12px;
  height: 12px;
}

/* When a chip is short of space, the note gives way before the name. */
.extra-chip-name {
  flex: 0 1 auto;
  min-width: 4ch;
  overflow: hidden;
  text-overflow: ellipsis;
}

.extra-chip-note {
  flex: 0 100 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--v-text-dim);
  font-weight: 500;
}

.extra-chip-note::before {
  content: '· ';
}

.extra-chip-flag {
  width: 12px;
  height: 12px;
  flex: none;
  color: var(--v-text-dim);
}

.extra-chip-actions {
  display: none;
  align-items: center;
  gap: 1px;
  padding: 0 3px 0 4px;
  border-left: 1px solid var(--v-divider-subtle);
}

.extra-chip:hover .extra-chip-actions,
.extra-chip:focus-within .extra-chip-actions {
  display: inline-flex;
}

.extra-chip-action {
  width: 20px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--v-text-secondary);
  cursor: pointer;
}

.extra-chip-action:hover {
  background: var(--v-surface-inline-strong);
  color: var(--v-text);
}

.extra-chip-action .icon {
  width: 13px;
  height: 13px;
}

.extra-chip.is-offline .extra-chip-thumb {
  opacity: 0.4;
}

.extra-chip.is-offline .extra-chip-name {
  text-decoration: line-through;
  text-decoration-color: color-mix(in srgb, var(--v-text-dim) 70%, transparent);
}

.extra-chip.is-needed {
  gap: 6px;
  padding: 0 9px;
  border: 1px dashed color-mix(in srgb, var(--v-warning) 55%, transparent);
  background: transparent;
  box-shadow: none;
  color: color-mix(in srgb, var(--v-warning) 82%, var(--v-text));
  font: inherit;
  font-size: var(--v-text-xs);
  font-weight: 600;
}

.extra-chip.is-needed .extra-chip-note {
  color: inherit;
  opacity: 0.72;
}

.extra-chip.is-needed .icon {
  width: 12px;
  height: 12px;
}

.extra-chip.is-needed.is-actionable {
  cursor: pointer;
}

.extra-chip.is-needed.is-actionable:hover {
  background: color-mix(in srgb, var(--v-warning) 11%, transparent);
  border-style: solid;
}

.extra-chip.is-needed:disabled {
  cursor: default;
}

.extra-chip.is-uploading {
  gap: 7px;
  padding: 0 9px 0 9px;
  color: var(--v-text);
}

.extra-chip-progress {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, color-mix(in srgb, var(--v-accent) 22%, transparent) var(--progress), transparent var(--progress));
  pointer-events: none;
}

.extra-add {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 9px;
  border: 1px dashed var(--v-surface-border-strong);
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: var(--v-text-muted);
  font: inherit;
  font-size: var(--v-text-xs);
  font-weight: 600;
  cursor: pointer;
}

.extra-add:hover {
  border-style: solid;
  color: var(--v-text);
  background: var(--v-surface-inline);
}

.extra-add .icon {
  width: 12px;
  height: 12px;
}

.trc-extras-manage {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: var(--v-text-muted);
  cursor: pointer;
}

.trc-extras-manage:hover {
  background: var(--v-surface-inline);
  color: var(--v-text);
}

.trc-extras-manage .icon {
  width: 14px;
  height: 14px;
}

/* Clients mostly download: their download button is always there. */
.trc-extras.is-shared .extra-chip-actions {
  display: inline-flex;
}

/* The manage panel opens under the whole row, not over a second line of chips. */
.trc-extras > .v-menu {
  align-self: end;
}

@media (hover: none) {
  .extra-chip-actions {
    display: inline-flex;
  }
}

/* On phones the label sits above the chips, as in the Brief row. */
@media (max-width: 768px) {
  .trc-extras {
    align-items: start;
    padding: 8px 8px 8px;
  }

  .trc-extras-lead {
    height: 20px;
  }

  .trc-extras-main {
    grid-template-columns: minmax(0, 1fr);
    gap: 6px;
  }
}
</style>
