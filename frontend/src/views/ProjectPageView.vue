<template>
  <section class="project-page-surface">
    <div class="project-page-canvas">
      <!-- ─── HERO ──────────────────────────────────────────── -->
      <header class="dash-hero">
        <div class="dash-hero-topline">
          <div class="dash-hero-eyebrow">
            <span class="v-eyebrow">Project Home</span>
          </div>

          <div v-if="canManagePage" class="dash-hero-tools">
            <span
              v-if="saveStateLabel"
              class="dash-hero-savestate"
              :class="`is-${autosaveState}`"
              aria-live="polite"
            >
              <svg v-if="autosaveState === 'saving'" class="icon dash-hero-savestate-spinner"><use href="#icon-loader"/></svg>
              <svg v-else-if="autosaveState === 'saved'" class="icon"><use href="#icon-check"/></svg>
              <svg v-else-if="autosaveState === 'error'" class="icon"><use href="#icon-info"/></svg>
              <span>{{ saveStateLabel }}</span>
            </span>
            <button
              type="button"
              class="dash-preview-toggle"
              :class="{ 'is-active': sharedPreviewMode }"
              :aria-pressed="sharedPreviewMode"
              @click="sharedPreviewMode = !sharedPreviewMode"
            >
              <svg class="icon"><use :href="sharedPreviewMode ? '#icon-eye-off' : '#icon-eye'"/></svg>
              <span>{{ sharedPreviewMode ? 'Edit' : 'Preview' }}</span>
            </button>
          </div>
        </div>

        <input
          v-if="canEditDashboard"
          v-model="draft.title"
          class="dash-hero-title-input"
          placeholder="Untitled dashboard"
          @input="scheduleSave"
          @blur="flushSave"
        />
        <h1 v-else class="dash-hero-title-static">{{ displayPage?.title || 'Untitled dashboard' }}</h1>

        <textarea
          v-if="canEditDashboard"
          v-model="draft.description"
          class="dash-hero-desc-input"
          placeholder="Add a short client-facing description"
          rows="1"
          @input="scheduleSave"
          @blur="flushSave"
        ></textarea>
        <p v-else-if="displayPage?.description" class="dash-hero-desc-static">{{ displayPage.description }}</p>

        <div class="dash-hero-meta" aria-label="Dashboard summary">
          <span v-if="lastUpdatedLabel" class="dash-meta-item is-updated">
            <svg class="icon"><use href="#icon-clock"/></svg>
            <span>{{ lastUpdatedLabel }}</span>
          </span>
          <span class="dash-meta-item">
            <strong>{{ dashboardSummary.trackers }}</strong>
            <span>{{ dashboardSummary.trackers === 1 ? 'tracker' : 'trackers' }}</span>
          </span>
          <span v-if="dashboardSummary.resources" class="dash-meta-item">
            <strong>{{ dashboardSummary.resources }}</strong>
            <span>{{ dashboardSummary.resources === 1 ? 'resource' : 'resources' }}</span>
          </span>
          <span v-if="dashboardSummary.uploads" class="dash-meta-item">
            <strong>{{ dashboardSummary.uploads }}</strong>
            <span>{{ dashboardSummary.uploads === 1 ? 'inbox' : 'inboxes' }}</span>
          </span>
        </div>
      </header>

      <!-- ─── BLOCKS ────────────────────────────────────────── -->
      <main class="dash-stream">
        <template v-for="(block, index) in displayedBlocks" :key="block.id || index">
          <article
            class="dash-block"
            :class="[blockDragClass(block, index), { 'is-readonly': !canEditDashboard }]"
            @dragover.prevent="onBlockDragOver(index)"
            @drop.prevent="dropBlock(index)"
          >
            <!-- Drag rail -->
            <div v-if="canEditDashboard" class="dash-block-rail">
              <button
                type="button"
                class="dash-block-drag"
                title="Drag to reorder"
                draggable="true"
                aria-label="Drag block to reorder"
                @dragstart="startBlockDrag($event, index)"
                @dragend="endBlockDrag"
              >
                <svg class="icon"><use href="#icon-drag"/></svg>
              </button>
            </div>

            <div class="dash-block-body">
              <!-- Block head: icon + title + actions -->
              <div class="dash-block-head">
                <span
                  class="dash-block-icon"
                  :class="`is-${block.type}`"
                  aria-hidden="true"
                >
                  <svg class="icon"><use :href="blockIcon(block.type)"/></svg>
                </span>

                <input
                  v-if="canEditDashboard"
                  v-model="block.title"
                  class="dash-block-title-input"
                  :placeholder="blockPlaceholder(block.type)"
                  @input="scheduleSave"
                  @blur="flushSave"
                />
                <h2 v-else class="dash-block-title-static">{{ block.title || blockPlaceholder(block.type) }}</h2>

                <div v-if="canEditDashboard" class="dash-block-actions">
                  <button
                    type="button"
                    class="v-icon-action is-compact is-muted dash-block-action-move"
                    title="Move block up"
                    :disabled="index === 0"
                    @click="moveBlock(index, -1)"
                  >
                    <svg class="icon"><use href="#icon-chevron-up"/></svg>
                  </button>
                  <button
                    type="button"
                    class="v-icon-action is-compact is-muted dash-block-action-move"
                    title="Move block down"
                    :disabled="index === displayedBlocks.length - 1"
                    @click="moveBlock(index, 1)"
                  >
                    <svg class="icon"><use href="#icon-chevron-down"/></svg>
                  </button>
                  <button
                    type="button"
                    class="v-icon-action is-compact is-muted"
                    :class="{ 'is-active': block.hidden }"
                    :title="block.hidden ? 'Show block' : 'Hide block'"
                    @click="toggleHidden(block)"
                  >
                    <svg class="icon"><use :href="block.hidden ? '#icon-eye' : '#icon-eye-off'"/></svg>
                  </button>
                  <button
                    type="button"
                    class="v-icon-action is-compact is-muted is-danger"
                    title="Remove block"
                    @click="removeBlock(index)"
                  >
                    <svg class="icon"><use href="#icon-trash"/></svg>
                  </button>
                </div>
              </div>

              <!-- TEXT block -->
              <template v-if="block.type === 'text'">
                <textarea
                  v-if="canEditDashboard"
                  v-model="block.body"
                  class="dash-text-input"
                  placeholder="Write project notes, context, or instructions."
                  @input="scheduleSave"
                  @blur="flushSave"
                ></textarea>
                <p v-else-if="block.body" class="dash-text-copy">{{ block.body }}</p>
                <p v-else-if="!isPublicPresentation" class="dash-text-empty">No notes yet.</p>
              </template>

              <!-- TRACKER LIST block -->
              <template v-else-if="block.type === 'tracker_list'">
                <div v-if="trackerEntries(block).length" class="dash-tracker-grid">
                  <template v-for="entry in trackerEntries(block)" :key="entry.key">
                    <button
                      v-if="entry.tracker"
                      type="button"
                      class="dash-tracker-card"
                      :aria-label="`Open ${entry.tracker.name}`"
                      @click="openTracker(entry.tracker.id || entry.tracker.slug || entry.tracker.name)"
                    >
                      <span class="dash-tracker-main">
                        <span class="dash-tracker-mark" aria-hidden="true">
                          <svg class="icon"><use href="#icon-project"/></svg>
                        </span>
                        <span class="dash-tracker-title-group">
                          <strong class="v-truncate">{{ entry.tracker.name }}</strong>
                          <span>{{ trackerMetaLabel(entry.tracker) }}</span>
                        </span>
                      </span>

                      <span class="dash-tracker-side">
                        <span v-if="trackerStatusLabels(entry.tracker).length" class="dash-tracker-status-labels">
                          <span
                            v-for="segment in trackerStatusLabels(entry.tracker)"
                            :key="segment.status"
                            class="dash-tracker-status-chip"
                            :style="trackerStatusChipStyle(segment.status)"
                          >
                            {{ segment.count }} {{ segment.label }}
                          </span>
                        </span>

                        <span class="dash-tracker-open" aria-hidden="true">
                          <svg class="icon"><use href="#icon-external-link"/></svg>
                        </span>
                      </span>
                    </button>
                    <div v-else-if="canManagePage && !isPublicPresentation" class="dash-tracker-missing">
                      <svg class="icon"><use href="#icon-info"/></svg>
                      <span>
                        <strong>Missing tracker</strong>
                        <span>{{ entry.ref }}</span>
                      </span>
                    </div>
                  </template>
                </div>
                <div v-else-if="!isPublicPresentation" class="dash-block-empty">
                  <svg class="icon"><use href="#icon-project"/></svg>
                  <span>{{ canEditDashboard ? 'Pick trackers below to feature them on this dashboard.' : 'No Vue Trackers selected.' }}</span>
                </div>

                <div v-if="canEditDashboard" class="dash-tracker-picker">
                  <span class="v-eyebrow">Available trackers</span>
                  <div class="dash-tracker-picker-row">
                    <button
                      v-for="tracker in projectTrackerItems"
                      :key="trackerKey(tracker)"
                      type="button"
                      class="dash-tracker-chip"
                      :class="{ 'is-selected': hasTracker(block, tracker) }"
                      :aria-pressed="hasTracker(block, tracker)"
                      @click="toggleTracker(block, tracker)"
                    >
                      <svg v-if="hasTracker(block, tracker)" class="icon dash-tracker-chip-check" aria-hidden="true"><use href="#icon-check"/></svg>
                      <svg v-else class="icon dash-tracker-chip-plus" aria-hidden="true"><use href="#icon-plus"/></svg>
                      <span>{{ tracker.name }}</span>
                    </button>
                    <span v-if="!projectTrackerItems.length" class="dash-tracker-picker-hint">
                      No trackers in this project yet.
                    </span>
                  </div>
                </div>
              </template>

              <!-- RESOURCE LIST block -->
              <template v-else-if="block.type === 'resource_list'">
                <form
                  v-if="canEditDashboard && activeLinkBlockId === block.id"
                  class="dash-link-form"
                  @submit.prevent="addLinkResource(block)"
                >
                  <span class="dash-link-form-icon" aria-hidden="true">
                    <svg class="icon"><use href="#icon-link"/></svg>
                  </span>
                  <input
                    v-model="linkUrl"
                    class="dash-link-form-input"
                    placeholder="Paste a URL (e.g. figma.com/file/…)"
                    autofocus
                  />
                  <button type="submit" class="v-btn v-btn-primary v-btn-sm">Add link</button>
                  <button type="button" class="v-btn v-btn-ghost v-btn-sm" @click="cancelLink">Cancel</button>
                </form>

                <div v-if="(block.resources || []).length" class="dash-resource-grid">
                  <article
                    v-for="resource in block.resources"
                    :key="resource.id || resource.url || resource.path"
                    class="dash-resource-card"
                    :class="[`is-${resource.kind || 'file'}`, { 'is-media': isMediaResource(resource) }]"
                  >
                    <button
                      type="button"
                      class="dash-resource-thumb"
                      :title="`Open ${resource.label || resourceName(resource)}`"
                      @click="openResource(resource)"
                    >
                      <span v-if="isMediaResource(resource)" class="dash-resource-thumb-media">
                        <VMediaThumbnail :src="getResourceThumbnail(resource)" :alt="resource.label || resource.name || 'Resource'" />
                      </span>
                      <span v-else-if="resource.kind === 'url'" class="dash-resource-thumb-favicon">
                        <svg class="icon"><use href="#icon-link"/></svg>
                      </span>
                      <span v-else class="dash-resource-thumb-icon">
                        <svg class="icon"><use :href="resourceIcon(resource)"/></svg>
                      </span>
                      <span class="dash-resource-thumb-kind" aria-hidden="true">{{ resourceKindLabel(resource) }}</span>
                    </button>
                    <div class="dash-resource-copy">
                      <input
                        v-if="canEditDashboard"
                        v-model="resource.label"
                        class="dash-resource-title-input"
                        :placeholder="resourceName(resource)"
                        @input="scheduleSave"
                        @blur="flushSave"
                      />
                      <strong v-else class="dash-resource-title-static v-truncate">{{ resource.label || resourceName(resource) }}</strong>
                      <span class="dash-resource-meta v-truncate">{{ resourceMeta(resource) }}</span>
                      <span class="dash-resource-actions">
                        <button
                          type="button"
                          class="dash-resource-open"
                          @click.stop="openResource(resource)"
                        >
                          <span>{{ resourceActionLabel(resource) }}</span>
                          <svg class="icon"><use href="#icon-external-link"/></svg>
                        </button>
                        <button
                          v-if="canDownloadResource(resource)"
                          type="button"
                          class="dash-resource-download"
                          title="Download resource"
                          @click.stop="downloadResource(resource)"
                        >
                          <svg class="icon"><use href="#icon-download"/></svg>
                        </button>
                      </span>
                    </div>
                    <button
                      v-if="canEditDashboard"
                      type="button"
                      class="v-icon-action is-compact is-muted is-danger dash-resource-remove"
                      title="Remove resource"
                      @click="removeResource(block, resource)"
                    >
                      <svg class="icon"><use href="#icon-trash"/></svg>
                    </button>
                  </article>
                </div>
                <div v-else-if="!isPublicPresentation && !(canEditDashboard && activeLinkBlockId === block.id)" class="dash-block-empty">
                  <svg class="icon"><use href="#icon-link"/></svg>
                  <span>{{ canEditDashboard ? 'Add a link, storage file, or upload to start curating.' : 'No resources selected.' }}</span>
                </div>

                <div v-if="canEditDashboard && activeLinkBlockId !== block.id" class="dash-resource-toolbar">
                  <button type="button" class="dash-add-pill" @click="beginLink(block)">
                    <svg class="icon"><use href="#icon-link"/></svg>
                    <span>Add link</span>
                  </button>
                  <button type="button" class="dash-add-pill" @click="openPageResourcePicker(block.id)">
                    <svg class="icon"><use href="#icon-folder"/></svg>
                    <span>Choose from storage</span>
                  </button>
                  <button type="button" class="dash-add-pill" @click="openPageResourceUpload(block.id, getUploadTarget())">
                    <svg class="icon"><use href="#icon-upload"/></svg>
                    <span>Upload</span>
                  </button>
                </div>
              </template>

              <!-- UPLOAD INBOX block -->
              <template v-else-if="block.type === 'upload_inbox'">
                <textarea
                  v-if="canEditDashboard"
                  v-model="block.description"
                  class="dash-text-input is-compact"
                  placeholder="Short upload instructions (visible to clients on the share page)."
                  @input="scheduleSave"
                  @blur="flushSave"
                ></textarea>
                <p v-else-if="block.description" class="dash-text-copy">{{ block.description }}</p>
                <p v-else-if="!isPublicPresentation" class="dash-text-copy">Drop files here when the team needs new references or client input.</p>

                <div v-if="canEditDashboard" class="dash-upload-admin-row">
                  <span>Target</span>
                  <code>{{ block.target_path || getUploadTarget() }}</code>
                </div>

                <div class="dash-upload-tile" :class="{ 'is-shareable': isPublicPresentation }">
                  <span class="dash-upload-tile-icon" aria-hidden="true">
                    <svg class="icon"><use href="#icon-cloud"/></svg>
                  </span>
                  <div class="dash-upload-tile-copy">
                    <strong>{{ isPublicPresentation ? 'Upload files' : 'Client upload inbox' }}</strong>
                    <span>{{ isPublicPresentation ? 'Files land directly in this project.' : 'Clients see an upload tile on the shared page.' }}</span>
                  </div>
                  <button
                    v-if="isPublicPresentation"
                    type="button"
                    class="v-btn v-btn-primary v-btn-sm dash-upload-tile-btn"
                    :disabled="!shareMode"
                    @click="handleSharedUpload(block)"
                  >
                    <svg class="icon"><use href="#icon-upload"/></svg>
                    <span>Upload files</span>
                  </button>
                </div>
              </template>
            </div>
          </article>
        </template>

        <!-- ─── ADD BLOCK ─────────────────────────────────── -->
        <div
          v-if="canEditDashboard"
          class="dash-add-row"
          :class="{ 'is-open': addMenuOpen }"
          @keydown.escape="closeAddMenu"
        >
          <button
            v-if="addMenuOpen && !isMobile"
            type="button"
            class="dash-add-backdrop"
            aria-label="Close add block menu"
            @click="closeAddMenu"
          ></button>
          <VMenu
            v-if="!isMobile"
            :open="addMenuOpen"
            align="center"
            min-width="280"
            panel-class="dash-add-menu"
            @update:open="(open) => { if (!open) closeAddMenu() }"
          >
            <template #trigger="{ triggerProps }">
              <button
                v-bind="triggerProps"
                type="button"
                class="dash-add-trigger"
                :class="{ 'is-open': addMenuOpen }"
                @click.stop="toggleAddMenu"
              >
                <svg class="icon"><use href="#icon-plus"/></svg>
                <span>Add block</span>
              </button>
            </template>
            <div class="dash-add-menu-grid">
              <button
                v-for="option in addBlockOptions"
                :key="option.type"
                type="button"
                class="dash-add-menu-item"
                role="menuitem"
                @click.stop="addBlock(option.type)"
              >
                <span class="dash-add-menu-icon" :class="`is-${option.type}`" aria-hidden="true">
                  <svg class="icon"><use :href="option.icon"/></svg>
                </span>
                <span class="dash-add-menu-copy">
                  <strong>{{ option.label }}</strong>
                  <span>{{ option.hint }}</span>
                </span>
              </button>
            </div>
          </VMenu>
          <button
            v-else
            type="button"
            class="dash-add-trigger"
            :class="{ 'is-open': addMenuOpen }"
            aria-haspopup="dialog"
            :aria-expanded="addMenuOpen"
            @click.stop="toggleAddMenu"
          >
            <svg class="icon"><use href="#icon-plus"/></svg>
            <span>Add block</span>
          </button>
          <VModal
            :model-value="isMobile && addMenuOpen"
            title="Add a block"
            presentation="sheet"
            size="sm"
            @update:modelValue="handleAddMenuVisibility"
          >
            <div class="dash-add-menu-grid is-sheet" role="menu">
              <button
                v-for="option in addBlockOptions"
                :key="option.type"
                type="button"
                class="dash-add-menu-item"
                role="menuitem"
                @click="addBlock(option.type)"
              >
                <span class="dash-add-menu-icon" :class="`is-${option.type}`" aria-hidden="true">
                  <svg class="icon"><use :href="option.icon"/></svg>
                </span>
                <span class="dash-add-menu-copy">
                  <strong>{{ option.label }}</strong>
                  <span>{{ option.hint }}</span>
                </span>
              </button>
            </div>
          </VModal>
        </div>
      </main>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import VMediaThumbnail from '../components/media/VMediaThumbnail.vue'
import { VMenu, VModal } from '../components/primitives'
import { getTrackerStatusColor, getTrackerStatusTextColor } from '../lib/trackerCatalogs'
import { formatDurationHMS, formatLocaleDate } from '../utils/formatters'
import { normalizeExternalHttpUrl } from '../utils/textSanitization'
import { useProjectTrackerSelectionStore } from '../ownership/projectTrackerSelection'
import { useSessionAuthStore } from '../ownership/sessionAuth'
import { useShareAccessContext } from '../ownership/shareAccessContext'
import { useProjectWorkspaceStore } from '../ownership/projectWorkspace'
import { useFileBrowserStore } from '../ownership/fileBrowser'
import { useViewerStore } from '../ownership/viewer'

const { currentProject, currentPage: page } = useProjectTrackerSelectionStore()
const { canEditProject: canEditProjectPermission } = useSessionAuthStore()
const { shareMode, shareAllowDownload } = useShareAccessContext()
const fileBrowserStore = useFileBrowserStore()
const { downloadProjectItem } = fileBrowserStore.downloads
const { openSharedPageUpload: openSharedUpload, openPageResourcePicker, openPageResourceUpload } = fileBrowserStore.pageResources
const { getProjectFileThumbnailUrl } = useViewerStore().media.core
const {
  isMobile,
  pageSaving: saving,
  projectTrackerItems,
  openTracker,
  openPageResourceFolder,
  openFileFromProject,
  clonePageDraft,
  savePage,
} = useProjectWorkspaceStore()

const canEditProject = computed(() => canEditProjectPermission.value && !currentProject.value?.storage_read_only)
const canManagePage = computed(() => canEditProject.value && !shareMode.value)
const draft = ref(clonePage(page.value))
const sharedPreviewMode = ref(false)
const canEditDashboard = computed(() => canManagePage.value && !sharedPreviewMode.value)
const displayPage = computed(() => (canManagePage.value ? draft.value : page.value))
const isPublicPresentation = computed(() => shareMode.value || sharedPreviewMode.value)

const addBlockOptions = [
  { type: 'text', label: 'Text', hint: 'Notes, briefs, or context.', icon: '#icon-file' },
  { type: 'tracker_list', label: 'Vue Trackers', hint: 'Spotlight project trackers.', icon: '#icon-project' },
  { type: 'resource_list', label: 'Resources', hint: 'Links, storage files, uploads.', icon: '#icon-link' },
  { type: 'upload_inbox', label: 'Client Uploads', hint: 'A drop zone for partners.', icon: '#icon-upload' },
]

const BLOCK_ICONS = {
  text: '#icon-file',
  tracker_list: '#icon-project',
  resource_list: '#icon-link',
  upload_inbox: '#icon-cloud',
}

const BLOCK_PLACEHOLDERS = {
  text: 'Notes',
  tracker_list: 'Vue Trackers',
  resource_list: 'Resources',
  upload_inbox: 'Client Uploads',
}

const autosaveState = ref('idle')
const activeLinkBlockId = ref('')
const linkUrl = ref('')
const draggingBlockIndex = ref(null)
const dragOverBlockIndex = ref(null)
const addMenuOpen = ref(false)
let saveTimer = null
let savedStateTimer = null
let saveVersion = 0

const displayedBlocks = computed(() => {
  const blocks = displayPage.value?.blocks || []
  if (canEditDashboard.value) return blocks
  const visibleBlocks = blocks.filter(block => !block.hidden)
  return isPublicPresentation.value ? visibleBlocks.filter(blockHasPublicContent) : visibleBlocks
})

const dashboardSummary = computed(() => {
  const blocks = (displayPage.value?.blocks || []).filter(block => !block.hidden)
  return blocks.reduce((summary, block) => {
    if (block.type === 'tracker_list') summary.trackers += resolvedTrackers(block).length
    if (block.type === 'resource_list') summary.resources += (block.resources || []).length
    if (block.type === 'upload_inbox' && block.enabled !== false) summary.uploads += 1
    return summary
  }, { trackers: 0, resources: 0, uploads: 0 })
})

const lastUpdatedLabel = computed(() => {
  const value = displayPage.value?.updated_at || displayPage.value?.updatedAt
  if (!value) return ''
  return `Updated ${formatShortDate(value)}`
})

const saveStateLabel = computed(() => {
  if (saving.value || autosaveState.value === 'saving') return 'Saving…'
  if (autosaveState.value === 'saved') return 'Saved'
  if (autosaveState.value === 'error') return 'Could not save'
  return ''
})

function pageIdentity(p) {
  if (!p) return ''
  return String(p.id || p.slug || p.path || '')
}

function pageRevision(p) {
  return String(p?.updated_at || p?.updatedAt || p?.revision || '')
}

// Only resync the draft from the parent when we're not actively editing or
// in the middle of an autosave round-trip. The workspace updates `page`
// with the just-saved data after every save; resyncing during a dirty or
// saving state would clobber any keystrokes the user typed after the save
// was scheduled (the autosave-deletes-my-typing bug). We always resync on a
// page identity change so loading a different page still works.
let lastSyncedPageId = pageIdentity(page.value)
watch(() => [pageIdentity(page.value), pageRevision(page.value)], ([nextId]) => {
  const next = page.value
  if (nextId !== lastSyncedPageId) {
    lastSyncedPageId = nextId
    draft.value = clonePage(next)
    autosaveState.value = 'idle'
    sharedPreviewMode.value = false
    return
  }
  if (autosaveState.value === 'dirty' || autosaveState.value === 'saving') return
  draft.value = clonePage(next)
})

function clonePage(source) {
  return clonePageDraft(source)
}

function blockIcon(type) {
  return BLOCK_ICONS[type] || '#icon-file'
}

function blockPlaceholder(type) {
  return BLOCK_PLACEHOLDERS[type] || 'Section title'
}

function scheduleSave() {
  if (!canManagePage.value) return
  autosaveState.value = 'dirty'
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(saveNow, 700)
}

function flushSave() {
  if (!canManagePage.value || autosaveState.value !== 'dirty') return
  window.clearTimeout(saveTimer)
  saveNow()
}

async function saveNow() {
  if (!canManagePage.value || !draft.value?.title?.trim()) return
  window.clearTimeout(saveTimer)
  saveVersion += 1
  const mySaveVersion = saveVersion
  autosaveState.value = 'saving'
  try {
    await savePage(clonePage(draft.value))
  } catch {
    if (mySaveVersion === saveVersion) autosaveState.value = 'error'
    return
  }
  // A newer save was kicked off while we were in flight — let it own the UI
  // state so we don't show a stale "Saved" pill over an in-flight save.
  if (mySaveVersion !== saveVersion) return
  // The user kept typing while the save was in flight, so we're already
  // back to 'dirty' (a fresh save is scheduled). Don't clobber that with
  // 'saved' — it makes the indicator flicker between keystrokes.
  if (autosaveState.value !== 'saving') return
  autosaveState.value = 'saved'
  window.clearTimeout(savedStateTimer)
  savedStateTimer = window.setTimeout(() => {
    if (autosaveState.value === 'saved') autosaveState.value = 'idle'
  }, 1200)
}

function makeBlock(type) {
  const id = `block-${Math.random().toString(36).slice(2, 10)}`
  if (type === 'tracker_list') return { id, type, title: 'Vue Trackers', tracker_ids: [] }
  if (type === 'resource_list') return { id, type, title: 'Resources', resources: [] }
  if (type === 'upload_inbox') return { id, type, title: 'Client Uploads', target_path: getUploadTarget(), description: '', enabled: true }
  return { id, type: 'text', title: 'Notes', body: '' }
}

function addBlock(type) {
  draft.value.blocks = [...(draft.value.blocks || []), makeBlock(type)]
  closeAddMenu()
  scheduleSave()
}

function toggleAddMenu() {
  addMenuOpen.value = !addMenuOpen.value
}

function closeAddMenu() {
  addMenuOpen.value = false
}

function handleAddMenuVisibility(open) {
  addMenuOpen.value = open
}

function startBlockDrag(event, index) {
  if (!canManagePage.value) return
  draggingBlockIndex.value = index
  dragOverBlockIndex.value = index
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.dropEffect = 'move'
  event.dataTransfer.setData('text/plain', String(index))
}

function onBlockDragOver(index) {
  if (!canManagePage.value || draggingBlockIndex.value === null) return
  dragOverBlockIndex.value = index
}

function dropBlock(index) {
  if (!canManagePage.value || draggingBlockIndex.value === null) return
  reorderBlock(draggingBlockIndex.value, index)
  endBlockDrag()
}

function endBlockDrag() {
  draggingBlockIndex.value = null
  dragOverBlockIndex.value = null
}

function reorderBlock(fromIndex, toIndex) {
  const blocks = [...(draft.value.blocks || [])]
  if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0 || fromIndex >= blocks.length || toIndex >= blocks.length) return
  const [block] = blocks.splice(fromIndex, 1)
  blocks.splice(toIndex, 0, block)
  draft.value.blocks = blocks
  scheduleSave()
}

function moveBlock(index, direction) {
  reorderBlock(index, index + direction)
}

function blockDragClass(block, index) {
  return {
    'is-hidden': canManagePage.value && block.hidden,
    'is-dragging': draggingBlockIndex.value === index,
    'is-drop-target': dragOverBlockIndex.value === index && draggingBlockIndex.value !== null && draggingBlockIndex.value !== index,
  }
}

function removeBlock(index) {
  draft.value.blocks = (draft.value.blocks || []).filter((_block, blockIndex) => blockIndex !== index)
  scheduleSave()
}

function toggleHidden(block) {
  block.hidden = !block.hidden
  scheduleSave()
}

function trackerRef(tracker) {
  return tracker?.id || tracker?.path || tracker?.slug || tracker?.name
}

function trackerKey(tracker) {
  return tracker?.id || tracker?.path || tracker?.slug || tracker?.name
}

function hasTracker(block, tracker) {
  const refs = block.tracker_ids || []
  const candidates = [trackerRef(tracker), tracker?.id, tracker?.path, tracker?.slug, tracker?.name].filter(Boolean)
  return refs.some(ref => candidates.includes(ref))
}

function toggleTracker(block, tracker) {
  const ref = trackerRef(tracker)
  if (!ref) return
  const refs = [...(block.tracker_ids || [])]
  const candidates = [ref, tracker?.id, tracker?.path, tracker?.slug, tracker?.name].filter(Boolean)
  const index = refs.findIndex(value => candidates.includes(value))
  if (index >= 0) refs.splice(index, 1)
  else refs.push(ref)
  block.tracker_ids = refs
  scheduleSave()
}

function resolveTracker(block, ref) {
  const candidates = [
    ...(block.trackers || []),
    ...(projectTrackerItems.value || []),
  ]
  return candidates.find(item => [item.id, item.path, item.slug, item.name].includes(ref))
}

function buildTrackerEntries(block) {
  const refs = block.tracker_ids || []
  if (refs.length) {
    return refs
      .map(ref => {
        const tracker = resolveTracker(block, ref)
        return {
          key: tracker ? trackerKey(tracker) : `missing-${ref}`,
          ref,
          tracker,
        }
      })
      .filter(entry => entry.tracker || (canManagePage.value && !isPublicPresentation.value))
  }
  return (block.trackers || []).map(tracker => ({
    key: trackerKey(tracker),
    ref: trackerKey(tracker),
    tracker,
  }))
}

const trackerEntriesByBlock = computed(() => new Map(
  (displayPage.value?.blocks || []).map(block => [block, buildTrackerEntries(block)]),
))

function trackerEntries(block) {
  return trackerEntriesByBlock.value.get(block) || buildTrackerEntries(block)
}

function resolvedTrackers(block) {
  return trackerEntries(block).map(entry => entry.tracker).filter(Boolean)
}

function blockHasPublicContent(block) {
  if (block.type === 'text') return Boolean(String(block.body || '').trim())
  if (block.type === 'tracker_list') return resolvedTrackers(block).length > 0
  if (block.type === 'resource_list') return (block.resources || []).length > 0
  if (block.type === 'upload_inbox') return block.enabled !== false
  return false
}

function trackerShotCount(tracker) {
  return Number(tracker?.shot_count ?? tracker?.shotCount ?? tracker?.total_shots ?? 0)
}

function trackerFrameCount(tracker) {
  const value = Number(tracker?.total_frames ?? tracker?.totalFrames ?? 0)
  return value > 0 ? value.toLocaleString() : ''
}

function trackerDurationLabel(tracker) {
  const value = Number(tracker?.total_duration ?? tracker?.totalDuration ?? 0)
  return value > 0 ? formatDurationHMS(value) : ''
}

function trackerUpdatedLabel(tracker) {
  const value = tracker?.updated_at || tracker?.updatedAt || tracker?.created_at || tracker?.createdAt
  return value ? `Updated ${formatShortDate(value)}` : ''
}

function trackerMetaLabel(tracker) {
  const shotCount = trackerShotCount(tracker)
  const parts = [
    trackerUpdatedLabel(tracker),
    `${shotCount} ${shotCount === 1 ? 'shot' : 'shots'}`,
    trackerDurationLabel(tracker),
  ].filter(Boolean)
  const frames = trackerFrameCount(tracker)
  if (frames) parts.push(`${frames} frames`)
  return parts.join(' · ')
}

function trackerStatusBreakdown(tracker) {
  const breakdown = tracker?.status_breakdown || tracker?.statusBreakdown || []
  return Array.isArray(breakdown) ? breakdown : []
}

function trackerStatusSegments(tracker) {
  const total = trackerShotCount(tracker)
  if (!total) return []
  return trackerStatusBreakdown(tracker)
    .map(segment => ({
      ...segment,
      count: Number(segment.count || 0),
      percent: Math.max(3, Math.round((Number(segment.count || 0) / total) * 100)),
    }))
    .filter(segment => segment.count > 0)
}

function trackerStatusLabels(tracker) {
  return trackerStatusLabelsByTracker.value.get(tracker) || []
}

function trackerStatusChipStyle(status) {
  return {
    '--dash-status-color': getTrackerStatusColor(status),
    '--dash-status-text': getTrackerStatusTextColor(status),
  }
}

const trackerStatusLabelsByTracker = computed(() => {
  const labels = new Map()
  for (const entries of trackerEntriesByBlock.value.values()) {
    for (const entry of entries) {
      if (entry.tracker && !labels.has(entry.tracker)) {
        labels.set(entry.tracker, trackerStatusSegments(entry.tracker).slice(0, 3))
      }
    }
  }
  return labels
})

function formatShortDate(timestamp) {
  return formatLocaleDate(timestamp, {
    locale: 'en-US',
    options: { month: 'short', day: 'numeric' },
  }) || 'recently'
}

function getUploadTarget() {
  const uploadBlock = (draft.value?.blocks || []).find(block => block.type === 'upload_inbox' && !block.hidden && block.enabled !== false)
  return uploadBlock?.target_path || `client-uploads/${draft.value?.slug || page.value?.slug || 'page'}`
}

function beginLink(block) {
  activeLinkBlockId.value = block.id
  linkUrl.value = ''
}

function cancelLink() {
  activeLinkBlockId.value = ''
  linkUrl.value = ''
}

function normalizeUrl(value) {
  return normalizeExternalHttpUrl(value)
}

function addLinkResource(block) {
  const url = normalizeUrl(linkUrl.value)
  if (!url) return
  block.resources = [...(block.resources || []), {
    id: `resource-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    kind: 'url',
    label: linkLabel(url),
    url,
  }]
  cancelLink()
  scheduleSave()
}

function removeResource(block, resource) {
  block.resources = (block.resources || []).filter(item => item !== resource)
  scheduleSave()
}

function linkLabel(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function resourceName(resource) {
  if (resource.kind === 'url') return linkLabel(resource.url || '')
  return resource.name || String(resource.path || '').split('/').filter(Boolean).pop() || 'Resource'
}

function resourceMeta(resource) {
  if (resource.kind === 'url') return linkLabel(resource.url || '')
  if (resource.kind === 'folder') return 'Folder'
  if (resource.duration_formatted) return resource.duration_formatted
  if (resource.size_formatted) return resource.size_formatted
  if (resource.is_video) return 'Video'
  if (resource.is_image) return 'Image'
  return 'File'
}

function resourceIcon(resource) {
  if (resource.kind === 'folder') return '#icon-folder'
  if (resource.is_pdf) return '#icon-pdf'
  if (resource.is_video) return '#icon-video'
  if (resource.is_image) return '#icon-image'
  return '#icon-file'
}

function resourceKindLabel(resource) {
  if (resource?.kind === 'url') return 'LINK'
  if (resource?.kind === 'folder') return 'FOLDER'
  if (resource?.is_video) return 'VIDEO'
  if (resource?.is_image) return 'IMAGE'
  if (resource?.is_pdf) return 'PDF'
  return 'FILE'
}

function resourceActionLabel(resource) {
  if (resource?.kind === 'folder') return 'Open folder'
  if (resource?.kind === 'url') return 'Open link'
  return 'Open file'
}

function canDownloadResource(resource) {
  if (!downloadProjectItem) return false
  if (resource?.kind === 'url' || resource?.kind === 'folder') return false
  return !shareMode.value || shareAllowDownload.value
}

function isMediaResource(resource) {
  return Boolean(resource?.is_video || resource?.is_image || ['video', 'image'].includes(resource?.type))
}

function getResourceThumbnail(resource) {
  return getProjectFileThumbnailUrl(resource)
}

function openResource(resource) {
  if (resource.kind === 'url' && resource.url) {
    const safeUrl = normalizeExternalHttpUrl(resource.url)
    if (safeUrl) window.open(safeUrl, '_blank', 'noopener,noreferrer')
    return
  }
  if (resource.kind === 'folder' && resource.path) {
    openPageResourceFolder(resource.path)
    return
  }
  openFileFromProject({
    ...resource,
    type: 'file',
    name: resource.name || resource.label || resource.path?.split('/').pop(),
    is_video: resource.is_video,
    is_image: resource.is_image,
    is_pdf: resource.is_pdf,
  })
}

function downloadResource(resource) {
  if (!canDownloadResource(resource)) return
  downloadProjectItem({
    ...resource,
    type: 'file',
    name: resource.name || resource.label || resource.path?.split('/').pop(),
  })
}

function handleSharedUpload(block) {
  if (!shareMode.value) return
  openSharedUpload(block.target_path)
}
</script>

<style scoped>
/* ─── Page shell ───────────────────────────────────── */
.project-page-surface {
  --dash-surface: color-mix(in srgb, var(--v-surface-panel) 52%, var(--v-bg-base));
  --dash-surface-hover: color-mix(in srgb, var(--v-surface-panel) 66%, var(--v-bg-base));
  --dash-surface-inset: color-mix(in srgb, var(--v-bg-base) 62%, var(--v-surface-panel));
  --dash-border: color-mix(in srgb, var(--v-border) 62%, transparent);
  --dash-border-strong: color-mix(in srgb, var(--v-border) 82%, white);
  --dash-rule: color-mix(in srgb, var(--v-divider-subtle) 72%, transparent);
  flex: 1;
  padding: 28px clamp(18px, 4vw, 56px) 96px;
  color: var(--v-text);
  background: var(--v-bg-base);
}

.project-page-canvas {
  width: min(100%, 820px);
  margin: 0 auto;
}

/* ─── Hero ─────────────────────────────────────────── */
.dash-hero {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-3);
  padding: 24px 0 22px;
  margin-bottom: 0;
  border-bottom: 1px solid var(--dash-rule);
}

.dash-hero-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
  min-height: 32px;
}

.dash-hero-eyebrow,
.dash-hero-tools {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.dash-hero-savestate {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px 4px 7px;
  border-radius: var(--v-radius-full);
  background: var(--v-surface-tint-strong);
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 600;
  letter-spacing: 0;
  transition: color var(--v-transition-fast), background var(--v-transition-fast);
}

.dash-hero-savestate .icon {
  width: 11px;
  height: 11px;
}

.dash-hero-savestate.is-saved {
  color: var(--v-accent);
  background: var(--v-accent-muted);
}

.dash-hero-savestate.is-saving {
  color: var(--v-info);
  background: var(--v-info-bg);
}

.dash-hero-savestate.is-error {
  color: var(--v-danger-text);
  background: var(--v-danger-bg);
}

.dash-hero-savestate-spinner {
  animation: dash-spin 0.9s linear infinite;
}

@keyframes dash-spin {
  to { transform: rotate(360deg); }
}

.dash-hero-title-input,
.dash-hero-title-static {
  margin: 0;
  width: 100%;
  max-width: 760px;
  border: 0;
  background: transparent;
  color: var(--v-text);
  font-family: inherit;
  font-size: clamp(28px, 3.1vw, 40px);
  font-weight: 760;
  line-height: 1.06;
  letter-spacing: 0;
  padding: 0;
  outline: 0;
}

.dash-hero-title-input::placeholder {
  color: color-mix(in srgb, var(--v-text-muted) 80%, transparent);
  font-weight: 700;
}

.dash-hero-title-input:hover:not(:focus) {
  cursor: text;
}

.dash-hero-desc-input,
.dash-hero-desc-static {
  margin: 0;
  width: 100%;
  max-width: 660px;
  border: 0;
  background: transparent;
  color: var(--v-text-muted);
  font-family: inherit;
  font-size: clamp(14px, 1.2vw, 16px);
  line-height: 1.5;
  padding: 0;
  outline: 0;
  resize: none;
  overflow: hidden;
  min-height: 1.6em;
}

.dash-hero-desc-input::placeholder {
  color: var(--v-text-muted);
}

.dash-preview-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  height: 30px;
  padding: 0 12px 0 10px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-button-radius);
  background: var(--v-surface-tint-strong);
  color: var(--v-text-secondary);
  font: inherit;
  font-size: var(--v-text-sm);
  font-weight: 650;
  letter-spacing: 0;
  cursor: pointer;
  transition:
    background var(--v-transition-fast),
    border-color var(--v-transition-fast),
    color var(--v-transition-fast),
    transform var(--v-transition-fast);
}

.dash-preview-toggle:hover,
.dash-preview-toggle:focus-visible,
.dash-preview-toggle.is-active {
  background: var(--v-accent-muted);
  border-color: color-mix(in srgb, var(--v-accent) 38%, transparent);
  color: var(--v-accent);
  outline: none;
}

.dash-preview-toggle:active {
  transform: translateY(1px);
}

.dash-preview-toggle .icon {
  width: 13px;
  height: 13px;
}

.dash-hero-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0;
  padding-top: 2px;
}

.dash-meta-item {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 24px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.dash-meta-item + .dash-meta-item {
  margin-left: 10px;
  padding-left: 11px;
}

.dash-meta-item + .dash-meta-item::before {
  content: "";
  position: absolute;
  left: 0;
  top: 50%;
  width: 3px;
  height: 3px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-text-muted) 55%, transparent);
  transform: translateY(-50%);
}

.dash-meta-item strong {
  color: var(--v-text);
  font-weight: 760;
}

.dash-meta-item .icon {
  width: 12px;
  height: 12px;
  color: var(--v-accent);
}

.dash-meta-item.is-updated {
  color: var(--v-text-secondary);
}

/* ─── Block stream ─────────────────────────────────── */
.dash-stream {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-top: 18px;
}

.dash-block {
  position: relative;
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: start;
  gap: var(--v-space-2);
  transition: opacity var(--v-transition-fast);
}

.dash-block.is-readonly {
  grid-template-columns: minmax(0, 1fr);
  gap: 0;
}

.dash-block.is-hidden {
  opacity: 0.55;
}

.dash-block.is-dragging {
  opacity: 0.4;
}

.dash-block.is-drop-target .dash-block-body {
  border-color: color-mix(in srgb, var(--v-accent) 50%, var(--v-border));
  background: color-mix(in srgb, var(--v-accent) 5%, var(--dash-surface));
}

/* Drag rail */
.dash-block-rail {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: var(--v-space-3);
  opacity: 0;
  transition: opacity var(--v-transition-fast);
}

.dash-block:hover .dash-block-rail,
.dash-block:focus-within .dash-block-rail {
  opacity: 1;
}

.dash-block-drag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 28px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--v-text-muted);
  border-radius: var(--v-button-radius);
  cursor: grab;
  transition: background var(--v-transition-fast), color var(--v-transition-fast);
}

.dash-block-drag:hover,
.dash-block-drag:focus-visible {
  background: var(--v-bg-hover);
  color: var(--v-text);
  outline: none;
}

.dash-block-drag:active {
  cursor: grabbing;
}

.dash-block-drag .icon {
  width: 13px;
  height: 13px;
}

/* Block body */
.dash-block-body {
  display: flex;
  flex-direction: column;
  gap: 13px;
  padding: 14px 16px 16px;
  border: 1px solid var(--dash-border);
  border-radius: var(--v-radius-lg);
  background: var(--dash-surface);
  box-shadow: 0 1px 0 color-mix(in srgb, white 2%, transparent) inset;
  transition:
    background var(--v-transition-fast),
    border-color var(--v-transition-fast);
}

.dash-block:hover .dash-block-body,
.dash-block:focus-within .dash-block-body {
  border-color: var(--dash-border-strong);
  background: var(--dash-surface-hover);
}

.dash-block-head {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
}

.dash-block-icon {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--v-radius-md);
  background: var(--dash-surface-inset);
  color: var(--v-text-secondary);
  flex: 0 0 auto;
}

.dash-block-icon.is-tracker_list {
  background: color-mix(in srgb, var(--v-accent) 14%, var(--dash-surface-inset));
  color: var(--v-accent);
}

.dash-block-icon.is-resource_list {
  background: color-mix(in srgb, var(--v-info) 14%, var(--dash-surface-inset));
  color: color-mix(in srgb, var(--v-info) 90%, white);
}

.dash-block-icon.is-upload_inbox {
  background: color-mix(in srgb, var(--v-warning) 14%, var(--dash-surface-inset));
  color: color-mix(in srgb, var(--v-warning) 92%, white);
}

.dash-block-icon .icon {
  width: 13px;
  height: 13px;
}

.dash-block-title-input,
.dash-block-title-static {
  margin: 0;
  width: 100%;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--v-text);
  font-family: inherit;
  font-size: var(--v-text-md);
  font-weight: 700;
  letter-spacing: 0;
  padding: 0;
  outline: 0;
}

.dash-block-title-input::placeholder {
  color: var(--v-text-muted);
  font-weight: 600;
}

.dash-block-title-input:hover:not(:focus) {
  cursor: text;
}

.dash-block-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  opacity: 0;
  transition: opacity var(--v-transition-fast);
}

.dash-block:hover .dash-block-actions,
.dash-block:focus-within .dash-block-actions,
.dash-block-actions:focus-within {
  opacity: 1;
}

.dash-block-actions .v-icon-action .icon {
  width: 14px;
  height: 14px;
}

.dash-block-actions .v-icon-action.is-active {
  color: var(--v-accent);
  background: var(--v-accent-muted);
}

.dash-block-actions .v-icon-action:disabled {
  opacity: 0.34;
  cursor: default;
  pointer-events: none;
}

/* ─── Block empty state ─────────────────────────── */
.dash-block-empty {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 10px 12px;
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--dash-surface-inset) 70%, transparent);
  border: 1px solid color-mix(in srgb, var(--v-control-border) 44%, transparent);
  color: var(--v-text-muted);
  font-size: var(--v-text-base);
}

.dash-block-empty .icon {
  width: 16px;
  height: 16px;
  color: var(--v-text-muted);
  flex: 0 0 auto;
}

/* ─── Text block ────────────────────────────────── */
.dash-text-input,
.dash-text-copy,
.dash-text-empty {
  margin: 0;
  color: var(--v-text-secondary);
  font-size: var(--v-text-md);
  line-height: 1.58;
  white-space: pre-wrap;
}

.dash-text-input {
  width: 100%;
  min-height: 96px;
  border: 1px solid color-mix(in srgb, var(--v-control-border) 66%, transparent);
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-bg-base) 40%, var(--dash-surface));
  color: var(--v-text);
  font-family: inherit;
  padding: 12px 13px;
  outline: 0;
  resize: vertical;
  transition:
    background var(--v-transition-fast),
    border-color var(--v-transition-fast),
    box-shadow var(--v-transition-fast);
}

.dash-text-input:focus {
  border-color: color-mix(in srgb, var(--v-accent) 42%, var(--v-control-border));
  background: color-mix(in srgb, var(--v-bg-base) 34%, var(--dash-surface));
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.dash-text-input.is-compact {
  min-height: 62px;
}

.dash-text-input::placeholder {
  color: var(--v-text-muted);
}

.dash-text-empty {
  color: var(--v-text-muted);
}

/* ─── Tracker list block ────────────────────────── */
.dash-tracker-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--v-space-2);
}

.dash-tracker-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--v-space-3);
  width: 100%;
  min-height: 62px;
  padding: 10px 10px 10px 12px;
  border: 1px solid color-mix(in srgb, var(--v-control-border) 52%, transparent);
  background: var(--dash-surface-inset);
  border-radius: var(--v-button-radius);
  color: var(--v-text);
  text-align: left;
  cursor: pointer;
  transition:
    background var(--v-transition-fast),
    border-color var(--v-transition-fast),
    transform var(--v-transition-fast);
}

.dash-tracker-card:hover,
.dash-tracker-card:focus-visible {
  background: color-mix(in srgb, var(--v-surface-inline) 44%, var(--dash-surface));
  border-color: color-mix(in srgb, var(--v-accent) 42%, var(--v-control-border-hover));
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-accent) 18%, transparent);
  transform: translateY(-1px);
  outline: none;
}

.dash-tracker-card:active {
  transform: translateY(0);
}

.dash-tracker-main {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.dash-tracker-mark {
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-accent) 14%, var(--dash-surface-inset));
  color: var(--v-accent);
  flex: 0 0 auto;
}

.dash-tracker-mark .icon {
  width: 15px;
  height: 15px;
}

.dash-tracker-title-group {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.dash-tracker-title-group strong {
  color: var(--v-text);
  font-size: var(--v-text-md);
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1.25;
  white-space: normal;
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.dash-tracker-title-group span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-variant-numeric: tabular-nums;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.dash-tracker-side {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--v-space-2);
  min-width: 0;
}

.dash-tracker-open {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border-radius: var(--v-radius-full);
  background: var(--v-surface-tint-hover);
  border: 1px solid color-mix(in srgb, var(--v-control-border) 46%, transparent);
  color: var(--v-text-secondary);
  transition:
    color var(--v-transition-fast),
    background var(--v-transition-fast),
    border-color var(--v-transition-fast),
    transform var(--v-transition-fast);
}

.dash-tracker-open .icon {
  width: 12px;
  height: 12px;
}

.dash-tracker-card:hover .dash-tracker-open {
  background: var(--v-accent-muted);
  border-color: color-mix(in srgb, var(--v-accent) 36%, transparent);
  color: var(--v-accent);
  transform: translateX(2px);
}

.dash-tracker-status-labels {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: var(--v-space-1);
  min-width: 0;
}

.dash-tracker-status-chip {
  --dash-status-color: var(--v-text-muted);
  --dash-status-text: var(--v-text-secondary);
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--dash-status-color) 10%, var(--dash-surface-inset));
  border: 1px solid color-mix(in srgb, var(--dash-status-color) 24%, transparent);
  color: var(--dash-status-text);
  font-size: var(--v-text-2xs);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.dash-tracker-missing {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  min-height: 64px;
  padding: var(--v-space-3);
  border: 1px dashed color-mix(in srgb, var(--v-warning) 42%, var(--v-control-border));
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-warning) 5%, var(--dash-surface-inset));
  color: var(--v-text-secondary);
}

.dash-tracker-missing > .icon {
  width: 16px;
  height: 16px;
  color: var(--v-warning);
  justify-self: center;
}

.dash-tracker-missing span {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.dash-tracker-missing strong {
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 700;
}

.dash-tracker-missing span span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  overflow: hidden;
  text-overflow: ellipsis;
}

.dash-tracker-picker {
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding-top: 10px;
  margin-top: 2px;
  border-top: 1px solid color-mix(in srgb, var(--v-divider-subtle) 80%, transparent);
}

.dash-tracker-picker-row {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.dash-tracker-chip,
.dash-add-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 0 12px 0 10px;
  border-radius: var(--v-button-radius);
  border: 1px solid var(--v-control-border);
  background: color-mix(in srgb, var(--v-surface-inset) 82%, var(--dash-surface));
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 650;
  letter-spacing: 0;
  cursor: pointer;
  max-width: 100%;
  transition:
    background var(--v-transition-fast),
    border-color var(--v-transition-fast),
    color var(--v-transition-fast),
    transform var(--v-transition-fast);
}

.dash-tracker-chip:hover,
.dash-add-pill:hover {
  transform: translateY(-1px);
  background: var(--v-control-bg-hover);
  border-color: var(--v-control-border-hover);
  color: var(--v-text);
}

.dash-tracker-chip.is-selected {
  background: var(--v-accent-muted);
  border-color: color-mix(in srgb, var(--v-accent) 35%, transparent);
  color: var(--v-accent);
}

.dash-tracker-chip .icon {
  width: 11px;
  height: 11px;
  flex: 0 0 auto;
}

.dash-tracker-chip span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dash-tracker-picker-hint {
  font-size: var(--v-text-sm);
  color: var(--v-text-muted);
}

/* ─── Resource list block ───────────────────────── */
.dash-resource-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.dash-add-pill {
  min-height: 34px;
  padding: 0 13px 0 11px;
}

.dash-add-pill .icon {
  width: 12px;
  height: 12px;
}

.dash-link-form {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: var(--v-space-2);
  padding: 7px 7px 7px 5px;
  border-radius: var(--v-radius-md);
  border: 1px solid color-mix(in srgb, var(--v-control-border) 70%, transparent);
  background: var(--dash-surface-inset);
}

.dash-link-form-icon {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--v-text-muted);
}

.dash-link-form-icon .icon {
  width: 14px;
  height: 14px;
}

.dash-link-form-input {
  border: 0;
  background: transparent;
  color: var(--v-text);
  font-family: inherit;
  font-size: var(--v-text-base);
  font-weight: 500;
  padding: 0;
  outline: 0;
  min-width: 0;
}

.dash-link-form-input::placeholder {
  color: var(--v-text-muted);
}

.dash-resource-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 10px;
}

.dash-resource-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0;
  border-radius: var(--v-radius-md);
  border: 1px solid color-mix(in srgb, var(--v-control-border) 65%, transparent);
  background: var(--dash-surface-inset);
  overflow: hidden;
  transition:
    border-color var(--v-transition-fast),
    background var(--v-transition-fast),
    transform var(--v-transition-fast);
}

.dash-resource-card:hover {
  border-color: var(--v-control-border-hover);
  background: color-mix(in srgb, var(--v-surface-inline) 50%, var(--dash-surface));
  transform: translateY(-1px);
}

.dash-resource-thumb {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: var(--v-bg-black);
  border: 0;
  padding: 0;
  cursor: pointer;
  color: var(--v-text-secondary);
  transition: background var(--v-transition-fast);
}

.dash-resource-card:hover .dash-resource-thumb {
  background: color-mix(in srgb, var(--v-bg-black) 88%, white);
}

.dash-resource-thumb-media {
  display: block;
  width: 100%;
  height: 100%;
}

.dash-resource-thumb-media :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.dash-resource-thumb-favicon,
.dash-resource-thumb-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--v-radius-md);
  background: var(--dash-surface);
  color: var(--v-text-secondary);
}

.dash-resource-thumb-favicon img {
  width: 18px;
  height: 18px;
  display: block;
}

.dash-resource-thumb-favicon .icon,
.dash-resource-thumb-icon .icon {
  width: 18px;
  height: 18px;
}

.dash-resource-thumb-kind {
  position: absolute;
  left: 8px;
  bottom: 8px;
  height: 18px;
  padding: 0 6px;
  border-radius: var(--v-radius-sm);
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: var(--v-text-3xs);
  font-weight: 700;
  letter-spacing: 0;
  display: inline-flex;
  align-items: center;
}

.dash-resource-copy {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 10px 12px 12px;
  min-width: 0;
}

.dash-resource-title-input,
.dash-resource-title-static {
  margin: 0;
  width: 100%;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--v-text);
  font-family: inherit;
  font-size: var(--v-text-base);
  font-weight: 700;
  letter-spacing: 0;
  padding: 0;
  outline: 0;
}

.dash-resource-title-input::placeholder {
  color: var(--v-text-muted);
}

.dash-resource-meta {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
}

.dash-resource-actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
}

.dash-resource-open,
.dash-resource-download {
  display: inline-flex;
  align-items: center;
  gap: var(--v-space-2);
  min-height: 28px;
  padding: 0 9px;
  border: 1px solid color-mix(in srgb, var(--v-control-border) 60%, transparent);
  border-radius: var(--v-button-radius);
  background: color-mix(in srgb, var(--v-bg-base) 32%, var(--dash-surface));
  color: var(--v-text-secondary);
  font: inherit;
  font-size: var(--v-text-sm);
  font-weight: 650;
  cursor: pointer;
  transition:
    background var(--v-transition-fast),
    border-color var(--v-transition-fast),
    color var(--v-transition-fast);
}

.dash-resource-open {
  justify-content: space-between;
  width: 100%;
  min-width: 0;
}

.dash-resource-download {
  justify-content: center;
  width: 30px;
  padding: 0;
}

.dash-resource-open:hover,
.dash-resource-open:focus-visible,
.dash-resource-download:hover,
.dash-resource-download:focus-visible {
  border-color: var(--v-control-border-hover);
  background: color-mix(in srgb, var(--v-surface-inline) 58%, var(--dash-surface));
  color: var(--v-text);
  outline: none;
}

.dash-resource-open .icon,
.dash-resource-download .icon {
  width: 12px;
  height: 12px;
}

.dash-resource-remove {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0;
  background: rgba(0, 0, 0, 0.72);
}

.dash-resource-card:hover .dash-resource-remove,
.dash-resource-remove:focus-visible {
  opacity: 1;
}

/* ─── Upload inbox block ────────────────────────── */
.dash-upload-admin-row {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  min-height: 22px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-weight: 650;
}

.dash-upload-admin-row code {
  min-width: 0;
  color: var(--v-text-secondary);
  font-family: var(--v-font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-size: var(--v-text-sm);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dash-upload-tile {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  align-items: center;
  gap: 13px;
  min-height: 68px;
  padding: 13px 15px;
  border-radius: var(--v-radius-lg);
  border: 1px dashed color-mix(in srgb, var(--v-warning) 30%, transparent);
  background: color-mix(in srgb, var(--v-warning) 4%, var(--dash-surface-inset));
}

.dash-upload-tile.is-shareable {
  border-style: solid;
  background: color-mix(in srgb, var(--v-warning) 9%, var(--dash-surface-inset));
}

.dash-upload-tile-icon {
  width: 38px;
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-warning) 16%, var(--dash-surface-inset));
  color: color-mix(in srgb, var(--v-warning) 92%, white);
  flex: 0 0 auto;
}

.dash-upload-tile-icon .icon {
  width: 18px;
  height: 18px;
}

.dash-upload-tile-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.dash-upload-tile-copy strong {
  color: var(--v-text);
  font-size: var(--v-text-md);
  font-weight: 700;
}

.dash-upload-tile-copy span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.45;
}

.dash-upload-tile-btn {
  gap: 6px;
  flex: 0 0 auto;
}

.dash-upload-tile-btn .icon {
  width: 13px;
  height: 13px;
}

/* ─── Add block ──────────────────────────────────── */
.dash-add-row {
  position: relative;
  display: flex;
  justify-content: center;
  margin: 10px 0 0;
  padding-left: 28px;
}

.dash-add-row.is-open {
  z-index: var(--v-z-dropdown);
}

.dash-add-backdrop {
  position: fixed;
  inset: 0;
  z-index: 99;
  border: 0;
  padding: 0;
  background: transparent;
}

.dash-add-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--v-space-2);
  width: auto;
  min-width: 136px;
  min-height: 40px;
  padding: 0 16px;
  border-radius: var(--v-button-radius);
  border: 1px dashed color-mix(in srgb, var(--v-control-border) 80%, transparent);
  background: transparent;
  color: var(--v-text-muted);
  font-family: inherit;
  font-size: var(--v-text-base);
  font-weight: 650;
  letter-spacing: 0;
  cursor: pointer;
  transition: background var(--v-transition-fast), border-color var(--v-transition-fast), color var(--v-transition-fast);
}

.dash-add-trigger:hover,
.dash-add-trigger.is-open {
  background: color-mix(in srgb, var(--v-surface-inset) 74%, transparent);
  border-color: color-mix(in srgb, var(--v-accent) 35%, transparent);
  color: var(--v-text);
  border-style: solid;
}

.dash-add-trigger .icon {
  width: 14px;
  height: 14px;
}

:deep(.dash-add-menu) {
  top: auto;
  bottom: calc(100% + 10px);
  margin-top: 0;
  transform-origin: bottom center;
  padding: var(--v-space-2);
  border-radius: var(--v-radius-lg);
}

.dash-add-menu-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--v-space-1);
}

.dash-add-menu-grid.is-sheet {
  gap: 6px;
}

.dash-add-menu-item {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  align-items: center;
  gap: var(--v-space-3);
  padding: 10px 12px;
  border: 0;
  background: transparent;
  color: var(--v-text);
  font-family: inherit;
  text-align: left;
  border-radius: var(--v-button-radius);
  cursor: pointer;
  transition: background var(--v-transition-fast);
}

.dash-add-menu-item:hover,
.dash-add-menu-item:focus-visible {
  background: var(--v-bg-hover);
  outline: none;
}

.dash-add-menu-icon {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--v-radius-md);
  background: var(--dash-surface-inset);
  color: var(--v-text-secondary);
  flex: 0 0 auto;
}

.dash-add-menu-icon.is-tracker_list {
  background: color-mix(in srgb, var(--v-accent) 16%, var(--dash-surface-inset));
  color: var(--v-accent);
}

.dash-add-menu-icon.is-resource_list {
  background: color-mix(in srgb, var(--v-info) 16%, var(--dash-surface-inset));
  color: color-mix(in srgb, var(--v-info) 92%, white);
}

.dash-add-menu-icon.is-upload_inbox {
  background: color-mix(in srgb, var(--v-warning) 16%, var(--dash-surface-inset));
  color: color-mix(in srgb, var(--v-warning) 92%, white);
}

.dash-add-menu-icon .icon {
  width: 16px;
  height: 16px;
}

.dash-add-menu-copy {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.dash-add-menu-copy strong {
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 650;
}

.dash-add-menu-copy span {
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.4;
}

/* ─── Mobile ───────────────────────────────────────── */
@media (max-width: 768px) {
  .project-page-surface {
    padding: 18px 12px 72px;
  }

  .dash-hero {
    gap: 11px;
    padding: 16px 2px 18px;
  }

  .dash-hero-topline {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }

  .dash-hero-eyebrow,
  .dash-hero-tools {
    width: 100%;
  }

  .dash-hero-eyebrow {
    justify-content: space-between;
  }

  .dash-hero-tools {
    justify-content: flex-end;
  }

  .dash-preview-toggle {
    min-height: 36px;
  }

  .dash-hero-title-input,
  .dash-hero-title-static {
    font-size: 29px;
    line-height: 1.09;
  }

  .dash-hero-desc-input,
  .dash-hero-desc-static {
    font-size: var(--v-text-md);
  }

  .dash-hero-meta {
    row-gap: 3px;
  }

  .dash-meta-item {
    min-height: 22px;
  }

  .dash-stream {
    padding-top: var(--v-space-4);
    gap: 10px;
  }

  .dash-block {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }

  .dash-block-rail {
    display: none;
  }

  .dash-block-body {
    padding: var(--v-space-3);
    border-radius: var(--v-radius-lg);
  }

  .dash-block-actions {
    opacity: 1;
  }

  .dash-block-action-move {
    display: none;
  }

  .dash-tracker-grid {
    grid-template-columns: 1fr;
  }

  .dash-tracker-card {
    grid-template-columns: minmax(0, 1fr);
    align-items: stretch;
    gap: 10px;
    min-height: 76px;
    padding: var(--v-space-3);
  }

  .dash-tracker-side {
    justify-content: space-between;
    width: 100%;
  }

  .dash-tracker-status-labels {
    justify-content: flex-start;
  }

  .dash-tracker-open {
    flex: 0 0 auto;
    width: 38px;
    height: 38px;
  }

  .dash-resource-grid {
    grid-template-columns: 1fr;
    gap: var(--v-space-2);
  }

  .dash-resource-thumb-favicon,
  .dash-resource-thumb-icon {
    width: 34px;
    height: 34px;
  }

  .dash-resource-copy {
    padding: 8px 10px 10px;
  }

  .dash-add-row {
    padding-left: 0;
  }

  .dash-add-trigger {
    width: 100%;
    min-height: 44px;
  }

  .dash-tracker-chip,
  .dash-add-pill {
    width: 100%;
    min-width: 0;
    min-height: 40px;
    justify-content: center;
  }

  .dash-tracker-picker-row,
  .dash-resource-toolbar {
    display: grid;
    grid-template-columns: 1fr;
  }

  .dash-link-form {
    grid-template-columns: 30px minmax(0, 1fr);
  }

  .dash-link-form .v-btn {
    grid-column: span 2;
    width: 100%;
    justify-content: center;
  }

  .dash-upload-tile {
    grid-template-columns: 40px minmax(0, 1fr);
    grid-template-areas:
      "icon copy"
      "btn btn";
    gap: var(--v-space-3);
  }

  .dash-upload-tile-icon {
    grid-area: icon;
  }

  .dash-upload-tile-copy {
    grid-area: copy;
  }

  .dash-upload-tile-btn {
    grid-area: btn;
    width: 100%;
    justify-content: center;
  }
}
</style>
