<template>
  <ul class="nav-tree" @keydown.esc="clearSelection">
    <AppNavigatorTreeNode :node="rootNode" />
  </ul>
</template>

<script setup>
import { computed, provide, reactive, ref, watch } from 'vue'
import AppNavigatorTreeNode from './AppNavigatorTreeNode.vue'
import { navigatorTreeKey } from './navigatorTreeKey'
import { clearProjectItemDrag, writeProjectItemDrag } from '../../lib/projectItemDrag'

const props = defineProps({
  rootLabel: { type: String, default: 'Folders' },
  rootPath: { type: String, default: '' },
  activePath: { type: String, default: null },
  loadItems: { type: Function, required: true },
  emptyLabel: { type: String, default: 'No files or folders yet' },
  dragScope: { type: Object, default: null },
})

const emit = defineEmits(['open-folder', 'open-file'])

const nodes = reactive({})
const expandedPaths = reactive(new Set())
const selectedPaths = reactive(new Set())
const draggingPaths = reactive(new Set())
const selectionAnchor = ref('')

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

function visibleDraggableNodes(path = props.rootPath, result = []) {
  for (const child of childrenOf(path)) {
    if (canDrag(child)) result.push(child)
    if (child.type !== 'file' && isExpanded(child.path)) visibleDraggableNodes(child.path, result)
  }
  return result
}

function updateSelection(node, event) {
  const path = keyFor(node.path)
  const additive = Boolean(event?.metaKey || event?.ctrlKey)
  if (event?.shiftKey) {
    const visible = visibleDraggableNodes()
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

async function ensureLoaded(path) {
  const key = keyFor(path)
  const status = nodes[key]?.status
  if (status === 'loading' || status === 'ready') return
  nodes[key] = { status: 'loading', items: [] }
  try {
    const items = await props.loadItems(key)
    nodes[key] = { status: 'ready', items: descendantsOf(key, items) }
  } catch {
    nodes[key] = { status: 'error', items: [] }
  }
}

function expand(path) {
  expandedPaths.add(keyFor(path))
  void ensureLoaded(path)
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
  if (canDrag(node)) {
    updateSelection(node, event)
    if (event?.shiftKey || event?.metaKey || event?.ctrlKey) return
  } else {
    clearSelection()
  }
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
  const selectedNodes = visibleDraggableNodes().filter(item => selectedPaths.has(keyFor(item.path)))
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

watch(
  () => [props.rootPath, props.activePath],
  () => {
    expand(props.rootPath)
    if (props.activePath === null) return
    for (const path of chainTo(props.activePath)) expand(path)
  },
  { immediate: true },
)

watch(
  () => props.dragScope?.projectId || '',
  clearSelection,
)

provide(navigatorTreeKey, {
  childrenOf,
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
