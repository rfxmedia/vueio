<template>
  <div class="navigator-item">
    <AppNavigatorRow
      :label="item.label"
      :icon="item.icon"
      :meta="item.meta"
      :tone="item.tone"
      :dot="item.dot"
      :active="item.active"
      :expandable="Boolean(item.loadChildren)"
      :expanded="expanded"
      :loading="loading"
      @select="$emit('select', item.run)"
      @toggle="toggle"
    />

    <div v-if="item.loadChildren" class="navigator-item-branch" :class="{ 'is-open': expanded }" :inert="expanded ? undefined : ''">
      <div class="navigator-item-branch-inner">
        <div class="navigator-item-children">
          <AppNavigatorRow
            v-for="child in children"
            :key="child.key"
            :label="child.label"
            :icon="child.icon"
            :meta="child.meta"
            :tone="child.tone || item.tone"
            :active="child.active"
            @select="$emit('select', child.run)"
          />

          <div v-if="archived.length" class="navigator-archive" :class="{ 'is-open': archiveExpanded }">
            <AppNavigatorRow
              label="Archived"
              icon="#icon-inbox"
              :meta="String(archived.length)"
              tone="default"
              expandable
              :expanded="archiveExpanded"
              @select="archiveExpanded = !archiveExpanded"
              @toggle="archiveExpanded = !archiveExpanded"
            />
            <div class="navigator-item-branch" :class="{ 'is-open': archiveExpanded }" :inert="archiveExpanded ? undefined : ''">
              <div class="navigator-item-branch-inner">
                <div class="navigator-item-children">
                  <AppNavigatorRow
                    v-for="child in archived"
                    :key="child.key"
                    :label="child.label"
                    :icon="child.icon"
                    :meta="child.meta"
                    tone="default"
                    :active="child.active"
                    @select="$emit('select', child.run)"
                  />
                </div>
              </div>
            </div>
          </div>

          <p v-if="loaded && !children.length && !archived.length" class="navigator-item-empty">No shots yet</p>
          <div v-if="failed" class="navigator-item-error">
            <span role="status">Shots unavailable</span>
            <button class="navigator-item-retry" type="button" @click="load">Retry</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import AppNavigatorRow from './AppNavigatorRow.vue'

const props = defineProps({
  item: { type: Object, required: true },
})

defineEmits(['select'])

const expanded = ref(false)
const archiveExpanded = ref(false)
const loading = ref(false)
const loaded = ref(false)
const failed = ref(false)
const children = ref([])
const archived = ref([])

async function load() {
  if (!props.item.loadChildren || loading.value) return
  loading.value = true
  failed.value = false
  try {
    const result = await props.item.loadChildren()
    children.value = result?.items || []
    archived.value = result?.archived || []
    loaded.value = true
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

function toggle() {
  expanded.value = !expanded.value
  if (expanded.value && !loaded.value) void load()
}
</script>

<style scoped>
.navigator-item-branch {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows var(--v-duration-normal) var(--v-ease-emphasized);
}

.navigator-item-branch.is-open {
  grid-template-rows: 1fr;
}

.navigator-item-branch-inner {
  overflow: hidden;
  opacity: 0;
  transform: translateY(-3px);
  transition:
    opacity var(--v-duration-normal) var(--v-ease-soft),
    transform var(--v-duration-normal) var(--v-ease-emphasized);
}

.navigator-item-branch.is-open > .navigator-item-branch-inner {
  opacity: 1;
  transform: translateY(0);
}

.navigator-item-children {
  margin-left: calc(var(--navigator-disclosure-width, 22px) / 2);
  padding-left: 5px;
  border-left: 1px solid color-mix(in srgb, var(--v-divider) 62%, transparent);
}

.navigator-archive {
  margin-top: 3px;
  padding-top: 3px;
  border-top: 1px solid color-mix(in srgb, var(--v-divider) 54%, transparent);
}

.navigator-item-empty {
  margin: 0;
  padding: 4px 7px 4px 20px;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-style: italic;
}

.navigator-item-error {
  display: flex;
  align-items: center;
  gap: 5px;
  min-height: 28px;
  padding: 2px 6px 2px 10px;
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
}

.navigator-item-retry {
  padding: 3px 7px;
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: var(--v-text-dim);
  font: inherit;
  font-size: var(--v-text-xs);
  cursor: pointer;
}

.navigator-item-retry:hover {
  color: var(--v-text);
  background: var(--v-bg-hover);
}

.navigator-item-retry:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: -2px;
}

@media (prefers-reduced-motion: reduce) {
  .navigator-item-branch,
  .navigator-item-branch-inner {
    transition: none;
    transform: none;
  }
}
</style>
