<template>
  <section class="extras-panel" :aria-label="`Extras of ${shot.shot_id} ${versionLabel}`">
    <header class="extras-panel-head">
      <div class="extras-panel-heading">
        <strong>Extras of {{ versionLabel }}</strong>
        <span>{{ summary }}</span>
      </div>
      <div class="extras-panel-head-actions">
        <button v-if="canManageExtras" type="button" class="v-btn v-btn-ghost v-btn-sm" @click="openAddExtras(shot, { mode: 'ask' }); emit('close')">
          <svg class="icon"><use href="#icon-clock" /></svg>Ask for
        </button>
        <button v-if="canAddExtraFiles" type="button" class="v-btn v-btn-secondary v-btn-sm" @click="openAddExtras(shot); emit('close')">
          <svg class="icon"><use href="#icon-plus" /></svg>Add
        </button>
      </div>
    </header>

    <ol class="extras-panel-list">
      <li
        v-for="(slot, index) in slots"
        :key="slot.id"
        class="extras-panel-row"
        :class="{ 'is-needed': !slot.file, 'is-team-only': slot.client_visible === false }"
      >
        <div v-if="canManageExtras && slots.length > 1" class="extras-panel-order">
          <button type="button" :disabled="index === 0 || busy(slot)" :aria-label="`Move ${slot.name} up`" title="Move up" @click="moveExtra(shot, slot, -1)">
            <svg class="icon"><use href="#icon-chevron-up" /></svg>
          </button>
          <button type="button" :disabled="index === slots.length - 1 || busy(slot)" :aria-label="`Move ${slot.name} down`" title="Move down" @click="moveExtra(shot, slot, 1)">
            <svg class="icon"><use href="#icon-chevron-down" /></svg>
          </button>
        </div>

        <button
          type="button"
          class="extras-panel-thumb"
          :class="{ 'is-empty': !slot.file || !thumbnail(slot) }"
          :disabled="!slot.file || !canViewShotExtra(slot.file)"
          :aria-label="slot.file ? `Open ${slot.name}` : `${slot.name} has no file for ${versionLabel}`"
          @click="open(slot)"
        >
          <img v-if="slot.file && thumbnail(slot)" :src="thumbnail(slot)" alt="" loading="lazy" @error="failedThumbs[slot.id] = true" />
          <svg v-else class="icon"><use :href="slot.file ? (slot.file.is_image ? '#icon-image' : '#icon-file') : '#icon-clock'" /></svg>
        </button>

        <div class="extras-panel-info">
          <form v-if="editing === slot.id" class="extras-panel-edit" @submit.prevent="saveEdit(slot)">
            <input ref="editInput" v-model="draft.name" class="v-input" maxlength="60" aria-label="Extra name" @keydown.esc.prevent="editing = ''" />
            <input v-model="draft.note" class="v-input" maxlength="80" placeholder="Note, such as Window" aria-label="Note" @keydown.esc.prevent="editing = ''" />
            <button type="submit" class="v-btn v-btn-primary v-btn-sm" :disabled="!draft.name.trim()">Save</button>
            <button type="button" class="v-btn v-btn-ghost v-btn-sm" @click="editing = ''">Cancel</button>
          </form>
          <template v-else>
            <div class="extras-panel-name">
              <span>{{ slot.name }}</span>
              <span v-if="slot.note" class="extras-panel-note">· {{ slot.note }}</span>
              <span v-if="slot.client_visible === false" class="extras-panel-pill">Only your team</span>
              <span v-if="!slot.file" class="extras-panel-pill is-needed">Needed</span>
              <button v-if="canManageExtras" type="button" class="extras-panel-icon-btn" :aria-label="`Rename ${slot.name}`" title="Rename" @click="startEdit(slot)">
                <svg class="icon"><use href="#icon-edit" /></svg>
              </button>
            </div>
            <div v-if="slot.file" class="extras-panel-file" :title="slot.file.download_name">
              <svg class="icon" aria-hidden="true"><use href="#icon-download" /></svg>
              <span>{{ slot.file.download_name }}</span>
              <span v-if="slot.file.exists === false" class="extras-panel-offline">Offline</span>
            </div>
            <div v-if="uploadFor(slot)" class="extras-panel-progress" role="status">
              <span :style="{ width: `${Math.round(uploadFor(slot).progress * 100)}%` }" />
              Uploading {{ uploadFor(slot).fileName }} · {{ Math.round(uploadFor(slot).progress * 100) }}%
            </div>
            <div v-else-if="canAddExtraFiles && (!slot.file || replacing === slot.id)" class="extras-panel-fill">
              <span class="extras-panel-fill-label">{{ slot.file ? 'Replace with' : 'Add a file' }}</span>
              <button type="button" class="v-btn v-btn-secondary v-btn-sm extras-panel-mini" :disabled="busy(slot)" @click="pickUpload(slot)">Upload</button>
              <button type="button" class="v-btn v-btn-secondary v-btn-sm extras-panel-mini" :disabled="busy(slot)" @click="pickProjectFile(slot)">Project file</button>
              <button
                v-for="earlier in earlierFiles(slot)"
                :key="earlier.version.id"
                type="button"
                class="v-btn v-btn-secondary v-btn-sm extras-panel-mini"
                :disabled="busy(slot)"
                @click="fill(slot, { fromVersionId: earlier.version.id })"
              >
                {{ formatVersionLabel(earlier.version) }}'s file
              </button>
              <button v-if="replacing === slot.id" type="button" class="v-btn v-btn-ghost v-btn-sm extras-panel-mini" @click="replacing = ''">Cancel</button>
            </div>
          </template>
        </div>

        <div v-if="editing !== slot.id" class="extras-panel-actions">
          <button
            v-if="canManageExtras"
            type="button"
            class="extras-panel-icon-btn"
            :class="{ 'is-on': slot.client_visible !== false }"
            :disabled="busy(slot)"
            :aria-pressed="slot.client_visible !== false ? 'true' : 'false'"
            :aria-label="slot.client_visible === false ? `Show ${slot.name} to clients` : `Keep ${slot.name} for your team only`"
            :title="slot.client_visible === false ? 'Only your team sees this. Select to show it to clients.' : 'Clients see this. Select to keep it for your team only.'"
            @click="updateExtra(shot, slot, { client_visible: slot.client_visible === false })"
          >
            <svg class="icon"><use :href="slot.client_visible === false ? '#icon-eye-off' : '#icon-eye'" /></svg>
          </button>
          <template v-if="slot.file">
            <button
              v-if="canViewShotExtra(slot.file)"
              type="button"
              class="extras-panel-icon-btn"
              :aria-label="`View ${slot.name}`"
              title="View"
              @click="open(slot)"
            >
              <svg class="icon"><use href="#icon-play" /></svg>
            </button>
            <button
              v-if="canCopyFilePaths && !shareMode"
              type="button"
              class="extras-panel-icon-btn"
              :aria-label="`Copy the path of ${slot.name}`"
              title="Copy path"
              @pointerenter="prefetchExtraPath(version, slot.file)"
              @click="copyExtraPath(version, slot.file)"
            >
              <svg class="icon"><use href="#icon-copy" /></svg>
            </button>
            <button
              v-if="canDownload"
              type="button"
              class="extras-panel-icon-btn"
              :disabled="slot.file.exists === false"
              :aria-label="`Download ${slot.file.download_name}`"
              title="Download"
              @click="downloadExtra(version, slot.file)"
            >
              <svg class="icon"><use href="#icon-download" /></svg>
            </button>
            <button
              v-if="canAddExtraFiles"
              type="button"
              class="extras-panel-icon-btn"
              :class="{ 'is-on': replacing === slot.id }"
              :aria-label="`Replace the file of ${slot.name} for ${versionLabel}`"
              title="Replace file"
              @click="replacing = replacing === slot.id ? '' : slot.id"
            >
              <svg class="icon"><use href="#icon-refresh" /></svg>
            </button>
            <button
              v-if="canManageExtras"
              type="button"
              class="extras-panel-icon-btn"
              :disabled="busy(slot)"
              :aria-label="`Remove the file of ${slot.name} from ${versionLabel}`"
              :title="`Remove the file from ${versionLabel}. ${slot.name} stays and shows as needed.`"
              @click="clearFile(slot)"
            >
              <svg class="icon"><use href="#icon-close" /></svg>
            </button>
          </template>
          <button
            v-if="canManageExtras"
            type="button"
            class="extras-panel-icon-btn is-danger"
            :disabled="busy(slot)"
            :aria-label="`Remove ${slot.name} from the shot`"
            title="Remove from the shot"
            @click="remove(slot)"
          >
            <svg class="icon"><use href="#icon-trash" /></svg>
          </button>
        </div>
      </li>
    </ol>

    <footer v-if="!shareMode || (filledCount && canDownload)" class="extras-panel-foot">
      <span v-if="!shareMode">{{ slots.length > 1 ? 'Extras with the same name are numbered in this order.' : 'A new version starts with this extra needed.' }}</span>
      <button v-if="filledCount && canDownload" type="button" class="v-btn v-btn-primary v-btn-sm" @click="downloadShotVersionPackage(shot, version); emit('close')">
        <svg class="icon"><use href="#icon-download" /></svg>Download {{ versionLabel }} with extras
      </button>
    </footer>
    <input ref="fileInput" type="file" hidden @change="uploadPicked" />
  </section>
</template>

<script setup>
import { computed, nextTick, reactive, ref } from 'vue'
import { useTrackerStore } from '../../ownership/tracker'

const props = defineProps({
  shot: { type: Object, required: true },
  version: { type: Object, default: null },
})
const emit = defineEmits(['close'])

const {
  canAddExtraFiles,
  canCopyFilePaths,
  canManageExtras,
  canViewShotExtra,
  chooseExtraProjectFiles,
  clearExtraFile,
  copyExtraPath,
  downloadExtra,
  downloadShotVersionPackage,
  extraBusy,
  fillExtra,
  formatVersionLabel,
  getEarlierExtraFiles,
  getExtraSlots,
  getExtraThumbnailUrl,
  getUploadsFor,
  moveExtra,
  openAddExtras,
  openShotExtra,
  prefetchExtraPath,
  removeExtra,
  shareMode,
  showShotDownloads,
  updateExtra,
} = useTrackerStore()

const editing = ref('')
const replacing = ref('')
const draft = reactive({ name: '', note: '' })
const editInput = ref(null)
const fileInput = ref(null)
const pendingFill = ref(null)
const failedThumbs = reactive({})

const versionLabel = computed(() => (props.version ? formatVersionLabel(props.version) : 'this version'))
const slots = computed(() => getExtraSlots(props.shot, props.version))
const filledCount = computed(() => slots.value.filter(slot => slot.file).length)
// Share links can turn downloads off; the team can always download.
const canDownload = computed(() => !shareMode.value || showShotDownloads.value)
const summary = computed(() => {
  const needed = slots.value.length - filledCount.value
  const files = `${filledCount.value} ${filledCount.value === 1 ? 'file' : 'files'}`
  return needed ? `${files} · ${needed} needed` : files
})

function busy(slot) {
  return Boolean(extraBusy[`${props.shot.id}:${slot.id}`] || extraBusy[`order:${props.shot.id}`])
}

function uploadFor(slot) {
  return getUploadsFor(props.shot, props.version).find(upload => upload.extraId === slot.id) || null
}

function thumbnail(slot) {
  return failedThumbs[slot.id] ? '' : getExtraThumbnailUrl(props.version, slot.file)
}

function earlierFiles(slot) {
  return getEarlierExtraFiles(props.shot, slot.id, props.version).slice(0, 2)
}

function open(slot) {
  if (!slot.file || !canViewShotExtra(slot.file)) return
  emit('close')
  void openShotExtra(props.shot, props.version, slot.file)
}

async function startEdit(slot) {
  editing.value = slot.id
  draft.name = slot.base_name || slot.name
  draft.note = slot.note || ''
  await nextTick()
  const input = Array.isArray(editInput.value) ? editInput.value[0] : editInput.value
  input?.focus?.()
  input?.select?.()
}

async function saveEdit(slot) {
  const name = draft.name.trim()
  if (!name) return
  const changes = {}
  if (name !== (slot.base_name || slot.name)) changes.name = name
  if ((draft.note.trim() || null) !== (slot.note || null)) changes.note = draft.note.trim()
  editing.value = ''
  if (Object.keys(changes).length) await updateExtra(props.shot, slot, changes)
}

async function fill(slot, source) {
  replacing.value = ''
  await fillExtra(props.shot, slot, source, props.version)
}

function pickUpload(slot) {
  pendingFill.value = slot
  fileInput.value?.click()
}

function uploadPicked(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  const slot = pendingFill.value
  pendingFill.value = null
  if (file && slot) void fill(slot, { file })
}

async function pickProjectFile(slot) {
  const [item] = await chooseExtraProjectFiles({ multiple: false })
  if (item?.file_path) await fill(slot, { filePath: item.file_path })
}

function clearFile(slot) {
  void clearExtraFile(props.shot, slot, props.version)
}

function remove(slot) {
  const earlier = (props.shot.versions || []).some(version => version.id !== props.version?.id && (version.extras || []).some(file => file.extra_id === slot.id))
  const warning = earlier ? ' Earlier versions lose it too.' : ''
  if (confirm(`Remove ${slot.name} from ${props.shot.shot_id}?${warning} The files stay in the project.`)) {
    void removeExtra(props.shot, slot)
  }
}
</script>

<style scoped>
.extras-panel {
  width: min(560px, calc(100vw - 32px));
  max-height: min(70vh, 640px);
  display: flex;
  flex-direction: column;
  color: var(--v-text);
}

.extras-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px 10px 14px;
  border-bottom: 1px solid var(--v-divider-subtle);
}

.extras-panel-heading {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.extras-panel-heading strong {
  font-size: var(--v-text-sm);
}

.extras-panel-heading span {
  color: var(--v-text-dim);
  font-size: var(--v-text-xs);
}

.extras-panel-head-actions {
  display: flex;
  gap: 6px;
}

.extras-panel-list {
  margin: 0;
  padding: 0;
  list-style: none;
  overflow-y: auto;
}

.extras-panel-row {
  display: grid;
  grid-template-columns: auto 64px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 9px 12px 9px 10px;
  border-bottom: 1px solid var(--v-divider-subtle);
}

.extras-panel-row:last-child {
  border-bottom: 0;
}

.extras-panel-order {
  display: flex;
  flex-direction: column;
}

.extras-panel-order button {
  width: 18px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 3px;
  background: transparent;
  color: var(--v-text-dim);
  cursor: pointer;
}

.extras-panel-order button:hover:not(:disabled) {
  color: var(--v-text);
  background: var(--v-surface-inline);
}

.extras-panel-order button:disabled {
  opacity: 0.3;
  cursor: default;
}

.extras-panel-order .icon {
  width: 12px;
  height: 12px;
}

.extras-panel-thumb {
  grid-column: 2;
  width: 64px;
  height: 36px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 4px;
  overflow: hidden;
  background: #000;
  color: var(--v-text-dim);
  cursor: pointer;
}

.extras-panel-thumb.is-empty {
  background: var(--v-surface-inline);
}

.extras-panel-row.is-needed .extras-panel-thumb {
  background: transparent;
  border: 1px dashed color-mix(in srgb, var(--v-warning) 50%, transparent);
  color: color-mix(in srgb, var(--v-warning) 80%, var(--v-text));
}

.extras-panel-thumb:disabled {
  cursor: default;
}

.extras-panel-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.extras-panel-thumb .icon {
  width: 14px;
  height: 14px;
}

.extras-panel-row.is-team-only .extras-panel-thumb img {
  opacity: 0.6;
}

.extras-panel-info {
  grid-column: 3;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.extras-panel-name {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: var(--v-text-sm);
  font-weight: 650;
}

/* When space is short, the note gives way before the name. */
.extras-panel-name > span:first-child {
  flex: 0 1 auto;
  min-width: 4ch;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.extras-panel-note {
  flex: 0 10000 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--v-text-dim);
  font-weight: 500;
  white-space: nowrap;
}

.extras-panel-pill {
  flex: none;
  height: 18px;
  padding: 0 7px;
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  background: var(--v-surface-inline-strong);
  color: var(--v-text-muted);
  font-size: 10px;
  font-weight: 700;
}

.extras-panel-pill.is-needed {
  background: color-mix(in srgb, var(--v-warning) 15%, transparent);
  color: color-mix(in srgb, var(--v-warning) 85%, var(--v-text));
}

.extras-panel-file {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  color: var(--v-text-dim);
  font-family: var(--v-font-mono);
  font-size: var(--v-text-2xs);
}

.extras-panel-file span:first-of-type {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.extras-panel-file .icon {
  width: 11px;
  height: 11px;
  flex: none;
}

.extras-panel-offline {
  flex: none;
  color: var(--v-warning);
  font-family: var(--v-font);
  font-weight: 600;
}

.extras-panel-fill {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
}

.extras-panel-mini {
  height: 24px;
  min-height: 24px;
  padding: 0 8px;
  font-size: var(--v-text-2xs);
}

.extras-panel-fill-label {
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 600;
  margin-right: 2px;
}

.extras-panel-progress {
  position: relative;
  overflow: hidden;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--v-surface-inline);
  color: var(--v-text-secondary);
  font-size: var(--v-text-2xs);
}

.extras-panel-progress span {
  position: absolute;
  inset: 0 auto 0 0;
  background: color-mix(in srgb, var(--v-accent) 24%, transparent);
}

.extras-panel-edit {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto auto;
  gap: 6px;
}

.extras-panel-edit .v-input {
  height: 28px;
  min-height: 28px;
  font-size: var(--v-text-xs);
}

.extras-panel-actions {
  grid-column: 4;
  display: flex;
  align-items: center;
  gap: 1px;
}

.extras-panel-icon-btn {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: var(--v-icon-btn-radius, 6px);
  background: transparent;
  color: var(--v-text-muted);
  cursor: pointer;
}

.extras-panel-name .extras-panel-icon-btn {
  width: 22px;
  height: 22px;
  opacity: 0;
}

.extras-panel-row:hover .extras-panel-name .extras-panel-icon-btn,
.extras-panel-name .extras-panel-icon-btn:focus-visible {
  opacity: 1;
}

.extras-panel-icon-btn:hover:not(:disabled) {
  background: var(--v-surface-inline);
  color: var(--v-text);
}

.extras-panel-icon-btn.is-on {
  color: var(--v-text);
}

.extras-panel-icon-btn.is-danger:hover:not(:disabled) {
  color: var(--v-danger-text);
}

.extras-panel-icon-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.extras-panel-icon-btn .icon {
  width: 15px;
  height: 15px;
}

.extras-panel-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px 10px 14px;
  border-top: 1px solid var(--v-divider-subtle);
  background: var(--v-modal-footer-bg, transparent);
  color: var(--v-text-dim);
  font-size: var(--v-text-xs);
}

.extras-panel-foot > .v-btn {
  margin-left: auto;
}

@media (hover: none) {
  .extras-panel-name .extras-panel-icon-btn {
    opacity: 1;
  }
}

/* On phones the actions take their own line under each extra, so names stay readable. */
@media (max-width: 640px) {
  .extras-panel-row {
    grid-template-columns: auto 64px minmax(0, 1fr);
    row-gap: 6px;
  }

  .extras-panel-actions {
    grid-column: 2 / -1;
    flex-wrap: wrap;
    gap: 4px;
  }

  .extras-panel-icon-btn {
    width: 36px;
    height: 36px;
  }

  .extras-panel-order button {
    width: 28px;
    height: 24px;
  }

  .extras-panel-foot {
    flex-wrap: wrap;
  }
}
</style>
