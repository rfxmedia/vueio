import api from '../lib/api'

export const THEME_COLOR_GROUPS = [
  {
    id: 'canvas',
    label: 'Surface fills',
    description: 'The three neutral fills the entire app is built from. Borders derive from these automatically.',
    tokens: [
      { cssVar: '--v-bg-base', label: 'Page background' },
      { cssVar: '--v-surface-panel', label: 'Main surface fill' },
      { cssVar: '--v-surface-inline', label: 'Raised control fill' },
    ],
  },
  {
    id: 'text',
    label: 'Text',
    description: 'Reading colors only. These do not control surface borders or outlines.',
    tokens: [
      { cssVar: '--v-text', label: 'Main text' },
      { cssVar: '--v-text-secondary', label: 'Supporting text' },
    ],
  },
  {
    id: 'accent',
    label: 'Accent',
    description: 'Action and semantic colors. Hover and workflow states derive from these.',
    tokens: [
      { cssVar: '--v-accent', label: 'Primary accent' },
      { cssVar: '--v-danger', label: 'Danger' },
      { cssVar: '--v-warning', label: 'Warning' },
      { cssVar: '--v-info', label: 'Info' },
    ],
  },
]

const THEME_COLOR_TOKENS = THEME_COLOR_GROUPS.flatMap(group => group.tokens)
const LEGACY_THEME_COLOR_KEYS = [
  '--v-bg-overlay',
  '--v-bg-elevated',
  '--v-bg-hover',
  '--v-bg-field',
  '--v-bg-field-hover',
  '--v-surface-canvas',
  '--v-surface-raised',
  '--v-surface-raised-strong',
  '--v-surface-inset',
  '--v-surface-inset-hover',
  '--v-surface-border-soft',
  '--v-surface-border-strong',
  '--v-surface-inline-strong',
  '--v-surface-inline-pressed',
  '--v-text-muted',
  '--v-text-dim',
  '--v-border',
  '--v-border-hover',
  '--v-divider',
  '--v-divider-subtle',
  '--v-control-bg',
  '--v-control-bg-hover',
  '--v-control-bg-active',
  '--v-control-border',
  '--v-control-border-hover',
  '--v-control-border-active',
  '--v-control-border-selected',
  '--v-menu-bg',
  '--v-menu-border',
  '--v-modal-bg',
  '--v-modal-border',
  '--v-modal-divider',
  '--v-modal-card-bg',
  '--v-modal-list-item-bg',
  '--v-accent-hover',
  '--v-accent-muted',
  '--v-accent-subtle',
  '--v-status-active',
  '--v-status-review',
  '--v-status-done',
  '--v-status-hold',
  '--v-status-draft',
]

export const DEFAULT_THEME_COLORS = {
  '--v-bg-base': '#0a0f14',
  '--v-surface-panel': '#141c23',
  '--v-surface-inline': '#1a242c',
  '--v-text': '#eef5f4',
  '--v-text-secondary': '#c9d6d8',
  '--v-accent': '#76dda8',
  '--v-danger': '#ff6b6b',
  '--v-warning': '#d9bd76',
  '--v-info': '#83b8d8',
}

export function normalizeThemeColor(value) {
  if (typeof value !== 'string') return null
  const cleaned = value.trim().toLowerCase()
  if (!cleaned.startsWith('#')) return null
  const payload = cleaned.slice(1)
  if (/^[0-9a-f]{3}$/.test(payload)) {
    return `#${payload.split('').map(char => `${char}${char}`).join('')}`
  }
  if (/^[0-9a-f]{6}$/.test(payload)) {
    return cleaned
  }
  return null
}

function sanitizeThemeColors(colors = {}) {
  const sanitized = {}
  for (const token of THEME_COLOR_TOKENS) {
    const normalized = normalizeThemeColor(colors[token.cssVar])
    if (normalized) {
      sanitized[token.cssVar] = normalized
    }
  }
  return sanitized
}

export function resolveThemeColors(colors = {}) {
  return {
    ...DEFAULT_THEME_COLORS,
    ...sanitizeThemeColors(colors),
  }
}

export function applyThemeColors(colors = {}) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  const resolved = resolveThemeColors(colors)
  for (const cssVar of LEGACY_THEME_COLOR_KEYS) {
    root.style.removeProperty(cssVar)
  }
  for (const [cssVar, value] of Object.entries(resolved)) {
    root.style.setProperty(cssVar, value)
  }
}

export async function loadAndApplyStoredTheme() {
  const { data } = await api.get('/api/theme', {
    headers: { Accept: 'application/json' },
  })
  applyThemeColors(data?.colors || {})
  return data
}
