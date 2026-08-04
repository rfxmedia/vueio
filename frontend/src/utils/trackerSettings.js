import { normalizeExternalHttpUrl } from './textSanitization'

export const TRACKER_TOOL_ACCESS_OPTIONS = [
  { value: 'admin', label: 'Admin' },
  { value: 'team', label: 'Team' },
  { value: 'all', label: 'All' },
]

export const DEFAULT_DELIVERY_MESSAGE = 'Thanks for reviewing with Vue.'

const TRACKER_TOOL_ACCESSES = new Set(TRACKER_TOOL_ACCESS_OPTIONS.map(option => option.value))

function cleanDeliveryLogoUploadName(value) {
  const name = String(value || '').trim().split(/[\\/]/).pop() || ''
  if (!name.startsWith('delivery-logo-')) return ''
  if (!/\.(jpe?g|png|gif|webp|bmp|tiff?|hei[cf])$/i.test(name)) return ''
  return name
}

export function normalizeDeliveryLinks(value) {
  if (!Array.isArray(value)) return []
  const links = []
  for (const item of value) {
    if (!item || typeof item !== 'object') continue
    const label = String(item.label || '').trim().slice(0, 48)
    const url = normalizeExternalHttpUrl(item.url)
    if (!label || !url) continue
    links.push({ label, url })
    if (links.length >= 4) break
  }
  return links
}

export function normalizeTrackerSettings(rawSettings = null, options = {}) {
  const preserveDeliveryMessage = options?.preserveDeliveryMessage === true
  const tools = {
    comparison: {
      enabled: true,
      access: 'team',
    },
    details: {
      enabled: true,
      access: 'all',
    },
    brief_preview: {
      enabled: true,
    },
    version_review: {
      enabled: false,
    },
    delivery: {
      enabled: false,
      message: DEFAULT_DELIVERY_MESSAGE,
      notes: '',
      links: [],
      logo_upload_name: '',
    },
  }

  for (const key of ['comparison', 'details']) {
    const item = rawSettings?.[key]
    if (!item || typeof item !== 'object') continue
    if ('enabled' in item) tools[key].enabled = item.enabled !== false
    if ('access' in item && TRACKER_TOOL_ACCESSES.has(String(item.access || '').toLowerCase())) {
      tools[key].access = String(item.access).toLowerCase()
    } else if (key === 'comparison' && 'share_access' in item) {
      tools[key].access = item.share_access === true ? 'all' : 'team'
    }
  }

  const briefPreview = rawSettings?.brief_preview
  if (briefPreview && typeof briefPreview === 'object' && 'enabled' in briefPreview) {
    tools.brief_preview.enabled = briefPreview.enabled !== false
  }

  const versionReview = rawSettings?.version_review
  if (versionReview && typeof versionReview === 'object' && 'enabled' in versionReview) {
    tools.version_review.enabled = versionReview.enabled === true
  }

  const delivery = rawSettings?.delivery
  if (delivery && typeof delivery === 'object') {
    if ('enabled' in delivery) tools.delivery.enabled = delivery.enabled === true
    if ('message' in delivery) {
      if (preserveDeliveryMessage) {
        tools.delivery.message = String(delivery.message ?? '')
      } else {
        const message = String(delivery.message || '').trim()
        tools.delivery.message = message || DEFAULT_DELIVERY_MESSAGE
      }
    }
    if ('notes' in delivery) {
      tools.delivery.notes = preserveDeliveryMessage
        ? String(delivery.notes ?? '')
        : String(delivery.notes || '').trim().slice(0, 1200)
    }
    if ('links' in delivery) {
      tools.delivery.links = preserveDeliveryMessage && Array.isArray(delivery.links)
        ? delivery.links.slice(0, 4).map(link => ({
            label: String(link?.label ?? ''),
            url: String(link?.url ?? ''),
          }))
        : normalizeDeliveryLinks(delivery.links)
    }
    if ('logo_upload_name' in delivery) {
      tools.delivery.logo_upload_name = cleanDeliveryLogoUploadName(delivery.logo_upload_name)
    }
  }

  return tools
}

export function trackerToolEnabledForContext(tracker, toolKey, { shareMode = false, currentUser = null, accessRole = null } = {}) {
  const tool = normalizeTrackerSettings(tracker?.settings)[toolKey]
  if (!tool?.enabled) return false
  if (toolKey === 'delivery') return true

  if (tool.access === 'all') return true
  if (shareMode) return false
  if (tool.access === 'admin') return currentUser?.role === 'admin'
  return Boolean(accessRole || currentUser)
}
