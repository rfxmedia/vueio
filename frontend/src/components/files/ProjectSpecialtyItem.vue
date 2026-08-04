<template>
  <div
    class="v-card v-card-interactive project-specialty-item"
    :class="[`is-${kind}`, { 'has-open-menu': menuOpen }]"
  >
    <button
      type="button"
      class="project-specialty-activation"
      :aria-label="`Open ${item.name}`"
      @click="$emit('activate', item)"
    >
      <svg class="icon project-specialty-icon" aria-hidden="true"><use :href="iconHref" /></svg>
      <span class="project-specialty-copy">
        <span class="v-truncate project-specialty-title" :title="item.name">{{ item.name }}</span>
        <span class="v-truncate project-specialty-meta">{{ kindLabel }}<template v-if="meta"> · {{ meta }}</template></span>
      </span>
    </button>
    <span v-if="$slots.actions" class="project-specialty-tail">
      <slot name="actions" />
    </span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  item: { type: Object, required: true },
  kind: {
    type: String,
    default: 'tracker',
    validator: (value) => ['dashboard', 'tracker'].includes(value),
  },
  meta: { type: String, default: '' },
  menuOpen: { type: Boolean, default: false },
})

defineEmits(['activate'])

const kindLabel = computed(() => ({
  dashboard: 'Dashboard',
  tracker: 'Tracker',
})[props.kind])

const iconHref = computed(() => ({
  dashboard: '#icon-layout',
  tracker: '#icon-project',
})[props.kind])
</script>

<style scoped>
.project-specialty-item {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: stretch;
  min-width: 0;
  min-height: 52px;
  overflow: hidden;
  border-color: color-mix(in srgb, var(--v-control-border) 72%, transparent);
  background: var(--v-surface-tint-strong);
  box-shadow: none;
}

.project-specialty-item:hover {
  border-color: var(--v-control-border-hover);
  background: var(--v-surface-inline-strong);
}

.project-specialty-item.has-open-menu {
  z-index: 50;
  overflow: visible;
}

.project-specialty-activation {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: center;
  gap: 9px;
  min-width: 0;
  min-height: 50px;
  padding: 7px 8px 7px 10px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.project-specialty-activation:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: -2px;
}

.project-specialty-icon {
  width: 16px;
  height: 16px;
  color: var(--v-text-secondary);
}

.is-tracker .project-specialty-icon {
  color: var(--v-accent);
}

.is-dashboard .project-specialty-icon {
  color: color-mix(in srgb, var(--v-page) 82%, white);
}

.project-specialty-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.project-specialty-title {
  color: var(--v-text);
  font-size: var(--v-text-sm);
  font-weight: 650;
  line-height: 1.2;
}

.project-specialty-meta {
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

.project-specialty-tail {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  min-width: 34px;
}

.project-specialty-item.dragging {
  opacity: 0.5;
}

.project-specialty-item[draggable="true"] {
  cursor: grab;
}

.project-specialty-item[draggable="true"]:active {
  cursor: grabbing;
}
</style>
