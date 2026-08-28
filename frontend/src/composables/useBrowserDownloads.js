import api, { buildShareCredentialQuery, getApiErrorDetail } from '../lib/api'
import { computed, ref } from 'vue'

import { buildBrowserDownloadUrl } from '../lib/browserDownloadUrls'
import { normalizeMediaEntity } from '../lib/mediaEntity'
import { zipNameFromPath } from '../utils/filenames'
import { notify } from '../utils/toasts'

function hasExtension(name) {
  return typeof name === 'string' && /\.[A-Za-z0-9]{2,8}$/.test(name.trim())
}

export function useBrowserDownloads({
  shareMode,
  pendingShareId,
  shareAllowDownload,
  sharedItemType,
  shareRoot,
  currentPath,
  files,
  currentProject,
  projectPath,
  projectFolderItems,
  projectFileItems,
  isProjectScopedPath,
  getShareCredential,
}) {
  const downloadAllFilesBusy = ref(false)
  const downloadAllProjectFolderBusy = ref(false)

  async function getPackageErrorMessage(error) {
    const detail = getApiErrorDetail(error)
    if (detail) return typeof detail === 'string' ? detail : detail.message || 'Unknown error'
    const data = error?.response?.data
    if (typeof Blob !== 'undefined' && data instanceof Blob) {
      try {
        const text = await data.text()
        if (text) {
          try {
            const parsed = JSON.parse(text)
            return parsed?.detail || text
          } catch (_jsonError) {
            return text
          }
        }
      } catch (_blobError) {
        // Fall through to generic error handling.
      }
    }
    if (error?.response?.status === 413) {
      return 'This package is too large to build inline. Download files individually, request a smaller folder, or use background packaging when available.'
    }
    return error?.message || 'Unknown error'
  }
  function buildDownloadUrl(item, projectId = null) {
    const media = normalizeMediaEntity(item)
    const resolvedProjectId = projectId || media?._projectId || (isProjectScopedPath(media?.path || '') ? currentProject.value?.id : null)
    return buildBrowserDownloadUrl({
      item: media,
      projectId: resolvedProjectId,
      shareContext: shareMode.value && pendingShareId.value
        ? { shareId: pendingShareId.value, credential: getShareCredential() }
        : null,
    })
  }

  function triggerBrowserDownload(url, fileName) {
    const link = document.createElement('a')
    link.href = url
    if (fileName) link.download = fileName
    document.body.appendChild(link)
    link.click()
    link.remove()
  }

  function getDownloadFilename(item) {
    const filePath = item?.path || ''
    const pathBase = filePath.split('/').pop() || 'download'
    const name = (item?.name || '').toString().trim()
    return hasExtension(name) ? name : pathBase
  }

  function triggerBlobDownload(blob, fileName) {
    const url = window.URL.createObjectURL(blob)
    triggerBrowserDownload(url, fileName)
    setTimeout(() => window.URL.revokeObjectURL(url), 10_000)
  }

  async function downloadZip(paths, zipName) {
    const url = (shareMode.value && pendingShareId.value)
      ? `/api/projects/shared/${pendingShareId.value}/download-zip${buildShareCredentialQuery({}, getShareCredential())}`
      : '/api/download-zip'
    const { data } = await api.post(url, { paths, filename: zipName }, { responseType: 'blob' })
    triggerBlobDownload(data, zipName)
  }

  function downloadFile(item) {
    const projectId = item?._projectId || (item?._projectFile ? currentProject.value?.id : null)
    triggerBrowserDownload(buildDownloadUrl(item, projectId), getDownloadFilename(item))
  }

  function downloadProjectItem(item) {
    if (!item) return
    const downloadPath = item.is_linked && !shareMode.value
      ? (item.source_path || item.full_path || item.path)
      : item.path
    downloadFile({
      ...item,
      path: downloadPath,
      _projectId: currentProject.value?.id || null,
      _projectFile: !item.is_linked,
    })
  }

  async function postProjectFolderZip(url, path, zipName) {
    const { data } = await api.post(url, { path, filename: zipName }, { responseType: 'blob' })
    triggerBlobDownload(data, zipName)
  }

  const canDownloadAllFiles = computed(() => {
    if (!files.value.length) return false
    if (shareMode.value) return shareAllowDownload.value && !!currentPath.value
    return !!currentPath.value
  })

  async function downloadAllFilesInCurrentFolder() {
    const targetPath = currentPath.value || (shareMode.value ? shareRoot.value : '')
    if (!targetPath) {
      notify('Open a folder first, then use Download All. Root-level storage downloads are intentionally disabled.')
      return
    }
    if (downloadAllFilesBusy.value) return

    downloadAllFilesBusy.value = true
    try {
      await downloadZip([targetPath], zipNameFromPath(targetPath, 'files'))
    } catch (error) {
      console.error('Failed to download folder package')
      notify('Download All failed: ' + await getPackageErrorMessage(error))
    } finally {
      downloadAllFilesBusy.value = false
    }
  }

  const canDownloadAllProjectFolder = computed(() => {
    if (!currentProject.value) return false
    if (shareMode.value && sharedItemType.value === 'folder') {
      return shareAllowDownload.value && !!shareRoot.value
    }
    if (!projectPath.value) return false
    if (shareMode.value && !shareAllowDownload.value) return false
    return projectFolderItems.value.length > 0 || projectFileItems.value.length > 0
  })

  function canDownloadProjectFolderItem(item) {
    if (!item || item.type !== 'folder' || !currentProject.value) return false
    if (shareMode.value) return shareAllowDownload.value
    return true
  }

  async function downloadProjectFolder(targetPath, fallbackName) {
    const projectId = currentProject.value?.id
    if (!projectId || !targetPath) {
      notify('Open a project folder first, then use Download All.')
      return
    }
    if (downloadAllProjectFolderBusy.value) return

    const zipName = zipNameFromPath(targetPath, fallbackName || 'project')
    downloadAllProjectFolderBusy.value = true
    try {
      if (shareMode.value && pendingShareId.value) {
        await downloadZip([targetPath], zipName)
        return
      }

      try {
        await postProjectFolderZip(`/api/horizons/projects/${projectId}/folder-zip`, targetPath, zipName)
      } catch (error) {
        if (![404, 409].includes(error?.response?.status)) throw error
        await postProjectFolderZip(`/api/projects/${projectId}/folder-zip`, targetPath, zipName)
      }
    } catch (error) {
      console.error('Failed to download project folder package')
      notify('Download All failed: ' + await getPackageErrorMessage(error))
    } finally {
      downloadAllProjectFolderBusy.value = false
    }
  }

  async function downloadCurrentProjectFolder() {
    const targetPath = shareMode.value && sharedItemType.value === 'folder'
      ? shareRoot.value
      : projectPath.value
    await downloadProjectFolder(targetPath, currentProject.value?.title || 'project')
  }

  return {
    getPackageErrorMessage,
    buildDownloadUrl,
    triggerBrowserDownload,
    getDownloadFilename,
    triggerBlobDownload,
    downloadZip,
    downloadFile,
    downloadProjectItem,
    canDownloadAllFiles,
    downloadAllFilesBusy,
    downloadAllFilesInCurrentFolder,
    canDownloadAllProjectFolder,
    canDownloadProjectFolderItem,
    downloadAllProjectFolderBusy,
    downloadProjectFolder,
    downloadCurrentProjectFolder,
  }
}
