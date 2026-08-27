const IDENTITY_COLORS = [
  'var(--v-accent)',
  'var(--v-info)',
  'var(--v-page)',
  'var(--v-warning)',
  'color-mix(in srgb, var(--v-info) 58%, var(--v-accent))',
  'color-mix(in srgb, var(--v-page) 58%, var(--v-danger))',
]

function stableHash(value) {
  let hash = 0
  for (const character of String(value || 'vueio')) {
    hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0
  }
  return Math.abs(hash)
}

export function getIdentityColor(seed) {
  return IDENTITY_COLORS[stableHash(seed) % IDENTITY_COLORS.length]
}

export function identityColorStyle(seed, property = '--v-identity-color') {
  return { [property]: getIdentityColor(seed) }
}
