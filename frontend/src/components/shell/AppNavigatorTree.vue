<template>
  <ul class="nav-tree">
    <AppNavigatorTreeNode :node="rootNode" />
  </ul>
</template>

<script setup>
import { computed, provide, reactive, watch } from 'vue'
import AppNavigatorTreeNode from './AppNavigatorTreeNode.vue'
import { navigatorTreeKey } from './navigatorTreeKey'

const props = defineProps({
  rootLabel: { type: String, default: 'Folders' },
  rootPath: { type: String, default: '' },
  activePath: { type: String, default: null },
  loadItems: { type: Function, required: true },
  emptyLabel: { type: String, default: 'No files or folders yet' },
})

const emit = defineEmits(['open-folder', 'open-file'])

const nodes = reactive({})
const expandedPaths = reactive(new Set())

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

function select(node) {
  if (node?.type === 'file') {
    emit('open-file', node.item || node)
    return
  }
  open(node?.path)
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

provide(navigatorTreeKey, {
  childrenOf,
  emptyLabel: props.emptyLabel,
  hasError,
  hasLoaded,
  isActive,
  isEmpty,
  isExpanded,
  isLoading,
  open,
  select,
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
