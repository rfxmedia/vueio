<template>
        <div v-if="projectContentsLoading" class="project-folder-loading" role="status" aria-live="polite">
          <span class="project-folder-loading-spinner" aria-hidden="true"></span>
          <span>Opening folder…</span>
        </div>
        <div v-if="projectContentsError" class="v-empty-state project-folder-error" role="alert">
          <svg class="icon v-empty-state-icon"><use href="#icon-alert"/></svg>
          <p class="v-empty-state-title">Folder could not load</p>
          <p class="v-empty-state-hint">{{ projectContentsError }}</p>
        </div>
        <!-- ═══════════════════════════════════════════════════════════════════ -->
        <!-- ARTIST WORKSPACE VIEW (folder browser with tracker shortcuts) -->
        <!-- ═══════════════════════════════════════════════════════════════════ -->
        <div v-if="currentUser?.role === 'artist'" class="project-contents">
          <div v-if="projectFolderContext?.is_linked_folder && projectUploadDisabledReason" class="project-folder-note v-inline-note">
            {{ projectUploadDisabledReason }}
          </div>
          <div v-if="!projectContentsError && hasNoProjectContents" class="v-empty-state">
            <svg class="icon v-empty-state-icon"><use href="#icon-folder"/></svg>
            <p class="v-empty-state-title">{{ emptyStateTitle }}</p>
            <p class="v-empty-state-hint">{{ emptyStateHint }}</p>
          </div>
          <div
            v-else-if="!projectContentsError"
            class="project-browser"
            @dragenter.prevent="handleProjectExternalDragEnter"
            @dragover.prevent="handleProjectExternalDragOver"
            @dragleave="handleProjectExternalDragLeave"
            @drop.prevent="handleProjectExternalDrop"
          >
            <section v-if="projectShortcutTrackers.length" class="project-browser-section">
              <header class="project-browser-section-header">
                <span class="project-browser-section-label">Quick access</span>
                <span class="project-browser-section-count">{{ projectShortcutTrackers.length }}</span>
              </header>
              <div class="project-specialty-shelf is-single-group">
                <div class="project-specialty-grid">
                  <ProjectSpecialtyItem
                    v-for="item in visibleProjectShortcutTrackers"
                    :key="item.path"
                    :item="item"
                    kind="tracker"
                    :meta="`${item.shot_count} shot${item.shot_count === 1 ? '' : 's'}`"
                    @activate="openTracker(item.slug || item.id || item.path || item.name)"
                  />
                </div>
                <div v-if="canLoadMoreProjectShortcutTrackers" class="v-load-more">
                  <button class="v-btn v-btn-secondary" @click="loadMoreProjectShortcutTrackers">
                    Load More Trackers ({{ projectShortcutTrackers.length - visibleProjectShortcutTrackers.length }} remaining)
                  </button>
                </div>
              </div>
            </section>

            <ProjectFileToolbar
              v-if="hasProjectFileControls"
              :view-mode="viewMode"
              :sort-key="fileSortKey"
              :sort-direction="fileSortDirection"
              :item-count="browserProjectFolderItems.length + projectFileItems.length"
              :path="projectPath"
              :breadcrumbs="projectBreadcrumbs"
              :home-path="artistWorkspaceRoot || ''"
              :can-download-all="canDownloadAllProjectFolder"
              :download-busy="downloadAllProjectFolderBusy"
              @set-view="setViewMode"
              @choose-sort="chooseFileSort"
              @toggle-direction="toggleFileSortDirection"
              @download-all="downloadCurrentProjectFolder"
              @navigate="navigateProjectFolder"
            />

            <section v-if="viewMode === 'grid' && (visibleBrowserProjectFolderItems.length || canLoadMoreProjectFolders)" class="project-browser-section">
              <header v-if="showProjectContentCategoryHeaders" class="project-browser-section-header">
                <span class="project-browser-section-label">{{ browserProjectFolderItems.some((f) => f.is_workspace) ? 'Workspaces' : 'Folders' }}</span>
                <span class="project-browser-section-count">{{ browserProjectFolderItems.length }}</span>
              </header>
              <div class="file-grid">
                <VFileBrowserItem
                  v-for="item in visibleBrowserProjectFolderItems"
                  :key="item.path"
                  :item="item"
                  :count-label="formatCountLabel(item.item_count)"
                  @activate="navigateProjectFolder(item.path)"
                  @dragenter.prevent.stop="handleProjectExternalDragEnter($event, item.path)"
                  @dragover.prevent.stop="handleProjectExternalDragOver($event, item.path)"
                  @dragleave.stop="handleProjectExternalDragLeave"
                  @drop.prevent.stop="handleProjectExternalDrop($event, item.path)"
                />
                <div v-if="canLoadMoreProjectFolders" class="v-load-more">
                  <button class="v-btn v-btn-secondary" @click="loadMoreProjectFolders">
                    Load More Folders ({{ projectFolderItems.length - visibleProjectFolderItems.length }} remaining)
                  </button>
                </div>
              </div>
            </section>

            <section v-if="viewMode === 'grid' && (visibleProjectFileItems.length || canLoadMoreProjectFiles)" class="project-browser-section">
              <header v-if="showProjectContentCategoryHeaders" class="project-browser-section-header">
                <span class="project-browser-section-label">Files</span>
                <span class="project-browser-section-count">{{ projectFileItems.length }}</span>
              </header>
              <div class="file-grid">
                <VFileBrowserItem
                  v-for="item in visibleProjectFileItems"
                  :key="item.path"
                  :item="item"
                  :thumbnail-url="getProjectFileThumbnailUrl(item)"
                  @activate="openFileFromProject"
                />
                <div v-if="canLoadMoreProjectFiles" class="v-load-more">
                  <button class="v-btn v-btn-secondary" @click="loadMoreProjectFiles">
                    Load More Files ({{ projectFileItems.length - visibleProjectFileItems.length }} remaining)
                  </button>
                </div>
              </div>
            </section>

            <section v-if="viewMode === 'list' && visibleProjectBrowserEntries.length" class="project-browser-section project-browser-list-section">
              <VFileListHeader
                :sort-key="fileSortKey"
                :sort-direction="fileSortDirection"
                :show-uploader="projectShowUploader"
                @sort="toggleFileSort"
              />
              <div class="file-list" :class="{ 'has-uploader': projectShowUploader }">
                <VFileBrowserItem
                  v-for="item in visibleProjectBrowserEntries"
                  :key="item.path"
                  :item="item"
                  view-mode="list"
                  :thumbnail-url="item.type === 'folder' ? '' : getProjectFileThumbnailUrl(item)"
                  :count-label="item.type === 'folder' ? formatCountLabel(item.item_count) : ''"
                  :show-uploader-column="projectShowUploader"
                  @activate="activateProjectBrowserEntry"
                />
              </div>
              <div v-if="canLoadMoreProjectFolders" class="v-load-more is-list-load-more">
                <button class="v-btn v-btn-secondary" @click="loadMoreProjectFolders">
                  Load More Folders ({{ projectFolderItems.length - visibleProjectFolderItems.length }} remaining)
                </button>
              </div>
              <div v-if="canLoadMoreProjectFiles" class="v-load-more is-list-load-more">
                <button class="v-btn v-btn-secondary" @click="loadMoreProjectFiles">
                  Load More Files ({{ projectFileItems.length - visibleProjectFileItems.length }} remaining)
                </button>
              </div>
            </section>

            <div v-if="projectUploadDragActive" class="v-drop-overlay">
              <div class="v-drop-overlay-inner">
                <div class="v-drop-overlay-title">Drop to upload</div>
                <div class="v-text-muted v-drop-overlay-subtitle">{{ projectUploadDropLabel }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- ═══════════════════════════════════════════════════════════════════ -->
        <!-- PROJECT FOLDER CONTENTS (admin view - when no tracker is selected) -->
        <!-- ═══════════════════════════════════════════════════════════════════ -->
        <div v-if="currentUser?.role !== 'artist'" class="project-contents">
          <div v-if="projectFolderContext?.is_linked_folder && projectUploadDisabledReason" class="project-folder-note v-inline-note">
            {{ projectUploadDisabledReason }}
          </div>
          <div v-if="!projectContentsError && hasNoProjectContents" class="v-empty-state">
            <svg class="icon v-empty-state-icon"><use href="#icon-folder"/></svg>
            <p class="v-empty-state-title">{{ emptyStateTitle }}</p>
            <p class="v-empty-state-hint">{{ emptyStateHint }}</p>
          </div>

          <div
            v-else-if="!projectContentsError"
            class="project-browser"
            @click="closeContentMenu"
            @dragenter.prevent="handleProjectExternalDragEnter"
            @dragover.prevent="handleProjectExternalDragOver"
            @dragleave="handleProjectExternalDragLeave"
            @drop.prevent="handleProjectExternalDrop"
          >
            <section v-if="hasProjectSpecialtyItems" class="project-browser-section project-specialty-section">
              <header class="project-browser-section-header">
                <span class="project-browser-section-label">Vue Assets</span>
                <span class="project-browser-section-count">{{ projectSpecialtyItemCount }}</span>
              </header>
              <div class="project-specialty-shelf">
                <div class="project-specialty-grid">
                  <ProjectSpecialtyItem
                    v-for="item in visibleProjectPageItems"
                    :key="item.id || item.path"
                    :item="item"
                    kind="dashboard"
                    :meta="`${item.block_count || 0} block${item.block_count === 1 ? '' : 's'}`"
                    :menu-open="contentMenuOpen === item.path"
                    @activate="openPage(item.slug || item.path)"
                  >
                    <template v-if="canEditProject || canShareProject" #actions>
                      <VMenu
                        :open="contentMenuOpen === item.path"
                        align="end"
                        class="v-row-overflow"
                        @update:open="open => !open && closeContentMenu()"
                      >
                        <template #trigger="{ triggerProps }">
                          <VOverflowButton floating class="menu-trigger" v-bind="triggerProps" :active="contentMenuOpen === item.path" @click="toggleContentMenu(item.path)" />
                        </template>
                        <button v-if="canShareProject" class="v-dropdown-item" @click="shareProjectPage(item); closeContentMenu()"><svg class="icon"><use href="#icon-share"/></svg> Share Dashboard</button>
                        <div v-if="canEditProject" class="v-dropdown-divider"></div>
                        <button v-if="canEditProject && currentUser?.role !== 'artist'" class="v-dropdown-item" @click="startRenamePage(item); closeContentMenu()"><svg class="icon"><use href="#icon-edit"/></svg> Rename</button>
                        <button v-if="canEditProject && currentUser?.role !== 'artist'" class="v-dropdown-item v-dropdown-item-danger" @click="deletePage(item); closeContentMenu()"><svg class="icon"><use href="#icon-trash"/></svg> Delete</button>
                      </VMenu>
                    </template>
                  </ProjectSpecialtyItem>

                  <ProjectSpecialtyItem
                    v-for="item in visibleProjectTrackerItems"
                    :key="item.path"
                    :item="item"
                    kind="tracker"
                    :meta="`${item.shot_count} shot${item.shot_count === 1 ? '' : 's'}`"
                    :menu-open="contentMenuOpen === item.path"
                    :class="{ 'dragging': projectDragItem?.path === item.path }"
                    :draggable="canEditProject"
                    @activate="openTracker(item.id || item.slug || item.name)"
                    @dragstart="startProjectDrag($event, item)"
                    @dragend="endProjectDrag"
                  >
                    <template v-if="canEditProject" #actions>
                      <VMenu
                        :open="contentMenuOpen === item.path"
                        align="end"
                        class="v-row-overflow"
                        @update:open="open => !open && closeContentMenu()"
                      >
                        <template #trigger="{ triggerProps }">
                          <VOverflowButton floating class="menu-trigger" v-bind="triggerProps" :active="contentMenuOpen === item.path" @click="toggleContentMenu(item.path)" />
                        </template>
                        <button class="v-dropdown-item" @click="startRenameTracker(item); closeContentMenu()"><svg class="icon"><use href="#icon-edit"/></svg> Rename</button>
                        <button class="v-dropdown-item" @click="duplicateItem(item); closeContentMenu()"><svg class="icon"><use href="#icon-copy"/></svg> Duplicate</button>
                        <div class="v-dropdown-divider"></div>
                        <button class="v-dropdown-item v-dropdown-item-danger" @click="deleteTracker(item.name); closeContentMenu()"><svg class="icon"><use href="#icon-trash"/></svg> Delete</button>
                      </VMenu>
                    </template>
                  </ProjectSpecialtyItem>
                </div>
                <div v-if="canLoadMoreProjectPages || canLoadMoreProjectTrackers" class="v-load-more">
                  <button v-if="canLoadMoreProjectPages" class="v-btn v-btn-secondary" @click="loadMoreProjectPages">
                    Load More Dashboards ({{ projectPageItems.length - visibleProjectPageItems.length }} remaining)
                  </button>
                  <button v-if="canLoadMoreProjectTrackers" class="v-btn v-btn-secondary" @click="loadMoreProjectTrackers">
                    Load More Trackers ({{ projectTrackerItems.length - visibleProjectTrackerItems.length }} remaining)
                  </button>
                </div>
              </div>
            </section>

            <ProjectFileToolbar
              v-if="hasProjectFileControls"
              :view-mode="viewMode"
              :sort-key="fileSortKey"
              :sort-direction="fileSortDirection"
              :item-count="browserProjectFolderItems.length + projectFileItems.length"
              :path="projectPath"
              :breadcrumbs="projectBreadcrumbs"
              :can-download-all="canDownloadAllProjectFolder"
              :download-busy="downloadAllProjectFolderBusy"
              @set-view="setViewMode"
              @choose-sort="chooseFileSort"
              @toggle-direction="toggleFileSortDirection"
              @download-all="downloadCurrentProjectFolder"
              @navigate="navigateProjectFolder"
            />

            <div v-if="hasNoProjectFiles" class="v-empty-state project-browser-empty">
              <svg class="icon v-empty-state-icon"><use href="#icon-folder"/></svg>
              <p class="v-empty-state-title">{{ emptyStateTitle }}</p>
              <p class="v-empty-state-hint">{{ emptyStateHint }}</p>
            </div>

            <section v-if="viewMode === 'grid' && (visibleBrowserProjectFolderItems.length || canLoadMoreProjectFolders || (projectPath && projectDragItem))" class="project-browser-section">
              <header v-if="showProjectContentCategoryHeaders" class="project-browser-section-header">
                <span class="project-browser-section-label">Folders</span>
                <span v-if="browserProjectFolderItems.length" class="project-browser-section-count">{{ browserProjectFolderItems.length }}</span>
              </header>
              <div class="file-grid">
            <!-- Drop zone for moving files to parent folder (only shows when dragging) -->
            <div
              v-if="projectPath && projectDragItem"
              class="v-card v-card-interactive file-card folder v-folder-card drop-zone"
              :class="{ 'drop-target': projectDropTarget === '__parent__' }"
              @dragover.prevent.stop="onProjectDragOverParent"
              @dragleave.stop="onProjectDragLeave"
              @drop.prevent.stop="onProjectDropToParent($event)"
            >
              <div class="v-file-activation">
                <div class="thumb"><svg class="icon folder-icon"><use href="#icon-folder"/></svg></div>
                <div class="file-info"><div class="v-truncate file-name">Move to parent folder</div></div>
              </div>
            </div>

            <!-- Folders -->
            <VFileBrowserItem
              v-for="item in visibleBrowserProjectFolderItems"
              :key="item.path"
              :item="item"
              :count-label="formatCountLabel(item.item_count)"
              :class="{ 'drop-target': projectDropTarget === item.path, 'dragging': projectDragItem?.path === item.path, 'has-open-menu': contentMenuOpen === item.path }"
              :draggable="canEditProject && item.link_kind !== 'folder-child' && !item.is_workspace"
              @activate="navigateProjectFolder(item.path)"
              @dragstart="startProjectDrag($event, item)"
              @dragend="endProjectDrag"
              @dragover.prevent.stop="onProjectDragOver($event, item)"
              @dragleave.stop="onProjectDragLeave"
              @drop.prevent.stop="onProjectDrop($event, item)"
            >
              <template #actions>
                <VMenu
                  v-if="canShowProjectFolderMenu(item)"
                  :open="contentMenuOpen === item.path"
                  align="end"
                  class="file-menu v-card-overflow"
                  @update:open="open => !open && closeContentMenu()"
                >
                  <template #trigger="{ triggerProps }">
                    <VOverflowButton floating class="menu-trigger" v-bind="triggerProps" :active="contentMenuOpen === item.path" @click="toggleContentMenu(item.path)" />
                  </template>
                  <VMenuActionList :actions="folderMenuActions(item)" />
                </VMenu>
              </template>
            </VFileBrowserItem>
            <div v-if="canLoadMoreProjectFolders" class="v-load-more">
              <button class="v-btn v-btn-secondary" @click="loadMoreProjectFolders">
                Load More Folders ({{ projectFolderItems.length - visibleProjectFolderItems.length }} remaining)
              </button>
            </div>
              </div>
            </section>

            <section v-if="viewMode === 'grid' && (visibleProjectFileItems.length || canLoadMoreProjectFiles)" class="project-browser-section">
              <header v-if="showProjectContentCategoryHeaders" class="project-browser-section-header">
                <span class="project-browser-section-label">Files</span>
                <span class="project-browser-section-count">{{ projectFileItems.length }}</span>
              </header>
              <div class="file-grid">
            <!-- Files (imported and linked) -->
            <VFileBrowserItem
              v-for="item in visibleProjectFileItems"
              :key="item.path"
              :item="item"
              :thumbnail-url="getProjectFileThumbnailUrl(item)"
              :class="{ 'is-linked': item.is_linked, 'dragging': projectDragItem?.path === item.path, 'has-open-menu': contentMenuOpen === item.path }"
              :draggable="canEditProject && item.link_kind !== 'folder-child'"
              @activate="openFileFromProject"
              @dragstart="startProjectDrag($event, item)"
              @dragend="endProjectDrag"
            >
              <template #actions>
                <VMenu
                  :open="contentMenuOpen === item.path"
                  align="end"
                  class="file-menu v-card-overflow"
                  @update:open="open => !open && closeContentMenu()"
                >
                  <template #trigger="{ triggerProps }">
                    <VOverflowButton floating class="menu-trigger" v-bind="triggerProps" :active="contentMenuOpen === item.path" @click="toggleContentMenu(item.path)" />
                  </template>
                  <VMenuActionList :actions="fileMenuActions(item)" />
                </VMenu>
              </template>
            </VFileBrowserItem>
            <div v-if="canLoadMoreProjectFiles" class="v-load-more">
              <button class="v-btn v-btn-secondary" @click="loadMoreProjectFiles">
                Load More Files ({{ projectFileItems.length - visibleProjectFileItems.length }} remaining)
              </button>
            </div>
              </div>
            </section>

            <section v-if="viewMode === 'list' && visibleProjectBrowserEntries.length" class="project-browser-section project-browser-list-section">
              <VFileListHeader
                :sort-key="fileSortKey"
                :sort-direction="fileSortDirection"
                :show-uploader="projectShowUploader"
                @sort="toggleFileSort"
              />
              <div class="file-list" :class="{ 'has-uploader': projectShowUploader }">
                <VFileBrowserItem
                  v-for="item in visibleProjectBrowserEntries"
                  :key="item.path"
                  :item="item"
                  view-mode="list"
                  :thumbnail-url="item.type === 'folder' ? '' : getProjectFileThumbnailUrl(item)"
                  :count-label="item.type === 'folder' ? formatCountLabel(item.item_count) : ''"
                  :show-uploader-column="projectShowUploader"
                  :class="{
                    'dragging': projectDragItem?.path === item.path,
                    'drop-target': projectDropTarget === item.path,
                    'has-open-menu': contentMenuOpen === item.path,
                  }"
                  :draggable="canEditProject && item.link_kind !== 'folder-child' && !item.is_workspace"
                  @activate="activateProjectBrowserEntry"
                  @dragstart="startProjectDrag($event, item)"
                  @dragend="endProjectDrag"
                  @dragover.prevent.stop="handleProjectListDragOver($event, item)"
                  @dragleave.stop="onProjectDragLeave"
                  @drop.prevent.stop="handleProjectListDrop($event, item)"
                >
                  <template #actions>
                    <VMenu
                      v-if="item.type === 'folder' && canShowProjectFolderMenu(item)"
                      :open="contentMenuOpen === item.path"
                      align="end"
                      class="file-menu v-row-overflow"
                      @update:open="open => !open && closeContentMenu()"
                    >
                      <template #trigger="{ triggerProps }">
                        <VOverflowButton floating class="menu-trigger" v-bind="triggerProps" :active="contentMenuOpen === item.path" @click="toggleContentMenu(item.path)" />
                      </template>
                      <VMenuActionList :actions="folderMenuActions(item)" />
                    </VMenu>

                    <VMenu
                      v-else-if="item.type === 'file'"
                      :open="contentMenuOpen === item.path"
                      align="end"
                      class="file-menu v-row-overflow"
                      @update:open="open => !open && closeContentMenu()"
                    >
                      <template #trigger="{ triggerProps }">
                        <VOverflowButton floating class="menu-trigger" v-bind="triggerProps" :active="contentMenuOpen === item.path" @click="toggleContentMenu(item.path)" />
                      </template>
                      <VMenuActionList :actions="fileMenuActions(item)" />
                    </VMenu>
                  </template>
                </VFileBrowserItem>
              </div>
              <div v-if="canLoadMoreProjectFolders" class="v-load-more is-list-load-more">
                <button class="v-btn v-btn-secondary" @click="loadMoreProjectFolders">
                  Load More Folders ({{ projectFolderItems.length - visibleProjectFolderItems.length }} remaining)
                </button>
              </div>
              <div v-if="canLoadMoreProjectFiles" class="v-load-more is-list-load-more">
                <button class="v-btn v-btn-secondary" @click="loadMoreProjectFiles">
                  Load More Files ({{ projectFileItems.length - visibleProjectFileItems.length }} remaining)
                </button>
              </div>
            </section>

            <div v-if="projectUploadDragActive" class="v-drop-overlay">
              <div class="v-drop-overlay-inner">
                <div class="v-drop-overlay-title">Drop to upload</div>
                <div class="v-text-muted v-drop-overlay-subtitle">{{ projectUploadDropLabel }}</div>
              </div>
            </div>
          </div>
        </div>
</template>

<script setup>
import VFileBrowserItem from '../components/files/VFileBrowserItem.vue'
import VFileListHeader from '../components/files/VFileListHeader.vue'
import ProjectFileToolbar from '../components/files/ProjectFileToolbar.vue'
import ProjectSpecialtyItem from '../components/files/ProjectSpecialtyItem.vue'
import { VMenu, VMenuActionList, VOverflowButton } from '../components/primitives'
import { computed } from 'vue'
import { useProjectTrackerSelectionStore } from '../ownership/projectTrackerSelection'
import { useSessionAuthStore } from '../ownership/sessionAuth'
import { useShareAccessContext } from '../ownership/shareAccessContext'
import { useProjectWorkspaceStore } from '../ownership/projectWorkspace'
import { useFileBrowserStore } from '../ownership/fileBrowser'
import { useViewerStore } from '../ownership/viewer'

const { currentProject } = useProjectTrackerSelectionStore()
const { currentUser, canEditProject: canEditProjectPermission } = useSessionAuthStore()
const { shareMode, shareAllowDownload } = useShareAccessContext()
const fileBrowserStore = useFileBrowserStore()
const {
  uploadDragActive: projectUploadDragActive,
  uploadDropLabel: projectUploadDropLabel,
  projectUploadDisabledReason,
  handleExternalDragEnter: handleProjectExternalDragEnter,
  handleExternalDragOver: handleProjectExternalDragOver,
  handleExternalDragLeave: handleProjectExternalDragLeave,
  handleProjectExternalDrop,
} = fileBrowserStore.uploads.project
const {
  canDownloadProjectFolderItem,
  downloadProjectItem,
  downloadProjectFolder,
  canDownloadAllProjectFolder,
  downloadAllProjectFolderBusy,
  downloadCurrentProjectFolder,
} = fileBrowserStore.downloads
const { formatCountLabel } = fileBrowserStore.browser
const {
  getProjectFileThumbnailUrl,
} = useViewerStore().media.core
const {
  projectContents,
  projectPath,
  projectBreadcrumbs,
  artistWorkspaceRoot,
  projectFolderContext,
  projectContentsLoading,
  projectContentsError,
  projectShortcutTrackers,
  visibleProjectShortcutTrackers,
  canLoadMoreProjectShortcutTrackers,
  loadMoreProjectShortcutTrackers,
  projectPageItems,
  visibleProjectPageItems,
  canLoadMoreProjectPages,
  loadMoreProjectPages,
  projectFolderItems,
  projectBrowserEntries,
  projectShowUploader,
  visibleProjectFolderItems,
  canLoadMoreProjectFolders,
  loadMoreProjectFolders,
  visibleProjectFileItems,
  canLoadMoreProjectFiles,
  loadMoreProjectFiles,
  viewMode,
  fileSortKey,
  fileSortDirection,
  setViewMode,
  chooseFileSort,
  toggleFileSort,
  toggleFileSortDirection,
  openTracker,
  openPage,
  navigateProjectFolder,
  openFileFromProject,
  projectDragItem,
  projectDropTarget,
  onProjectDragOverParent,
  onProjectDragLeave,
  onProjectDropToParent,
  startProjectDrag,
  endProjectDrag,
  onProjectDragOver,
  onProjectDrop,
  canShareProject,
  contentMenuOpen,
  toggleContentMenu,
  closeContentMenu,
  shareProjectContent,
  shareProjectPage,
  startRenamePage,
  deletePage,
  startRenameFolder,
  duplicateItem,
  deleteProjectFolder,
  unlinkProjectItem,
  projectTrackerItems,
  visibleProjectTrackerItems,
  canLoadMoreProjectTrackers,
  loadMoreProjectTrackers,
  startRenameTracker,
  deleteTracker,
  startRenameFile,
  deleteProjectFile,
  projectFileItems,
} = useProjectWorkspaceStore()

const canEditProject = computed(() => canEditProjectPermission.value && !currentProject.value?.storage_read_only)

/* Menus as data — each list is rendered by both the grid and list layouts, so
   the two can no longer drift apart the way the file menus had. VMenu closes
   on select, so no action needs to call closeContentMenu itself. */
const canUnlink = computed(() => canEditProject.value && currentUser.value?.role !== 'artist')

function folderMenuActions(item) {
  const editable = canEditProject.value && !item.is_workspace
  return [
    { label: 'Download', icon: '#icon-download', show: canDownloadProjectFolderItem(item), run: () => downloadProjectFolder(item.path, item.name) },
    { label: 'Share Folder', icon: '#icon-share', show: canShareProject.value && !item.is_linked, run: () => shareProjectContent(item, true) },
    { divider: true },
    { label: 'Rename', icon: '#icon-edit', show: editable && !item.is_linked, run: () => startRenameFolder(item) },
    { label: 'Duplicate', icon: '#icon-copy', show: editable && item.link_kind !== 'folder-child', run: () => duplicateItem(item) },
    { divider: true },
    { label: 'Delete', icon: '#icon-trash', danger: true, show: editable && !item.is_linked, run: () => deleteProjectFolder(item.path) },
    { label: 'Unlink', icon: '#icon-link', danger: true, show: canUnlink.value && item.is_linked && item.link_kind === 'direct-folder', run: () => unlinkProjectItem(item) },
  ]
}

function fileMenuActions(item) {
  const detachable = canEditProject.value && item.link_kind !== 'folder-child'
  return [
    { label: 'Share File', icon: '#icon-share', show: canShareProject.value && !item.is_linked, run: () => shareProjectContent(item, false) },
    { label: 'Download', icon: '#icon-download', show: !shareMode.value || shareAllowDownload.value, run: () => downloadProjectItem(item) },
    { divider: true },
    { label: 'Rename', icon: '#icon-edit', show: canEditProject.value && !item.is_linked, run: () => startRenameFile(item) },
    { label: 'Duplicate', icon: '#icon-copy', show: detachable && !item.is_workspace, run: () => duplicateItem(item) },
    { divider: true },
    { label: 'Delete', icon: '#icon-trash', danger: true, show: canEditProject.value && !item.is_linked, run: () => deleteProjectFile(item) },
    { label: 'Unlink', icon: '#icon-link', danger: true, show: canUnlink.value && item.is_linked && item.link_kind === 'direct-file', run: () => unlinkProjectItem(item) },
  ]
}
const browserProjectFolderItems = computed(() => projectFolderItems.value)
const visibleBrowserProjectFolderItems = computed(() => visibleProjectFolderItems.value)
const visibleProjectBrowserEntries = computed(() => projectBrowserEntries.value)
const hasProjectToolItems = computed(() => projectPageItems.value.length > 0 || projectTrackerItems.value.length > 0)
const hasProjectSpecialtyItems = computed(() => hasProjectToolItems.value)
const projectSpecialtyItemCount = computed(() => (
  projectPageItems.value.length + projectTrackerItems.value.length
))

const hasNoProjectContents = computed(() => (
  !projectContentsLoading.value
  && (projectContents.value || []).length === 0
  && (currentUser.value?.role === 'artist' || (!projectPageItems.value.length && !projectTrackerItems.value.length))
))
const hasNoProjectFiles = computed(() => (
  !projectContentsLoading.value
  && Boolean(projectPath.value)
  && !browserProjectFolderItems.value.length
  && !projectFileItems.value?.length
))
const hasProjectFileControls = computed(() => Boolean(
  projectPath.value ||
  browserProjectFolderItems.value.length ||
  projectFileItems.value?.length ||
  canDownloadAllProjectFolder.value
))
const showProjectContentCategoryHeaders = computed(() => Boolean(
  browserProjectFolderItems.value.length && projectFileItems.value?.length
))
const isNestedFolder = computed(() => Boolean(projectPath.value))

const emptyStateTitle = computed(() => {
  if (currentUser.value?.role === 'artist') return 'Your workspace is empty'
  if (shareMode.value && isNestedFolder.value) return 'This shared folder is empty'
  if (isNestedFolder.value) return 'This folder is empty'
  return 'This project is empty'
})

const emptyStateHint = computed(() => {
  if (currentUser.value?.role === 'artist') return 'Upload files or create folders to get started'
  if (shareMode.value) return 'There are no files or folders available here.'
  if (isNestedFolder.value) return 'Add files or folders here when this part of the project is ready.'
  return 'Click "New" to add a shot tracker, folder, or file'
})

function activateProjectBrowserEntry(item) {
  if (item?.type === 'folder') {
    navigateProjectFolder(item.path)
    return
  }
  openFileFromProject(item)
}

function canShowProjectFolderMenu(item) {
  if (!item || item.is_workspace) return false
  return (shareMode.value && shareAllowDownload.value) || canShareProject.value || canEditProject.value
}

function handleProjectListDragOver(event, item) {
  if (item?.type === 'folder') onProjectDragOver(event, item)
}

function handleProjectListDrop(event, item) {
  if (item?.type === 'folder') onProjectDrop(event, item)
}
</script>

<style>
.project-contents { min-height: 300px; }

.project-folder-note { margin-bottom: var(--v-space-3); }
.project-folder-loading {
  position: sticky;
  top: 0;
  z-index: 8;
  display: inline-flex;
  align-items: center;
  gap: var(--v-space-2);
  margin: 0 24px -8px;
  padding: 8px 12px;
  border: 1px solid var(--v-border);
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-bg-elevated) 92%, transparent);
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 600;
  box-shadow: var(--v-shadow-sm);
  backdrop-filter: blur(12px);
}
.project-folder-loading-spinner {
  width: 14px;
  height: 14px;
  border-radius: var(--v-radius-full);
  border: 2px solid var(--v-border);
  border-top-color: var(--v-accent);
  animation: v-spin 0.8s linear infinite;
}

.project-specialty-section {
  gap: var(--v-space-2);
}

.project-specialty-shelf {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.project-specialty-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(172px, 220px));
  gap: 6px;
}

.project-specialty-shelf > .v-load-more {
  padding-top: 0;
}

/* Parent-folder drop target follows the same compact folder silhouette. */
.project-contents .file-card.drop-zone {
  border-style: dashed;
  background: transparent;
}

/* Linked files retain a distinct edge; folders communicate the state in metadata. */
.project-contents .file-card.is-linked:not(.v-folder-card) { border-style: dashed; }

/* Link badge (NAS linked items) */
.project-contents .thumb .link-badge {
  top: var(--v-space-3);
  right: var(--v-space-3);
  bottom: auto;
  width: var(--v-overlay-pill-height);
  padding: 0;
  color: var(--v-accent);
  backdrop-filter: blur(8px);
}
.project-contents .thumb .link-badge .icon { color: currentColor; }
.project-browser .v-drop-overlay { border-radius: var(--v-radius-lg); }

.project-folder-error {
  margin: 16px 24px 0;
}

/* Drag & Drop States */
.project-contents .file-card.dragging { opacity: 0.5; }
.project-contents .file-card.drop-target {
  background: color-mix(in srgb, var(--v-accent) 7%, var(--v-surface-panel));
  border-color: color-mix(in srgb, var(--v-accent) 42%, var(--v-surface-border-strong));
  transform: none;
}
.project-contents .file-card[draggable="true"] { cursor: grab; }
.project-contents .file-card[draggable="true"]:active { cursor: grabbing; }

.project-contents .thumb .duration-badge { bottom: 6px; right: 6px; }
.pdf-icon { color: var(--v-danger-text); }


@media (max-width: 768px) {
  .project-contents { padding: 14px; }

  .project-specialty-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 420px) {
  .project-specialty-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
