import { ref } from 'vue'
import api, { getApiErrorMessage } from '../lib/api'

import { getParentBrowserPath } from '../lib/browserSurface'
import { notify } from '../utils/toasts'

export function useProjectContentInteractions({
  currentProject,
  projectPath,
  refreshProjectContents,
  handleProjectExternalDragOver,
  handleProjectExternalDragLeave,
  handleProjectExternalDrop,
}) {
  const projectDragItem = ref(null)
  const projectDropTarget = ref(null)
  const contentMenuOpen = ref(null)
  const showRenameModal = ref(false)
  const renameTarget = ref(null)
  const renameNewName = ref('')

  function isExternalFileDrag(event) {
    const types = Array.from(event?.dataTransfer?.types || [])
    return types.includes('Files') || (event?.dataTransfer?.files?.length || 0) > 0
  }

  function getParentProjectPath() {
    return getParentBrowserPath(projectPath.value)
  }

  function resetProjectDragState() {
    projectDragItem.value = null
    projectDropTarget.value = null
  }

  function toggleContentMenu(path) {
    contentMenuOpen.value = contentMenuOpen.value === path ? null : path
  }

  function closeContentMenu() {
    contentMenuOpen.value = null
  }

  function startProjectDrag(event, item) {
    projectDragItem.value = {
      path: item.path,
      name: item.name,
      type: item.type,
      is_linked: item.is_linked || false,
    }
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', item.path)
  }

  function endProjectDrag() {
    resetProjectDragState()
  }

  function onProjectDragOver(event, folder) {
    if (projectDragItem.value) {
      if (projectDragItem.value.path === folder.path) return
      if (folder.path.startsWith(projectDragItem.value.path + '/')) return
      projectDropTarget.value = folder.path
      event.dataTransfer.dropEffect = 'move'
      return
    }
    if (isExternalFileDrag(event)) {
      handleProjectExternalDragOver?.(event, folder.path)
    }
  }

  function onProjectDragLeave(event) {
    if (projectDragItem.value) {
      projectDropTarget.value = null
      return
    }
    handleProjectExternalDragLeave?.(event)
  }

  function onProjectDragOverParent(event) {
    if (projectDragItem.value) {
      if (!projectPath.value) return
      projectDropTarget.value = '__parent__'
      event.dataTransfer.dropEffect = 'move'
      return
    }
    if (isExternalFileDrag(event)) {
      handleProjectExternalDragOver?.(event, getParentProjectPath())
    }
  }

  async function onProjectDropToParent(event) {
    if (projectDragItem.value) {
      if (!currentProject.value || !projectPath.value) return
      try {
        await api.put(
          `/api/projects/${currentProject.value.id}/files/move`,
          { target_folder: getParentProjectPath() },
          { params: { path: projectDragItem.value.path } }
        )
        await refreshProjectContents()
      } catch (error) {
        notify('Failed to move: ' + (getApiErrorMessage(error)))
      } finally {
        resetProjectDragState()
      }
      return
    }

    if (isExternalFileDrag(event)) {
      await handleProjectExternalDrop?.(event, getParentProjectPath())
    }
  }

  async function onProjectDrop(event, targetFolder) {
    if (projectDragItem.value) {
      if (!currentProject.value) return
      if (projectDragItem.value.path === targetFolder.path) return
      try {
        await api.put(
          `/api/projects/${currentProject.value.id}/files/move`,
          { target_folder: targetFolder.path },
          { params: { path: projectDragItem.value.path } }
        )
        await refreshProjectContents()
      } catch (error) {
        notify('Failed to move: ' + (getApiErrorMessage(error)))
      } finally {
        resetProjectDragState()
      }
      return
    }

    if (isExternalFileDrag(event)) {
      await handleProjectExternalDrop?.(event, targetFolder?.path || '')
    }
  }

  function closeRenameModalState() {
    showRenameModal.value = false
    renameTarget.value = null
  }

  function startRenameFile(item) {
    renameTarget.value = { ...item, type: 'file' }
    renameNewName.value = item.name.replace(/\.[^.]+$/, '')
    showRenameModal.value = true
  }

  function startRenameFolder(item) {
    renameTarget.value = { ...item, type: 'folder' }
    renameNewName.value = item.name
    showRenameModal.value = true
  }

  function startRenameTracker(item) {
    renameTarget.value = { ...item, type: 'tracker' }
    renameNewName.value = item.name
    showRenameModal.value = true
  }

  function startRenamePage(item) {
    renameTarget.value = { ...item, type: 'page' }
    renameNewName.value = item.name || item.title || ''
    showRenameModal.value = true
  }

  async function confirmRename() {
    if (!renameTarget.value || !renameNewName.value.trim() || !currentProject.value) return

    try {
      if (renameTarget.value.type === 'tracker') {
        await api.put(
          `/api/projects/${currentProject.value.id}/trackers/${encodeURIComponent(renameTarget.value.id || renameTarget.value.slug || renameTarget.value.name)}`,
          { name: renameNewName.value.trim() }
        )
      } else if (renameTarget.value.type === 'page') {
        await api.put(
          `/api/projects/${currentProject.value.id}/pages/${encodeURIComponent(renameTarget.value.id || renameTarget.value.slug || renameTarget.value.path)}`,
          { title: renameNewName.value.trim() }
        )
      } else {
        await api.put(
          `/api/projects/${currentProject.value.id}/files/rename`,
          { new_name: renameNewName.value.trim() },
          { params: { path: renameTarget.value.path } }
        )
      }
      closeRenameModalState()
      renameNewName.value = ''
      await refreshProjectContents()
    } catch (error) {
      notify('Failed to rename: ' + (getApiErrorMessage(error)))
    }
  }

  return {
    projectDragItem,
    projectDropTarget,
    contentMenuOpen,
    showRenameModal,
    renameTarget,
    renameNewName,
    toggleContentMenu,
    closeContentMenu,
    startProjectDrag,
    endProjectDrag,
    onProjectDragOver,
    onProjectDragLeave,
    onProjectDragOverParent,
    onProjectDropToParent,
    onProjectDrop,
    closeRenameModalState,
    startRenameFile,
    startRenameFolder,
    startRenameTracker,
    startRenamePage,
    confirmRename,
  }
}
