<template>
  <div
    class="nav-row"
    :class="[`is-tone-${tone}`, { 'is-active': active, 'is-open': expanded }]"
  >
    <span class="nav-row-marker" aria-hidden="true"></span>

    <button
      v-if="expandable"
      class="nav-row-twisty"
      :class="{ 'is-loading': loading }"
      type="button"
      :aria-label="expanded ? `Collapse ${label}` : `Expand ${label}`"
      :aria-expanded="expanded ? 'true' : 'false'"
      @click.stop="$emit('toggle')"
    >
      <svg class="icon"><use href="#icon-chevron-right"/></svg>
    </button>
    <span v-else class="nav-row-twisty is-empty" aria-hidden="true"></span>

    <button
      class="nav-row-main"
      type="button"
      :aria-current="active ? 'page' : undefined"
      @click="$emit('select')"
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
})

defineEmits(['select', 'toggle'])
</script>

<style scoped>
.nav-row {
  --nav-row-tone: var(--v-text-dim);
  --nav-row-marker: var(--v-accent);
  position: relative;
  display: grid;
  grid-template-columns: 15px minmax(0, 1fr);
  align-items: center;
  min-width: 0;
  border-radius: var(--v-radius-sm);
  color: var(--v-text-secondary);
  transition:
    background var(--v-duration-fast) var(--v-ease-soft),
    color var(--v-duration-fast) var(--v-ease-soft);
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
  background: color-mix(in srgb, var(--nav-row-marker) 11%, transparent);
}

.nav-row-marker {
  position: absolute;
  left: -5px;
  top: 50%;
  width: 2px;
  height: 15px;
  border-radius: var(--v-radius-full);
  background: var(--nav-row-marker);
  transform: translateY(-50%) scaleY(0);
  opacity: 0;
  transition:
    transform var(--v-duration-normal) var(--v-ease-emphasized),
    opacity var(--v-duration-fast) linear;
}

.nav-row.is-active .nav-row-marker {
  transform: translateY(-50%) scaleY(1);
  opacity: 1;
}

.nav-row-twisty {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 15px;
  height: 20px;
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
  height: 26px;
  padding: 0 7px 0 3px;
  border: 0;
  border-radius: var(--v-radius-sm);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform var(--v-duration-fast) var(--v-ease-soft);
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
  color: color-mix(in srgb, var(--nav-row-tone) 50%, var(--v-text-dim));
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
  font-size: var(--v-text-sm);
  font-weight: 500;
  line-height: 1.2;
  transition: color var(--v-duration-fast) var(--v-ease-soft);
}

.nav-row.is-active .nav-row-label {
  font-weight: 640;
}

.nav-row-meta {
  color: var(--v-text-dim);
  font-size: var(--v-text-2xs);
  font-variant-numeric: tabular-nums;
  opacity: 0.38;
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
  .nav-row-main,
  .nav-row-marker,
  .nav-row-twisty .icon {
    transition: none;
  }

  .nav-row-twisty.is-loading .icon {
    animation: none;
  }
}
</style>
