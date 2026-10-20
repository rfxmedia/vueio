<template>
  <div
    class="v-card v-card-interactive project-specialty-item"
    :class="[`is-${kind}`, { 'has-open-menu': menuOpen, 'has-actions': $slots.actions }]"
  >
    <button
      type="button"
      class="project-specialty-activation"
      :aria-label="activationLabel"
      @click="$emit('activate', item)"
    >
      <span class="project-specialty-head">
        <span class="project-specialty-tile" aria-hidden="true">
          <svg class="icon project-specialty-icon"><use :href="iconHref" /></svg>
        </span>
        <span class="project-specialty-title" :title="item.name">{{ item.name }}</span>
      </span>
      <span v-if="description" class="project-specialty-description" :title="description">{{ description }}</span>
      <span class="project-specialty-meta">
        <span v-if="progress" class="project-specialty-progress" :class="{ 'is-complete': progress.complete }" :title="progress.title">
          <svg class="project-specialty-ring" viewBox="0 0 16 16" aria-hidden="true">
            <circle class="project-specialty-ring-track" cx="8" cy="8" r="6" />
            <circle
              class="project-specialty-ring-fill"
              cx="8"
              cy="8"
              r="6"
              pathLength="100"
              :stroke-dasharray="`${progress.percent} 100`"
            />
          </svg>
          {{ progress.label }}
        </span>
        <span v-else>{{ countLabel }}</span>
        <time v-if="createdLabel" :datetime="createdDateTime" :title="createdTitle">Created {{ createdLabel }}</time>
        <time v-if="activityAt" :datetime="activityDateTime" :title="activityTitle">Active {{ activityLabel }}</time>
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
  formatLocaleDate,
  toDate,
} from '../../utils/formatters'

const props = defineProps({
  item: { type: Object, required: true },
  kind: {
    type: String,
    default: 'tracker',
    validator: (value) => ['dashboard', 'tracker'].includes(value),
  },
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

const description = computed(() => String(props.item.description || '').trim())

const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`

// Trackers with shots show a progress ring; the count covers everything else.
const progress = computed(() => {
  const total = Number(props.item.shot_count) || 0
  if (props.kind !== 'tracker' || total === 0) return null
  const done = Math.min(Number(props.item.done_count) || 0, total)
  return {
    percent: Math.round((done / total) * 100),
    complete: done === total,
    label: `${done}/${total} done`,
    title: `${done} of ${plural(total, 'shot')} done`,
  }
})

const countLabel = computed(() => (
  props.kind === 'dashboard' ? plural(Number(props.item.block_count) || 0, 'block') : 'No shots yet'
))

// The year only appears when it is not the current one.
const createdLabel = computed(() => {
  const date = toDate(props.item.created_at, { unit: 'seconds' })
  if (!date) return ''
  const sameYear = date.getFullYear() === new Date().getFullYear()
  return formatLocaleDate(props.item.created_at, {
    unit: 'seconds',
    options: { month: 'short', day: 'numeric', ...(sameYear ? {} : { year: 'numeric' }) },
  })
})
const createdTitle = computed(() => formatActivityAbsoluteTimestamp(props.item.created_at))
const createdDateTime = computed(() => formatIsoTimestamp(props.item.created_at))
const activityLabel = computed(() => formatActivityRelativeTimestamp(props.activityAt))
const activityTitle = computed(() => formatActivityAbsoluteTimestamp(props.activityAt))
const activityDateTime = computed(() => formatIsoTimestamp(props.activityAt))
const activationLabel = computed(() => [
  `Open ${props.item.name}`,
  kindLabel.value,
  description.value,
  progress.value?.title || countLabel.value,
  createdLabel.value ? `created ${createdLabel.value}` : '',
  activityLabel.value ? `last activity ${activityLabel.value}` : '',
].filter(Boolean).join(', '))
</script>

<style scoped>
.project-specialty-item {
  position: relative;
  display: flex;
  min-width: 0;
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
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding: 11px 12px;
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

.project-specialty-head {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}

.has-actions .project-specialty-head {
  padding-right: 24px;
}

/* Same tile as the folder cards; the tint names the asset kind. */
.project-specialty-tile {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: var(--v-radius-sm);
  background: color-mix(in srgb, var(--v-text) 5%, transparent);
}

.project-specialty-icon {
  width: 14px;
  height: 14px;
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

/* Long names wrap to a second line before they clip. */
.project-specialty-title,
.project-specialty-description {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  overflow-wrap: anywhere;
}

.project-specialty-title {
  min-width: 0;
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 600;
  line-height: 1.3;
}

.project-specialty-description {
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  line-height: 1.45;
}

/* Pinned to the bottom so the detail lines match across a row. */
.project-specialty-meta {
  display: flex;
  align-items: center;
  column-gap: 6px;
  min-width: 0;
  margin-top: auto;
  padding-top: 4px;
  overflow: hidden;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.35;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.project-specialty-meta > * + *::before {
  content: "·";
  margin-right: 6px;
  opacity: 0.55;
}

.project-specialty-meta > :last-child {
  overflow: hidden;
  text-overflow: ellipsis;
}

.project-specialty-progress {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--v-text-secondary);
}

.project-specialty-ring {
  width: 13px;
  height: 13px;
  flex: 0 0 auto;
  transform: rotate(-90deg);
}

.project-specialty-ring circle {
  fill: none;
  stroke-width: 2.25;
}

.project-specialty-ring-track {
  stroke: color-mix(in srgb, var(--v-text) 14%, transparent);
}

.project-specialty-ring-fill {
  stroke: var(--v-status-done);
  stroke-linecap: round;
}

/* Zero progress keeps a clean empty ring instead of a round-cap dot. */
.project-specialty-ring-fill[stroke-dasharray^="0 "] {
  stroke: transparent;
}

.project-specialty-progress.is-complete {
  color: var(--v-status-done-text);
}

.project-specialty-tail {
  position: absolute;
  top: 7px;
  right: 6px;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
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
