import { getBrowserResourceRefs } from './browserResourceRefs'
import { buildShareCredentialQuery } from './api'

export function buildBrowserDownloadUrl({ item, projectId = null, shareContext = null } = {}) {
  const { media, path, shotVersionId, mediaAssetId } = getBrowserResourceRefs(item)

  if (shareContext?.shareId) {
    const shareId = encodeURIComponent(shareContext.shareId)
    const credential = shareContext.credential || {}
    if (shotVersionId) {
      return `/api/projects/shared/${shareId}/shot-versions/${encodeURIComponent(shotVersionId)}/download${buildShareCredentialQuery({}, credential)}`
    }
    if (mediaAssetId) {
      return `/api/projects/shared/${shareId}/media-assets/${encodeURIComponent(mediaAssetId)}/download${buildShareCredentialQuery({}, credential)}`
    }
    return `/api/projects/shared/${shareId}/download${buildShareCredentialQuery({ path }, credential)}`
  }

  const resolvedProjectId = projectId || media?._projectId || null
  if (resolvedProjectId && shotVersionId) {
    return `/api/horizons/projects/${encodeURIComponent(resolvedProjectId)}/shot-versions/${encodeURIComponent(shotVersionId)}/download`
  }
  if (resolvedProjectId && mediaAssetId) {
    return `/api/horizons/projects/${encodeURIComponent(resolvedProjectId)}/media-assets/${encodeURIComponent(mediaAssetId)}/download`
  }
  if (resolvedProjectId) {
    const params = new URLSearchParams({ path, project_id: resolvedProjectId })
    return `/api/stream?${params.toString()}`
  }
  return `/api/download?path=${encodeURIComponent(path)}`
}
