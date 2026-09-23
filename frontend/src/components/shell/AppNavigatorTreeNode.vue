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
      :selection-mode="tree.selectionMode.value"
      :thumbnail="tree.thumbnailFor(node)"
      :show-thumbnail="!isFolder && tree.showThumbnails.value"
      :file-visual="node.fileVisual"
      @select="tree.select(node, $event)"
      @open="tree.openNode(node)"
      @toggle="tree.toggle(node.path)"
      @dragstart="tree.startDrag(node, $event)"
      @dragend="tree.finishDrag"
    />

    <div v-if="isFolder" class="nav-tree-branch" :class="{ 'is-open': isOpen }" :inert="isOpen ? undefined : ''">
      <div class="nav-tree-branch-inner">
        <ul v-if="tree.hasLoaded(node.path)" class="nav-tree-children">
          <AppNavigatorTreeNode v-for="child in visibleChildren" :key="child.path" :node="child" />

          <li v-if="hiddenCount" class="nav-tree-aside is-more">
            <button class="nav-tree-more" type="button" @click="tree.revealAll(node.path)">
              <svg class="icon" aria-hidden="true"><use href="#icon-chevron-down"/></svg>
              <span>Show {{ hiddenCount }} more</span>
            </button>
          </li>
          <li v-if="tree.isEmpty(node.path)" class="nav-tree-aside">{{ tree.emptyLabel }}</li>
          <li v-if="tree.hasError(node.path)" class="nav-tree-aside is-error">Contents unavailable</li>
        </ul>
      </div>
    </div>
  </li>
</template>

<script setup>
import { computed, inject } from 'vue'
import AppNavigatorRow from './AppNavigatorRow.vue'
import { navigatorTreeKey } from './navigatorTreeKey'

const props = defineProps({
  node: { type: Object, required: true },
})

const tree = inject(navigatorTreeKey)

const isFolder = computed(() => props.node.type !== 'file')
const isOpen = computed(() => tree.isExpanded(props.node.path))
const children = computed(() => tree.childrenOf(props.node.path))
const visibleChildren = computed(() => tree.visibleChildrenOf(props.node.path))
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
  min-height: 0;
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
  display: flex;
  flex-direction: column;
  gap: 1px;
  margin-left: calc(var(--navigator-disclosure-width, 24px) / 2);
  padding: 1px 0 1px 5px;
  border-left: 1px solid color-mix(in srgb, var(--v-divider) 56%, transparent);
  transition: border-color var(--v-duration-fast) var(--v-ease-soft);
}

.nav-tree-children:hover {
  border-left-color: var(--v-divider);
}

.nav-tree-aside {
  padding: 5px var(--v-space-2) 6px var(--navigator-disclosure-width, 24px);
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
}

.nav-tree-aside.is-more {
  padding: 0;
}

.nav-tree-aside.is-error {
  color: var(--v-danger-text);
}

.nav-tree-more {
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
  width: 100%;
  min-height: 28px;
  padding: 0 var(--v-space-2) 0 calc(var(--navigator-disclosure-width, 24px) + 1px);
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: var(--v-text-muted);
  font: inherit;
  font-size: var(--v-text-sm);
  font-weight: 500;
  text-align: left;
  cursor: pointer;
  transition: color var(--v-duration-fast) var(--v-ease-soft), background var(--v-duration-fast) var(--v-ease-soft);
}

.nav-tree-more .icon {
  width: 12px;
  height: 12px;
}

.nav-tree-more:hover {
  color: var(--v-text);
  background: var(--v-bg-hover);
}

.nav-tree-more:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: -2px;
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
