const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff', 'tif', 'heic', 'heif', 'svg', 'exr', 'dpx'])
const GENERATED_IMAGE_PREVIEW_EXTENSIONS = new Set(['exr', 'dpx'])
const VIDEO_EXTENSIONS = new Set(['mp4', 'mov', 'mkv', 'avi', 'webm', 'm4v', 'mxf', 'prores', 'r3d', 'braw'])
const PDF_EXTENSIONS = new Set(['pdf'])

function normalizeExtension(value) {
  const raw = String(value || '').trim().toLowerCase()
  if (!raw) return ''
  return raw.startsWith('.') ? raw.slice(1) : raw
}

function extensionFromPath(path) {
  const name = String(path || '').split(/[\\/]/).filter(Boolean).pop() || ''
  const dotIndex = name.lastIndexOf('.')
  if (dotIndex <= 0 || dotIndex === name.length - 1) return ''
  return normalizeExtension(name.slice(dotIndex + 1))
}

function deriveMediaKind(input, extension) {
  const explicitKind = String(input?.media_kind || input?.mediaKind || '').trim().toLowerCase()
  if (['video', 'image', 'pdf', 'file'].includes(explicitKind)) return explicitKind
  if (input?.is_pdf === true || PDF_EXTENSIONS.has(extension)) return 'pdf'
  if (input?.is_image === true || input?.type === 'image' || IMAGE_EXTENSIONS.has(extension)) return 'image'
  if (input?.is_video === true || input?.type === 'video' || VIDEO_EXTENSIONS.has(extension)) return 'video'
  return 'file'
}

export function normalizeMediaEntity(input) {
  if (typeof input === 'string') {
    const path = input
    const extension = extensionFromPath(path)
    const mediaKind = deriveMediaKind({ path }, extension)
    return {
      path,
      file_path: path,
      extension,
      media_kind: mediaKind,
      is_pdf: mediaKind === 'pdf',
      is_image: mediaKind === 'image',
      is_video: mediaKind === 'video',
      media_entity_type: path ? 'path' : null,
      media_entity_id: path || null,
      media_entity_key: path ? `path:${path}` : null,
      media_asset_id: null,
      horizons_media_asset_id: null,
      version_id: null,
      horizons_shot_version_id: null,
    }
  }

  if (!input) return null

  const path = input.path || input.file_path || ''
  const extension = normalizeExtension(input.extension) || extensionFromPath(path) || extensionFromPath(input.name)
  const mediaKind = deriveMediaKind(input, extension)
  const mediaAssetId =
    input.horizons_media_asset_id ||
    input.media_asset_id ||
    (input.media_entity_type === 'media_asset' ? input.media_entity_id : null) ||
    null
  const shotVersionId =
    input.horizons_shot_version_id ||
    input.version_id ||
    (input.media_entity_type === 'shot_version' ? input.media_entity_id : null) ||
    null

  const mediaEntityType =
    input.media_entity_type ||
    (shotVersionId ? 'shot_version' : mediaAssetId ? 'media_asset' : path ? 'path' : null)
  const mediaEntityId =
    input.media_entity_id ||
    shotVersionId ||
    mediaAssetId ||
    path ||
    null
  const mediaEntityKey =
    input.media_entity_key ||
    (mediaEntityType === 'shot_version'
      ? `version:${mediaEntityId}`
      : mediaEntityType === 'media_asset'
        ? `asset:${mediaEntityId}`
        : mediaEntityId
          ? `path:${mediaEntityId}`
          : null)

  return {
    ...input,
    path,
    file_path: input.file_path || path,
    extension: input.extension || extension,
    media_kind: mediaKind,
    is_pdf: mediaKind === 'pdf',
    is_image: mediaKind === 'image',
    is_video: mediaKind === 'video',
    media_asset_id: mediaAssetId,
    horizons_media_asset_id: mediaAssetId,
    version_id: shotVersionId,
    horizons_shot_version_id: shotVersionId,
    media_entity_type: mediaEntityType,
    media_entity_id: mediaEntityId,
    media_entity_key: mediaEntityKey,
  }
}

export function getCanonicalMediaRefs(input) {
  const media = normalizeMediaEntity(input)
  return {
    mediaAssetId: media?.horizons_media_asset_id || null,
    shotVersionId: media?.horizons_shot_version_id || null,
  }
}

function getShotVersionId(input) {
  return input?.horizons_shot_version_id
    || input?.version_id
    || (input?.media_entity_type === 'shot_version' ? input.media_entity_id : null)
    || ((input?.label !== undefined || input?.version !== undefined) ? input?.id : null)
    || null
}

export function mediaEntitiesMatch(left, right) {
  if (!left || !right) return false

  const leftVersionId = getShotVersionId(left)
  const rightVersionId = getShotVersionId(right)
  if (leftVersionId && rightVersionId) return leftVersionId === rightVersionId

  const leftAssetId = left.horizons_media_asset_id || left.media_asset_id || null
  const rightAssetId = right.horizons_media_asset_id || right.media_asset_id || null
  if (leftAssetId && rightAssetId) return leftAssetId === rightAssetId

  const leftPath = left.path || left.file_path || ''
  const rightPath = right.path || right.file_path || ''
  return Boolean(leftPath && rightPath && leftPath === rightPath)
}

export function appendCanonicalMediaRefs(params, input) {
  const { mediaAssetId, shotVersionId } = getCanonicalMediaRefs(input)
  if (mediaAssetId) params.set('horizons_media_asset_id', mediaAssetId)
  if (shotVersionId) params.set('horizons_shot_version_id', shotVersionId)
  return params
}

export function hasCanonicalObjectRefs(input) {
  const { mediaAssetId, shotVersionId } = getCanonicalMediaRefs(input)
  return !!(mediaAssetId || shotVersionId)
}

export function getMediaKind(input) {
  return normalizeMediaEntity(input)?.media_kind || 'file'
}

export function usesGeneratedImagePreview(input) {
  const media = normalizeMediaEntity(input)
  return media?.is_image === true && GENERATED_IMAGE_PREVIEW_EXTENSIONS.has(normalizeExtension(media.extension))
}
