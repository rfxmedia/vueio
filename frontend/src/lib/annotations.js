import { clamp } from '../utils/math'

export function isSafePngDataUrl(value) {
  return typeof value === 'string' && value.startsWith('data:image/png;base64,')
}

function parseAnnotationTarget(value) {
  if (!value) return null
  if (typeof value === 'object') return value
  const raw = String(value || '').trim()
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

export function getPdfAnnotationTarget(commentOrTarget) {
  const target = parseAnnotationTarget(commentOrTarget?.annotation_target ?? commentOrTarget)
  if (!target || target.kind !== 'pdf-region') return null
  const page = Number(target.page)
  if (!Number.isFinite(page) || page < 1) return null
  const rect = target.rect && typeof target.rect === 'object' ? target.rect : null
  return {
    kind: 'pdf-region',
    page: Math.max(1, Math.floor(page)),
    rect: normalizeRect(rect),
  }
}

export function buildPdfAnnotationTarget({ page, rect }) {
  const pageNumber = Math.max(1, Math.floor(Number(page) || 1))
  return JSON.stringify({
    kind: 'pdf-region',
    page: pageNumber,
    rect: normalizeRect(rect) || { x: 0, y: 0, width: 1, height: 1 },
  })
}

function normalizeRect(rect) {
  if (!rect || typeof rect !== 'object') return null
  const x = clamp(Number(rect.x), 0, 1)
  const y = clamp(Number(rect.y), 0, 1)
  const width = clamp(Number(rect.width), 0, 1)
  const height = clamp(Number(rect.height), 0, 1)
  return {
    x,
    y,
    width: Math.min(width, 1 - x),
    height: Math.min(height, 1 - y),
  }
}
