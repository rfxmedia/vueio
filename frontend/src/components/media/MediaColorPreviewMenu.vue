<template>
  <input ref="colorPreviewFileInput" type="file" accept=".cube" hidden @change="loadColorPreviewFile" />
  <VMenu
    :open="open"
    align="end"
    min-width="278"
    :teleport="true"
    panel-class="viewer-color-preview-menu"
    panel-label="Color preview"
    @update:open="open = $event"
  >
    <template #trigger="{ triggerProps }">
      <button
        v-bind="triggerProps"
        type="button"
        class="v-btn v-btn-quiet v-btn-icon viewer-color-preview-trigger"
        :class="{ active: open || colorPreviewSelection !== 'source' }"
        :aria-label="colorPreviewButtonLabel"
        @click.stop="open = !open"
      >
        <svg class="icon" aria-hidden="true"><use href="#icon-color"/></svg>
      </button>
    </template>
    <div class="viewer-color-preview-panel" :aria-busy="colorPreviewLoading">
      <div class="viewer-color-preview-heading">
        <span class="v-section-label">Color preview</span>
      </div>
      <button
        v-for="option in colorPreviewChoices"
        :key="option.value"
        type="button"
        class="v-dropdown-item viewer-color-preview-option"
        :class="{ active: option.value === colorPreviewSelection }"
        :disabled="option.value !== 'source' && colorPreviewLoading"
        role="menuitemradio"
        :aria-checked="option.value === colorPreviewSelection ? 'true' : 'false'"
        @click.stop="selectColorPreview(option.value)"
      >
        <span class="viewer-color-preview-option__copy">
          <span class="viewer-color-preview-option__label">{{ option.label }}</span>
          <span class="viewer-color-preview-option__hint">{{ option.hint }}</span>
        </span>
        <svg v-if="option.value === colorPreviewSelection" class="icon viewer-color-preview-option__check"><use href="#icon-check"/></svg>
      </button>
      <p v-if="colorPreviewLibraryLoading" class="viewer-color-preview-hint" role="status">Loading workspace LUTs…</p>
      <template v-if="colorPreviewLibraryError">
        <p class="viewer-color-preview-error" role="alert">{{ colorPreviewLibraryError }}</p>
        <button type="button" class="v-dropdown-item" role="menuitem" :disabled="colorPreviewLibraryLoading" @click.stop="onRefreshColorPreviewLibrary?.()">Retry workspace LUTs</button>
      </template>
      <div class="viewer-color-preview-actions">
        <button
          type="button"
          class="v-dropdown-item"
          role="menuitem"
          :disabled="colorPreviewLoading"
          @click.stop="colorPreviewFileInput?.click()"
        >{{ colorPreviewCustomLut ? 'Replace temporary LUT…' : 'Load temporary LUT…' }}</button>
        <button
          v-if="colorPreviewCustomLut"
          type="button"
          class="v-dropdown-item"
          role="menuitem"
          :disabled="colorPreviewLoading"
          @click.stop="onClearColorPreviewLut?.()"
        >Remove temporary LUT</button>
      </div>
      <p v-if="colorPreviewLoading" class="viewer-color-preview-hint" role="status">Loading LUT…</p>
      <p v-if="colorPreviewError" class="viewer-color-preview-error" role="alert">{{ colorPreviewError }}</p>
      <p v-if="!colorPreviewAvailable" class="viewer-color-preview-hint" role="status">Color preview is unavailable in this browser.</p>
      <details class="viewer-color-preview-help">
        <summary @click.stop @keydown.enter.stop @keydown.space.stop>About LUT previews</summary>
        <p>LUTs affect the viewer and screenshots. Original files stay unchanged. Match the LUT to your footage’s input encoding.</p>
        <p>Temporary LUTs clear when this page closes or refreshes.</p>
      </details>
    </div>
  </VMenu>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { VMenu } from '../primitives'

const props = defineProps({
  colorPreviewPresets: { type: Array, default: () => [] },
  colorPreviewLibraryLoading: { type: Boolean, default: false },
  colorPreviewLibraryError: { type: String, default: '' },
  onRefreshColorPreviewLibrary: { type: Function, default: null },
  colorPreviewSelection: { type: String, default: 'source' },
  colorPreviewCustomLut: { type: Object, default: null },
  colorPreviewAvailable: { type: Boolean, default: true },
  colorPreviewLoading: { type: Boolean, default: false },
  colorPreviewError: { type: String, default: '' },
  onSetColorPreviewMode: { type: Function, default: null },
  onLoadColorPreviewLut: { type: Function, default: null },
  onClearColorPreviewLut: { type: Function, default: null },
})
const open = defineModel('open', { type: Boolean, default: false })
const colorPreviewFileInput = ref(null)
const colorPreviewChoices = computed(() => [
  { value: 'source', label: 'Source', hint: 'Original colors' },
  ...props.colorPreviewPresets,
  ...(props.colorPreviewCustomLut ? [{ value: 'lut', label: props.colorPreviewCustomLut.name, hint: `Temporary · ${props.colorPreviewCustomLut.size}-point 3D LUT` }] : []),
])
const colorPreviewButtonLabel = computed(() => (
  props.colorPreviewAvailable
    ? `Color preview. ${colorPreviewChoices.value.find(option => option.value === props.colorPreviewSelection)?.label || 'Source'}`
    : 'Color preview unavailable'
))

watch(open, value => { if (value) props.onRefreshColorPreviewLibrary?.() })

async function selectColorPreview(value) {
  if (value !== 'source' && props.colorPreviewLoading) return
  await props.onSetColorPreviewMode?.(value)
  await nextTick()
  if (value === 'source' || (!props.colorPreviewError && props.colorPreviewSelection === value)) open.value = false
}

function loadColorPreviewFile(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (file && !props.colorPreviewLoading) props.onLoadColorPreviewLut?.(file)
}
</script>

<style>
.viewer-color-preview-trigger {
  width: var(--viewer-control-size, var(--v-icon-btn-size));
  min-height: var(--viewer-control-size, var(--v-icon-btn-size));
  padding: 0;
  color: var(--v-text-muted);
}
.viewer-color-preview-trigger .icon {
  width: var(--viewer-control-glyph, var(--v-icon-btn-glyph));
  height: var(--viewer-control-glyph, var(--v-icon-btn-glyph));
}
.viewer-color-preview-trigger.active {
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 11%, transparent);
}
.viewer-color-preview-menu {
  width: min(320px, calc(100vw - var(--v-space-4)));
  max-height: min(70vh, 440px);
  padding: var(--v-space-1);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.viewer-color-preview-panel {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-1);
}

.viewer-color-preview-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
  padding: var(--v-space-2) var(--v-space-3) var(--v-space-1);
}

.viewer-color-preview-option {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 16px;
  min-height: 48px;
  padding: var(--v-space-2) var(--v-space-3);
  gap: var(--v-space-3);
}

.viewer-color-preview-option.active {
  background: color-mix(in srgb, var(--v-accent) 8%, var(--v-bg-hover));
}

.viewer-color-preview-option__copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  text-align: left;
}

.viewer-color-preview-option__label {
  color: var(--v-text);
  font-size: var(--v-text-sm);
  font-weight: 600;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.viewer-color-preview-option__hint {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.2;
}

.viewer-color-preview-option__check {
  width: 14px;
  height: 14px;
  align-self: center;
  color: var(--v-accent);
}

.viewer-color-preview-help {
  margin-top: var(--v-space-1);
  padding: var(--v-space-1) var(--v-space-3) 0;
  border-top: 1px solid var(--v-border);
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.45;
}

.viewer-color-preview-help summary {
  padding-block: var(--v-space-2);
  cursor: pointer;
}

.viewer-color-preview-help summary:hover {
  color: var(--v-text);
}

.viewer-color-preview-help summary:focus-visible {
  outline: 2px solid var(--v-accent);
  outline-offset: 2px;
  border-radius: var(--v-radius-sm);
}

.viewer-color-preview-help p {
  margin: 0 0 var(--v-space-2);
}

.viewer-color-preview-actions {
  margin-top: var(--v-space-1);
  padding-top: var(--v-space-1);
  border-top: 1px solid var(--v-border);
}

.viewer-color-preview-actions .v-dropdown-item {
  min-height: var(--v-btn-height-lg);
}

.viewer-color-preview-hint,
.viewer-color-preview-error {
  margin: 0;
  padding: var(--v-space-1) var(--v-space-3);
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.viewer-color-preview-error { color: var(--v-danger-text); }

</style>
