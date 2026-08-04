import { getCanonicalMediaRefs, normalizeMediaEntity } from './mediaEntity'

export function getBrowserResourceRefs(item) {
  const media = normalizeMediaEntity(item)
  const { shotVersionId, mediaAssetId } = getCanonicalMediaRefs(media)
  return {
    media,
    path: media?.path || '',
    shotVersionId,
    mediaAssetId,
  }
}
