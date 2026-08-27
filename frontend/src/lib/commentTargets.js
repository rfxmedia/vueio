function normalizeCommentPath(path) {
  return String(path || '').trim().replace(/^\/+|\/+$/g, '')
}

function buildCommentTargetKey(target = {}) {
  if (target.horizons_shot_version_id) return `version:${target.horizons_shot_version_id}`
  if (target.horizons_media_asset_id) return `asset:${target.horizons_media_asset_id}`
  return `path:${normalizeCommentPath(target.path)}`
}

export function buildCommentBatchTarget(target = {}) {
  const path = normalizeCommentPath(target.path)
  const horizons_media_asset_id = target.horizons_media_asset_id || target.media_asset_id || null
  const horizons_shot_version_id = target.horizons_shot_version_id || target.version_id || target.id || null
  return {
    path,
    horizons_media_asset_id,
    horizons_shot_version_id,
    key: buildCommentTargetKey({ path, horizons_media_asset_id, horizons_shot_version_id }),
  }
}

export function buildVersionCommentBatchTarget(version) {
  if (!version?.file_path) return null
  return buildCommentBatchTarget({
    path: version.file_path,
    horizons_media_asset_id: version.media_asset_id || null,
    horizons_shot_version_id: version.id || null,
  })
}

export function chunkCommentTargets(targets, maxItems = 80) {
  const normalized = []
  for (const target of targets || []) {
    if (!target?.path) continue
    normalized.push(buildCommentBatchTarget(target))
  }
  const chunks = []
  for (let i = 0; i < normalized.length; i += maxItems) {
    chunks.push(normalized.slice(i, i + maxItems))
  }
  return chunks
}
