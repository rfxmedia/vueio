<template>
  <div
    class="nav-row"
    :class="[
      `is-tone-${tone}`,
      { 'is-active': active, 'is-open': expanded, 'is-selected': selected, 'is-dragging': dragging },
    ]"
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
    <span v-else class="nav-row-twisty is-empty" aria-hidden="true"></span>

    <button
      class="nav-row-main"
      type="button"
      :draggable="draggable"
      :aria-current="active ? 'page' : undefined"
      @click="$emit('select', $event)"
      @dragstart="$emit('dragstart', $event)"
      @dragend="$emit('dragend', $event)"
    >
      <span v-if="dot" class="nav-row-dot" :class="`is-${dot}`" aria-hidden="true"></span>
      <svg v-else class="icon nav-row-icon" aria-hidden="true"><use :href="icon"/></svg>
      <span class="nav-row-label v-truncate" :title="label">{{ label }}</span>
      <span v-if="meta" class="nav-row-meta">{{ meta }}</span>
    </button>
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  icon: { type: String, default: '#icon-folder' },
  meta: { type: String, default: '' },
  tone: {
    type: String,
    default: 'default',
    validator: (value) => ['default', 'accent', 'page'].includes(value),
  },
  dot: { type: String, default: '' },
  active: { type: Boolean, default: false },
  expandable: { type: Boolean, default: false },
  expanded: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
  draggable: { type: Boolean, default: false },
  dragging: { type: Boolean, default: false },
})

defineEmits(['select', 'toggle', 'dragstart', 'dragend'])
</script>

<style scoped>
.nav-row {
  --nav-row-tone: var(--v-text-dim);
  --nav-row-marker: var(--v-accent);
  position: relative;
  display: grid;
  grid-template-columns: var(--navigator-disclosure-width, 22px) minmax(0, 1fr);
  align-items: center;
  min-width: 0;
  min-height: var(--navigator-row-height, 30px);
  border: 1px solid transparent;
  border-radius: var(--v-radius-sm);
  color: var(--v-text-secondary);
  transition:
    background var(--v-duration-fast) var(--v-ease-soft),
    border-color var(--v-duration-fast) var(--v-ease-soft),
    color var(--v-duration-fast) var(--v-ease-soft);
}

.nav-row::before {
  content: '';
  position: absolute;
  left: 1px;
  top: 7px;
  bottom: 7px;
  width: 2px;
  border-radius: var(--v-radius-full);
  background: var(--nav-row-marker);
  opacity: 0;
  transform: scaleY(0.45);
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
  color: var(--v-text);
}

.nav-row.is-active {
  color: var(--v-text);
  border-color: color-mix(in srgb, var(--nav-row-marker) 12%, transparent);
  background: color-mix(in srgb, var(--nav-row-marker) 7%, var(--v-surface-inline));
}

.nav-row.is-selected {
  border-color: color-mix(in srgb, var(--v-accent) 24%, var(--v-control-border));
  background: var(--v-control-bg-active);
  box-shadow: var(--v-control-ring-selected);
  color: var(--v-text);
}

.nav-row.is-dragging {
  opacity: 0.58;
}

.nav-row.is-active::before {
  transform: scaleY(1);
  opacity: 1;
}

.nav-row-twisty {
  display: flex;
  align-items: center;
  justify-content: center;
  align-self: stretch;
  width: 100%;
  min-height: calc(var(--navigator-row-height, 30px) - 2px);
  padding: 0;
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: color-mix(in srgb, var(--v-text-dim) 68%, transparent);
  cursor: pointer;
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
  width: 11px;
  height: 11px;
  transition: transform var(--v-duration-normal) var(--v-ease-emphasized);
}

.nav-row.is-open .nav-row-twisty .icon {
  transform: rotate(90deg);
}

.nav-row-twisty.is-loading .icon {
  animation: v-nav-row-pulse 1.1s ease-in-out infinite;
}

.nav-row-main {
  display: grid;
  grid-template-columns: 15px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
  height: calc(var(--navigator-row-height, 30px) - 2px);
  padding: 0 8px 0 2px;
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform var(--v-duration-fast) var(--v-ease-soft);
}

.nav-row-main[draggable="true"] {
  cursor: grab;
}

.nav-row.is-dragging .nav-row-main {
  cursor: grabbing;
}

.nav-row-main:active {
  transform: scale(0.985);
}

.nav-row-main:focus-visible {
  outline: 2px solid var(--v-border-focus);
  outline-offset: -2px;
}

.nav-row-icon {
  width: 14px;
  height: 14px;
  color: color-mix(in srgb, var(--nav-row-tone) 58%, var(--v-text-dim));
  transition: color var(--v-duration-fast) var(--v-ease-soft);
}

.nav-row:hover .nav-row-icon,
.nav-row.is-active .nav-row-icon {
  color: var(--nav-row-tone);
}

.nav-row-dot {
  justify-self: center;
  width: 6px;
  height: 6px;
  border-radius: var(--v-radius-full);
  background: var(--v-status-draft);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-status-draft) 20%, transparent);
  transition: box-shadow var(--v-duration-fast) var(--v-ease-soft);
}

.nav-row-dot.is-active { background: var(--v-status-active); box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-status-active) 24%, transparent); }
.nav-row-dot.is-review { background: var(--v-status-review); box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-status-review) 24%, transparent); }
.nav-row-dot.is-done { background: var(--v-status-done); box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-status-done) 24%, transparent); }
.nav-row-dot.is-hold { background: var(--v-status-hold); box-shadow: 0 0 0 2px color-mix(in srgb, var(--v-status-hold) 24%, transparent); }

.nav-row-label {
  font-size: var(--navigator-row-font-size, var(--v-text-sm));
  font-weight: 540;
  line-height: 1.2;
  transition: color var(--v-duration-fast) var(--v-ease-soft);
}

.nav-row.is-active .nav-row-label {
  font-weight: 640;
}

.nav-row-meta {
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-variant-numeric: tabular-nums;
  opacity: 0.72;
  transition: opacity var(--v-duration-fast) var(--v-ease-soft);
}

.nav-row:hover .nav-row-meta,
.nav-row.is-active .nav-row-meta {
  opacity: 0.95;
}

@keyframes v-nav-row-pulse {
  0%, 100% { opacity: 0.25; }
  50% { opacity: 0.85; }
}

@media (prefers-reduced-motion: reduce) {
  .nav-row,
  .nav-row::before,
  .nav-row-main,
  .nav-row-twisty .icon {
    transition: none;
  }

  .nav-row-twisty.is-loading .icon {
    animation: none;
  }

  .nav-row-main:active {
    transform: none;
  }
}
</style>
