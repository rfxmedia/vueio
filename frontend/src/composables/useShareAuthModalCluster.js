import { computed, ref } from 'vue'
import api, { getApiErrorMessage } from '../lib/api'
import { notify } from '../utils/toasts'

function getDefaultExpirationDate() {
  const date = new Date()
  date.setDate(date.getDate() + 30)
  return date.toISOString().split('T')[0]
}

function createDefaultShareForm() {
  return {
    expiresDate: getDefaultExpirationDate(),
    password: '',
    allowDownload: false,
    allowUpload: false,
    requestFiles: false,
  }
}

function createDefaultShareEditForm() {
  return {
    expiresDate: '',
    password: '',
    allowDownload: false,
    allowUpload: false,
  }
}

const PROJECT_SHARE_TYPES = new Set(['project', 'tracker', 'page', 'project-file', 'project-folder'])

export function useShareAuthModalCluster({
  route,
  activeModule,
  currentPath,
  currentProject,
  currentTracker,
  currentPage,
  projectPath,
  currentMedia,
  isAdmin,
  shareMode,
  sharePasswordRequired,
  shareAccessError,
  pendingShareId,
  pendingShareType,
  loadSharedContent,
  loadSharedProjectContent,
  handleError,
}) {
  const shareModal = ref(null)
  const projectShareUrl = ref('')
  const showShareCreate = ref(false)
  const shareCreateTarget = ref(null)
  const shareCreateType = ref('file')
  const shareCreateForm = ref(createDefaultShareForm())
  const sharePasswordInput = ref('')
  const shareCreateTab = ref('create')
  const projectShares = ref([])
  const projectSharesLoading = ref(false)
  const projectSharesError = ref('')
  const projectShareBusyId = ref('')
  const editingProjectShare = ref(null)
  const projectShareEditForm = ref(createDefaultShareEditForm())
  const lastCreatedWasFileRequest = ref(false)

  const shareUrl = computed(() => {
    if (!shareModal.value || shareModal.value === 'project') return ''
    return `${window.location.origin}/s/${shareModal.value}`
  })

  const shareCreateProjectId = computed(() => getShareProjectId(shareCreateTarget.value, shareCreateType.value))
  const canManageProjectShares = computed(() => Boolean(shareCreateProjectId.value))

  function getShareProjectId(target, type) {
    if (!PROJECT_SHARE_TYPES.has(type)) return ''
    return target?.id || currentProject.value?.id || ''
  }

  function apiErrorMessage(error, fallback) {
    return getApiErrorMessage(error, fallback)
  }

  function setSharePasswordInput(value) {
    sharePasswordInput.value = value
  }

  function getPendingShareSubpath() {
    const pathParam = route?.params?.path
    return Array.isArray(pathParam) ? pathParam.join('/') : (pathParam || '')
  }

  async function submitSharePassword() {
    if (!sharePasswordInput.value || !pendingShareId.value) return
    shareAccessError.value = ''
    const subPath = getPendingShareSubpath()
    if (pendingShareType.value === 'project-file') {
      await loadSharedProjectContent(pendingShareId.value, subPath, sharePasswordInput.value)
      if (!sharePasswordRequired.value) sharePasswordInput.value = ''
      return
    }
    await loadSharedContent(pendingShareId.value, pendingShareType.value, sharePasswordInput.value, subPath)
    if (!sharePasswordRequired.value) sharePasswordInput.value = ''
  }

  function openShareCreate(target, type) {
    shareCreateTarget.value = target
    shareCreateType.value = type
    shareCreateForm.value = createDefaultShareForm()
    shareCreateTab.value = 'create'
    projectShares.value = []
    projectSharesError.value = ''
    editingProjectShare.value = null
    showShareCreate.value = true
    if (getShareProjectId(target, type)) {
      loadProjectShares()
    }
  }

  function shareFile(item) {
    const isFolder = item?.type === 'folder' || item?.is_folder === true
    const projectId = item?._projectId || currentProject.value?.id
    const isProjectMedia = Boolean(
      projectId &&
      !isFolder &&
      item?.path &&
      (
        item?._projectFile ||
        item?._projectId ||
        item?.media_asset_id ||
        item?.horizons_media_asset_id ||
        item?.version_id ||
        item?.horizons_shot_version_id ||
        item?.media_entity_type === 'media_asset' ||
        item?.media_entity_type === 'shot_version'
      )
    )

    if (isProjectMedia) {
      openShareCreate({
        ...item,
        id: projectId,
        path: item.path,
        name: item.name || item.path.split('/').pop() || 'Media',
        is_folder: false,
      }, 'project-file')
      return
    }

    openShareCreate(item, isFolder ? 'folder' : 'file')
  }

  function shareProjectFromList(project) {
    openShareCreate(project, 'project')
  }

  function shareCurrentPage() {
    if (currentProject.value) {
      if (currentPage?.value) {
        openShareCreate({
          id: currentProject.value.id,
          page_id: currentPage.value.id,
          title: `${currentProject.value.title} / ${currentPage.value.title}`,
        }, 'page')
        return
      }

      if (currentTracker.value) {
        openShareCreate({
          id: currentProject.value.id,
          tracker_id: currentTracker.value.id,
          tracker_name: currentTracker.value.name,
          title: `${currentProject.value.title} / ${currentTracker.value.name}`,
        }, 'tracker')
        return
      }

      if (projectPath.value) {
        openShareCreate({
          id: currentProject.value.id,
          path: projectPath.value,
          name: projectPath.value.split('/').pop() || currentProject.value.title,
          is_folder: true,
        }, 'project-folder')
        return
      }

      openShareCreate(currentProject.value, 'project')
      return
    }

    if (activeModule.value === 'files') {
      openShareCreate({
        path: currentPath.value || '',
        name: currentPath.value?.split('/').pop() || 'Root Folder',
      }, 'folder')
    }
  }

  function shareProject() {
    shareCurrentPage()
  }

  function shareProjectContent(item, isFolder = false) {
    if (!currentProject.value) return

    openShareCreate({
      id: currentProject.value.id,
      path: item.path,
      name: item.name,
      is_folder: isFolder,
      is_linked: item.is_linked || false,
    }, isFolder ? 'project-folder' : 'project-file')
  }

  function shareProjectPage(page) {
    if (!currentProject.value || !page?.id) return

    openShareCreate({
      id: currentProject.value.id,
      page_id: page.id,
      title: page.title || page.name || 'Page',
    }, 'page')
  }

  function canShareProjectItem(project) {
    return Boolean(project && (isAdmin.value || project.access_role === 'owner'))
  }

  const canShareFromNav = computed(() => {
    if (shareMode.value) return false
    if (currentMedia.value) return canShareProjectItem(currentProject.value)
    if (activeModule.value === 'files' && currentPath.value) return isAdmin.value
    if (currentProject.value) return canShareProjectItem(currentProject.value)
    return false
  })

  function shareFromNav() {
    if (currentMedia.value) shareFile(currentMedia.value)
    else if (currentPage.value) shareCurrentPage()
    else if (currentProject.value) shareProject()
    else if (activeModule.value === 'files') shareCurrentPage()
  }

  function cancelShareCreate() {
    showShareCreate.value = false
    shareCreateTarget.value = null
    shareCreateTab.value = 'create'
    projectShares.value = []
    projectSharesError.value = ''
    editingProjectShare.value = null
  }

  function closeShareModal() {
    shareModal.value = null
  }

  async function confirmShareCreate() {
    if (!shareCreateTarget.value) {
      notify('No target selected for sharing')
      return
    }

    const expiresDate = shareCreateForm.value.expiresDate || getDefaultExpirationDate()

    try {
      const basePayload = {
        expires_at: new Date(expiresDate + 'T23:59:59').getTime() / 1000,
        password: shareCreateForm.value.password || '',
        allow_download: shareCreateForm.value.requestFiles ? false : shareCreateForm.value.allowDownload,
      }

      let response
      if (shareCreateType.value === 'project' || shareCreateType.value === 'tracker' || shareCreateType.value === 'page') {
        const payload = { ...basePayload }
        if (shareCreateType.value === 'tracker' && shareCreateTarget.value.tracker_id) {
          payload.tracker_id = shareCreateTarget.value.tracker_id
        } else if (shareCreateType.value === 'tracker' && shareCreateTarget.value.tracker_name) {
          payload.tracker_name = shareCreateTarget.value.tracker_name
        }
        if (shareCreateType.value === 'page' && shareCreateTarget.value.page_id) {
          payload.page_id = shareCreateTarget.value.page_id
        }
        response = await api.post(`/api/projects/${shareCreateTarget.value.id}/share`, payload, {
          headers: { 'Content-Type': 'application/json' },
        })
        projectShareUrl.value = `${window.location.origin}${response.data.url}`
        shareModal.value = 'project'
      } else if (shareCreateType.value === 'project-file' || shareCreateType.value === 'project-folder') {
        const payload = {
          ...basePayload,
          path: shareCreateTarget.value.path,
          is_folder: shareCreateType.value === 'project-folder',
          allow_upload: shareCreateType.value === 'project-folder'
            ? (!!shareCreateForm.value.allowUpload || !!shareCreateForm.value.requestFiles)
            : false,
          request_files: shareCreateType.value === 'project-folder' && !!shareCreateForm.value.requestFiles,
        }
        response = await api.post(`/api/projects/${shareCreateTarget.value.id}/share-content`, payload, {
          headers: { 'Content-Type': 'application/json' },
        })
        projectShareUrl.value = `${window.location.origin}${response.data.url}`
        shareModal.value = 'project'
      } else {
        const targetPath = shareCreateTarget.value.path
        if (targetPath === undefined || targetPath === null) {
          notify('Invalid path for sharing')
          return
        }
        const payload = {
          ...basePayload,
          path: targetPath,
          allow_upload: shareCreateType.value === 'folder'
            ? (!!shareCreateForm.value.allowUpload || !!shareCreateForm.value.requestFiles)
            : false,
          request_files: shareCreateType.value === 'folder' && !!shareCreateForm.value.requestFiles,
        }
        response = await api.post('/api/share', payload, {
          headers: { 'Content-Type': 'application/json' },
        })
        shareModal.value = response.data.id
      }

      lastCreatedWasFileRequest.value = !!shareCreateForm.value.requestFiles
      showShareCreate.value = false
    } catch (error) {
      handleError('Failed to create share link', error)
    }
  }

  async function copyShareLink(url) {
    try {
      await navigator.clipboard.writeText(url || shareUrl.value)
      notify('Link copied!')
    } catch {
      notify('Copy failed')
    }
  }

  function setShareCreateTab(tab) {
    shareCreateTab.value = tab
    if (tab === 'shares' && canManageProjectShares.value && !projectShares.value.length && !projectSharesLoading.value) {
      loadProjectShares()
    }
  }

  async function loadProjectShares() {
    const projectId = shareCreateProjectId.value
    if (!projectId) return

    projectSharesLoading.value = true
    projectSharesError.value = ''
    try {
      const { data } = await api.get(`/api/projects/${projectId}/shares`, {
        params: { active_only: true, limit: 100 },
      })
      projectShares.value = data.shares || []
    } catch (error) {
      projectSharesError.value = apiErrorMessage(error, 'Failed to load active shares.')
    } finally {
      projectSharesLoading.value = false
    }
  }

  function buildProjectShareUrl(share) {
    if (!share?.id) return ''
    const baseUrl = window.location.origin
    if (share.share_type === 'project' || share.share_type === 'tracker' || share.share_type === 'page') {
      return `${baseUrl}/p/${share.id}`
    }
    if (share.share_type === 'project-file' || share.share_type === 'project-folder') {
      return `${baseUrl}/p/${share.id}/f`
    }
    return `${baseUrl}/s/${share.id}`
  }

  async function copyProjectShareLink(share) {
    try {
      await navigator.clipboard.writeText(buildProjectShareUrl(share))
      notify('Share link copied')
    } catch {
      notify('Copy failed')
    }
  }

  function openProjectShareEditor(share) {
    editingProjectShare.value = share
    projectShareEditForm.value = {
      expiresDate: share.expires_at ? new Date(share.expires_at * 1000).toISOString().split('T')[0] : '',
      password: '',
      allowDownload: !!share.allow_download,
      allowUpload: !!share.allow_upload,
    }
  }

  function closeProjectShareEditor() {
    editingProjectShare.value = null
    projectShareEditForm.value = createDefaultShareEditForm()
  }

  async function saveProjectShareEdit() {
    const share = editingProjectShare.value
    const projectId = shareCreateProjectId.value
    if (!share || !projectId) return

    projectShareBusyId.value = share.id
    try {
      await api.put(`/api/projects/${projectId}/shares/${share.id}`, {
        expires_at: projectShareEditForm.value.expiresDate
          ? new Date(`${projectShareEditForm.value.expiresDate}T23:59:59`).getTime() / 1000
          : 0,
        password: projectShareEditForm.value.password,
        allow_download: projectShareEditForm.value.allowDownload,
        allow_upload: projectShareEditForm.value.allowUpload,
      })
      closeProjectShareEditor()
      await loadProjectShares()
    } catch (error) {
      notify(`Failed to update share: ${apiErrorMessage(error, 'Unknown error')}`)
    } finally {
      projectShareBusyId.value = ''
    }
  }

  async function revokeProjectShare(share) {
    const projectId = shareCreateProjectId.value
    if (!share || !projectId) return
    const label = share.target_name || share.path || share.id
    if (!confirm(`Revoke share link for "${label}"?`)) return

    projectShareBusyId.value = share.id
    try {
      await api.put(`/api/projects/${projectId}/shares/${share.id}`, { is_active: false })
      if (editingProjectShare.value?.id === share.id) closeProjectShareEditor()
      await loadProjectShares()
    } catch (error) {
      notify(`Failed to revoke share: ${apiErrorMessage(error, 'Unknown error')}`)
    } finally {
      projectShareBusyId.value = ''
    }
  }

  return {
    showShareCreate,
    shareCreateTarget,
    shareCreateType,
    shareCreateForm,
    shareCreateTab,
    canManageProjectShares,
    projectShares,
    projectSharesLoading,
    projectSharesError,
    projectShareBusyId,
    editingProjectShare,
    projectShareEditForm,
    lastCreatedWasFileRequest,
    setShareCreateTab,
    loadProjectShares,
    copyProjectShareLink,
    openProjectShareEditor,
    closeProjectShareEditor,
    saveProjectShareEdit,
    revokeProjectShare,
    cancelShareCreate,
    confirmShareCreate,
    shareModal,
    projectShareUrl,
    shareUrl,
    closeShareModal,
    copyShareLink,
    shareFile,
    shareProjectFromList,
    shareCurrentPage,
    shareProject,
    shareProjectContent,
    shareProjectPage,
    canShareProjectItem,
    canShareFromNav,
    shareFromNav,
    sharePasswordInput,
    setSharePasswordInput,
    submitSharePassword,
  }
}
