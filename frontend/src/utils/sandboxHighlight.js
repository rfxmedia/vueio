// Colors the HTML of a Vue Sandbox page for the code editor. It returns
// escaped HTML with <span> classes; it only colors and never changes text,
// so the editor's text and its colored copy always line up.

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;' }
const escapeHtml = text => text.replace(/[&<>]/g, character => ESCAPES[character])
const span = (kind, text) => (text ? `<span class="hl-${kind}">${escapeHtml(text)}</span>` : '')

const TAG = /<(\/?)([A-Za-z][\w:.-]*)([^>]*)(>?)/y
const ATTRIBUTE = /(\s+)([^\s=/>]+)(\s*=\s*)?("[^"]*"?|'[^']*'?|[^\s>]+)?/g
const SCRIPT_TOKEN = /(\/\/[^\n]*|\/\*[\s\S]*?(?:\*\/|$))|("(?:[^"\\\n]|\\.)*"?|'(?:[^'\\\n]|\\.)*'?|`(?:[^`\\]|\\[\s\S])*`?)|\b(\d[\d_]*(?:\.\d+)?)\b|\b(const|let|var|function|return|if|else|for|while|do|switch|case|break|continue|new|class|extends|import|from|export|default|async|await|try|catch|finally|throw|typeof|instanceof|in|of|this|null|undefined|true|false)\b/g
const STYLE_TOKEN = /(\/\*[\s\S]*?(?:\*\/|$))|("[^"\n]*"?|'[^'\n]*'?)|(@[\w-]+)|([\w-]+)(?=\s*:[^{}]*[;}\n])|(#[\da-fA-F]{3,8}\b|-?\d*\.?\d+(?:px|rem|em|vh|vw|%|s|ms|fr|deg)?\b)/g
// Pages larger than this are shown without colors so typing stays fast.
export const HIGHLIGHT_MAX_CHARS = 400_000

function highlightWith(pattern, kinds, text) {
  let out = ''
  let last = 0
  pattern.lastIndex = 0
  for (let match = pattern.exec(text); match; match = pattern.exec(text)) {
    if (!match[0]) { pattern.lastIndex += 1; continue }
    out += escapeHtml(text.slice(last, match.index))
    const group = kinds.findIndex((_kind, index) => match[index + 1] !== undefined)
    out += span(kinds[group], match[0])
    last = match.index + match[0].length
  }
  return out + escapeHtml(text.slice(last))
}

function highlightTag(match) {
  const [, slash, name, attributes, close] = match
  let out = span('tag', `<${slash}${name}`)
  let last = 0
  ATTRIBUTE.lastIndex = 0
  for (let attribute = ATTRIBUTE.exec(attributes); attribute; attribute = ATTRIBUTE.exec(attributes)) {
    out += escapeHtml(attributes.slice(last, attribute.index))
    const [, space, attributeName, equals = '', value = ''] = attribute
    out += escapeHtml(space) + span('attr', attributeName) + escapeHtml(equals) + span('string', value)
    last = attribute.index + attribute[0].length
  }
  return out + escapeHtml(attributes.slice(last)) + span('tag', close)
}

export function highlightHtml(source) {
  let out = ''
  let index = 0
  while (index < source.length) {
    const open = source.indexOf('<', index)
    if (open < 0) {
      out += escapeHtml(source.slice(index))
      break
    }
    out += escapeHtml(source.slice(index, open))
    if (source.startsWith('<!--', open)) {
      const end = source.indexOf('-->', open + 4)
      const stop = end < 0 ? source.length : end + 3
      out += span('comment', source.slice(open, stop))
      index = stop
      continue
    }
    if (/^<!doctype/i.test(source.slice(open, open + 9))) {
      const end = source.indexOf('>', open)
      const stop = end < 0 ? source.length : end + 1
      out += span('comment', source.slice(open, stop))
      index = stop
      continue
    }
    TAG.lastIndex = open
    const match = TAG.exec(source)
    if (!match) {
      out += '&lt;'
      index = open + 1
      continue
    }
    out += highlightTag(match)
    index = open + match[0].length
    const name = match[2].toLowerCase()
    if (!match[1] && (name === 'script' || name === 'style')) {
      const close = new RegExp(`</${name}`, 'ig')
      close.lastIndex = index
      const end = close.exec(source)?.index ?? source.length
      const body = source.slice(index, end)
      out += name === 'script'
        ? highlightWith(SCRIPT_TOKEN, ['comment', 'string', 'number', 'keyword'], body)
        : highlightWith(STYLE_TOKEN, ['comment', 'string', 'keyword', 'attr', 'number'], body)
      index = end
    }
  }
  return out
}
