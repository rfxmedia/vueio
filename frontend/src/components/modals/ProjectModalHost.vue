<template>
  <ProjectSettingsModal
    :show="settings.showProjectSettingsModal"
    scope="project"
    :is-mobile="isMobile"
    :project="settings.activeProjectSettingsTarget"
    :can-edit-project="settings.canEditActiveProjectSettings"
    :can-manage-project-team="settings.canManageActiveProjectTeam"
    :saving="settings.projectSettingsSaving"
    :team-saving="settings.projectTeamSaving"
    :team-loading="settings.projectTeamLoading"
    :draft-title="settings.projectSettingsDraftTitle"
    :draft-description="settings.projectSettingsDraftDescription"
    :draft-due-date="settings.projectSettingsDraftDueDate"
    :draft-status="settings.projectSettingsDraftStatus"
    :status-options="settings.PROJECT_STATUS_OPTIONS"
    :thumbnail-url="settings.projectSettingsThumbnailUrl"
    :app-identity="appIdentity"
    :team-members="settings.projectTeamMembers"
    :team-options="settings.projectTeamOptions"
    :team-add-user-id="settings.projectTeamAddUserId"
    :team-add-role="settings.projectTeamAddRole"
    :current-user-id="session.currentUser?.id || ''"
    :close="settings.closeProjectSettingsModal"
    :save="settings.saveProjectSettings"
    :open-thumbnail-picker="openProjectThumbnailPicker"
    :add-team-member="settings.addProjectTeamMember"
    :update-team-member="settings.updateProjectTeamMemberRole"
    :remove-team-member="settings.removeProjectTeamMember"
    :open-relocate-project="openRelocateProject"
    :open-migrate-project="openMigrateProject"
    @update:draft-title="settings.projectSettingsDraftTitle = $event"
    @update:draft-description="settings.projectSettingsDraftDescription = $event"
    @update:draft-due-date="settings.projectSettingsDraftDueDate = $event"
    @update:draft-status="settings.projectSettingsDraftStatus = $event"
    @update:team-add-user-id="settings.projectTeamAddUserId = $event"
    @update:team-add-role="settings.projectTeamAddRole = $event"
  />

  <ProjectStorageModal
    :show="settings.showProjectStorageModal"
    :project="settings.projectStorageTarget"
    :roots="settings.projectStorageRoots"
    :mode="settings.projectStorageMode"
    @close="settings.closeProjectStorage"
    @updated="settings.handleProjectStorageUpdated"
  />

  <ProjectSettingsModal
    :show="settings.showTrackerSettingsModal"
    scope="tracker"
    :is-mobile="isMobile"
    :project="selection.currentProject"
    :tracker="selection.currentTracker"
    :can-edit-project="settings.canEditTrackerSettings"
    :saving="settings.trackerSettingsSaving"
    :draft-settings="settings.trackerSettingsDraft"
    :delivery-logo-url="settings.trackerSettingsDeliveryLogoUrl"
    :app-identity="appIdentity"
    :delivery-logo-uploading="settings.trackerSettingsDeliveryLogoUploading"
    :close="settings.closeTrackerSettingsModal"
    :save="settings.saveTrackerSettings"
    :upload-delivery-logo="settings.uploadTrackerSettingsDeliveryLogo"
    :choose-delivery-logo-from-nas="settings.chooseTrackerSettingsDeliveryLogoFromNas"
    :remove-delivery-logo="settings.removeTrackerSettingsDeliveryLogo"
    :open-delivery-preview="settings.openTrackerSettingsDeliveryPreview"
    @update:draft-settings="updateTrackerSettings"
  />

  <DashboardSettingsModal
    :show="settings.showDashboardSettingsModal"
    :is-mobile="isMobile"
    :page="selection.currentPage"
    :saving="settings.dashboardSettingsSaving"
    :draft-title="settings.dashboardSettingsDraftTitle"
    :draft-description="settings.dashboardSettingsDraftDescription"
    :close="settings.closeDashboardSettingsModal"
    :save="settings.saveDashboardSettings"
    @update:draft-title="settings.dashboardSettingsDraftTitle = $event"
    @update:draft-description="settings.dashboardSettingsDraftDescription = $event"
  />

  <ProjectActionModals
    :show-create-project="actions.showCreateProject"
    :new-project-title="actions.newProjectTitle"
    :new-project-desc="actions.newProjectDesc"
    :new-project-due="actions.newProjectDue"
    :project-storage-roots="settings.projectStorageRoots"
    :new-project-storage-root="settings.newProjectStorageRoot"
    :new-project-storage-path="settings.newProjectStoragePath"
    :close-create-project="actions.closeCreateProjectModal"
    :create-project="actions.createProject"
    :show-create-page="actions.showCreatePage"
    :new-page-title="actions.newPageTitle"
    :new-page-desc="actions.newPageDesc"
    :close-create-page="actions.closeCreatePageModal"
    :create-page="actions.createPage"
    :show-create-tracker="actions.showCreateTracker"
    :new-tracker-name="actions.newTrackerName"
    :close-create-tracker="actions.closeCreateTrackerModal"
    :create-tracker="tracker.createTracker"
    :show-create-folder="actions.showCreateFolder"
    :new-folder-name="actions.newFolderName"
    :close-create-folder="actions.closeCreateFolderModal"
    :create-project-folder="actions.createProjectFolder"
    :show-rename-modal="actions.showRenameModal"
    :rename-target="actions.renameTarget"
    :rename-new-name="actions.renameNewName"
    :close-rename-modal="actions.closeRenameModalState"
    :confirm-rename="actions.confirmRename"
    :show-thumb-upload="thumbnails.showThumbUpload"
    :thumb-upload-mode="thumbnails.thumbUploadMode"
    :thumb-upload-preview="thumbnails.thumbUploadPreview"
    :thumb-upload-data="thumbnails.thumbUploadData"
    :close-thumb-upload="thumbnails.closeThumbUploadModal"
    :handle-thumb-upload="thumbnails.handleThumbUpload"
    :open-thumb-from-nas="thumbnails.openThumbFromNas"
    :confirm-thumb-upload="thumbnails.confirmThumbUpload"
    @update:new-project-title="actions.newProjectTitle = $event"
    @update:new-project-desc="actions.newProjectDesc = $event"
    @update:new-project-due="actions.newProjectDue = $event"
    @update:new-project-storage-root="settings.newProjectStorageRoot = $event"
    @update:new-project-storage-path="settings.newProjectStoragePath = $event"
    @update:new-page-title="actions.newPageTitle = $event"
    @update:new-page-desc="actions.newPageDesc = $event"
    @update:new-tracker-name="actions.newTrackerName = $event"
    @update:new-folder-name="actions.newFolderName = $event"
    @update:rename-new-name="actions.renameNewName = $event"
  />

  <ProjectFileImportModal
    :show="projectUpload.showUploadModal"
    :title="projectUpload.uploadModalTitle"
    :description="projectUpload.uploadModalDescription"
    :can-upload="projectUpload.canUploadNow"
    :upload-disabled-reason="projectUpload.uploadDisabledReason"
    :upload-error="projectUpload.uploadError"
    :upload-modal-drag-active="projectUpload.uploadModalDragActive"
    :upload-queue="projectUpload.uploadQueue"
    :upload-summary="projectUpload.uploadSummary"
    :upload-has-active="projectUpload.uploadHasActive"
    :upload-has-removable="projectUpload.uploadHasRemovable"
    :close-upload="projectUpload.closeUploadModal"
    :handle-modal-drag-enter="projectUpload.handleModalDragEnter"
    :handle-modal-drag-over="projectUpload.handleModalDragOver"
    :handle-modal-drag-leave="projectUpload.handleModalDragLeave"
    :handle-modal-drop="projectUpload.handleModalDrop"
    :handle-file-upload="projectUpload.handleFileUpload"
    :retry-upload="projectUpload.retryUpload"
    :cancel-upload="projectUpload.cancelUpload"
    :cancel-all-uploads="projectUpload.cancelAllUploads"
    :clear-completed-uploads="projectUpload.clearCompletedUploads"
  />

  <ProjectFileImportModal
    :show="sharedUpload.showUploadModal"
    :title="sharedUploadTitle"
    :description="sharedUploadDescription"
    :can-upload="sharedUpload.canUploadNow"
    :upload-disabled-reason="sharedUpload.uploadDisabledReason"
    :upload-error="sharedUpload.uploadError"
    :upload-modal-drag-active="sharedUpload.uploadModalDragActive"
    :upload-queue="sharedUpload.uploadQueue"
    :upload-summary="sharedUpload.uploadSummary"
    :upload-has-active="sharedUpload.uploadHasActive"
    :upload-has-removable="sharedUpload.uploadHasRemovable"
    :close-upload="sharedUpload.closeUploadModal"
    requires-uploader-name
    :uploader-name="sharedUpload.uploaderName"
    :uploader-name-error="sharedUpload.uploaderNameError"
    :set-uploader-name="sharedUpload.setUploaderName"
    :handle-modal-drag-enter="sharedUpload.handleModalDragEnter"
    :handle-modal-drag-over="sharedUpload.handleModalDragOver"
    :handle-modal-drag-leave="sharedUpload.handleModalDragLeave"
    :handle-modal-drop="sharedUpload.handleModalDrop"
    :handle-file-upload="sharedUpload.handleFileUpload"
    :retry-upload="sharedUpload.retryUpload"
    :cancel-upload="sharedUpload.cancelUpload"
    :cancel-all-uploads="sharedUpload.cancelAllUploads"
    :clear-completed-uploads="sharedUpload.clearCompletedUploads"
  />

  <FilePickerModal
    :show="picker.showFilePicker"
    :is-version-picker-mode="picker.isVersionPickerMode"
    :file-picker-title="picker.filePickerTitle"
    :picker-mode="picker.pickerMode"
    :show-tracker-import-mode-toggle="picker.showTrackerImportModeToggle"
    :tracker-import-mode="picker.trackerImportMode"
    :tracker-import-mode-tabs="picker.trackerImportModeTabs"
    :picker-path="picker.pickerPath"
    :picker-files="picker.pickerFiles"
    :picker-source="picker.pickerSource"
    :can-use-project-picker="picker.canUseProjectPicker"
    :picker-source-tabs="picker.pickerSourceTabs"
    :selected-version-picker-shot="picker.selectedVersionPickerShot"
    :selected-version-picker-current-media="picker.selectedVersionPickerCurrentMedia"
    :selected-version-picker-current-path="picker.selectedVersionPickerCurrentPath"
    :version-picker-current-info="picker.versionPickerCurrentInfo"
    :version-picker-shots="picker.versionPickerShots"
    :version-picker-target-shot-id="picker.versionPickerTargetShotId"
    :version-picker-file-search="picker.versionPickerFileSearch"
    :version-picker-notes="picker.versionPickerNotes"
    :version-picker-browser-items="picker.versionPickerBrowserItems"
    :version-picker-selected-candidate-path="picker.versionPickerSelectedCandidatePath"
    :can-load-more-version-picker-candidates="picker.canLoadMoreVersionPickerCandidates"
    :remaining-version-picker-candidate-count="picker.remainingVersionPickerCandidateCount"
    :version-picker-footer-text="picker.versionPickerFooterText"
    :can-apply-version-picker-selection="picker.canApplyVersionPickerSelection"
    :version-picker-apply-busy="picker.versionPickerApplyBusy"
    :selected-shot-import-count="picker.selectedShotImportCount"
    :can-apply-shot-import-selection="picker.canApplyShotImportSelection"
    :shot-import-apply-busy="picker.shotImportApplyBusy"
    :shot-import-apply-label="picker.shotImportApplyLabel"
    :selected-project-link-count="picker.selectedProjectLinkCount"
    :can-apply-project-link-selection="picker.canApplyProjectLinkSelection"
    :project-link-apply-busy="picker.projectLinkApplyBusy"
    :project-link-apply-label="picker.projectLinkApplyLabel"
    :close-file-picker="picker.closeFilePicker"
    :get-thumbnail-url="getThumbnailUrl"
    :get-media-duration-label="picker.getMediaDurationLabel"
    :get-shot-version-count="picker.getShotVersionCount"
    :get-picker-item-media="picker.getPickerItemMedia"
    :select-version-picker-shot="picker.selectVersionPickerShot"
    :set-version-picker-file-search="picker.setVersionPickerFileSearch"
    :set-version-picker-notes="picker.setVersionPickerNotes"
    :set-picker-source="picker.setPickerSource"
    :picker-go-up="picker.pickerGoUp"
    :picker-select="picker.pickerSelect"
    :set-tracker-import-mode="picker.setTrackerImportMode"
    :load-more-version-picker-candidates="picker.loadMoreVersionPickerCandidates"
    :is-picker-selected="picker.isPickerSelected"
    :import-folder="picker.importFolder"
    :apply-shot-import-selection="picker.applyShotImportSelection"
    :link-folder-to-project="picker.linkFolderToProject"
    :apply-project-link-selection="picker.applyProjectLinkSelection"
    :apply-version-picker-selection="picker.applyVersionPickerSelection"
    :upload-comment-files="picker.uploadCommentFiles"
  />
</template>

<script setup>
import { computed, proxyRefs } from 'vue'

import { useAppChromeStore } from '../../ownership/appChrome'
import { useAppIdentityStore } from '../../ownership/appIdentity'
import { useFileBrowserStore } from '../../ownership/fileBrowser'
import { useProjectSettingsStore } from '../../ownership/projectSettings'
import { useProjectTrackerSelectionStore } from '../../ownership/projectTrackerSelection'
import { useProjectWorkspaceStore } from '../../ownership/projectWorkspace'
import { useSessionAuthStore } from '../../ownership/sessionAuth'
import { useShareAccessContext } from '../../ownership/shareAccessContext'
import { useTrackerStore } from '../../ownership/tracker'
import { useViewerStore } from '../../ownership/viewer'
import { normalizeTrackerSettings } from '../../utils/trackerSettings'
import DashboardSettingsModal from './DashboardSettingsModal.vue'
import FilePickerModal from './FilePickerModalView.vue'
import ProjectActionModals from './ProjectActionModals.vue'
import ProjectFileImportModal from './ProjectFileImportModal.vue'
import ProjectSettingsModal from './ProjectSettingsModal.vue'
import ProjectStorageModal from './ProjectStorageModal.vue'

const fileBrowserStore = useFileBrowserStore()
const { isMobile } = useAppChromeStore()
const { identity: appIdentity } = useAppIdentityStore()
const actions = proxyRefs(useProjectWorkspaceStore())
const projectUpload = proxyRefs(fileBrowserStore.uploads.project)
const sharedUpload = proxyRefs(fileBrowserStore.uploads.shared)
const picker = proxyRefs(fileBrowserStore.picker)
const thumbnails = proxyRefs(fileBrowserStore.thumbnails)
const tracker = proxyRefs(useTrackerStore())
const settings = proxyRefs({ ...useProjectSettingsStore() })
const selection = proxyRefs(useProjectTrackerSelectionStore())
const session = proxyRefs(useSessionAuthStore())
const { sharedItemType, shareRequestFiles } = useShareAccessContext()
const { getThumbnailUrl } = useViewerStore().media.core

const sharedUploadTitle = computed(() => {
  if (shareRequestFiles.value) return 'Send Files'
  return sharedItemType.value === 'page' ? 'Upload Files to Vue Dashboard' : 'Upload Files to Shared Folder'
})
const sharedUploadDescription = computed(() => {
  if (shareRequestFiles.value) return 'Choose files or a folder to send. Your name is stored with the upload for identification.'
  return sharedItemType.value === 'page'
    ? 'Upload files into this dashboard inbox. Your name is stored with the upload for identification.'
    : 'Upload files or folders directly into this shared folder. Your name is stored with the upload for identification.'
})

function openProjectThumbnailPicker() {
  thumbnails.editProjectThumb(settings.activeProjectSettingsTarget)
}

function openRelocateProject() {
  settings.openProjectStorage(settings.activeProjectSettingsTarget, 'relocate')
}

function openMigrateProject() {
  settings.openProjectStorage(settings.activeProjectSettingsTarget, 'migrate')
}

function updateTrackerSettings(value) {
  settings.trackerSettingsDraft = normalizeTrackerSettings(value, { preserveDeliveryMessage: true })
}
</script>
