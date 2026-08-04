import { getMediaKind } from './mediaEntity'

const DEFAULT_PROJECT_FOLDER_CONTEXT = Object.freeze({
  mode: 'project',
  is_linked_folder: false,
  can_upload: true,
  upload_disabled_reason: '',
})

export function cloneProjectFolderContext() {
  return { ...DEFAULT_PROJECT_FOLDER_CONTEXT }
}

export function formatCountLabel(count) {
  if (count === null || count === undefined) return ''
  return `${count} item${count !== 1 ? 's' : ''}`
}

export function getParentBrowserPath(path = '') {
  if (!path) return ''
  const parts = path.split('/')
  parts.pop()
  return parts.join('/')
}

export function openBrowserMediaItem(item, {
  openImage,
  openPdf,
  openVideo,
  buildFileData = (value) => value,
} = {}) {
  if (!item) return
  const fileData = buildFileData(item)
  const mediaKind = getMediaKind(fileData)
  if (mediaKind === 'pdf') {
    openPdf?.(fileData)
    return
  }
  if (mediaKind === 'image') {
    openImage?.(fileData)
    return
  }
  if (mediaKind === 'video') {
    openVideo?.(fileData)
  }
}
