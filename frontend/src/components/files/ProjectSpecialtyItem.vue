<template>
  <div
    class="v-card v-card-interactive project-specialty-item"
    :class="[`is-${kind}`, { 'has-open-menu': menuOpen }]"
  >
    <button
      type="button"
      class="project-specialty-activation"
      :aria-label="activationLabel"
      @click="$emit('activate', item)"
    >
      <span class="project-specialty-tile" aria-hidden="true">
        <svg class="icon project-specialty-icon"><use :href="iconHref" /></svg>
      </span>
      <span class="project-specialty-copy">
        <span class="v-truncate project-specialty-title" :title="item.name">{{ item.name }}</span>
        <span class="project-specialty-meta">
          <span class="v-truncate">{{ meta || kindLabel }}</span>
          <time
            v-if="activityAt"
            class="project-specialty-activity"
            :datetime="activityDateTime"
            :title="activityTitle"
          >Active {{ activityLabel }}</time>
        </span>
      </span>
    </button>
    <span v-if="$slots.actions" class="project-specialty-tail">
      <slot name="actions" />
    </span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import {
  formatActivityAbsoluteTimestamp,
  formatActivityRelativeTimestamp,
  formatIsoTimestamp,
} from '../../utils/formatters'

const props = defineProps({
  item: { type: Object, required: true },
  kind: {
    type: String,
    default: 'tracker',
    validator: (value) => ['dashboard', 'tracker'].includes(value),
  },
  meta: { type: String, default: '' },
  activityAt: { type: [Number, String], default: null },
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

const activityLabel = computed(() => formatActivityRelativeTimestamp(props.activityAt))
const activityTitle = computed(() => formatActivityAbsoluteTimestamp(props.activityAt))
const activityDateTime = computed(() => formatIsoTimestamp(props.activityAt))
const activationLabel = computed(() => [
  `Open ${props.item.name}`,
  `${kindLabel.value}${props.meta ? `, ${props.meta}` : ''}`,
  activityLabel.value ? `last activity ${activityLabel.value}` : '',
].filter(Boolean).join(', '))
</script>

<style scoped>
.project-specialty-item {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: stretch;
  min-width: 0;
  min-height: 56px;
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
  grid-template-columns: 32px minmax(0, 1fr);
  align-items: center;
  gap: 11px;
  min-width: 0;
  min-height: 54px;
  padding: 10px 4px 10px 12px;
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

/* Same tile as the folder cards; the tint names the asset kind. */
.project-specialty-tile {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--v-radius-sm);
  background: color-mix(in srgb, var(--v-text) 5%, transparent);
}

.project-specialty-icon {
  width: 16px;
  height: 16px;
  color: var(--v-text-secondary);
}

.is-tracker .project-specialty-tile {
  background: var(--v-accent-muted);
}

.is-tracker .project-specialty-icon {
  color: var(--v-accent);
}

.is-dashboard .project-specialty-tile {
  background: color-mix(in srgb, var(--v-page) 16%, transparent);
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
  font-size: var(--v-text-base);
  font-weight: 600;
  line-height: 1.3;
}

.project-specialty-meta {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.35;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.project-specialty-activity {
  flex: 0 0 auto;
}

.project-specialty-activity::before {
  content: "·";
  margin-right: 6px;
  opacity: 0.55;
}

.project-specialty-tail {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  min-width: 34px;
  transition: opacity var(--v-duration-normal) var(--v-ease-soft);
}

/* With a pointer, the overflow menu waits for hover like the folder cards. */
@media (hover: hover) {
  .project-specialty-item:not(:hover, :focus-within, .has-open-menu) .project-specialty-tail {
    opacity: 0;
  }
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
