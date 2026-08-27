<template>
  <div
    ref="rootRef"
    class="tracker-inline-select"
    :class="[
      `is-${tone}`,
      {
        'is-open': open,
        'is-readonly': !interactive,
        'is-highlighted': highlighted,
        'is-accented': !!accent,
      },
    ]"
    :style="accentStyle"
  >
    <component
      :is="interactive ? 'button' : 'div'"
      ref="triggerRef"
      class="tracker-inline-select-trigger v-control-pill"
      :type="interactive ? 'button' : undefined"
      :aria-haspopup="interactive ? 'menu' : undefined"
      :aria-expanded="interactive ? String(open) : undefined"
      :aria-label="interactive ? triggerAriaLabel : undefined"
      @click.stop="interactive && $emit('trigger', $event)"
      @keydown="handleTriggerKeydown"
    >
      <span v-if="$slots.leading" class="tracker-inline-select-leading"><slot name="leading" /></span>
      <span class="tracker-inline-select-label"><slot>{{ label }}</slot></span>
      <span v-if="$slots.meta" class="tracker-inline-select-meta"><slot name="meta" /></span>
      <svg v-if="showChevron && interactive" class="icon tracker-inline-select-chevron"><use href="#icon-chevron-down" /></svg>
    </component>

    <Transition name="v-menu-pop">
      <div
        v-if="open"
        ref="menuRef"
        class="tracker-inline-select-menu v-menu-panel"
        :class="{ 'is-flipped': flipUp }"
        role="menu"
        :aria-label="menuAriaLabel"
        @click.stop
        @keydown="handleMenuKeydown"
      >
        <slot name="menu" />
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { useOutsideClick } from '../../composables/useOutsideClick'

const props = defineProps({
  label: { type: String, default: '' },
  tone: { type: String, default: 'default' },
  open: { type: Boolean, default: false },
  flipUp: { type: Boolean, default: false },
  interactive: { type: Boolean, default: true },
  showChevron: { type: Boolean, default: true },
  highlighted: { type: Boolean, default: false },
  // Hue this control reflects (e.g. a shot status). Drives the pill tint and the
  // leading dot's halo, so every surface renders the same value identically.
  accent: { type: String, default: '' },
  accentText: { type: String, default: '' },
})

const emit = defineEmits(['trigger', 'close'])

const accentStyle = computed(() => {
  if (!props.accent) return null
  return {
    '--tracker-select-accent': props.accent,
    '--tracker-select-accent-text': props.accentText || 'var(--v-text-secondary)',
  }
})

const fieldLabel = computed(() => ({
  status: 'Status',
  category: 'Tag',
  assignee: 'Assignee',
})[props.tone] || '')

const triggerAriaLabel = computed(() => {
  if (!fieldLabel.value) return props.label
  if (props.label.trim().toLowerCase() === fieldLabel.value.toLowerCase()) return fieldLabel.value
  return `${fieldLabel.value}: ${props.label}`
})

const menuAriaLabel = computed(() => `${fieldLabel.value || props.label} options`)

const menuRef = ref(null)
const triggerRef = ref(null)
const rootRef = ref(null)

useOutsideClick(rootRef, handleDismiss, {
  enabled: () => props.open,
  escape: true,
})

function menuItems() {
  return Array.from(menuRef.value?.querySelectorAll('button:not([disabled]), [role="menuitem"]:not([aria-disabled="true"])') || [])
}

function focusItem(direction) {
  const items = menuItems()
  if (!items.length) return
  const current = items.indexOf(document.activeElement)
  const index = direction === 'first'
    ? 0
    : direction === 'last'
      ? items.length - 1
      : direction === 'next'
        ? (current + 1 + items.length) % items.length
        : (current - 1 + items.length) % items.length
  items[index]?.focus({ preventScroll: true })
}

async function handleTriggerKeydown(event) {
  if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return
  event.preventDefault()
  if (!props.open) {
    emit('trigger', event)
    await nextTick()
  }
  focusItem(event.key === 'ArrowDown' ? 'first' : 'last')
}

function handleMenuKeydown(event) {
  const directions = { ArrowDown: 'next', ArrowUp: 'previous', Home: 'first', End: 'last' }
  if (directions[event.key]) {
    event.preventDefault()
    focusItem(directions[event.key])
    return
  }
}

function handleDismiss(event, reason) {
  if (reason === 'escape') event.preventDefault()
  emit('close', event)
  if (reason === 'escape') nextTick(() => triggerRef.value?.focus({ preventScroll: true }))
}
</script>

<style scoped>
.tracker-inline-select {
  position: relative;
  width: 100%;
  --tracker-select-gap: var(--v-space-2);
  --tracker-select-leading-size: 14px;
}

.tracker-inline-select-trigger {
  width: 100%;
  display: inline-flex;
  align-items: center;
  gap: var(--tracker-select-gap);
  justify-content: flex-start;
}

button.tracker-inline-select-trigger {
  cursor: pointer;
}

/* ─── Tone system ────────────────────────────────────────────
   Status carries the colour; tag and assignee stay quiet, so a column of
   these reads as one status stripe rather than three equal boxes. Shared by
   the tracker rows and the media viewer topbar. */
.tracker-inline-select.is-status.is-accented .tracker-inline-select-trigger {
  background: color-mix(in srgb, var(--tracker-select-accent) 12%, var(--v-control-bg));
  border-color: color-mix(in srgb, var(--tracker-select-accent) 26%, transparent);
  color: var(--tracker-select-accent-text);
  font-weight: 650;
}

.tracker-inline-select.is-status.is-accented button.tracker-inline-select-trigger:hover {
  background: color-mix(in srgb, var(--tracker-select-accent) 18%, var(--v-control-bg));
  border-color: color-mix(in srgb, var(--tracker-select-accent) 38%, transparent);
}

/* Slotted dot, so it needs :deep to cross the scope boundary. */
.tracker-inline-select.is-status.is-accented :deep(.tracker-inline-select-leading > *) {
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--tracker-select-accent) 22%, transparent);
}

.tracker-inline-select.is-category .tracker-inline-select-trigger,
.tracker-inline-select.is-assignee .tracker-inline-select-trigger {
  background: color-mix(in srgb, var(--v-control-bg) 72%, transparent);
  border-color: color-mix(in srgb, var(--v-control-border) 80%, transparent);
  color: var(--v-text-secondary);
}

.tracker-inline-select.is-category button.tracker-inline-select-trigger:hover,
.tracker-inline-select.is-assignee button.tracker-inline-select-trigger:hover {
  background: var(--v-control-bg-hover);
  border-color: var(--v-control-border-hover);
  color: var(--v-text);
}

.tracker-inline-select.is-open .tracker-inline-select-trigger,
button.tracker-inline-select-trigger:focus-visible {
  box-shadow: 0 0 0 3px var(--v-accent-muted);
}

.tracker-inline-select.is-highlighted .tracker-inline-select-trigger {
  color: var(--v-text);
}

.tracker-inline-select.is-readonly .tracker-inline-select-trigger {
  cursor: default;
  color: var(--v-text-secondary);
}

.tracker-inline-select-leading,
.tracker-inline-select-meta,
.tracker-inline-select-chevron {
  flex-shrink: 0;
}

.tracker-inline-select-leading {
  width: var(--tracker-select-leading-size);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.tracker-inline-select-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--v-text-base);
  font-weight: 600;
  text-align: left;
}

.tracker-inline-select-meta {
  font-size: var(--v-text-2xs);
  color: var(--v-text-muted);
}

.tracker-inline-select-chevron {
  width: 12px;
  height: 12px;
  color: var(--v-text-muted);
}

.tracker-inline-select-menu {
  position: absolute;
  z-index: var(--v-z-dropdown);
  top: calc(100% + 8px);
  left: 0;
  min-width: 220px;
  max-width: min(320px, calc(100vw - 32px));
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px;
}

.tracker-inline-select-menu.is-flipped {
  top: auto;
  bottom: calc(100% + 8px);
}

.tracker-inline-select.tracker-assignee-select .tracker-inline-select-menu {
  right: 0;
  left: auto;
}

@media (max-width: 768px) {
  .tracker-inline-select-menu {
    min-width: min(220px, calc(100vw - 24px));
    max-width: min(280px, calc(100vw - 24px));
  }
}
</style>
