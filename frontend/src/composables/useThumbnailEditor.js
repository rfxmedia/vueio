import { ref } from 'vue'

import api, { getApiErrorMessage } from '../lib/api'
import { notify } from '../utils/toasts'

export function useThumbnailEditor({
  currentProject,
  currentPath,
  projectSettingsTarget,
  getThumbnailUrl,
  getProjectFolderThumbnailUrl,
  bumpProjectHeaderThumbnailRefresh,
  loadProjects,
  refreshProjectContents,
  loadFiles,
  openThumbnailPicker,
}) {
  const showThumbUpload = ref(null)
  const thumbUploadMode = ref('browser-folder')
  const thumbUploadPreview = ref(null)
  const thumbUploadData = ref(null)
  const thumbUploadTarget = ref(null)

  function closeThumbUploadModal() {
    showThumbUpload.value = null
    thumbUploadPreview.value = null
    thumbUploadData.value = null
    thumbUploadTarget.value = null
  }

  function openBrowserFolderThumb(item) {
    thumbUploadMode.value = 'browser-folder'
    thumbUploadTarget.value = item
    thumbUploadPreview.value = null
    thumbUploadData.value = null
    showThumbUpload.value = true
  }

  function editProjectThumb(project) {
    if (!project) return
    thumbUploadMode.value = 'project'
    thumbUploadTarget.value = project
    thumbUploadPreview.value = null
    thumbUploadData.value = null
    showThumbUpload.value = true
  }

  function openProjectFolderThumb(item) {
    if (!item?.path) return
    thumbUploadMode.value = 'project-folder'
    thumbUploadTarget.value = item
    thumbUploadPreview.value = item.custom_thumbnail && currentProject.value?.id
      ? getProjectFolderThumbnailUrl(item.path)
      : null
    thumbUploadData.value = null
    showThumbUpload.value = true
  }

  function handleThumbUpload(event) {
    const file = event.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (loadEvent) => {
      thumbUploadPreview.value = loadEvent.target.result
      thumbUploadData.value = { type: 'upload', file, name: file.name }
    }
    reader.readAsDataURL(file)
  }

  function selectThumbnailSource(item) {
    thumbUploadPreview.value = getThumbnailUrl(item)
    thumbUploadData.value = {
      type: 'nas',
      path: item.path,
      name: item.name,
      mediaType: item.type,
    }
    showThumbUpload.value = true
  }

  function openThumbFromNas() {
    openThumbnailPicker()
    showThumbUpload.value = false
  }

  async function confirmThumbUpload() {
    if (!thumbUploadData.value || !thumbUploadTarget.value) return

    try {
      if (thumbUploadMode.value === 'project' || thumbUploadMode.value === 'project-folder') {
        const entityType = thumbUploadMode.value === 'project' ? 'project' : 'folder'
        const entityPath = entityType === 'folder' ? thumbUploadTarget.value.path : null
        const targetProjectId = entityType === 'project'
          ? thumbUploadTarget.value.id
          : currentProject.value?.id
        if (!targetProjectId) throw new Error('No project selected for thumbnail update')

        if (thumbUploadData.value.type === 'upload') {
          const formData = new FormData()
          formData.append('file', thumbUploadData.value.file)
          formData.append('entity_type', entityType)
          if (entityPath) formData.append('path', entityPath)
          await api.post(`/api/horizons/projects/${targetProjectId}/thumbnail/upload`, formData)
        } else if (thumbUploadData.value.type === 'nas') {
          await api.post(`/api/horizons/projects/${targetProjectId}/thumbnail/select`, {
            entity_type: entityType,
            path: entityPath,
            source_path: thumbUploadData.value.path,
          })
        }

        if (entityType === 'project') {
          if (thumbUploadTarget.value?.thumbnail_path !== undefined) {
            thumbUploadTarget.value.thumbnail_path = '__entity_thumbnail__'
          }
          if (projectSettingsTarget.value?.id === thumbUploadTarget.value.id) {
            projectSettingsTarget.value.thumbnail_path = '__entity_thumbnail__'
          }
          if (currentProject.value?.id === thumbUploadTarget.value.id) {
            currentProject.value.thumbnail_path = '__entity_thumbnail__'
            bumpProjectHeaderThumbnailRefresh()
          }
          await loadProjects()
        } else {
          await refreshProjectContents()
        }
      } else {
        if (thumbUploadData.value.type === 'upload') {
          const formData = new FormData()
          formData.append('file', thumbUploadData.value.file)
          formData.append('target_path', thumbUploadTarget.value.path)
          await api.post('/api/folder-thumbnail/upload', formData)
        } else if (thumbUploadData.value.type === 'nas') {
          await api.post('/api/folder-thumbnail/set', null, {
            params: {
              target_path: thumbUploadTarget.value.path,
              source_path: thumbUploadData.value.path,
            },
          })
        }
        await loadFiles(currentPath.value)
      }

      closeThumbUploadModal()
    } catch (error) {
      notify(`Failed to set thumbnail: ${getApiErrorMessage(error)}`)
    }
  }

  return {
    showThumbUpload,
    thumbUploadMode,
    thumbUploadPreview,
    thumbUploadData,
    thumbUploadTarget,
    closeThumbUploadModal,
    openBrowserFolderThumb,
    editProjectThumb,
    openProjectFolderThumb,
    handleThumbUpload,
    selectThumbnailSource,
    openThumbFromNas,
    confirmThumbUpload,
  }
}
