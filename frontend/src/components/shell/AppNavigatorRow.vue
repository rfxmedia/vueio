<template>
  <div
    class="nav-row"
    :class="[
      `is-tone-${tone}`,
      { 'has-status': statusVariant },
      { 'is-active': active, 'is-open': expanded, 'is-selected': selected, 'is-dragging': dragging, 'has-thumbnail': thumbnail || showThumbnail, 'is-selectable': selectionMode },
    ]"
    @click.self="$emit('select', $event)"
    @dblclick.self="selectionMode && !$event.shiftKey && !$event.metaKey && !$event.ctrlKey && $emit('open')"
  >
    <button
      v-if="expandable"
      class="nav-row-twisty"
      :class="{ 'is-loading': loading }"
      type="button"
      :aria-label="expanded ? `Collapse ${label}` : `Expand ${label}`"
      :aria-expanded="expanded ? 'true' : 'false'"
      :aria-busy="loading ? 'true' : undefined"
      @click.stop="$emit('toggle')"
    >
      <svg class="icon"><use href="#icon-chevron-right"/></svg>
    </button>
    <span v-else-if="!statusVariant" class="nav-row-twisty is-empty" aria-hidden="true"></span>

    <button
      class="nav-row-main"
      type="button"
      :draggable="draggable"
      :aria-current="active ? 'page' : undefined"
      :aria-label="meta ? `${label}, ${meta}` : undefined"
      :aria-pressed="selectionMode ? selected : undefined"
      @dblclick="selectionMode && !$event.shiftKey && !$event.metaKey && !$event.ctrlKey && $emit('open')"
      @keydown.enter.prevent="selectionMode ? $emit('open') : $emit('select', $event)"
      @mousedown.shift.prevent
      @click="$emit('select', $event)"
      @dragstart="$emit('dragstart', $event)"
      @dragend="$emit('dragend', $event)"
    >
      <span v-if="thumbnail || showThumbnail" class="nav-row-thumbnail" aria-hidden="true">
        <VMediaThumbnail v-if="thumbnail" :src="thumbnail" />
        <VFileTypeGlyph v-else-if="fileVisual" :visual="fileVisual" compact thumbnail />
        <svg v-else class="icon nav-row-icon"><use :href="icon" /></svg>
      </span>
      <svg v-else-if="!statusVariant" class="icon nav-row-icon" aria-hidden="true"><use :href="icon"/></svg>
      <span class="nav-row-label v-truncate" :title="label">{{ label }}</span>
    </button>
    <span v-if="meta" class="nav-row-meta" aria-hidden="true">{{ meta }}</span>
    <button
      v-if="selectionMode"
      type="button"
      class="nav-row-open"
      :aria-label="`Open ${label}`"
      :title="`Open ${label}`"
      @click.stop="$emit('open')"
    ><svg class="icon" aria-hidden="true"><use :href="expandable ? '#icon-chevron-right' : '#icon-play'" /></svg></button>
  </div>
</template>

<script setup>
import VMediaThumbnail from '../media/VMediaThumbnail.vue'
import VFileTypeGlyph from '../files/VFileTypeGlyph.vue'

defineProps({
  label: { type: String, required: true },
  icon: { type: String, default: '#icon-folder' },
  meta: { type: String, default: '' },
  tone: {
    type: String,
    default: 'default',
    validator: (value) => ['default', 'accent', 'page'].includes(value),
  },
  statusVariant: { type: String, default: '' },
  active: { type: Boolean, default: false },
  expandable: { type: Boolean, default: false },
  expanded: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
  draggable: { type: Boolean, default: false },
  dragging: { type: Boolean, default: false },
  thumbnail: { type: String, default: '' },
  showThumbnail: { type: Boolean, default: false },
  fileVisual: { type: Object, default: null },
  selectionMode: { type: Boolean, default: false },
})

defineEmits(['select', 'open', 'toggle', 'dragstart', 'dragend'])
</script>

<style scoped>
.nav-row {
  --nav-row-tone: var(--v-text-dim);
  --nav-row-marker: var(--v-accent);
  --nav-row-height: var(--navigator-row-height, 32px);
  position: relative;
  display: grid;
  grid-template-columns: var(--navigator-disclosure-width, 24px) minmax(0, 1fr) auto;
  grid-template-areas: 'disclosure main trailing';
  align-items: center;
  min-width: 0;
  min-height: var(--nav-row-height);
  padding-right: var(--v-space-2);
  border-radius: var(--v-radius-sm);
  color: var(--v-text-secondary);
  transition:
    background var(--v-duration-fast) var(--v-ease-soft),
    box-shadow var(--v-duration-fast) var(--v-ease-soft),
    color var(--v-duration-fast) var(--v-ease-soft);
}

/* The active marker grows in from the row centre. */
.nav-row::before {
  content: '';
  position: absolute;
  left: 2px;
  top: 50%;
  width: 3px;
  height: 14px;
  margin-top: -7px;
  border-radius: var(--v-radius-full);
  background: var(--nav-row-marker);
  opacity: 0;
  transform: scaleY(0.4);
  transition:
    opacity var(--v-duration-fast) linear,
    transform var(--v-duration-normal) var(--v-ease-emphasized);
}

.nav-row.is-tone-accent {
  --nav-row-tone: var(--v-accent);
}

.nav-row.is-tone-page {
  --nav-row-tone: var(--v-page);
  --nav-row-marker: var(--v-page);
}

.nav-row:hover {
  background: var(--v-bg-hover);
}

.nav-row:hover,
.nav-row:focus-within {
  color: var(--v-text);
}

.nav-row.is-active {
  color: var(--v-text);
  background: color-mix(in srgb, var(--nav-row-marker) 8%, var(--v-surface-inline));
}

.nav-row.is-active::before {
  opacity: 1;
  transform: scaleY(1);
}

.nav-row.is-selected {
  color: var(--v-text);
  background: color-mix(in srgb, var(--v-accent) 12%, var(--v-surface-inline));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-accent) 30%, transparent);
}

.nav-row.is-dragging {
  opacity: 0.5;
}

.nav-row.has-status {
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas: 'main trailing';
}

.nav-row.has-status .nav-row-main {
  padding-left: var(--v-space-2);
}

.nav-row.has-thumbnail {
  --nav-row-height: max(var(--navigator-row-height, 32px), 36px);
}

.nav-row-thumbnail {
  position: relative;
  display: grid;
  place-items: center;
  flex: 0 0 40px;
  width: 40px;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border-radius: 4px;
  background: var(--v-surface-inline);
  color: var(--v-text-muted);
}

/* A hairline frame keeps dark and light artwork crisp against the rail. */
.nav-row-thumbnail::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-text) 9%, transparent);
  pointer-events: none;
  transition: box-shadow var(--v-duration-fast) var(--v-ease-soft);
}

.nav-row.is-active .nav-row-thumbnail::after {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--nav-row-marker) 55%, transparent);
}

.nav-row-thumbnail :deep(.v-media-thumb-status .icon) {
  width: 12px;
  height: 12px;
}

.nav-row-twisty {
  grid-area: disclosure;
  display: flex;
  align-items: center;
  justify-content: center;
  align-self: stretch;
  width: 100%;
  min-height: var(--nav-row-height);
  padding: 0;
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: var(--v-text-muted);
  cursor: pointer;
  transition: color var(--v-duration-fast) var(--v-ease-soft);
}

.nav-row-twisty.is-empty {
  cursor: default;
}

.nav-row-twisty:hover {
  color: var(--v-text);
}

.nav-row-twisty:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: -2px;
  color: var(--v-text);
}

.nav-row-twisty .icon {
  width: 10px;
  height: 10px;
  transition: transform var(--v-duration-normal) var(--v-ease-emphasized);
}

.nav-row.is-open .nav-row-twisty .icon {
  transform: rotate(90deg);
}

.nav-row-twisty.is-loading .icon {
  animation: v-nav-row-pulse 1.1s ease-in-out infinite;
}

.nav-row-main {
  grid-area: main;
  display: flex;
  align-items: center;
  align-self: stretch;
  gap: var(--v-space-2);
  min-width: 0;
  min-height: var(--nav-row-height);
  padding: 0 var(--v-space-2) 0 0;
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.nav-row-main[draggable="true"] {
  cursor: grab;
}

.nav-row.is-dragging .nav-row-main {
  cursor: grabbing;
}

.nav-row-main:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: -2px;
}

.nav-row-icon {
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  color: color-mix(in srgb, var(--nav-row-tone) 62%, var(--v-text-muted));
  transition: color var(--v-duration-fast) var(--v-ease-soft);
}

.nav-row:hover .nav-row-icon,
.nav-row.is-active .nav-row-icon,
.nav-row.is-selected .nav-row-icon {
  color: var(--nav-row-tone);
}

.nav-row-label {
  flex: 1;
  min-width: 0;
  font-size: var(--navigator-row-font-size, var(--v-text-base));
  font-weight: 400;
  line-height: 1.4;
}

.nav-row.is-active .nav-row-label {
  font-weight: 550;
}

.nav-row-meta {
  grid-area: trailing;
  pointer-events: none;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  text-align: right;
}

/* In the file tree, the open action replaces the count on interaction. */
.nav-row-open {
  grid-area: trailing;
  display: grid;
  place-items: center;
  align-self: center;
  width: 24px;
  height: 24px;
  margin-right: -4px;
  padding: 0;
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: var(--v-text-dim);
  opacity: 0;
  pointer-events: none;
  cursor: pointer;
  transition:
    opacity var(--v-duration-fast) linear,
    color var(--v-duration-fast) var(--v-ease-soft),
    background var(--v-duration-fast) var(--v-ease-soft);
}

.nav-row-open .icon {
  width: 12px;
  height: 12px;
}

.nav-row:hover .nav-row-open,
.nav-row:focus-within .nav-row-open,
.nav-row.is-selected .nav-row-open {
  opacity: 1;
  pointer-events: auto;
}

.nav-row.is-selectable:hover .nav-row-meta,
.nav-row.is-selectable:focus-within .nav-row-meta,
.nav-row.is-selectable.is-selected .nav-row-meta {
  visibility: hidden;
}

.nav-row-open:hover {
  color: var(--v-text);
  background: color-mix(in srgb, var(--v-text) 9%, transparent);
}

.nav-row-open:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: -2px;
}

@keyframes v-nav-row-pulse {
  0%, 100% { opacity: 0.25; }
  50% { opacity: 0.85; }
}

@media (prefers-reduced-motion: reduce) {
  .nav-row,
  .nav-row::before,
  .nav-row-twisty,
  .nav-row-twisty .icon,
  .nav-row-icon,
  .nav-row-open,
  .nav-row-thumbnail::after {
    transition: none;
  }

  .nav-row-twisty.is-loading .icon {
    animation: none;
  }
}
</style>
