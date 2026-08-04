function sanitizeZipNamePart(value) {
  return String(value || '')
    .trim()
    .replace(/[^A-Za-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function ensureZipExtension(name) {
  return name.toLowerCase().endsWith('.zip') ? name : `${name}.zip`
}

export function zipNameFromPath(path, fallback = 'download') {
  const raw = String(path || '').split('/').filter(Boolean).pop() || fallback
  return ensureZipExtension(sanitizeZipNamePart(raw) || fallback)
}

export function zipNameFromParts(parts, fallback = 'download') {
  const safe = (parts || [])
    .map(sanitizeZipNamePart)
    .filter(Boolean)
    .join('-') || fallback
  return ensureZipExtension(safe)
}
