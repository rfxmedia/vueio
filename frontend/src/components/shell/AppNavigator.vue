<template>
  <aside
    v-if="context"
    class="app-navigator"
    :class="[`is-${variant}`, { 'is-collapsed': collapsed }]"
    aria-label="Context navigation"
    :aria-hidden="collapsed ? 'true' : undefined"
    :inert="collapsed ? '' : undefined"
  >
    <div class="navigator-inner">
      <header class="navigator-head">
        <button class="navigator-scope" type="button" @click="activate(context.scope.run)">
          <span class="navigator-scope-mark" :class="{ 'has-thumb': showThumb }">
            <img v-if="showThumb" :src="context.thumbnail" alt="" @error="thumbFailed = true"/>
            <svg v-else class="icon" aria-hidden="true"><use :href="context.icon"/></svg>
          </span>
          <span class="navigator-scope-copy">
            <span class="navigator-eyebrow v-eyebrow">{{ context.eyebrow }}</span>
            <span class="navigator-title v-truncate" :title="context.title">{{ context.title }}</span>
          </span>
        </button>
      </header>

      <div class="navigator-body">
        <button v-if="context.back" class="navigator-back" type="button" @click="activate(context.back.run)">
          <svg class="icon" aria-hidden="true"><use href="#icon-back"/></svg>
          <span>{{ context.back.label }}</span>
        </button>

        <section
          v-for="group in sections"
          :key="group.key"
          class="navigator-section"
          :class="[
            `is-tone-${group.tone}`,
            group.statusVariant ? `is-status-${group.statusVariant}` : '',
            { 'is-open': groupIsOpen(group) },
          ]"
        >
          <button
            class="navigator-group-head"
            type="button"
            :aria-expanded="groupIsOpen(group) ? 'true' : 'false'"
            @click="toggleGroup(group.key)"
          >
            <span class="navigator-group-dot" aria-hidden="true"></span>
            <span class="navigator-group-label v-section-label">{{ group.label }}</span>
            <span v-if="group.count" class="navigator-group-count">{{ group.count }}</span>
            <svg class="icon navigator-group-chevron" aria-hidden="true"><use href="#icon-chevron-right"/></svg>
          </button>

          <div class="navigator-group-body" :inert="groupIsOpen(group) ? undefined : ''">
            <div class="navigator-group-body-inner">
              <AppNavigatorRow
                v-for="item in visibleItems(group)"
                :key="item.key"
                :label="item.label"
                :icon="item.icon"
                :meta="item.meta"
                :tone="item.tone"
                :dot="item.dot"
                :active="item.active"
                @select="activate(item.run)"
              />

              <button
                v-if="hiddenCount(group)"
                class="navigator-more"
                type="button"
                @click="revealAll(group.key)"
              >
                Show {{ hiddenCount(group) }} more
              </button>

              <AppNavigatorTree
                v-if="group.tree"
                :key="context.key"
                :root-label="group.tree.rootLabel"
                :root-path="group.tree.rootPath"
                :active-path="group.tree.activePath"
                :load-items="group.tree.loadItems"
                :empty-label="group.tree.emptyLabel"
                @open-folder="(path) => activate(() => group.tree.openFolder(path))"
                @open-file="(item) => activate(() => group.tree.openFile(item))"
              />
            </div>
          </div>
        </section>

        <p v-if="!sections.length" class="navigator-empty">{{ context.emptyLabel || 'Nothing here yet' }}</p>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import AppNavigatorRow from './AppNavigatorRow.vue'
import AppNavigatorTree from './AppNavigatorTree.vue'
import { useContextNavigator } from '../../composables/useContextNavigator'

const GROUP_LIMIT = 8

const props = defineProps({
  variant: {
    type: String,
    default: 'rail',
    validator: (value) => ['rail', 'drawer'].includes(value),
  },
  collapsed: { type: Boolean, default: false },
})

const emit = defineEmits(['navigate'])

const { navigatorContext: context, isGroupOpen, toggleGroup } = useContextNavigator()

const expandedGroups = reactive(new Set())
const thumbFailed = ref(false)

const sections = computed(() => {
  if (!context.value) return []
  const groups = context.value.groups.map((group) => ({ ...group, count: group.items.length }))
  if (context.value.tree) {
    groups.push({
      key: 'tree',
      label: context.value.tree.label,
      tone: 'default',
      items: [],
      count: 0,
      tree: context.value.tree,
    })
  }
  return groups
})

const showThumb = computed(() => Boolean(context.value?.thumbnail) && !thumbFailed.value)

watch(() => context.value?.thumbnail, () => { thumbFailed.value = false })

function visibleItems(group) {
  if (expandedGroups.has(group.key)) return group.items
  return group.items.slice(0, GROUP_LIMIT)
}

function groupIsOpen(group) {
  return isGroupOpen(group.key, group.defaultOpen !== false)
}

function hiddenCount(group) {
  return group.items.length - visibleItems(group).length
}

function revealAll(key) {
  expandedGroups.add(key)
}

function activate(run) {
  run?.()
  emit('navigate')
}
</script>

<style scoped>
.app-navigator {
  width: var(--v-navigator-width);
  flex-shrink: 0;
  overflow: hidden;
  border-right: 1px solid var(--v-divider);
  background: color-mix(in srgb, var(--v-surface-panel) 34%, var(--v-bg-base));
  transition:
    width var(--v-duration-normal) var(--v-ease-emphasized),
    opacity var(--v-duration-fast) linear;
}

.app-navigator.is-collapsed {
  width: 0;
  border-right-width: 0;
  opacity: 0;
}

.navigator-inner {
  display: flex;
  flex-direction: column;
  width: var(--v-navigator-width);
  height: 100%;
  min-height: 0;
}

.navigator-head {
  display: flex;
  align-items: center;
  height: var(--v-shell-header-height);
  padding: 0 8px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--v-divider);
}

.navigator-scope {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  align-items: center;
  gap: 9px;
  width: 100%;
  min-width: 0;
  padding: 4px 6px;
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-scope:hover {
  background: var(--v-bg-hover);
}

.navigator-scope:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: -2px;
}

.navigator-scope-mark {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  overflow: hidden;
  border-radius: var(--v-radius-sm);
  background: var(--v-surface-inline);
  color: var(--v-accent);
}

.navigator-scope-mark.has-thumb {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, white 8%, transparent);
}

.navigator-scope-mark img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.navigator-scope-mark .icon {
  width: 15px;
  height: 15px;
}

.navigator-scope-copy {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}


.navigator-title {
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 650;
  line-height: 1.25;
}

.navigator-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-height: 0;
  padding: 10px 10px 24px;
  overflow-y: auto;
  overscroll-behavior: contain;
  mask-image: linear-gradient(to bottom, #000 0, #000 calc(100% - 22px), transparent 100%);
  -webkit-mask-image: linear-gradient(to bottom, #000 0, #000 calc(100% - 22px), transparent 100%);
}

.navigator-back {
  display: flex;
  align-items: center;
  gap: 6px;
  align-self: flex-start;
  margin-bottom: 6px;
  padding: 3px 8px 3px 5px;
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: var(--v-text-dim);
  font-size: var(--v-text-xs);
  font-weight: 600;
  cursor: pointer;
  transition:
    color var(--v-duration-fast) var(--v-ease-soft),
    background var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-back:hover {
  color: var(--v-text);
  background: var(--v-bg-hover);
}

.navigator-back .icon {
  width: 12px;
  height: 12px;
  transition: transform var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-back:hover .icon {
  transform: translateX(-2px);
}

.navigator-section {
  --navigator-section-tone: var(--v-text-dim);
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.navigator-section + .navigator-section {
  margin-top: 9px;
}

.navigator-section.is-tone-accent {
  --navigator-section-tone: var(--v-accent);
}

.navigator-section.is-tone-page {
  --navigator-section-tone: var(--v-page);
}

.navigator-section.is-status-active { --navigator-section-tone: var(--v-status-active); }
.navigator-section.is-status-review { --navigator-section-tone: var(--v-status-review); }
.navigator-section.is-status-hold { --navigator-section-tone: var(--v-status-hold); }
.navigator-section.is-status-draft { --navigator-section-tone: var(--v-status-draft); }
.navigator-section.is-status-done { --navigator-section-tone: var(--v-status-done); }

.navigator-group-head {
  display: grid;
  grid-template-columns: 15px minmax(0, 1fr) auto 14px;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
  height: 26px;
  padding: 0 4px 0 3px;
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: var(--v-text-dim);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    color var(--v-duration-fast) var(--v-ease-soft),
    background var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-group-head:hover {
  color: var(--v-text-secondary);
  background: var(--v-bg-hover);
}

.navigator-group-head:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: -2px;
}

.navigator-group-dot {
  justify-self: center;
  width: 5px;
  height: 5px;
  border-radius: var(--v-radius-full);
  background: var(--navigator-section-tone);
  opacity: 0.55;
  transition: opacity var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-section.is-open .navigator-group-dot,
.navigator-group-head:hover .navigator-group-dot {
  opacity: 1;
}


.navigator-group-count {
  color: var(--v-text-dim);
  font-size: var(--v-text-2xs);
  font-variant-numeric: tabular-nums;
  opacity: 0.5;
}

.navigator-group-chevron {
  width: 11px;
  height: 11px;
  opacity: 0.5;
  transition: transform var(--v-duration-normal) var(--v-ease-emphasized);
}

.navigator-section.is-open .navigator-group-chevron {
  transform: rotate(90deg);
}

.navigator-group-body {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows var(--v-duration-normal) var(--v-ease-emphasized);
}

.navigator-section.is-open .navigator-group-body {
  grid-template-rows: 1fr;
}

.navigator-group-body-inner {
  overflow: hidden;
  opacity: 0;
  transition: opacity var(--v-duration-normal) var(--v-ease-soft);
}

.navigator-section.is-open .navigator-group-body-inner {
  opacity: 1;
}

.navigator-more {
  margin: 2px 0 0 20px;
  padding: 2px 6px;
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: var(--v-text-dim);
  font: inherit;
  font-size: var(--v-text-xs);
  cursor: pointer;
  transition:
    color var(--v-duration-fast) var(--v-ease-soft),
    background var(--v-duration-fast) var(--v-ease-soft);
}

.navigator-more:hover {
  color: var(--v-text);
  background: var(--v-bg-hover);
}

.navigator-empty {
  margin: 0;
  padding: 0 6px;
  color: var(--v-text-dim);
  font-size: var(--v-text-xs);
}

.app-navigator.is-drawer {
  width: 100%;
  border-right: 0;
  background: transparent;
}

.app-navigator.is-drawer .navigator-inner {
  width: 100%;
  height: auto;
}

.app-navigator.is-drawer .navigator-head {
  height: auto;
  padding: 0 0 8px;
  border-bottom: 0;
}

.app-navigator.is-drawer .navigator-body {
  padding: 0;
  overflow: visible;
  mask-image: none;
  -webkit-mask-image: none;
}

@media (prefers-reduced-motion: reduce) {
  .app-navigator,
  .navigator-group-body,
  .navigator-group-body-inner,
  .navigator-group-chevron,
  .navigator-back .icon {
    transition: none;
  }
}
</style>
