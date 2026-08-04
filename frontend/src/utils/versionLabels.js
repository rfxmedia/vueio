export function formatVersionLabel(version, fallbackIndex = null, options = {}) {
  const {
    emptyLabel = 'Version',
    uppercaseVPrefix = false,
    fallbackIndexAsRaw = false,
  } = options
  const fallbackValue = fallbackIndexAsRaw ? fallbackIndex : ''
  const raw = String(version?.label ?? version?.version ?? fallbackValue ?? '').trim()
  if (raw) {
    if (/^v/i.test(raw)) return uppercaseVPrefix ? raw.toUpperCase() : `V${raw.slice(1)}`
    if (/^\d+$/.test(raw)) return `V${raw}`
    return raw
  }
  if (!fallbackIndexAsRaw && fallbackIndex !== null && fallbackIndex !== undefined) {
    return `V${fallbackIndex}`
  }
  return emptyLabel
}
