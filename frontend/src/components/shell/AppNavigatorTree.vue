<template>
  <ul class="nav-tree" @keydown.esc="clearSelection">
    <AppNavigatorTreeNode :node="rootNode" />
  </ul>
</template>

<script setup>
import { computed, onBeforeUnmount, provide, reactive, ref, watch } from 'vue'
import AppNavigatorTreeNode from './AppNavigatorTreeNode.vue'
import { navigatorTreeKey } from './navigatorTreeKey'
import { clearProjectItemDrag, writeProjectItemDrag } from '../../lib/projectItemDrag'
import { useFolderChanges } from '../../composables/useFolderChanges'

const LEVEL_LIMIT = 12

const props = defineProps({
  rootLabel: { type: String, default: 'Folders' },
  rootPath: { type: String, default: '' },
  activePath: { type: String, default: null },
  loadItems: { type: Function, required: true },
  emptyLabel: { type: String, default: 'No files or folders yet' },
  dragScope: { type: Object, default: null },
  watchScope: { type: Object, default: null },
  active: { type: Boolean, default: true },
  selectionMode: { type: Boolean, default: true },
  thumbnailFor: { type: Function, default: null },
})

const emit = defineEmits(['open-folder', 'open-file'])

const nodes = reactive({})
const expandedPaths = reactive(new Set())
const revealedPaths = reactive(new Set())
const selectedPaths = reactive(new Set())
const draggingPaths = reactive(new Set())
const selectionAnchor = ref('')
const requests = new Map()

const rootNode = computed(() => ({ path: props.rootPath || '', name: props.rootLabel }))

function keyFor(path) {
  return path || ''
}

function stateOf(path) {
  return nodes[keyFor(path)]
}

function childrenOf(path) {
  return stateOf(path)?.items || []
}

function visibleChildrenOf(path) {
  const children = childrenOf(path)
  return revealedPaths.has(keyFor(path)) ? children : children.slice(0, LEVEL_LIMIT)
}

function revealAll(path) {
  revealedPaths.add(keyFor(path))
}

function hasLoaded(path) {
  const status = stateOf(path)?.status
  return status === 'ready' || status === 'error'
}

function isLoading(path) {
  return stateOf(path)?.status === 'loading'
}

function isEmpty(path) {
  const state = stateOf(path)
  return state?.status === 'ready' && state.items.length === 0
}

function hasError(path) {
  return stateOf(path)?.status === 'error'
}

function isExpanded(path) {
  return expandedPaths.has(keyFor(path))
}

function isActive(path) {
  return props.activePath !== null && keyFor(props.activePath) === keyFor(path)
}

function canDrag(node) {
  return Boolean(props.dragScope?.projectId && node?.item && ['file', 'folder', 'image', 'video'].includes(node.item.type))
}

function isSelected(path) {
  return selectedPaths.has(keyFor(path))
}

function isDragging(path) {
  return draggingPaths.has(keyFor(path))
}

function replaceSelection(paths) {
  selectedPaths.clear()
  for (const path of paths) selectedPaths.add(keyFor(path))
}

function clearSelection() {
  selectedPaths.clear()
  selectionAnchor.value = ''
}

function visibleNodes(path = props.rootPath, result = []) {
  if (!isExpanded(path)) return result
  for (const child of visibleChildrenOf(path)) {
    result.push(child)
    if (child.type !== 'file' && isExpanded(child.path)) visibleNodes(child.path, result)
  }
  return result
}

function updateSelection(node, event) {
  const path = keyFor(node.path)
  const additive = Boolean(event?.metaKey || event?.ctrlKey)
  if (event?.shiftKey) {
    const visible = visibleNodes()
    const anchorPath = selectionAnchor.value || path
    const anchorIndex = visible.findIndex(item => keyFor(item.path) === anchorPath)
    const targetIndex = visible.findIndex(item => keyFor(item.path) === path)
    if (anchorIndex < 0 || targetIndex < 0) {
      replaceSelection([path])
      selectionAnchor.value = path
      return
    }
    const [start, end] = anchorIndex <= targetIndex
      ? [anchorIndex, targetIndex]
      : [targetIndex, anchorIndex]
    const range = visible.slice(start, end + 1).map(item => item.path)
    replaceSelection(additive ? [...selectedPaths, ...range] : range)
    if (!selectionAnchor.value) selectionAnchor.value = path
    return
  }

  if (additive) {
    if (selectedPaths.has(path)) selectedPaths.delete(path)
    else selectedPaths.add(path)
    selectionAnchor.value = path
    return
  }

  replaceSelection([path])
  selectionAnchor.value = path
}

// A listing that echoes its own parent would recurse forever, so only accept
// entries that sit strictly below the folder they were requested for.
function descendantsOf(parent, items) {
  if (!Array.isArray(items)) return []
  const prefix = parent ? `${parent}/` : ''
  return items.filter((item) => Boolean(item?.path) && item.path.startsWith(prefix) && item.path !== parent)
}

function removeBranch(path) {
  const matches = key => key === path || key.startsWith(`${path}/`)
  for (const key of Object.keys(nodes)) {
    if (matches(key)) delete nodes[key]
  }
  for (const [key, request] of requests) {
    if (!matches(key)) continue
    request.controller.abort()
    requests.delete(key)
  }
  if ([...draggingPaths].some(matches)) finishDrag()
  for (const paths of [expandedPaths, revealedPaths, selectedPaths]) {
    for (const key of paths) {
      if (matches(key)) paths.delete(key)
    }
  }
  if (matches(selectionAnchor.value)) selectionAnchor.value = ''
}

function replaceChildren(path, items) {
  const nextTypes = new Map(items.map(item => [item.path, item.type]))
  for (const child of childrenOf(path)) {
    if (!nextTypes.has(child.path) || (child.type !== 'file' && nextTypes.get(child.path) === 'file')) {
      removeBranch(child.path)
    }
  }
  nodes[path] = { status: 'ready', items }
  if (path) {
    const parent = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : ''
    const parentState = stateOf(parent)
    if (parentState) {
      parentState.items = parentState.items.map(child => (
        child.path === path ? { ...child, count: items.length } : child
      ))
    }
  }
}

function ensureLoaded(path, { force = false } = {}) {
  const key = keyFor(path)
  const pending = requests.get(key)
  if (pending) {
    pending.refresh ||= force
    return pending.promise
  }
  if (!force && stateOf(key)?.status === 'ready') return
  const request = { controller: new AbortController(), refresh: false, promise: null }
  requests.set(key, request)
  const isCurrent = () => requests.get(key) === request
  request.promise = (async () => {
    do {
      request.refresh = false
      const previous = stateOf(key)
      if (!previous || previous.status !== 'ready') nodes[key] = { status: 'loading', items: [] }
      try {
        const items = await props.loadItems(key, { force, signal: request.controller.signal })
        if (!isCurrent()) return
        replaceChildren(key, descendantsOf(key, items))
      } catch (error) {
        if (!isCurrent()) return
        if (!previous || previous.status !== 'ready' || [400, 401, 403, 404, 409, 410].includes(error?.response?.status)) {
          replaceChildren(key, [])
          nodes[key].status = 'error'
        }
      }
      force = request.refresh
    } while (force && isCurrent())
  })().finally(() => {
    if (isCurrent()) requests.delete(key)
  })
  return request.promise
}

function expand(path) {
  expandedPaths.add(keyFor(path))
}

function toggle(path) {
  const key = keyFor(path)
  if (expandedPaths.has(key)) expandedPaths.delete(key)
  else expand(key)
}

function open(path) {
  expand(path)
  emit('open-folder', keyFor(path))
}

function select(node, event) {
  if (props.selectionMode) updateSelection(node, event)
  else openNode(node)
}

function openNode(node) {
  if (node?.type === 'file') {
    emit('open-file', node.item || node)
    return
  }
  open(node?.path)
}

function startDrag(node, event) {
  if (!canDrag(node) || !event?.dataTransfer) {
    event?.preventDefault?.()
    return
  }
  if (!selectedPaths.has(keyFor(node.path))) updateSelection(node)
  const selectedNodes = visibleNodes().filter(item => canDrag(item) && selectedPaths.has(keyFor(item.path)))
  const dragNodes = selectedNodes.length ? selectedNodes : [node]
  const payload = writeProjectItemDrag(event.dataTransfer, {
    projectId: props.dragScope.projectId,
    items: dragNodes.map(item => item.item),
  })
  if (!payload) {
    event.preventDefault()
    return
  }
  draggingPaths.clear()
  for (const item of dragNodes) draggingPaths.add(keyFor(item.path))
  event.stopPropagation()
}

function finishDrag() {
  draggingPaths.clear()
  clearProjectItemDrag()
}

// The chain of folders between the tree root and `path`, so navigating anywhere
// in the main view reveals that folder in the sidebar.
function chainTo(path) {
  const root = keyFor(props.rootPath)
  const target = keyFor(path)
  if (!target || target === root) return []
  if (root && !target.startsWith(`${root}/`)) return []
  const relative = root ? target.slice(root.length + 1) : target
  const chain = []
  let accumulated = root
  for (const segment of relative.split('/').filter(Boolean)) {
    accumulated = accumulated ? `${accumulated}/${segment}` : segment
    chain.push(accumulated)
  }
  return chain
}

function revealActivePath() {
  expand(props.rootPath)
  if (props.activePath === null) return
  for (const path of chainTo(props.activePath)) expand(path)
}

function cancelLoads() {
  for (const request of requests.values()) request.controller.abort()
  requests.clear()
}

watch(
  [
    () => props.rootPath,
    () => props.watchScope?.userId,
    () => props.watchScope?.projectId,
    () => props.watchScope?.shareId,
    () => props.watchScope?.shareToken,
  ],
  () => {
    cancelLoads()
    for (const path of Object.keys(nodes)) delete nodes[path]
    expandedPaths.clear()
    revealedPaths.clear()
    clearSelection()
    if (draggingPaths.size) finishDrag()
    revealActivePath()
  },
  { immediate: true, flush: 'sync' },
)

watch(() => props.activePath, revealActivePath)

const visibleExpandedPaths = computed(() => {
  const paths = []
  if (!props.active) return paths
  function visit(path) {
    if (!isExpanded(path)) return
    paths.push(keyFor(path))
    for (const child of visibleChildrenOf(path)) {
      if (child.type !== 'file') visit(child.path)
    }
  }
  visit(props.rootPath)
  return paths
})

watch(visibleExpandedPaths, (paths, previous = []) => {
  const previousPaths = new Set(previous)
  for (const path of paths) {
    if (!previousPaths.has(path) || !stateOf(path)) void ensureLoaded(path, { force: true })
  }
}, { immediate: true })

useFolderChanges(
  () => props.watchScope && visibleExpandedPaths.value.length
    ? { ...props.watchScope, paths: visibleExpandedPaths.value }
    : null,
  async (paths) => {
    const visible = new Set(visibleExpandedPaths.value)
    await Promise.all(paths.filter(path => visible.has(path)).map(path => ensureLoaded(path, { force: true })))
  },
)

onBeforeUnmount(() => {
  cancelLoads()
  if (draggingPaths.size) finishDrag()
})

provide(navigatorTreeKey, {
  childrenOf,
  visibleChildrenOf,
  revealAll,
  emptyLabel: props.emptyLabel,
  hasError,
  hasLoaded,
  canDrag,
  isActive,
  isDragging,
  isEmpty,
  isExpanded,
  isLoading,
  isSelected,
  open,
  openNode,
  selectionMode: computed(() => props.selectionMode),
  thumbnailFor: (node) => props.active ? props.thumbnailFor?.(node.item) || '' : '',
  select,
  startDrag,
  finishDrag,
  toggle,
})
</script>

<style scoped>
.nav-tree {
  list-style: none;
  margin: 0;
  padding: 0;
  min-width: 0;
}
</style>
