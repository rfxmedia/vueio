export function formatDateMMDDYYYY(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  if (Number.isNaN(d.getTime())) return dateStr
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}/${d.getFullYear()}`
}

export function formatSizeBytes(value, { zeroLabel = '0 B', compact = false } = {}) {
  const bytes = Number(value)
  if (!Number.isFinite(bytes) || bytes <= 0) return zeroLabel
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(sizes.length - 1, Math.floor(Math.log(bytes) / Math.log(k)))
  const size = bytes / Math.pow(k, i)
  const formatted = compact && (size >= 10 || i === 0)
    ? size.toFixed(0)
    : parseFloat(size.toFixed(1))
  return `${formatted} ${sizes[i]}`
}

export function normalizeTimestamp(value, { unit = 'auto' } = {}) {
  if (value instanceof Date) {
    const timestamp = value.getTime()
    return Number.isNaN(timestamp) ? null : timestamp
  }

  const numeric = Number(value)
  if (Number.isFinite(numeric) && numeric > 0) {
    if (unit === 'seconds') return numeric * 1000
    if (unit === 'milliseconds') return numeric
    return numeric < 100000000000 ? numeric * 1000 : numeric
  }

  if (typeof value === 'string' && value.trim()) {
    const timestamp = Date.parse(value)
    return Number.isNaN(timestamp) ? null : timestamp
  }

  return null
}

export function toDate(value, options) {
  const timestamp = normalizeTimestamp(value, options)
  return timestamp === null ? null : new Date(timestamp)
}

export function formatLocaleDate(value, { unit = 'auto', locale, options } = {}) {
  const date = toDate(value, { unit })
  return date ? date.toLocaleDateString(locale, options) : ''
}

export function formatLocaleTime(value, { unit = 'auto', locale, options } = {}) {
  const date = toDate(value, { unit })
  return date ? date.toLocaleTimeString(locale, options) : ''
}

export function formatLocaleDateTime(value, { unit = 'auto', locale, options } = {}) {
  const date = toDate(value, { unit })
  return date ? date.toLocaleString(locale, options) : ''
}

export function formatIsoTimestamp(value, { unit = 'auto' } = {}) {
  const date = toDate(value, { unit })
  return date ? date.toISOString() : ''
}

export function formatDateMMDDYYYYFromEpoch(epochSeconds) {
  const date = toDate(epochSeconds, { unit: 'seconds' })
  return date ? formatDateMMDDYYYY(date.toISOString()) : '—'
}

export function formatShareDateLabel(epochSeconds) {
  return formatLocaleDate(epochSeconds, {
    unit: 'seconds',
    options: { month: 'short', day: 'numeric', year: 'numeric' },
  }) || '—'
}

export function formatUploadDateLabel(epochSeconds) {
  if (!epochSeconds) return '—'
  const date = formatLocaleDate(epochSeconds, {
    unit: 'seconds',
    locale: 'en-US',
    options: { month: 'short', day: 'numeric', year: 'numeric' },
  })
  const time = formatLocaleTime(epochSeconds, {
    unit: 'seconds',
    locale: 'en-US',
    options: { hour: 'numeric', minute: '2-digit', hour12: true },
  })
  return `${date} at ${time}`
}

export function formatActivityAbsoluteTimestamp(epochSeconds) {
  if (!epochSeconds) return ''
  return formatLocaleDateTime(epochSeconds, {
    unit: 'seconds',
    options: { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' },
  })
}

export function formatActivityRelativeTimestamp(epochSeconds) {
  if (!epochSeconds) return ''
  const diff = Math.max(0, Date.now() / 1000 - Number(epochSeconds))
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  if (diff < 86400 * 7) return `${Math.round(diff / 86400)}d ago`
  return formatLocaleDate(epochSeconds, {
    unit: 'seconds',
    options: { month: 'short', day: 'numeric' },
  })
}

export function formatTimecodeWithFrames(seconds, fps = 24) {
  if (seconds === undefined || seconds === null || Number.isNaN(seconds)) return '0:00:00'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const f = Math.floor((seconds % 1) * fps)
  return h > 0
    ? `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}:${f.toString().padStart(2, '0')}`
    : `${m}:${s.toString().padStart(2, '0')}:${f.toString().padStart(2, '0')}`
}

export function formatDurationHMS(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return h > 0 ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`
}

export function formatVersionDateLabel(timestamp) {
  if (!timestamp) return ''
  return formatLocaleDate(timestamp, {
    unit: 'seconds',
    locale: 'en-US',
    options: { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' },
  })
}

export function formatVersionDateShortLabel(timestamp) {
  if (!timestamp) return ''
  const d = formatLocaleDate(timestamp, { locale: 'en-US', options: { month: 'short', day: 'numeric' } })
  const tm = formatLocaleTime(timestamp, { locale: 'en-US', options: { hour: '2-digit', minute: '2-digit' } })
  return `${d}\n${tm}`
}

function formatShortDateTime(timestampMs) {
  const date = toDate(timestampMs, { unit: 'milliseconds' })
  if (!date) return ''
  const sameYear = date.getFullYear() === new Date().getFullYear()
  const datePart = formatLocaleDate(date, {
    options: { month: 'short', day: 'numeric', ...(sameYear ? {} : { year: 'numeric' }) },
  })
  const timePart = formatLocaleTime(date, { options: { hour: 'numeric', minute: '2-digit' } })
  return `${datePart}, ${timePart}`
}

export function fileTimestampLabel(item) {
  const timestamp = fileTimestampValue(item)
  return timestamp ? formatShortDateTime(timestamp) : ''
}

export function fileTimestampValue(item) {
  return normalizeTimestamp(item?.uploaded_at)
    ?? normalizeTimestamp(item?.created_at ?? item?.ctime)
    ?? normalizeTimestamp(item?.modified_at ?? item?.mtime)
    ?? 0
}

export function fileCardMetaParts(item, { includeDuration = false } = {}) {
  const parts = []
  const extension = String(item?.extension || '').trim().toUpperCase()
  if (extension) parts.push({ key: 'extension', label: extension, className: 'file-ext' })
  if (item?.size_formatted) parts.push({ key: 'size', label: item.size_formatted })
  const timestamp = fileTimestampLabel(item)
  if (timestamp) parts.push({ key: 'date', label: timestamp, className: 'file-date' })
  if (includeDuration && item?.duration_formatted) {
    parts.push({ key: 'duration', label: item.duration_formatted, className: 'file-duration' })
  }
  return parts
}
