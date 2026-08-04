import { computed, reactive, ref, watch } from 'vue'
import api, { getApiErrorMessage } from '../lib/api'
import { notify } from '../utils/toasts'

const CATEGORY_COLORS = [
  '#6366f1',
  '#8b5cf6',
  '#ec4899',
  '#f43f5e',
  '#f97316',
  '#eab308',
  '#22c55e',
  '#14b8a6',
  '#06b6d4',
  '#3b82f6',
]

const TRACKER_SAVE_DEBOUNCE = 150
const TRACKER_UNTAGGED_LABEL = 'Untagged'
const LEGACY_UNCATEGORIZED_LABEL = 'Uncategorized'
const TRACKER_UNASSIGNED_FILTER = '__unassigned__'
export const BULK_UNCATEGORIZED_VALUE = '__uncategorized__'
export const BULK_UNASSIGNED_VALUE = '__unassigned__'

function createEmptyTrackerFilters() {
  return { statuses: [], categories: [], assignees: [], publications: [] }
}

function normalizeTrackerCategory(value) {
  const normalized = String(value ?? '').trim()
  return (!normalized || normalized === LEGACY_UNCATEGORIZED_LABEL) ? TRACKER_UNTAGGED_LABEL : normalized
}

function getTrackerShotTag(shot) {
  return normalizeTrackerCategory(shot?.tag ?? shot?.category)
}

function buildTrackerAssigneeFilterValue(userId) {
  return `user:${userId}`
}

function getTrackerShotAssigneeFilterValues(shot) {
  const ids = Array.isArray(shot?.assignee_user_ids) ? shot.assignee_user_ids : []
  const fallbackId = shot?.assignee_user_id ?? shot?.assignee?.id ?? null
  const uniqueIds = Array.from(new Set([...ids, fallbackId].filter(Boolean)))
  return uniqueIds.length
    ? uniqueIds.map((assigneeId) => buildTrackerAssigneeFilterValue(assigneeId))
    : [TRACKER_UNASSIGNED_FILTER]
}

function hasActiveTrackerFilters(filters) {
  return Boolean(
    filters?.statuses?.length
    || filters?.categories?.length
    || filters?.assignees?.length
    || filters?.publications?.length,
  )
}

function getTrackerActiveFilterCount(filters) {
  return (
    (filters?.statuses?.length || 0)
    + (filters?.categories?.length || 0)
    + (filters?.assignees?.length || 0)
    + (filters?.publications?.length || 0)
  )
}

function getTrackerPublicationFacts(shot) {
  const versions = Array.isArray(shot?.versions) ? shot.versions : []
  const states = new Set(versions.map(version => (
    String(version?.share_state || 'published').toLowerCase()
  )))
  const latestState = String(versions.at(-1)?.share_state || 'published').toLowerCase()
  return { states, latestState }
}

export function filterTrackerShots(shots, filters) {
  const statusSet = new Set(filters?.statuses || [])
  const categorySet = new Set((filters?.categories || []).map(normalizeTrackerCategory))
  const assigneeSet = new Set(filters?.assignees || [])
  const publicationSet = new Set(filters?.publications || [])
  if (!statusSet.size && !categorySet.size && !assigneeSet.size && !publicationSet.size) return shots

  return shots.filter((shot) => {
    if (statusSet.size && !statusSet.has(shot?.status || 'not_started')) return false
    if (categorySet.size && !categorySet.has(getTrackerShotTag(shot))) return false
    const assignees = getTrackerShotAssigneeFilterValues(shot)
    if (assigneeSet.size && !assignees.some((assignee) => assigneeSet.has(assignee))) return false
    if (publicationSet.size) {
      const { states, latestState } = getTrackerPublicationFacts(shot)
      const matchesPublication = [...publicationSet].some(state => {
        if (state === 'internal') return latestState === 'internal'
        if (state === 'has_internal') return states.has('internal')
        return states.has(state)
      })
      if (!matchesPublication) return false
    }
    return true
  })
}

function normalizeTrackerTagName(value) {
  const tag = String(value || '').trim()
  if (!tag || tag === LEGACY_UNCATEGORIZED_LABEL || tag === TRACKER_UNTAGGED_LABEL) return ''
  return tag
}

function dedupeTrackerTags(values = []) {
  const tags = []
  const seen = new Set()
  for (const value of values || []) {
    const tag = normalizeTrackerTagName(value)
    const key = tag.toLowerCase()
    if (!tag || seen.has(key)) continue
    seen.add(key)
    tags.push(tag)
  }
  return tags
}

export function useTrackerListController(ctx) {
  const trackerViewMode = ref('table')
  const trackerFilters = ref(createEmptyTrackerFilters())
  const trackerSortKey = ref(null)
  const trackerSortDir = ref('asc')
  const draggedShotIndex = ref(null)
  const dragOverIndex = ref(null)
  const currentTrackerRef = () => (
    ctx.currentTracker.value?.id || ctx.currentTracker.value?.slug || ctx.currentTracker.value?.name || ''
  )

  const showCategoryPicker = ref(null)
  const categorySearchFilter = ref('')
  const showStatusPicker = ref(null)
  const showAssigneePicker = ref(null)
  const dropdownFlipUp = ref(false)

  const contextMenu = reactive({
    show: false,
    type: null,
    x: 0,
    y: 0,
    target: null,
    worldPos: null,
  })

  const selectedShots = ref(new Set())
  const pressedShotId = ref(null)
  const expandedShotId = ref(null)

  const trackerPendingChanges = reactive({
    categories: false,
    shots: new Set(),
  })

  let trackerSaveTimer = null
  const trackerSaving = ref(false)

  const hasPendingChanges = computed(() => (
    trackerPendingChanges.categories ||
    trackerPendingChanges.shots.size > 0
  ))

  const trackerCategories = computed(() => [
    TRACKER_UNTAGGED_LABEL,
    ...getOrderedTrackerTags(),
  ])

  function getOrderedTrackerTags() {
    const storedTags = dedupeTrackerTags([
      ...(ctx.currentTracker.value?.tags || []),
      ...(ctx.currentTracker.value?.categories || []),
    ])
    const storedKeys = new Set(storedTags.map(tag => tag.toLowerCase()))
    const missingTags = []
    for (const shot of ctx.currentTracker.value?.shots || []) {
      const tag = normalizeTrackerTagName(shot.tag ?? shot.category)
      const key = tag.toLowerCase()
      if (!tag || storedKeys.has(key)) continue
      storedKeys.add(key)
      missingTags.push(tag)
    }

    return [...storedTags, ...missingTags]
  }

  function setTrackerTags(tags) {
    if (!ctx.currentTracker.value) return
    const nextTags = dedupeTrackerTags(tags)
    ctx.currentTracker.value.categories = nextTags
    ctx.currentTracker.value.tags = nextTags
    queueTrackerSave('categories')
  }

  function moveTrackerTag(tagName, direction) {
    if (ctx.shareMode.value || !ctx.canManageShotCategories?.value) return
    const tag = normalizeTrackerTagName(tagName)
    if (!tag) return
    const step = Number(direction || 0) < 0 ? -1 : 1
    const tags = getOrderedTrackerTags()
    const index = tags.findIndex(item => item.toLowerCase() === tag.toLowerCase())
    const nextIndex = index + step
    if (index < 0 || nextIndex < 0 || nextIndex >= tags.length) return
    const nextTags = [...tags]
    ;[nextTags[index], nextTags[nextIndex]] = [nextTags[nextIndex], nextTags[index]]
    setTrackerTags(nextTags)
  }

  const filteredCategories = computed(() => {
    const filter = (categorySearchFilter.value || '').toLowerCase().trim()
    if (!filter) return trackerCategories.value
    return trackerCategories.value.filter(category => category.toLowerCase().includes(filter))
  })

  function setCategorySearchFilter(value) {
    categorySearchFilter.value = value
  }

  function checkDropdownFlip(event, dropdownHeight = 280) {
    const rect = event?.target?.getBoundingClientRect?.()
    if (!rect) {
      dropdownFlipUp.value = false
      return
    }

    const spaceBelow = window.innerHeight - rect.bottom
    dropdownFlipUp.value = spaceBelow < dropdownHeight
  }

  function toggleShotStatusPicker(event, shotId) {
    checkDropdownFlip(event)
    const nextShotId = showStatusPicker.value === shotId ? null : shotId
    showStatusPicker.value = nextShotId
    showCategoryPicker.value = null
    showAssigneePicker.value = null
    if (nextShotId) categorySearchFilter.value = ''
  }

  function toggleShotCategoryPicker(event, shotId) {
    if (!canBulkUpdateCategory.value || ctx.shareMode.value) return
    checkDropdownFlip(event)
    const nextShotId = showCategoryPicker.value === shotId ? null : shotId
    showCategoryPicker.value = nextShotId
    showStatusPicker.value = null
    showAssigneePicker.value = null
    if (!nextShotId) categorySearchFilter.value = ''
  }

  async function toggleShotAssigneePicker(event, shotId) {
    if (!canAssignShots.value || ctx.shareMode.value) return
    await ctx.loadProjectTeamOptions?.()
    checkDropdownFlip(event)
    const nextShotId = showAssigneePicker.value === shotId ? null : shotId
    showAssigneePicker.value = nextShotId
    showStatusPicker.value = null
    showCategoryPicker.value = null
    if (nextShotId) categorySearchFilter.value = ''
  }

  function getCategoryColor(categoryName) {
    if (!normalizeTrackerTagName(categoryName)) {
      return 'var(--v-text-muted)'
    }

    let hash = 0
    for (let i = 0; i < categoryName.length; i++) {
      hash = categoryName.charCodeAt(i) + ((hash << 5) - hash)
    }

    const index = Math.abs(hash) % CATEGORY_COLORS.length
    return CATEGORY_COLORS[index]
  }

  function getLatestShotVersions(shot) {
    const versions = shot?.versions || []
    const latest = versions[versions.length - 1]
    return latest?.file_path ? [{ ...latest, _version_count: versions.length }] : []
  }

  function getLatestShotFilePath(shot) {
    const versions = shot?.versions || []
    const latest = versions[versions.length - 1]
    return latest?.file_path || null
  }

  function getShotThumbnailUrl(shot) {
    const filePath = getLatestShotFilePath(shot)
    if (!filePath) return null
    return ctx.getThumbnailUrl(filePath)
  }

  function queueTrackerSave(changeType, shotId = null) {
    if (changeType === 'categories') {
      trackerPendingChanges.categories = true
    } else if (changeType === 'shot' && shotId) {
      trackerPendingChanges.shots.add(shotId)
    }

    if (trackerSaveTimer) clearTimeout(trackerSaveTimer)
    trackerSaveTimer = setTimeout(flushTrackerSave, TRACKER_SAVE_DEBOUNCE)
  }

  async function flushTrackerSave() {
    if (!ctx.currentTracker.value || !ctx.currentProject.value) return

    if (trackerSaving.value) {
      trackerSaveTimer = setTimeout(flushTrackerSave, 100)
      return
    }

    const savingCategories = trackerPendingChanges.categories
    const savingShots = new Set(trackerPendingChanges.shots)

    trackerPendingChanges.categories = false
    trackerPendingChanges.shots.clear()

    if (!savingCategories && savingShots.size === 0) return

    trackerSaving.value = true

    try {
      if (savingCategories) {
        const tags = getOrderedTrackerTags()
        await api.put(
          `/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(currentTrackerRef())}`,
          { tags, categories: tags },
        )
      }

      for (const shotId of savingShots) {
        const shot = (ctx.currentTracker.value.shots || []).find(item => item.shot_id === shotId)
        if (!shot) continue
        const shotRef = shot.id || shotId

        await api.put(
          `/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(currentTrackerRef())}/shots/${encodeURIComponent(shotRef)}`,
          { tag: shot.category, category: shot.category },
        )
      }
    } catch (error) {
      console.error('Tracker save failed')

      if (savingCategories) trackerPendingChanges.categories = true
      for (const shotId of savingShots) trackerPendingChanges.shots.add(shotId)
      trackerSaveTimer = setTimeout(flushTrackerSave, 1000)
    } finally {
      trackerSaving.value = false
    }
  }

  async function forceTrackerSave() {
    if (trackerSaveTimer) clearTimeout(trackerSaveTimer)
    await flushTrackerSave()
  }

  function closeContextMenu() {
    contextMenu.show = false
    contextMenu.type = null
    contextMenu.x = 0
    contextMenu.y = 0
    contextMenu.target = null
    contextMenu.worldPos = null
  }

  function closeTrackerUi() {
    showCategoryPicker.value = null
    showStatusPicker.value = null
    showAssigneePicker.value = null
    dropdownFlipUp.value = false
    categorySearchFilter.value = ''
  }

  function getShotSelectionKey(shot) {
    if (!shot) return ''
    return String(shot.id || shot._originalId || shot.shot_id || '').trim()
  }

  function isShotSelected(shot) {
    const key = getShotSelectionKey(shot)
    return !!key && selectedShots.value.has(key)
  }

  function toggleShotSelected(shot, force = null) {
    const key = getShotSelectionKey(shot)
    if (!key) return
    const next = new Set(selectedShots.value)
    const shouldSelect = force === null ? !next.has(key) : !!force
    if (shouldSelect) next.add(key)
    else next.delete(key)
    selectedShots.value = next
  }

  function clearSelectedShots() {
    selectedShots.value = new Set()
    pressedShotId.value = null
  }

  function selectVisibleShots(shots = [], force = true) {
    const next = new Set(selectedShots.value)
    for (const shot of shots || []) {
      const key = getShotSelectionKey(shot)
      if (!key) continue
      if (force) next.add(key)
      else next.delete(key)
    }
    selectedShots.value = next
  }

  function resetSelectionState() {
    clearSelectedShots()
    expandedShotId.value = null
  }

  function queueShotCategorySave(shot, categoryName) {
    if (!shot) return
    shot.category = categoryName
    shot.tag = categoryName
    queueTrackerSave('shot', shot.shot_id)
  }

  async function assignCategory(shot, categoryName) {
    if (ctx.shareMode.value || !canBulkUpdateCategory.value || !shot) return

    const nextCategory = normalizeTrackerTagName(categoryName) || null
    queueShotCategorySave(shot, nextCategory)

    showCategoryPicker.value = null
    categorySearchFilter.value = ''
  }

  async function assignOrCreateCategory(shot, name) {
    if (ctx.shareMode.value || !canBulkUpdateCategory.value || !shot) return

    const trimmed = (name || '').trim()
    if (!trimmed || trimmed === LEGACY_UNCATEGORIZED_LABEL || trimmed === TRACKER_UNTAGGED_LABEL) {
      await assignCategory(shot, null)
      return
    }

    const currentCategories = getOrderedTrackerTags()
    if (!currentCategories.includes(trimmed)) {
      setTrackerTags([...currentCategories, trimmed])
    }

    queueShotCategorySave(shot, trimmed)
    showCategoryPicker.value = null
    categorySearchFilter.value = ''
  }

  async function deleteCategory(categoryName) {
    const tagName = normalizeTrackerTagName(categoryName)
    if (!tagName || ctx.shareMode.value) return

    const nextTags = getOrderedTrackerTags().filter(category => category.toLowerCase() !== tagName.toLowerCase())
    ctx.currentTracker.value.categories = nextTags
    ctx.currentTracker.value.tags = nextTags

    for (const shot of ctx.currentTracker.value.shots || []) {
      if (normalizeTrackerTagName(shot.tag ?? shot.category).toLowerCase() === tagName.toLowerCase()) {
        queueShotCategorySave(shot, null)
      }
    }

    queueTrackerSave('categories')
  }

  async function deleteCategoryFromMenu() {
    const categoryName = contextMenu.target
    if (!normalizeTrackerTagName(categoryName)) {
      closeContextMenu()
      return
    }

    if (!confirm(`Delete tag "${categoryName}"? Shots will be moved to Untagged.`)) {
      closeContextMenu()
      return
    }

    await deleteCategory(categoryName)
    closeContextMenu()
  }

  async function deleteCategoryFromTable(categoryName) {
    if (!normalizeTrackerTagName(categoryName)) return

    if (!confirm(`Delete tag "${categoryName}"? All shots will be moved to Untagged.`)) {
      showCategoryPicker.value = null
      return
    }

    await deleteCategory(categoryName)
    showCategoryPicker.value = null
    categorySearchFilter.value = ''
  }

  function toggleTrackerFilterValue(groupKey, value) {
    if (!['statuses', 'categories', 'assignees', 'publications'].includes(groupKey) || !value) return
    const currentValues = Array.isArray(trackerFilters.value?.[groupKey]) ? trackerFilters.value[groupKey] : []
    const nextValues = [...currentValues]
    const existingIndex = nextValues.indexOf(value)
    if (existingIndex >= 0) nextValues.splice(existingIndex, 1)
    else nextValues.push(value)
    trackerFilters.value = { ...trackerFilters.value, [groupKey]: nextValues }
  }

  function clearTrackerFilters() {
    if (hasActiveTrackerFilters(trackerFilters.value)) trackerFilters.value = createEmptyTrackerFilters()
  }

  const hasTrackerFilters = computed(() => hasActiveTrackerFilters(trackerFilters.value))
  const trackerActiveFilterCount = computed(() => getTrackerActiveFilterCount(trackerFilters.value))

  function toggleTrackerSort(key) {
    if (!key) return
    if (trackerSortKey.value !== key) {
      trackerSortKey.value = key
      trackerSortDir.value = key === 'updated' ? 'desc' : 'asc'
      return
    }
    if (trackerSortDir.value === 'asc') trackerSortDir.value = 'desc'
    else {
      trackerSortKey.value = null
      trackerSortDir.value = 'asc'
    }
  }

  const shotIdCollator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })
  const statusRank = status => {
    const index = ctx.statusOrder.indexOf(status || '')
    return index >= 0 ? index : 999
  }
  const activeTrackerShots = computed(() => (ctx.currentTracker.value?.shots || []).filter(shot => !shot?.archived_at))
  const archivedTrackerShots = computed(() => (ctx.currentTracker.value?.shots || [])
    .filter(shot => shot?.archived_at)
    .sort((left, right) => (right.archived_at || 0) - (left.archived_at || 0)))
  const canReorderShots = computed(() => (
    !ctx.shareMode.value &&
    ctx.canEditProject.value &&
    ctx.currentUser.value?.role !== 'artist' &&
    !ctx.currentProject.value?.storage_read_only &&
    !hasTrackerFilters.value &&
    !trackerSortKey.value
  ))

  const trackerShotsForDisplay = computed(() => {
    let shots = activeTrackerShots.value
    if (!shots.length) return shots
    shots = filterTrackerShots(shots, trackerFilters.value)
    const key = trackerSortKey.value
    if (!key) return shots
    const direction = trackerSortDir.value === 'desc' ? -1 : 1
    const indexed = shots.map((shot, index) => ({ shot, index }))
    indexed.sort((left, right) => {
      const a = left.shot
      const b = right.shot
      let comparison = 0
      if (key === 'status') {
        comparison = statusRank(a.status) - statusRank(b.status)
        if (!comparison) comparison = shotIdCollator.compare(a.shot_id || '', b.shot_id || '')
      } else if (key === 'id') comparison = shotIdCollator.compare(a.shot_id || '', b.shot_id || '')
      else if (key === 'updated') {
        comparison = (ctx.getShotLatestCreatedAt(a) || 0) - (ctx.getShotLatestCreatedAt(b) || 0)
        if (!comparison) comparison = shotIdCollator.compare(a.shot_id || '', b.shot_id || '')
      } else if (key === 'category') {
        comparison = shotIdCollator.compare(getTrackerShotTag(a), getTrackerShotTag(b))
        if (!comparison) comparison = shotIdCollator.compare(a.shot_id || '', b.shot_id || '')
      } else if (key === 'assignee') {
        comparison = shotIdCollator.compare(ctx.getShotAssigneeLabel(a), ctx.getShotAssigneeLabel(b))
        if (!comparison) comparison = shotIdCollator.compare(a.shot_id || '', b.shot_id || '')
      }
      return comparison ? comparison * direction : left.index - right.index
    })
    return indexed.map(item => item.shot)
  })

  const canAssignShots = computed(() => (
    !ctx.shareMode.value && !!ctx.currentProject.value && ctx.currentUser.value?.role !== 'artist' &&
    (ctx.isAdmin.value || ['admin', 'owner', 'editor'].includes(ctx.currentProject.value?.access_role || ''))
  ))
  const canArchiveShots = computed(() => canAssignShots.value)
  const showShotAssignees = computed(() => {
    if (ctx.shareMode.value || !ctx.currentTracker.value) return false
    if (canAssignShots.value) return true
    return activeTrackerShots.value.some(shot => ctx.getShotAssigneeIds(shot).length || shot?.assignee?.display_name)
  })
  const trackerStatusOptions = computed(() => ctx.statusOrder.map(status => ({
    value: status,
    label: ctx.formatStatus(status),
    count: activeTrackerShots.value.filter(shot => (shot?.status || 'not_started') === status).length,
    color: ctx.statusColorMap[status] || 'var(--v-text-muted)',
  })))
  const canBulkUpdateStatus = computed(() => !ctx.shareMode.value && ctx.canEditProject.value)
  const canBulkUpdateCategory = computed(() => !ctx.shareMode.value && ctx.canEditProject.value)
  const canBulkUpdateAssignee = computed(() => canAssignShots.value)
  const selectionEnabled = computed(() => (
    canBulkUpdateStatus.value || canBulkUpdateCategory.value || canBulkUpdateAssignee.value || ctx.canDeleteShots.value
  ))
  const selectedTrackerShots = computed(() => activeTrackerShots.value.filter(shot => isShotSelected(shot)))
  const selectedArchivedShots = computed(() => archivedTrackerShots.value.filter(shot => isShotSelected(shot)))
  const canDownloadTrackerLatest = computed(() => (
    ctx.showShotDownloads.value && trackerShotsForDisplay.value.some(shot => ctx.getAllLatestShotFiles(shot).length > 0)
  ))
  const canDownloadSelectedTrackerLatest = computed(() => (
    selectedTrackerShots.value.some(shot => ctx.getAllLatestShotFiles(shot).length > 0)
  ))
  const allVisibleSelected = computed(() => (
    trackerShotsForDisplay.value.length > 0 && trackerShotsForDisplay.value.every(shot => isShotSelected(shot))
  ))
  const allArchivedSelected = computed(() => (
    archivedTrackerShots.value.length > 0 && archivedTrackerShots.value.every(shot => isShotSelected(shot))
  ))
  const bulkCategoryOptions = computed(() => [
    { value: BULK_UNCATEGORIZED_VALUE, label: TRACKER_UNTAGGED_LABEL },
    ...trackerCategories.value
      .filter(category => category && category !== TRACKER_UNTAGGED_LABEL && category !== LEGACY_UNCATEGORIZED_LABEL)
      .map(category => ({ value: category, label: category })),
  ])
  const bulkAssigneeOptions = computed(() => [
    { value: BULK_UNASSIGNED_VALUE, label: 'Unassigned' },
    ...ctx.assignmentCandidates.value.map(candidate => ({
      value: candidate.id,
      label: candidate.display_name || candidate.username || 'Assigned',
    })),
  ])

  function clearShotSelectionSet(shots) {
    const keys = new Set((shots || []).map(getShotSelectionKey).filter(Boolean))
    if (!keys.size) return
    const next = new Set(selectedShots.value)
    keys.forEach(key => next.delete(key))
    selectedShots.value = next
  }
  const clearActiveSelectedShots = () => clearShotSelectionSet(activeTrackerShots.value)
  const clearArchivedSelectedShots = () => clearShotSelectionSet(archivedTrackerShots.value)
  function toggleActiveShotSelected(shot) {
    if (!isShotSelected(shot)) clearArchivedSelectedShots()
    toggleShotSelected(shot)
  }
  function toggleArchivedShotSelected(shot) {
    if (!isShotSelected(shot)) clearActiveSelectedShots()
    toggleShotSelected(shot)
  }
  function toggleSelectAllVisible() {
    if (!allVisibleSelected.value) clearArchivedSelectedShots()
    selectVisibleShots(trackerShotsForDisplay.value, !allVisibleSelected.value)
  }
  function toggleSelectAllArchived() {
    if (!allArchivedSelected.value) clearActiveSelectedShots()
    selectVisibleShots(archivedTrackerShots.value, !allArchivedSelected.value)
  }

  const trackerCategoryOptions = computed(() => {
    const active = new Set(trackerFilters.value.categories || [])
    const counts = new Map()
    activeTrackerShots.value.forEach(shot => {
      const category = getTrackerShotTag(shot)
      counts.set(category, (counts.get(category) || 0) + 1)
    })
    return trackerCategories.value
      .filter(category => (counts.get(category) || 0) > 0 || active.has(category))
      .map(category => ({ value: category, label: category, count: counts.get(category) || 0, color: getCategoryColor(category) }))
  })
  const trackerAssigneeOptions = computed(() => {
    const active = new Set(trackerFilters.value.assignees || [])
    const options = new Map()
    const counts = new Map()
    let unassigned = 0
    ctx.assignmentCandidates.value.forEach(candidate => {
      const value = buildTrackerAssigneeFilterValue(candidate.id)
      options.set(value, { value, label: candidate.display_name || candidate.username || 'Assigned', icon: '#icon-user' })
    })
    activeTrackerShots.value.forEach(shot => {
      const ids = ctx.getShotAssigneeIds(shot)
      const assignees = ctx.getShotAssignees(shot)
      if (!ids.length) {
        unassigned += 1
        return
      }
      ids.forEach(id => {
        const value = buildTrackerAssigneeFilterValue(id)
        const assignee = assignees.find(item => item?.id === id)
        options.set(value, {
          value,
          label: assignee?.display_name || assignee?.username || options.get(value)?.label || 'Assigned',
          icon: '#icon-user',
        })
        counts.set(value, (counts.get(value) || 0) + 1)
      })
    })
    const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })
    const result = [...options.values()]
      .filter(option => (counts.get(option.value) || 0) > 0 || active.has(option.value))
      .sort((a, b) => collator.compare(a.label, b.label))
      .map(option => ({ ...option, count: counts.get(option.value) || 0 }))
    if (unassigned > 0 || active.has(TRACKER_UNASSIGNED_FILTER)) {
      result.unshift({ value: TRACKER_UNASSIGNED_FILTER, label: 'Unassigned', count: unassigned, icon: '#icon-user' })
    }
    return result
  })
  const trackerFilterGroups = computed(() => {
    const groups = [{ key: 'statuses', label: 'Status', options: trackerStatusOptions.value }]
    if (!ctx.shareMode.value) {
      const counts = { pending: 0, internal: 0, has_internal: 0 }
      activeTrackerShots.value.forEach(shot => {
        const { states, latestState } = getTrackerPublicationFacts(shot)
        if (states.has('pending')) counts.pending += 1
        if (latestState === 'internal') counts.internal += 1
        if (states.has('internal')) counts.has_internal += 1
      })
      const active = new Set(trackerFilters.value.publications || [])
      const options = [
        { value: 'pending', label: 'Pending for shares', color: 'var(--v-warning)', count: counts.pending },
        { value: 'internal', label: 'Latest is internal', color: 'var(--v-text-muted)', count: counts.internal },
        { value: 'has_internal', label: 'Contains internal versions', color: 'var(--v-text-muted)', count: counts.has_internal },
      ].filter(option => option.count > 0 || active.has(option.value))
      if (options.length) groups.push({ key: 'publications', label: 'Visibility', options })
    }
    if (trackerCategoryOptions.value.length) groups.push({ key: 'categories', label: 'Tag', options: trackerCategoryOptions.value })
    if (trackerAssigneeOptions.value.length) groups.push({ key: 'assignees', label: 'Assignee', options: trackerAssigneeOptions.value })
    return groups
  })

  function onDragStart(event, index) {
    draggedShotIndex.value = index
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', index)
  }
  function onDragOver(event, index) {
    event.preventDefault()
    if (draggedShotIndex.value !== null && draggedShotIndex.value !== index) dragOverIndex.value = index
  }
  const onDragLeave = () => { dragOverIndex.value = null }
  async function onDrop(event, targetIndex) {
    event.preventDefault()
    const sourceIndex = draggedShotIndex.value
    if (sourceIndex === null || sourceIndex === targetIndex || !ctx.currentProject.value || !ctx.currentTracker.value) return
    const previous = ctx.currentTracker.value.shots || []
    const shots = [...activeTrackerShots.value]
    if (sourceIndex < 0 || sourceIndex >= shots.length || targetIndex < 0 || targetIndex >= shots.length) {
      draggedShotIndex.value = null
      dragOverIndex.value = null
      return
    }
    const [moved] = shots.splice(sourceIndex, 1)
    shots.splice(targetIndex, 0, moved)
    ctx.currentTracker.value.shots = [...shots, ...archivedTrackerShots.value]
    try {
      const ids = shots.map(shot => shot._originalId || shot.shot_id).filter(Boolean)
      const anchor = moved?._originalId || moved?.shot_id || ids[0]
      if (anchor) {
        await api.put(
          `/api/projects/${ctx.currentProject.value.id}/trackers/${encodeURIComponent(currentTrackerRef())}/shots/${encodeURIComponent(anchor)}`,
          { shot_order: ids },
        )
        await ctx.loadTrackerActivity(currentTrackerRef())
      }
    } catch (error) {
      ctx.currentTracker.value.shots = previous
      notify(`Failed to save shot order: ${getApiErrorMessage(error)}`)
    }
    draggedShotIndex.value = null
    dragOverIndex.value = null
  }
  function onDragEnd() {
    draggedShotIndex.value = null
    dragOverIndex.value = null
  }
  function handleBeforeUnload(event) {
    if (!hasPendingChanges.value) return undefined
    forceTrackerSave()
    event.preventDefault()
    event.returnValue = ''
    return ''
  }

  function repairMissingCategories() {
    if (!ctx.currentTracker.value || ctx.shareMode.value) return

    const storedTags = dedupeTrackerTags([
      ...(ctx.currentTracker.value.tags || []),
      ...(ctx.currentTracker.value.categories || []),
    ])
    const orderedTags = getOrderedTrackerTags()
    const changed = storedTags.length !== orderedTags.length || storedTags.some((tag, index) => tag !== orderedTags[index])

    if (changed) {
      ctx.currentTracker.value.categories = orderedTags
      ctx.currentTracker.value.tags = orderedTags
      queueTrackerSave('categories')
    }
  }

  watch(ctx.currentTracker, (newTracker) => {
    if (!newTracker) return

    ctx.loadTrackerBriefPreviews?.(newTracker)
    repairMissingCategories()
    resetSelectionState()
    closeTrackerUi()
    closeContextMenu()
  })

  const trackerIdentityKey = computed(() => {
    if (!ctx.currentProject.value || !ctx.currentTracker.value) return ''
    return `${ctx.currentProject.value.id}:${currentTrackerRef()}`
  })
  watch(trackerIdentityKey, (nextKey, previousKey) => {
    if (nextKey && nextKey !== previousKey) clearTrackerFilters()
  })

  watch(trackerFilters, () => {
    resetSelectionState()
    closeTrackerUi()
    closeContextMenu()
  })

  return {
    trackerViewMode,
    trackerFilters,
    trackerSortKey,
    trackerSortDir,
    dragOverIndex,
    trackerSaving,
    hasPendingChanges,
    showCategoryPicker,
    categorySearchFilter,
    showStatusPicker,
    showAssigneePicker,
    dropdownFlipUp,
    contextMenu,
    selectedShots,
    pressedShotId,
    expandedShotId,
    trackerCategories,
    hasTrackerFilters,
    trackerActiveFilterCount,
    canReorderShots,
    activeTrackerShots,
    archivedTrackerShots,
    trackerShotsForDisplay,
    canAssignShots,
    canArchiveShots,
    showShotAssignees,
    trackerStatusOptions,
    canBulkUpdateStatus,
    canBulkUpdateCategory,
    canBulkUpdateAssignee,
    selectionEnabled,
    selectedTrackerShots,
    selectedArchivedShots,
    canDownloadTrackerLatest,
    canDownloadSelectedTrackerLatest,
    allVisibleSelected,
    allArchivedSelected,
    bulkCategoryOptions,
    bulkAssigneeOptions,
    trackerFilterGroups,
    filteredCategories,
    setCategorySearchFilter,
    toggleShotStatusPicker,
    toggleShotCategoryPicker,
    toggleShotAssigneePicker,
    getCategoryColor,
    getShotSelectionKey,
    isShotSelected,
    toggleShotSelected,
    clearSelectedShots,
    selectVisibleShots,
    clearActiveSelectedShots,
    clearArchivedSelectedShots,
    toggleActiveShotSelected,
    toggleArchivedShotSelected,
    toggleSelectAllVisible,
    toggleSelectAllArchived,
    getLatestShotVersions,
    getLatestShotFilePath,
    getShotThumbnailUrl,
    assignCategory,
    assignOrCreateCategory,
    moveTrackerTag,
    deleteCategoryFromMenu,
    deleteCategoryFromTable,
    toggleTrackerFilterValue,
    clearTrackerFilters,
    toggleTrackerSort,
    onDragStart,
    onDragOver,
    onDragLeave,
    onDrop,
    onDragEnd,
    handleBeforeUnload,
    closeContextMenu,
    forceTrackerSave,
    saveShot: ctx.saveShot,
    selectStatus: ctx.selectStatus,
  }
}
