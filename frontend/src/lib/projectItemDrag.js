export const PROJECT_ITEM_DRAG_MIME = 'application/x-vueio-project-items+json'

const PAYLOAD_VERSION = 1
const MAX_DRAG_ITEMS = 500
const PROJECT_ITEM_TYPES = new Set(['file', 'folder', 'image', 'video'])
let activeDragPayload = null

function cleanString(value, maxLength = 4096) {
  return String(value || '').replaceAll('\0', '').slice(0, maxLength)
}

function normalizeDragItem(item) {
  if (!item || !PROJECT_ITEM_TYPES.has(item.type)) return null
  const type = item.type === 'folder' ? 'folder' : 'file'
  const path = cleanString(item.path)
  if (!path) return null
  return {
    type,
    path,
    name: cleanString(item.name || path.split('/').at(-1), 512),
    source_path: cleanString(item.source_path),
    media_asset_id: cleanString(item.media_asset_id || item.horizons_media_asset_id, 256),
    extension: cleanString(item.extension, 32),
    is_image: Boolean(item.is_image || item.type === 'image'),
    is_video: Boolean(item.is_video || item.type === 'video'),
    is_pdf: Boolean(item.is_pdf),
    is_linked: Boolean(item.is_linked),
    is_workspace: Boolean(item.is_workspace),
  }
}

export function createProjectItemDragPayload({ projectId, items } = {}) {
  const normalizedProjectId = cleanString(projectId, 256)
  if (!normalizedProjectId) return null

  const seen = new Set()
  const normalizedItems = []
  for (const item of Array.isArray(items) ? items : []) {
    const normalized = normalizeDragItem(item)
    if (!normalized || seen.has(normalized.path)) continue
    seen.add(normalized.path)
    normalizedItems.push(normalized)
    if (normalizedItems.length >= MAX_DRAG_ITEMS) break
  }
  if (!normalizedItems.length) return null

  return {
    version: PAYLOAD_VERSION,
    projectId: normalizedProjectId,
    items: normalizedItems,
  }
}

export function hasProjectItemDrag(dataTransfer) {
  const types = Array.from(dataTransfer?.types || [])
  return types.includes(PROJECT_ITEM_DRAG_MIME)
}

export function writeProjectItemDrag(dataTransfer, input) {
  if (!dataTransfer) return null
  activeDragPayload = null
  const payload = createProjectItemDragPayload(input)
  if (!payload) return null

  // Browsers may hide custom drag data until drop. Keep the already-sanitized
  // payload in memory so same-page hover targets can still give accurate feedback.
  activeDragPayload = payload
  dataTransfer.effectAllowed = 'copy'
  dataTransfer.setData(PROJECT_ITEM_DRAG_MIME, JSON.stringify(payload))
  dataTransfer.setData('text/plain', payload.items.map(item => item.name).join('\n'))
  return payload
}

export function clearProjectItemDrag() {
  activeDragPayload = null
}

export function readProjectItemDrag(dataTransfer) {
  if (!hasProjectItemDrag(dataTransfer)) return null
  try {
    const raw = dataTransfer.getData(PROJECT_ITEM_DRAG_MIME) || ''
    if (!raw) return activeDragPayload
    if (raw.length > 1_000_000) return null
    const parsed = JSON.parse(raw)
    if (parsed?.version !== PAYLOAD_VERSION) return null
    return createProjectItemDragPayload({ projectId: parsed.projectId, items: parsed.items })
  } catch {
    return null
  }
}
