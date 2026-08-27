import { computed, getCurrentScope, onScopeDispose, ref, shallowRef, watch } from 'vue'

import api from '../lib/api'
import { normalizeProjectContentItems, projectContentItemTarget } from '../lib/projectContentItems'
import { sanitizeUiText } from '../utils/textSanitization'

const GROUP_ORDER = ['shot', 'media_asset', 'tracker', 'page']
const GROUP_LABELS = {
  shot: 'Shots',
  media_asset: 'Files',
  tracker: 'Trackers',
  page: 'Pages',
}
const INITIAL_GROUP_LIMIT = 5
const MAX_RESULTS_PER_GROUP = 20

function readSource(source) {
  if (typeof source === 'function') return source()
  return source && typeof source === 'object' && 'value' in source ? source.value : source
}

function targetKey(item) {
  return `${item?.target_type || ''}:${item?.target_id || ''}`
}

function normalizedMentionLabel(item) {
  const fallback = item?.target_id || 'item'
  const label = sanitizeUiText(item?.label || item?.name || fallback)
    .replace(/\s+/g, ' ')
    .replace(/^@+/, '')
    .trim()
  return (label || fallback).slice(0, 119)
}

export function commentMentionMarker(item) {
  return `@${normalizedMentionLabel(item)}`
}

function parentPath(path) {
  const normalized = String(path || '').replace(/^\/+|\/+$/g, '')
  const separator = normalized.lastIndexOf('/')
  return separator < 0 ? '' : normalized.slice(0, separator)
}

export function findCommentMentionToken(value, caret) {
  const source = String(value ?? '')
  const end = Number.isInteger(caret) ? Math.min(Math.max(caret, 0), source.length) : source.length
  let start = source.lastIndexOf('@', Math.max(0, end - 1))

  while (start >= 0) {
    const previous = start > 0 ? source[start - 1] : ''
    if (start === 0 || /\s/.test(previous)) break
    start = source.lastIndexOf('@', start - 1)
  }
  if (start < 0) return null

  const query = source.slice(start + 1, end)
  if (query.length > 120 || /[\r\n\t]/.test(query) || /\s{2}/.test(query) || query.includes('@')) return null
  return { start, end, query }
}

async function defaultMentionSearch({ projectId, query, trackerId, signal }) {
  const response = await api.get(`/api/projects/${encodeURIComponent(projectId)}/mention-search`, {
    params: {
      q: query,
      context_tracker_id: trackerId || undefined,
      limit: MAX_RESULTS_PER_GROUP,
    },
    signal,
  })
  return response.data?.groups || []
}

async function defaultProjectContents({ projectId, path, signal }) {
  const response = await api.get(`/api/projects/${encodeURIComponent(projectId)}/contents`, {
    params: { path },
    signal,
  })
  return response.data || {}
}

export function useCommentMentionAutocomplete({
  enabled = true,
  projectId,
  trackerId,
  shots,
  debounceMs = 150,
  fetchMentionGroups = defaultMentionSearch,
  fetchProjectContents = defaultProjectContents,
} = {}) {
  const open = ref(false)
  const mode = ref('search')
  const query = ref('')
  const token = shallowRef(null)
  const anchorElement = shallowRef(null)
  const serverGroups = ref([])
  const loading = ref(false)
  const error = ref('')
  const activeIndex = ref(0)
  const expandedTypes = ref(new Set())
  const browsePath = ref('')
  const browseItems = ref([])
  const browseBreadcrumbs = ref([])
  const optedOutStarts = new Set()
  let searchTimer = null
  let searchController = null
  let browseController = null
  let requestSequence = 0

  const localShotItems = computed(() => {
    const needle = query.value.trim().toLowerCase()
    return (readSource(shots) || [])
      .filter(shot => !shot?.archived_at)
      .map(shot => {
        const targetId = shot?.id || shot?._originalId || shot?.shot_id
        const label = shot?.shot_id || shot?.shot_code || shot?.name || ''
        if (!targetId || !label) return null
        return {
          target_type: 'shot',
          target_id: targetId,
          label,
          sublabel: readSource(trackerId) ? 'Current tracker' : 'Shot',
          kind: 'shot',
          tracker_id: readSource(trackerId) || shot.tracker_id || '',
          status: shot.status || '',
          latest_version_label: shot.latest_version_label || shot.versions?.at?.(-1)?.label || '',
        }
      })
      .filter(Boolean)
      .filter(item => !needle || item.label.toLowerCase().includes(needle))
      .sort((left, right) => {
        const leftPrefix = left.label.toLowerCase().startsWith(needle) ? 0 : 1
        const rightPrefix = right.label.toLowerCase().startsWith(needle) ? 0 : 1
        return leftPrefix - rightPrefix || left.label.localeCompare(right.label, undefined, { numeric: true })
      })
  })

  const groups = computed(() => {
    const byType = new Map((serverGroups.value || []).map(group => [group.type, group]))
    return GROUP_ORDER.map(type => {
      const serverGroup = byType.get(type) || { items: [], has_more: false }
      const candidates = type === 'shot'
        ? [...localShotItems.value, ...(serverGroup.items || [])]
        : [...(serverGroup.items || [])]
      const seen = new Set()
      const unique = candidates.filter(item => {
        const key = targetKey(item)
        if (!item?.target_id || seen.has(key)) return false
        seen.add(key)
        return true
      })
      const expanded = expandedTypes.value.has(type)
      const visibleLimit = expanded ? MAX_RESULTS_PER_GROUP : INITIAL_GROUP_LIMIT
      return {
        type,
        label: GROUP_LABELS[type],
        items: unique.slice(0, visibleLimit),
        has_more: !expanded && (unique.length > visibleLimit || serverGroup.has_more),
      }
    }).filter(group => group.items.length || group.has_more)
  })

  const currentFolderMention = computed(() => {
    const path = String(browsePath.value || '').replace(/^\/+|\/+$/g, '')
    if (!path) return null
    const lastCrumb = browseBreadcrumbs.value.at?.(-1)
    const label = lastCrumb?.name || lastCrumb?.label || path.split('/').filter(Boolean).at(-1) || 'Project folder'
    return {
      action: 'mention-folder',
      target_type: 'folder',
      target_id: path,
      label,
      sublabel: 'Everything inside is linked to this comment',
      kind: 'folder',
    }
  })

  const browseRows = computed(() => {
    const needle = query.value.trim().toLowerCase()
    const rows = browseItems.value
      .filter(item => !needle || String(item.name || item.title || '').toLowerCase().includes(needle))
      .map(item => {
        if (item.type === 'folder') {
          return {
            ...projectContentItemTarget(item),
            action: 'folder',
            label: item.name || 'Folder',
            sublabel: item.is_workspace ? 'Workspace · Open to browse or mention' : 'Folder · Open to browse or mention',
            kind: item.is_workspace ? 'workspace' : 'folder',
          }
        }
        return projectContentItemTarget(item)
      })
      .filter(Boolean)
      .sort((left, right) => {
        const leftFolder = left.action === 'folder' ? 0 : 1
        const rightFolder = right.action === 'folder' ? 0 : 1
        const leftWorkspace = left.is_workspace ? 0 : 1
        const rightWorkspace = right.is_workspace ? 0 : 1
        return leftFolder - rightFolder || leftWorkspace - rightWorkspace || left.label.localeCompare(right.label)
      })
    return currentFolderMention.value ? [currentFolderMention.value, ...rows] : rows
  })

  const navigationItems = computed(() => mode.value === 'browse'
    ? browseRows.value
    : [
        ...groups.value.flatMap(group => group.items),
        { action: 'browse', kind: 'browse', label: 'Browse project files…', sublabel: 'Folders, workspaces, and pages' },
      ])
  const activeItem = computed(() => navigationItems.value[activeIndex.value] || null)
  const activeDescendant = computed(() => open.value && activeItem.value
    ? `comment-mention-option-${activeIndex.value}`
    : undefined)

  function cancelSearch() {
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = null
    searchController?.abort()
    searchController = null
  }

  function dismiss({ optOut = false } = {}) {
    if (optOut && token.value) optedOutStarts.add(token.value.start)
    open.value = false
    mode.value = 'search'
    loading.value = false
    error.value = ''
    activeIndex.value = 0
    cancelSearch()
    browseController?.abort()
    browseController = null
  }

  function reset() {
    optedOutStarts.clear()
    token.value = null
    query.value = ''
    anchorElement.value = null
    serverGroups.value = []
    expandedTypes.value = new Set()
    browsePath.value = ''
    browseItems.value = []
    browseBreadcrumbs.value = []
    dismiss()
  }

  async function performSearch() {
    const currentProjectId = String(readSource(projectId) || '').trim()
    if (!open.value || mode.value !== 'search' || !currentProjectId) return
    searchController?.abort()
    const controller = new AbortController()
    const sequence = ++requestSequence
    searchController = controller
    loading.value = true
    error.value = ''
    try {
      const result = await fetchMentionGroups({
        projectId: currentProjectId,
        query: query.value.trim(),
        trackerId: String(readSource(trackerId) || '').trim(),
        signal: controller.signal,
      })
      if (sequence !== requestSequence || controller.signal.aborted) return
      serverGroups.value = Array.isArray(result) ? result : []
      activeIndex.value = Math.min(activeIndex.value, Math.max(0, navigationItems.value.length - 1))
    } catch (searchError) {
      if (controller.signal.aborted) return
      serverGroups.value = []
      error.value = 'Project results are temporarily unavailable'
    } finally {
      if (searchController === controller) searchController = null
      if (sequence === requestSequence) loading.value = false
    }
  }

  function scheduleSearch() {
    cancelSearch()
    searchTimer = setTimeout(() => {
      searchTimer = null
      void performSearch()
    }, Math.max(0, debounceMs))
  }

  function syncFromTextarea(textarea, anchor = null) {
    const currentEnabled = Boolean(readSource(enabled))
    const currentProjectId = String(readSource(projectId) || '').trim()
    if (!currentEnabled || !currentProjectId || !textarea) {
      dismiss()
      return false
    }

    const hasSelection = Number.isInteger(textarea.selectionEnd)
      && textarea.selectionEnd !== textarea.selectionStart
    const nextToken = hasSelection
      ? null
      : findCommentMentionToken(textarea.value, textarea.selectionStart)
    for (const start of [...optedOutStarts]) {
      if (textarea.value[start] !== '@') optedOutStarts.delete(start)
    }
    if (!nextToken || optedOutStarts.has(nextToken.start)) {
      dismiss()
      return false
    }

    const tokenChanged = token.value?.start !== nextToken.start
    token.value = nextToken
    query.value = nextToken.query
    anchorElement.value = anchor || textarea.closest?.('.composer') || textarea
    open.value = true
    if (tokenChanged) {
      mode.value = 'search'
      expandedTypes.value = new Set()
      activeIndex.value = 0
    }
    if (mode.value === 'search') scheduleSearch()
    else activeIndex.value = 0
    return true
  }

  function showMore(type) {
    expandedTypes.value = new Set([...expandedTypes.value, type])
  }

  async function loadBrowsePath(path = '') {
    const currentProjectId = String(readSource(projectId) || '').trim()
    if (!currentProjectId) return
    browseController?.abort()
    const controller = new AbortController()
    browseController = controller
    loading.value = true
    error.value = ''
    try {
      const data = await fetchProjectContents({
        projectId: currentProjectId,
        path,
        signal: controller.signal,
      })
      if (controller.signal.aborted) return
      browsePath.value = String(data?.path ?? path).replace(/^\/+|\/+$/g, '')
      browseItems.value = normalizeProjectContentItems(data?.items)
      browseBreadcrumbs.value = Array.isArray(data?.breadcrumbs) ? data.breadcrumbs : []
      activeIndex.value = 0
    } catch (browseError) {
      if (controller.signal.aborted) return
      browseItems.value = []
      error.value = 'This project folder could not be loaded'
    } finally {
      if (browseController === controller) {
        browseController = null
        loading.value = false
      }
    }
  }

  async function enterBrowse() {
    cancelSearch()
    mode.value = 'browse'
    activeIndex.value = 0
    await loadBrowsePath('')
  }

  async function enterFolder(item) {
    if (!item?.path) return
    await loadBrowsePath(item.path)
  }

  async function goBack() {
    if (mode.value !== 'browse') return false
    if (!browsePath.value) {
      mode.value = 'search'
      activeIndex.value = 0
      scheduleSearch()
      return true
    }
    await loadBrowsePath(parentPath(browsePath.value))
    return true
  }

  function moveActive(direction) {
    const count = navigationItems.value.length
    if (!count) return
    activeIndex.value = (activeIndex.value + direction + count) % count
  }

  function activate(item = activeItem.value) {
    if (!item || item.disabled) return null
    if (item.action === 'browse') {
      void enterBrowse()
      return null
    }
    if (item.action === 'folder') {
      void enterFolder(item)
      return null
    }
    return item.target_id ? item : null
  }

  function handleKeydown(event) {
    if (!open.value) return null
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      moveActive(event.key === 'ArrowDown' ? 1 : -1)
      return { handled: true }
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      dismiss({ optOut: true })
      return { handled: true }
    }
    if (event.key === 'ArrowLeft' && mode.value === 'browse') {
      event.preventDefault()
      void goBack()
      return { handled: true }
    }
    if (event.key === 'ArrowRight' && ['browse', 'folder'].includes(activeItem.value?.action)) {
      event.preventDefault()
      if (activeItem.value.action === 'browse') void enterBrowse()
      else void enterFolder(activeItem.value)
      return { handled: true }
    }
    if (event.key === 'Backspace' && mode.value === 'browse' && !query.value) {
      event.preventDefault()
      void goBack()
      return { handled: true }
    }
    if (event.key === 'Enter' || event.key === 'Tab') {
      const selected = activate()
      if (!selected && !activeItem.value) return null
      event.preventDefault()
      return { handled: true, item: selected }
    }
    return null
  }

  function select(item, value) {
    if (!item?.target_id || !token.value) return null
    const source = String(value ?? '')
    const marker = commentMentionMarker(item)
    const suffix = source.slice(token.value.end)
    const hasFollowingSpace = suffix.startsWith(' ')
    const inserted = hasFollowingSpace ? marker : `${marker} `
    const text = `${source.slice(0, token.value.start)}${inserted}${suffix}`
    const caret = token.value.start + marker.length + 1
    dismiss()
    return { item, marker, text, caret }
  }

  watch(
    () => [Boolean(readSource(enabled)), String(readSource(projectId) || '')],
    ([available, currentProjectId], [, previousProjectId] = []) => {
      if (!available || !currentProjectId || (previousProjectId && currentProjectId !== previousProjectId)) reset()
    },
  )

  if (getCurrentScope()) {
    onScopeDispose(() => {
      cancelSearch()
      browseController?.abort()
    })
  }

  return {
    open,
    mode,
    query,
    token,
    anchorElement,
    groups,
    browsePath,
    browseRows,
    browseBreadcrumbs,
    loading,
    error,
    activeIndex,
    activeItem,
    activeDescendant,
    navigationItems,
    syncFromTextarea,
    handleKeydown,
    activate,
    select,
    showMore,
    enterBrowse,
    enterFolder,
    goBack,
    dismiss,
    reset,
  }
}
