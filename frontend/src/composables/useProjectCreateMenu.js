import { computed } from 'vue'

import { useFileBrowserStore } from '../ownership/fileBrowser'
import { useProjectTrackerSelectionStore } from '../ownership/projectTrackerSelection'
import { useProjectWorkspaceStore } from '../ownership/projectWorkspace'
import { useSessionAuthStore } from '../ownership/sessionAuth'
import { useShareAccessContext } from '../ownership/shareAccessContext'

/**
 * The project header and folder-canvas context menu are two entry points for
 * the same permission-gated creation actions. Keep the action definitions here
 * so neither surface can expose a capability the other one hides.
 */
export function useProjectCreateMenu() {
  const { currentProject } = useProjectTrackerSelectionStore()
  const { currentUser, canEditProject: canEditProjectPermission } = useSessionAuthStore()
  const { shareMode } = useShareAccessContext()
  const workspace = useProjectWorkspaceStore()
  const fileBrowser = useFileBrowserStore()

  const canEditProject = computed(() => (
    canEditProjectPermission.value && !currentProject.value?.storage_read_only
  ))
  const canShowProjectCreateMenu = computed(() => (
    !shareMode.value
    && (
      canEditProject.value
      || (
        !canEditProject.value
        && currentUser.value?.role === 'artist'
        && Boolean(workspace.projectPath.value)
      )
    )
  ))

  function closeMenu() {
    workspace.closeNewMenu()
  }

  function openUpload() {
    fileBrowser.uploads.project.openUpload()
    closeMenu()
  }

  function openLinkPicker() {
    fileBrowser.picker.openProjectLinkPicker()
    closeMenu()
  }

  const projectCreateMenuActions = computed(() => {
    const isArtist = currentUser.value?.role === 'artist'
    const canUpload = fileBrowser.uploads.project.canUploadToProject.value
    const uploadDisabledReason = fileBrowser.uploads.project.projectUploadDisabledReason.value

    return [
      { label: 'Vue Dashboard', icon: '#icon-file', show: !isArtist, run: workspace.openProjectCreatePage },
      { label: 'Vue Tracker', icon: '#icon-project', show: !isArtist, run: workspace.openProjectCreateTracker },
      { label: 'Folder', icon: '#icon-folder', run: workspace.openProjectCreateFolderFromMenu },
      { divider: true },
      {
        label: 'Upload Files',
        icon: '#icon-upload',
        disabled: !canUpload,
        title: uploadDisabledReason || '',
        run: openUpload,
      },
      { label: 'Link from storage', icon: '#icon-link', show: !isArtist, run: openLinkPicker },
    ]
  })

  return {
    canShowProjectCreateMenu,
    projectCreateMenuActions,
  }
}
