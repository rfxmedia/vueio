const UI_TEXT_SANITIZE_PATTERN = /[\u00AD\u034F\u061C\u180E\u200B-\u200F\u202A-\u202E\u2060-\u2069\uFEFF\uFFF9-\uFFFC\uFFFD]/g
const UI_TEXT_URL_PATTERN = /(?:https?:\/\/|www\.)[^\s<>"'`{}|\\^\[\]]+/gi
const UI_TEXT_URL_TRAILING_PATTERN = /[),.;!?]+$/g

export function sanitizeUiText(value) {
  return String(value ?? '')
    .normalize('NFKC')
    .replace(UI_TEXT_SANITIZE_PATTERN, '')
}

export function normalizeExternalHttpUrl(value, { maxLength = 500 } = {}) {
  const raw = String(value ?? '').trim()
  if (!raw) return ''
  const candidate = /^[a-z][a-z0-9+.-]*:/i.test(raw) ? raw : `https://${raw}`
  if (candidate.length > maxLength || candidate.includes('\\')) return ''
  if ([...candidate].some(character => {
    const code = character.charCodeAt(0)
    return code < 32 || code === 127
  })) return ''
  try {
    const parsed = new URL(candidate)
    const authority = candidate.match(/^[a-z][a-z0-9+.-]*:\/\/([^/?#]*)/i)?.[1] || ''
    if (
      !['http:', 'https:'].includes(parsed.protocol) ||
      !parsed.hostname ||
      authority.includes('@') ||
      parsed.username ||
      parsed.password
    ) return ''
    return parsed.href
  } catch {
    return ''
  }
}

export function segmentTextLinks(value) {
  const source = sanitizeUiText(value)
  const segments = []
  let lastIndex = 0

  for (const match of source.matchAll(UI_TEXT_URL_PATTERN)) {
    const fullMatch = match[0]
    const offset = match.index ?? 0

    if (offset > lastIndex) {
      segments.push({ type: 'text', text: source.slice(lastIndex, offset) })
    }

    const trimmed = fullMatch.replace(UI_TEXT_URL_TRAILING_PATTERN, '')
    const trailing = fullMatch.slice(trimmed.length)
    const href = normalizeExternalHttpUrl(trimmed)

    if (href) {
      segments.push({
        type: 'link',
        text: trimmed,
        href,
      })
    } else {
      segments.push({ type: 'text', text: trimmed })
    }

    if (trailing) {
      segments.push({ type: 'text', text: trailing })
    }

    lastIndex = offset + fullMatch.length
  }

  if (lastIndex < source.length) {
    segments.push({ type: 'text', text: source.slice(lastIndex) })
  }

  return segments.length ? segments : [{ type: 'text', text: source }]
}
