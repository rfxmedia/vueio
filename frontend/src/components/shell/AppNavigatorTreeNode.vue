<template>
  <li class="nav-tree-node">
    <AppNavigatorRow
      :label="node.name"
      :icon="node.icon || '#icon-folder'"
      :meta="metaLabel"
      :tone="node.isWorkspace ? 'accent' : 'default'"
      :active="tree.isActive(node.path)"
      :expandable="isFolder"
      :expanded="isFolder && isOpen"
      :loading="isFolder && tree.isLoading(node.path)"
      :selected="tree.isSelected(node.path)"
      :draggable="tree.canDrag(node)"
      :dragging="tree.isDragging(node.path)"
      @select="tree.select(node, $event)"
      @toggle="tree.toggle(node.path)"
      @dragstart="tree.startDrag(node, $event)"
      @dragend="tree.finishDrag"
    />

    <div v-if="isFolder" class="nav-tree-branch" :class="{ 'is-open': isOpen }" :inert="isOpen ? undefined : ''">
      <div class="nav-tree-branch-inner">
        <ul v-if="tree.hasLoaded(node.path)" class="nav-tree-children">
          <AppNavigatorTreeNode v-for="child in visibleChildren" :key="child.path" :node="child" />

          <li v-if="hiddenCount" class="nav-tree-aside">
            <button class="nav-tree-more" type="button" @click="showAll = true">
              Show {{ hiddenCount }} more
            </button>
          </li>
          <li v-if="tree.isEmpty(node.path)" class="nav-tree-aside is-note">{{ tree.emptyLabel }}</li>
          <li v-if="tree.hasError(node.path)" class="nav-tree-aside is-error">Contents unavailable</li>
        </ul>
      </div>
    </div>
  </li>
</template>

<script setup>
import { computed, inject, ref } from 'vue'
import AppNavigatorRow from './AppNavigatorRow.vue'
import { navigatorTreeKey } from './navigatorTreeKey'

const LEVEL_LIMIT = 12

const props = defineProps({
  node: { type: Object, required: true },
})

const tree = inject(navigatorTreeKey)
const showAll = ref(false)

const isFolder = computed(() => props.node.type !== 'file')
const isOpen = computed(() => tree.isExpanded(props.node.path))
const children = computed(() => tree.childrenOf(props.node.path))
const visibleChildren = computed(() => (
  showAll.value ? children.value : children.value.slice(0, LEVEL_LIMIT)
))
const hiddenCount = computed(() => children.value.length - visibleChildren.value.length)
const metaLabel = computed(() => (
  Number.isFinite(props.node.count) ? String(props.node.count) : props.node.meta || ''
))
</script>

<style scoped>
.nav-tree-node,
.nav-tree-children {
  list-style: none;
  margin: 0;
  padding: 0;
}

/* Collapsing a loaded branch keeps it mounted so the accordion can animate both ways. */
.nav-tree-branch {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows var(--v-duration-normal) var(--v-ease-emphasized);
}

.nav-tree-branch.is-open {
  grid-template-rows: 1fr;
}

.nav-tree-branch-inner {
  overflow: hidden;
  opacity: 0;
  transform: translateY(-3px);
  transition:
    opacity var(--v-duration-normal) var(--v-ease-soft),
    transform var(--v-duration-normal) var(--v-ease-emphasized);
}

.nav-tree-branch.is-open .nav-tree-branch-inner {
  opacity: 1;
  transform: translateY(0);
}

.nav-tree-children {
  margin-left: calc(var(--navigator-disclosure-width, 22px) / 2);
  padding-left: 5px;
  border-left: 1px solid color-mix(in srgb, var(--v-divider) 62%, transparent);
  transition: border-color var(--v-duration-fast) var(--v-ease-soft);
}

.nav-tree-children:hover {
  border-left-color: var(--v-divider);
}

.nav-tree-aside {
  padding: 2px 0 4px 20px;
  color: var(--v-text-dim);
  font-size: var(--v-text-xs);
}

.nav-tree-aside.is-note {
  font-style: italic;
  opacity: 0.72;
}

.nav-tree-aside.is-error {
  color: color-mix(in srgb, var(--v-danger) 72%, white);
}

.nav-tree-more {
  padding: 2px 6px;
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: var(--v-text-dim);
  font: inherit;
  font-size: var(--v-text-xs);
  cursor: pointer;
  transition: color var(--v-duration-fast) var(--v-ease-soft), background var(--v-duration-fast) var(--v-ease-soft);
}

.nav-tree-more:hover {
  color: var(--v-text);
  background: var(--v-bg-hover);
}

@media (prefers-reduced-motion: reduce) {
  .nav-tree-branch,
  .nav-tree-branch-inner {
    transition: none;
  }

  .nav-tree-branch-inner {
    transform: none;
  }
}
</style>
