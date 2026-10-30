<template>
  <section class="viewer-extras" :aria-label="`Extras of ${versionLabel}`">
    <header class="viewer-extras-head">
      <div>
        <h3>Extras of {{ versionLabel }}</h3>
        <p>{{ summary }}</p>
      </div>
      <button v-if="canAddExtraFiles" type="button" class="v-btn v-btn-secondary v-btn-sm" @click="openAddExtras(shot)">
        <svg class="icon"><use href="#icon-plus" /></svg>Add
      </button>
    </header>

    <ul class="viewer-extras-list">
      <li v-for="slot in slots" :key="slot.id" class="viewer-extra" :class="{ 'is-needed': !slot.file }">
        <button
          type="button"
          class="viewer-extra-thumb"
          :disabled="!slot.file || !canViewShotExtra(slot.file)"
          :aria-label="slot.file ? `Open ${slot.name}` : `${slot.name} is needed`"
          @click="slot.file && openShotExtra(shot, version, slot.file)"
        >
          <img v-if="slot.file && thumbnail(slot)" :src="thumbnail(slot)" alt="" loading="lazy" @error="failedThumbs[slot.id] = true" />
          <svg v-else class="icon"><use :href="slot.file ? '#icon-file' : '#icon-clock'" /></svg>
        </button>
        <div class="viewer-extra-info">
          <div class="viewer-extra-name">
            <span>{{ slot.name }}</span>
            <span v-if="slot.note" class="viewer-extra-note">· {{ slot.note }}</span>
            <svg v-if="!shareMode && slot.client_visible === false" class="icon viewer-extra-flag" aria-label="Only your team sees this"><use href="#icon-eye-off" /></svg>
          </div>
          <div v-if="slot.file" class="viewer-extra-file" :title="slot.file.download_name">{{ slot.file.download_name }}</div>
          <div v-else-if="uploadFor(slot)" class="viewer-extra-file">Uploading · {{ Math.round(uploadFor(slot).progress * 100) }}%</div>
          <div v-else class="viewer-extra-needed">Needed for {{ versionLabel }}</div>

          <div v-if="slot.file" class="viewer-extra-actions">
            <button
              v-if="canViewShotExtra(slot.file)"
              type="button"
              class="v-btn v-btn-ghost v-btn-sm"
              @click="openShotExtra(shot, version, slot.file)"
            >
              <svg class="icon"><use href="#icon-play" /></svg>View
            </button>
            <button
              v-if="canCompareShotExtra(version, slot.file)"
              type="button"
              class="v-btn v-btn-ghost v-btn-sm"
              :title="`See ${slot.name} on top of ${versionLabel} or beside it`"
              @click="startShotExtraCompare(shot, version, slot.file)"
            >
              <svg class="icon"><use href="#icon-compare" /></svg>Compare
            </button>
            <span class="viewer-extra-tools">
              <button
                v-if="!shareMode && canCopyFilePaths"
                type="button"
                class="v-btn v-btn-quiet v-btn-icon v-btn-sm"
                :aria-label="`Copy the path of ${slot.name}`"
                :title="`Copy the path of ${slot.name}`"
                @pointerenter="prefetchExtraPath(version, slot.file)"
                @click="copyExtraPath(version, slot.file)"
              >
                <svg class="icon"><use href="#icon-copy" /></svg>
              </button>
              <button
                v-if="canDownload && slot.file.exists !== false"
                type="button"
                class="v-btn v-btn-quiet v-btn-icon v-btn-sm"
                :aria-label="`Download ${slot.file.download_name}`"
                :title="`Download ${slot.file.download_name}`"
                @click="downloadExtra(version, slot.file)"
              >
                <svg class="icon"><use href="#icon-download" /></svg>
              </button>
            </span>
          </div>
          <div v-else-if="canAddExtraFiles && !uploadFor(slot)" class="viewer-extra-actions">
            <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click="pickUpload(slot)">
              <svg class="icon"><use href="#icon-upload" /></svg>Upload
            </button>
            <button type="button" class="v-btn v-btn-ghost v-btn-sm" @click="pickProjectFile(slot)">Project file</button>
            <button
              v-for="earlier in earlierFiles(slot)"
              :key="earlier.version.id"
              type="button"
              class="v-btn v-btn-ghost v-btn-sm"
              @click="fillExtra(shot, slot, { fromVersionId: earlier.version.id }, version)"
            >
              {{ formatVersionLabel(earlier.version) }}'s file
            </button>
          </div>
        </div>
      </li>
    </ul>

    <footer v-if="filledCount && canDownload" class="viewer-extras-foot">
      <button type="button" class="v-btn v-btn-secondary v-btn-sm" @click="downloadShotVersionPackage(shot, version)">
        <svg class="icon"><use href="#icon-download" /></svg>Download {{ versionLabel }} with extras
      </button>
    </footer>
    <input ref="fileInput" type="file" hidden @change="uploadPicked" />
  </section>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useTrackerStore } from '../../ownership/tracker'

const props = defineProps({
  shot: { type: Object, required: true },
  version: { type: Object, required: true },
})

const {
  canAddExtraFiles,
  canCompareShotExtra,
  canCopyFilePaths,
  canViewShotExtra,
  chooseExtraProjectFiles,
  copyExtraPath,
  downloadExtra,
  downloadShotVersionPackage,
  fillExtra,
  formatVersionLabel,
  getEarlierExtraFiles,
  getExtraSlots,
  getExtraThumbnailUrl,
  getUploadsFor,
  openAddExtras,
  openShotExtra,
  prefetchExtraPath,
  shareMode,
  showShotDownloads,
  startShotExtraCompare,
} = useTrackerStore()

const fileInput = ref(null)
const pendingFill = ref(null)
const failedThumbs = reactive({})

const versionLabel = computed(() => formatVersionLabel(props.version))
const slots = computed(() => getExtraSlots(props.shot, props.version))
const filledCount = computed(() => slots.value.filter(slot => slot.file).length)
const canDownload = computed(() => !shareMode.value || showShotDownloads.value)
const summary = computed(() => {
  const needed = slots.value.length - filledCount.value
  const files = `${filledCount.value} ${filledCount.value === 1 ? 'file' : 'files'}`
  return needed ? `${files} · ${needed} needed` : `${files} · they change with the version you open`
})

function thumbnail(slot) {
  return failedThumbs[slot.id] ? '' : getExtraThumbnailUrl(props.version, slot.file)
}

function uploadFor(slot) {
  return getUploadsFor(props.shot, props.version).find(upload => upload.extraId === slot.id) || null
}

function earlierFiles(slot) {
  return getEarlierExtraFiles(props.shot, slot.id, props.version).slice(0, 2)
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
  if (file && slot) void fillExtra(props.shot, slot, { file }, props.version)
}

async function pickProjectFile(slot) {
  const [item] = await chooseExtraProjectFiles({ multiple: false })
  if (item?.file_path) await fillExtra(props.shot, slot, { filePath: item.file_path }, props.version)
}
</script>

<style scoped>
.viewer-extras {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  color: var(--v-text);
}

.viewer-extras-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 14px 10px;
}

.viewer-extras-head h3 {
  margin: 0;
  font-size: var(--v-text-sm);
  font-weight: 700;
}

.viewer-extras-head p {
  margin: 2px 0 0;
  color: var(--v-text-dim);
  font-size: var(--v-text-xs);
}

.viewer-extras-list {
  margin: 0;
  padding: 0 8px;
  list-style: none;
}

.viewer-extra {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 10px;
  padding: 10px 6px;
  border-top: 1px solid var(--v-divider-subtle);
}

.viewer-extra-thumb {
  width: 72px;
  height: 40px;
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

.viewer-extra-thumb:disabled {
  cursor: default;
}

.viewer-extra.is-needed .viewer-extra-thumb {
  background: transparent;
  border: 1px dashed color-mix(in srgb, var(--v-warning) 50%, transparent);
  color: color-mix(in srgb, var(--v-warning) 80%, var(--v-text));
}

.viewer-extra-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.viewer-extra-thumb .icon {
  width: 14px;
  height: 14px;
}

.viewer-extra-info {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.viewer-extra-name {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  font-size: var(--v-text-sm);
  font-weight: 650;
}

.viewer-extra-name > span:first-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.viewer-extra-note {
  color: var(--v-text-dim);
  font-weight: 500;
  white-space: nowrap;
}

.viewer-extra-flag {
  width: 12px;
  height: 12px;
  flex: none;
  color: var(--v-text-dim);
}

.viewer-extra-file {
  color: var(--v-text-dim);
  font-family: var(--v-font-mono);
  font-size: var(--v-text-2xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.viewer-extra-needed {
  color: color-mix(in srgb, var(--v-warning) 85%, var(--v-text));
  font-size: var(--v-text-xs);
  font-weight: 600;
}

.viewer-extra-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 4px;
  margin-top: 4px;
  margin-left: -8px;
}

.viewer-extra.is-needed .viewer-extra-actions {
  margin-left: 0;
}

.viewer-extra-tools {
  display: inline-flex;
  margin-left: auto;
}

.viewer-extras-foot {
  padding: 12px 14px 16px;
  border-top: 1px solid var(--v-divider-subtle);
}
</style>
