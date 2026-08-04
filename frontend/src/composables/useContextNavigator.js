import { computed, reactive, ref } from 'vue'
import api, { buildShareCredentialQuery } from '../lib/api'
import { useAppChromeStore } from '../ownership/appChrome'
import { useFileBrowserStore } from '../ownership/fileBrowser'
import { useProjectTrackerSelectionStore } from '../ownership/projectTrackerSelection'
import { useProjectWorkspaceStore } from '../ownership/projectWorkspace'
import { useSessionAuthStore } from '../ownership/sessionAuth'
import { useShareAccessContext } from '../ownership/shareAccessContext'
import { getMediaKind } from '../lib/mediaEntity'
import { isFileBrowserEntry } from '../utils/fileBrowserItems'

const NAVIGATOR_OPEN_STORAGE_KEY = 'vueio.navigator.open'
const NAVIGATOR_GROUPS_STORAGE_KEY = 'vueio.navigator.collapsedGroups'

const PROJECT_STATUS_GROUPS = [
  { status: 'in_progress', label: 'Active', variant: 'active' },
  { status: 'waiting_review', label: 'Review', variant: 'review' },
  { status: 'edits_requested', label: 'Edits requested', variant: 'hold' },
  { status: 'not_started', label: 'Not started', variant: 'draft' },
  { status: 'done', label: 'Completed', variant: 'done', defaultOpen: false },
]

function readStoredOpen() {
  try {
    return globalThis.localStorage?.getItem(NAVIGATOR_OPEN_STORAGE_KEY) !== '0'
  } catch {
    return true
  }
}

function readCollapsedGroups() {
  try {
    const raw = globalThis.localStorage?.getItem(NAVIGATOR_GROUPS_STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((key) => typeof key === 'string') : []
  } catch {
    return []
  }
}

// Shared across every mount point so the rail and the mobile drawer agree.
const navigatorOpen = ref(readStoredOpen())
const collapsedGroups = reactive(new Set(readCollapsedGroups()))

function persistOpen(value) {
  try {
    globalThis.localStorage?.setItem(NAVIGATOR_OPEN_STORAGE_KEY, value ? '1' : '0')
  } catch {
    // Preference persistence is best effort.
  }
}

function persistCollapsedGroups() {
  try {
    globalThis.localStorage?.setItem(NAVIGATOR_GROUPS_STORAGE_KEY, JSON.stringify([...collapsedGroups]))
  } catch {
    // Preference persistence is best effort.
  }
}

// Mirrors the status palette the project list already uses.
export function projectStatusVariant(status) {
  if (status === 'in_progress') return 'active'
  if (status === 'waiting_review') return 'review'
  if (status === 'edits_requested') return 'hold'
  if (status === 'done' || status === 'completed') return 'done'
  return 'draft'
}

function canonicalProjectStatus(status) {
  if (status === 'active') return 'in_progress'
  if (status === 'completed') return 'done'
  return status || 'not_started'
}

function statusLabel(status) {
  return String(status || 'Other')
    .replaceAll('_', ' ')
    .replace(/^./, (letter) => letter.toUpperCase())
}

export function buildProjectNavigatorGroups(projects, openProject) {
  const buckets = new Map()
  for (const project of projects || []) {
    const status = canonicalProjectStatus(project.status)
    if (!buckets.has(status)) buckets.set(status, [])
    buckets.get(status).push({
      key: `project:${project.id}`,
      label: project.title,
      meta: project.shot_count ? String(project.shot_count) : '',
      dot: projectStatusVariant(status),
      tone: 'default',
      active: false,
      run: () => openProject(project.id),
    })
  }

  const knownStatuses = new Set(PROJECT_STATUS_GROUPS.map((group) => group.status))
  const groups = PROJECT_STATUS_GROUPS
    .filter((group) => buckets.has(group.status))
    .map((group) => ({
      key: `projects:${group.status}`,
      label: group.label,
      tone: 'default',
      statusVariant: group.variant,
      defaultOpen: group.defaultOpen !== false,
      items: buckets.get(group.status),
    }))

  const extraStatuses = [...buckets.keys()]
    .filter((status) => !knownStatuses.has(status))
    .sort()
  for (const status of extraStatuses) {
    groups.push({
      key: `projects:${status}`,
      label: statusLabel(status),
      tone: 'default',
      statusVariant: 'draft',
      defaultOpen: true,
      items: buckets.get(status),
    })
  }
  return groups
}

function fileIcon(item) {
  const kind = getMediaKind(item)
  if (kind === 'image') return '#icon-image'
  if (kind === 'video') return '#icon-video'
  if (kind === 'pdf') return '#icon-pdf'
  return '#icon-file'
}

export function toNavigatorNode(item) {
  const isFolder = item.type === 'folder'
  return {
    path: item.path,
    name: item.name,
    type: isFolder ? 'folder' : 'file',
    count: isFolder ? (Number.isFinite(item.item_count) ? item.item_count : item.file_count) : undefined,
    meta: isFolder ? '' : String(item.extension || '').toUpperCase(),
    icon: isFolder ? '#icon-folder' : fileIcon(item),
    isWorkspace: Boolean(item.is_workspace),
    item,
  }
}

function countLabel(value) {
  if (!Number.isFinite(value) || value < 0) return ''
  return String(value)
}

export function useContextNavigator() {
  const { activeModule, goToProjects } = useAppChromeStore()
  const { currentUser } = useSessionAuthStore()
  const { shareMode } = useShareAccessContext()
  const { currentProject, currentTracker, currentPage } = useProjectTrackerSelectionStore()
  const {
    projectPath,
    artistWorkspaceRoot,
    projectPageItems,
    projectTrackerItems,
    sortedProjects,
    openPage,
    openTracker,
    openProject,
    openFileFromProject,
    navigateProjectFolder,
    currentProjectHeaderThumbnailUrl,
  } = useProjectWorkspaceStore()
  const { currentPath, handleClick, navigateTo, goToFiles } = useFileBrowserStore().browser

  async function loadProjectItems(path) {
    const projectId = currentProject.value?.id
    if (!projectId) return []
    const query = buildShareCredentialQuery({ path: path || '', include_counts: true })
    const { data } = await api.get(`/api/projects/${projectId}/contents${query}`)
    return (data?.items || [])
      .filter(isFileBrowserEntry)
      .map(toNavigatorNode)
  }

  async function loadStorageItems(path) {
    const query = buildShareCredentialQuery({ path: path || '', include_counts: true })
    const { data } = await api.get(`/api/files${query}`)
    return (data?.items || [])
      .filter(isFileBrowserEntry)
      .map(toNavigatorNode)
  }

  const projectRootPath = computed(() => (
    currentUser.value?.role === 'artist' ? artistWorkspaceRoot.value || '' : ''
  ))

  const projectContext = computed(() => {
    const project = currentProject.value
    if (!project) return null

    const dashboards = (projectPageItems.value || []).map((item) => ({
      key: `page:${item.id || item.slug || item.path}`,
      label: item.title || item.name,
      meta: countLabel(item.block_count),
      icon: '#icon-layout',
      tone: 'page',
      active: Boolean(currentPage.value) && (
        currentPage.value.id === item.id
        || (item.slug && currentPage.value.slug === item.slug)
      ),
      run: () => openPage(item.slug || item.path || item.id),
    }))

    const trackers = (projectTrackerItems.value || []).map((item) => ({
      key: `tracker:${item.id || item.slug || item.path}`,
      label: item.name,
      meta: countLabel(item.shot_count),
      icon: '#icon-project',
      tone: 'accent',
      active: Boolean(currentTracker.value) && (
        currentTracker.value.id === item.id
        || (item.slug && currentTracker.value.slug === item.slug)
        || currentTracker.value.name === item.name
      ),
      run: () => openTracker(item.id || item.slug || item.name),
    }))

    const groups = []
    if (dashboards.length) groups.push({ key: 'dashboards', label: 'Dashboards', tone: 'page', items: dashboards })
    if (trackers.length) groups.push({ key: 'trackers', label: 'Trackers', tone: 'accent', items: trackers })

    const rootPath = projectRootPath.value
    return {
      key: `project:${project.id}`,
      eyebrow: 'Project',
      title: project.title,
      icon: '#icon-project',
      thumbnail: currentProjectHeaderThumbnailUrl.value || '',
      scope: { run: () => navigateProjectFolder(rootPath) },
      back: { label: 'All projects', run: goToProjects },
      groups,
      tree: {
        label: 'Files',
        rootLabel: 'Project files',
        rootPath,
        activePath: currentTracker.value || currentPage.value ? null : projectPath.value || rootPath,
        loadItems: loadProjectItems,
        openFolder: navigateProjectFolder,
        openFile: openFileFromProject,
        emptyLabel: 'No files or folders yet',
      },
    }
  })

  const projectsContext = computed(() => {
    const groups = buildProjectNavigatorGroups(sortedProjects.value, openProject)

    return {
      key: 'projects',
      eyebrow: 'Workspace',
      title: 'Projects',
      icon: '#icon-project',
      scope: { run: goToProjects },
      back: null,
      groups,
      tree: null,
      emptyLabel: 'No projects yet',
    }
  })

  const filesContext = computed(() => ({
    key: 'files',
    eyebrow: 'Storage',
    title: 'Files',
    icon: '#icon-folder',
    scope: { run: goToFiles },
    back: null,
    groups: [],
    tree: {
      label: 'Files',
      rootLabel: 'All files',
      rootPath: '',
      activePath: currentPath.value || '',
      loadItems: loadStorageItems,
      openFolder: navigateTo,
      openFile: handleClick,
      emptyLabel: 'No files or folders here',
    },
  }))

  const navigatorContext = computed(() => {
    if (!currentUser.value || shareMode.value) return null
    if (activeModule.value === 'projects') return currentProject.value ? projectContext.value : projectsContext.value
    if (activeModule.value === 'files') return filesContext.value
    return null
  })

  const hasNavigator = computed(() => Boolean(navigatorContext.value))

  function setNavigatorOpen(value) {
    navigatorOpen.value = Boolean(value)
    persistOpen(navigatorOpen.value)
  }

  function toggleNavigator() {
    setNavigatorOpen(!navigatorOpen.value)
  }

  function isGroupOpen(key, defaultOpen = true) {
    return defaultOpen ? !collapsedGroups.has(key) : collapsedGroups.has(key)
  }

  function toggleGroup(key) {
    if (collapsedGroups.has(key)) collapsedGroups.delete(key)
    else collapsedGroups.add(key)
    persistCollapsedGroups()
  }

  return {
    navigatorContext,
    hasNavigator,
    navigatorOpen,
    setNavigatorOpen,
    toggleNavigator,
    isGroupOpen,
    toggleGroup,
  }
}
