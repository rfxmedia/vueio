<template>
    <!-- FILE BROWSER MODULE -->
    <!-- ════════════════════════════════════════════════════════════════════ -->
    <!-- No Access Screen -->
    <main v-if="showMainContent && !shareMode && currentUser && !canAccessFileBrowser && !canAccessProjectManager" class="no-access-view main-content">
      <div class="v-empty-state">
        <svg class="icon v-empty-state-icon"><use href="#icon-folder"/></svg>
        <p class="v-empty-state-title">No Access</p>
        <p class="v-empty-state-copy">You don't have access to any apps yet.</p>
        <p class="v-empty-state-hint">Please contact your administrator to request access.</p>
      </div>
    </main>

    <main v-if="activeModule === 'files' && canAccessFileBrowser" v-show="showMainContent" class="browser">
      <section
        v-if="shareRequestFiles"
        class="file-request-page"
        @dragenter.prevent="handleSharedExternalDragEnter($event)"
        @dragover.prevent="handleSharedExternalDragOver($event)"
        @dragleave="handleSharedExternalDragLeave($event)"
        @drop.prevent="handleSharedExternalDrop($event)"
      >
        <div class="file-request-card v-modal-card">
          <div class="file-request-icon" aria-hidden="true">
            <svg class="icon"><use href="#icon-inbox" /></svg>
          </div>
          <div class="file-request-copy">
            <span class="v-field-label">File request</span>
            <h1>Upload files to {{ shareTargetLabel }}</h1>
            <p>Files are delivered securely to this folder. Its existing contents stay private.</p>
          </div>
          <button
            type="button"
            class="v-modal-upload-zone file-request-action"
            :class="{ 'v-upload-zone-active': sharedUploadDragActive }"
            :disabled="!canUploadToSharedFolder"
            :title="sharedUploadDisabledReason || ''"
            @click="openSharedUploadModal"
          >
            <svg class="icon"><use href="#icon-upload" /></svg>
            <span class="v-modal-upload-zone-title">Choose files or a folder</span>
            <span class="v-modal-upload-zone-hint">You can also drop them anywhere on this panel.</span>
          </button>
          <div v-if="sharedUploadQueue.length" class="file-request-progress v-inline-note">
            <span>{{ sharedUploadSummary.label }}</span>
            <span>{{ sharedUploadSummary.progress }}</span>
          </div>
        </div>
        <p class="file-request-privacy">
          <svg class="icon"><use href="#icon-lock" /></svg>
          Only the folder owner can view uploaded files.
        </p>
      </section>
      <div v-else-if="loading" class="loading"><div class="spinner"></div></div>
      <div v-else-if="filesError" class="v-empty-state" role="alert">
        <svg class="icon v-empty-state-icon"><use href="#icon-alert"/></svg>
        <p class="v-empty-state-title">Folder could not load</p>
        <p class="v-empty-state-hint">{{ filesError }}</p>
      </div>
      <div v-else-if="files.length === 0 && !canNavigateUp && !(shareMode && shareAllowUpload)" class="v-empty-state">
        <svg class="icon v-empty-state-icon"><use href="#icon-folder"/></svg>
        <p class="v-empty-state-title">No files here</p>
      </div>
      <template v-else>
        <div class="browser-file-toolbar v-toolbar">
          <div class="browser-file-toolbar-copy">
            <span class="browser-file-toolbar-title">{{ browserTitle }}</span>
            <span class="v-text-muted browser-file-toolbar-meta">
              <template v-if="shareMode && shareAllowUpload && sharedUploadQueue.length">
                {{ sharedUploadSummary.label }} · {{ sharedUploadSummary.progress }}
              </template>
              <template v-else>{{ files.length }} item{{ files.length === 1 ? '' : 's' }}</template>
            </span>
          </div>
          <div class="browser-file-toolbar-right">
            <VFileBrowserControls
              :view-mode="viewMode"
              :sort-key="fileSortKey"
              :sort-direction="fileSortDirection"
              @set-view="setViewMode"
              @choose-sort="chooseFileSort"
              @toggle-direction="toggleFileSortDirection"
            />
            <div class="browser-file-toolbar-actions">
            <button
              v-if="shareMode && shareAllowUpload"
              class="v-btn v-btn-secondary v-btn-sm"
              :disabled="!canUploadToSharedFolder"
              :title="sharedUploadDisabledReason || ''"
              @click="openSharedUploadModal"
            >
              <svg class="icon"><use href="#icon-upload" /></svg>
              <span class="v-file-toolbar-action-label">Upload Files</span>
            </button>
            <button
              v-if="canDownloadAllFiles"
              class="v-btn v-btn-secondary v-btn-sm"
              :disabled="downloadAllFilesBusy"
              @click="downloadAllFilesInCurrentFolder"
            >
              <svg class="icon"><use href="#icon-download" /></svg>
              <span class="v-file-toolbar-action-label">{{ downloadAllFilesBusy ? 'Packaging…' : 'Download All' }}</span>
            </button>
            </div>
          </div>
        </div>
        <VFileListHeader
          v-if="viewMode === 'list' && files.length"
          :sort-key="fileSortKey"
          :sort-direction="fileSortDirection"
          :show-uploader="showUploaderColumn"
          @sort="toggleFileSort"
        />
        <div
          :class="viewMode === 'grid' ? 'file-grid' : 'file-list'"
          @dragenter.prevent="shareMode && shareAllowUpload && handleSharedExternalDragEnter($event)"
          @dragover.prevent="shareMode && shareAllowUpload && handleSharedExternalDragOver($event)"
          @dragleave="shareMode && shareAllowUpload && handleSharedExternalDragLeave($event)"
          @drop.prevent="shareMode && shareAllowUpload && handleSharedExternalDrop($event)"
        >
          <div v-if="files.length === 0" class="v-empty-state browser-upload-empty">
            <svg class="icon v-empty-state-icon"><use href="#icon-folder"/></svg>
            <p class="v-empty-state-title">No files here yet</p>
            <p class="v-empty-state-hint">Upload files or folders to get this delivery started.</p>
          </div>
          <template v-else>
            <!-- Back navigation now handled by unified header back button -->
            <template v-for="entry in browserEntries" :key="entry.key">
              <header v-if="entry.kind === 'section'" class="project-browser-section-header file-grid-section-header">
                <span class="project-browser-section-label">{{ entry.label }}</span>
                <span class="project-browser-section-count">{{ entry.count }}</span>
              </header>
              <VFileBrowserItem
                v-else
                :item="entry.item"
                :view-mode="viewMode"
                :thumbnail-url="entry.item.type === 'folder' ? '' : getThumbnailUrl(entry.item)"
                :count-label="entry.item.type === 'folder' ? formatCountLabel(entry.item.file_count) : ''"
                :comment-count="getCommentCount(entry.item)"
                :show-uploader-column="showUploaderColumn"
                :show-linked-state="false"
                :class="{ 'has-open-menu': fileMenuOpen === entry.item.path }"
                @activate="handleClick"
              >
                <template #actions>
                  <div
                    v-if="!shareMode || shareAllowDownload"
                    class="file-menu"
                    :class="{ 'v-card-overflow': viewMode === 'grid', 'v-row-overflow': viewMode !== 'grid', 'is-open': fileMenuOpen === entry.item.path }"
                    @click.stop
                  >
                    <VMenu
                      :open="fileMenuOpen === entry.item.path"
                      align="end"
                      panel-class="file-menu-dropdown"
                      @update:open="open => !open && clearFileMenu()"
                    >
                      <template #trigger="{ triggerProps }">
                        <VOverflowButton floating v-bind="triggerProps" :active="fileMenuOpen === entry.item.path" @click="toggleFileMenu(entry.item)" />
                      </template>
                      <button v-if="!shareMode && isAdmin" class="v-dropdown-item" @click="shareFile(entry.item); clearFileMenu()"><svg class="icon"><use href="#icon-share"/></svg> Share</button>
                      <button v-if="entry.item.type !== 'folder' && (!shareMode || shareAllowDownload)" class="v-dropdown-item" @click="downloadFile(entry.item); clearFileMenu()"><svg class="icon"><use href="#icon-download"/></svg> Download</button>
                      <div v-if="entry.item.type !== 'folder' && !shareMode" class="v-dropdown-divider"></div>
                      <button v-if="entry.item.type !== 'folder' && !shareMode" class="v-dropdown-item" @click="regenerateThumbnail(entry.item)"><svg class="icon"><use href="#icon-refresh"/></svg> Regenerate Thumbnail</button>
                    </VMenu>
                  </div>
                </template>
              </VFileBrowserItem>
            </template>
          </template>
          <div v-if="canLoadMoreFiles" class="v-load-more">
            <button class="v-btn v-btn-secondary" @click="loadMoreFiles">
              Load More ({{ files.length - visibleFiles.length }} remaining)
            </button>
          </div>
          <div v-if="shareMode && shareAllowUpload && sharedUploadDragActive" class="v-drop-overlay">
            <div class="v-drop-overlay-inner">
              <div class="v-drop-overlay-title">Drop to upload</div>
              <div class="v-text-muted v-drop-overlay-subtitle">{{ sharedUploadDropLabel }}</div>
            </div>
          </div>
        </div>
      </template>
    </main>
</template>

<script setup>
import { computed } from 'vue'

import VFileBrowserControls from '../components/files/VFileBrowserControls.vue'
import VFileBrowserItem from '../components/files/VFileBrowserItem.vue'
import VFileListHeader from '../components/files/VFileListHeader.vue'
import { VMenu, VOverflowButton } from '../components/primitives'
import { buildCommentBatchTarget } from '../lib/commentTargets'
import { useFileBrowserStore } from '../ownership/fileBrowser'
import { useSessionAuthStore } from '../ownership/sessionAuth'
import { useShareAccessContext } from '../ownership/shareAccessContext'
import { useViewerStore } from '../ownership/viewer'
import { isFileBrowserFolder } from '../utils/fileBrowserItems'

const {
  currentUser,
  canAccessFileBrowser,
  canAccessProjectManager,
  isAdmin,
} = useSessionAuthStore()

const {
  shareMode,
  shareAllowDownload,
  shareAllowUpload,
  shareRequestFiles,
  shareTargetLabel,
} = useShareAccessContext()

const fileBrowserStore = useFileBrowserStore()
const { showMainContent, activeModule, loading } = fileBrowserStore.shell
const {
  files,
  breadcrumbs,
  canNavigateUp,
  visibleFiles,
  commentCounts,
  filesError,
  formatCountLabel,
  canLoadMoreFiles,
  viewMode,
  fileSortKey,
  fileSortDirection,
  setViewMode,
  chooseFileSort,
  toggleFileSort,
  toggleFileSortDirection,
  handleClick,
  toggleFileMenu,
  fileMenuOpen,
  clearFileMenu,
  regenerateThumbnail,
  loadMoreFiles,
} = fileBrowserStore.browser

const {
  downloadFile,
  canDownloadAllFiles,
  downloadAllFilesBusy,
  downloadAllFilesInCurrentFolder,
} = fileBrowserStore.downloads
const {
  canUploadToSharedFolder,
  sharedUploadDisabledReason,
  uploadQueue: sharedUploadQueue,
  uploadSummary: sharedUploadSummary,
  uploadDragActive: sharedUploadDragActive,
  uploadDropLabel: sharedUploadDropLabel,
  openUploadModal: openSharedUploadModal,
  handleExternalDragEnter: handleSharedExternalDragEnter,
  handleExternalDragOver: handleSharedExternalDragOver,
  handleExternalDragLeave: handleSharedExternalDragLeave,
  handleSharedExternalDrop,
} = fileBrowserStore.uploads.shared
const { shareFile } = fileBrowserStore.actions
const { getThumbnailUrl } = useViewerStore().media.core

const browserTitle = computed(() => {
  const trail = breadcrumbs.value || []
  if (trail.length) return trail[trail.length - 1]?.name || 'Files'
  return shareMode.value ? 'Shared folder' : 'Files'
})

const showUploaderColumn = computed(() => files.value.some((item) => Boolean(item.uploaded_by || item.uploader_name)))
const folderCount = computed(() => files.value.filter(isFileBrowserFolder).length)
const fileCount = computed(() => files.value.length - folderCount.value)
const showGridSections = computed(() => (
  viewMode.value === 'grid' && folderCount.value > 0 && fileCount.value > 0
))
const browserEntries = computed(() => {
  const items = visibleFiles.value || []
  if (!showGridSections.value) {
    return items.map((item) => ({ kind: 'item', key: `item:${item.path}`, item }))
  }

  const folders = items.filter(isFileBrowserFolder)
  const contentFiles = items.filter((item) => !isFileBrowserFolder(item))
  const entries = []
  if (folders.length) {
    entries.push({ kind: 'section', key: 'section:folders', label: 'Folders', count: folderCount.value })
    entries.push(...folders.map((item) => ({ kind: 'item', key: `item:${item.path}`, item })))
  }
  if (contentFiles.length) {
    entries.push({ kind: 'section', key: 'section:files', label: 'Files', count: fileCount.value })
    entries.push(...contentFiles.map((item) => ({ kind: 'item', key: `item:${item.path}`, item })))
  }
  return entries
})

function getCommentCount(item) {
  const target = buildCommentBatchTarget({
    path: item.path,
    horizons_media_asset_id: item.media_asset_id || item.horizons_media_asset_id || null,
    horizons_shot_version_id: item.horizons_shot_version_id || item.version_id || null,
  })
  return commentCounts.value[target.key] || 0
}
</script>

<style>
.browser {
  flex: 1;
  overflow-y: auto;
}

.file-grid-section-header {
  grid-column: 1 / -1;
  margin-bottom: -2px;
}

.file-grid-section-header:not(:first-child) {
  margin-top: 10px;
}

.file-request-page {
  min-height: calc(100dvh - var(--v-nav-height, 52px));
  padding: clamp(var(--v-space-5), 8vh, 88px) var(--v-space-5) var(--v-space-8);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--v-space-4);
}

.file-request-card {
  width: min(100%, 620px);
  padding: clamp(var(--v-space-5), 4vw, var(--v-space-8));
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--v-space-5);
  text-align: center;
}

.file-request-icon {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-lg);
  background: var(--v-control-bg);
  color: var(--v-accent-hover);
}

.file-request-icon .icon {
  width: 21px;
  height: 21px;
}

.file-request-copy {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--v-space-2);
}

.file-request-copy h1 {
  margin: 0;
  color: var(--v-text);
  font-size: clamp(22px, 3vw, 28px);
  line-height: 1.15;
}

.file-request-copy p {
  max-width: 430px;
  margin: 0;
  color: var(--v-text-muted);
  line-height: 1.55;
}

.file-request-action {
  width: 100%;
  min-height: 164px;
  color: inherit;
  cursor: pointer;
}

.file-request-action:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.file-request-progress {
  width: 100%;
  display: flex;
  justify-content: space-between;
  gap: var(--v-space-3);
  border: 1px solid var(--v-info-border);
  background: var(--v-info-bg);
  color: color-mix(in srgb, var(--v-info) 74%, white);
}

.file-request-privacy {
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
}

.file-request-privacy .icon {
  width: 13px;
  height: 13px;
}

@media (max-width: 548px) {
  .file-request-page {
    min-height: calc(100dvh - var(--v-nav-height, 52px));
    justify-content: center;
    padding: var(--v-space-4);
  }

  .file-request-card {
    padding: var(--v-space-5);
    gap: var(--v-space-4);
  }

  .file-request-action {
    min-height: 148px;
  }
}

.browser-file-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-4);
}

.browser-file-toolbar-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.browser-file-toolbar-actions {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  flex-shrink: 0;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 400px;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 2px solid var(--v-border);
  border-top-color: var(--v-accent);
  border-radius: 50%;
  animation: v-spin 0.8s infinite linear;
}
</style>
