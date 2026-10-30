<template>
  <!-- The whole row opens the extras panel. The chips only preview the extras. -->
  <VMenu
    v-if="visible"
    class="trc-extras-menu"
    :open="panelOpen"
    align="end"
    teleport
    :close-on-select="false"
    panel-role="dialog"
    :panel-label="`Extras of ${shot.shot_id}`"
    panel-class="extras-panel-menu"
    @update:open="value => { panelOpen = value }"
  >
    <template #trigger="{ triggerProps }">
      <button
        v-bind="triggerProps"
        type="button"
        class="trc-extras"
        :class="{ 'is-open': panelOpen, 'is-stacked': stacked }"
        :aria-label="`Open the extras of ${shot.shot_id}: ${summary}`"
        @click.stop="panelOpen = !panelOpen"
      >
        <span class="trc-extras-lead" aria-hidden="true">
          <span class="trc-extras-icon"><svg class="icon"><use href="#icon-layers" /></svg></span>
          <span v-if="filledCount" class="trc-extras-count">{{ filledCount }}</span>
        </span>
        <div class="trc-extras-main">
          <span class="trc-extras-tag">Extras</span>
          <span ref="chipsRef" class="trc-extras-chips" :class="{ 'is-overflowing': overflowing }" aria-hidden="true">
            <template v-for="slot in slots" :key="slot.id">
              <span
                v-if="slot.file"
                class="extra-chip"
                :class="{ 'is-offline': slot.file.exists === false }"
              >
                <span class="extra-chip-thumb" :class="{ 'is-empty': !thumbnail(slot) }">
                  <img v-if="thumbnail(slot)" :src="thumbnail(slot)" alt="" loading="lazy" @error="failedThumbs[slot.id] = true" />
                  <svg v-else class="icon"><use :href="slot.file.is_image ? '#icon-image' : '#icon-file'" /></svg>
                </span>
                <span class="extra-chip-name">{{ slot.name }}</span>
                <span v-if="slot.note" class="extra-chip-note">{{ slot.note }}</span>
                <svg v-if="!shareMode && slot.client_visible === false" class="icon extra-chip-flag"><use href="#icon-eye-off" /></svg>
              </span>
              <span v-else-if="uploadFor(slot)" class="extra-chip is-uploading">
                <span class="extra-chip-progress" :style="{ '--progress': `${Math.round(uploadFor(slot).progress * 100)}%` }" />
                <span class="extra-chip-name">{{ slot.name }}</span>
                <span class="extra-chip-note">{{ Math.round(uploadFor(slot).progress * 100) }}%</span>
              </span>
              <span v-else class="extra-chip is-needed">
                <span class="extra-chip-name">{{ slot.name }}</span>
                <span class="extra-chip-note">Needed</span>
              </span>
            </template>
            <span v-for="upload in newUploads" :key="upload.key" class="extra-chip is-uploading">
              <span class="extra-chip-progress" :style="{ '--progress': `${Math.round(upload.progress * 100)}%` }" />
              <span class="extra-chip-name">{{ upload.name }}</span>
              <span class="extra-chip-note">{{ Math.round(upload.progress * 100) }}%</span>
            </span>
          </span>
        </div>
        <span class="trc-open-hint" aria-hidden="true">
          <svg viewBox="0 0 13 13" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M2.5 6.5H10.5M10.5 6.5L7 3M10.5 6.5L7 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </span>
      </button>
    </template>
    <ShotExtrasPanel :shot="shot" :version="version" @close="panelOpen = false" />
  </VMenu>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useTrackerStore } from '../../ownership/tracker'
import { VMenu } from '../primitives'
import ShotExtrasPanel from './ShotExtrasPanel.vue'

const props = defineProps({
  shot: { type: Object, required: true },
  // Phones and grid cards stack the label above the chips, like the Brief row.
  stacked: { type: Boolean, default: false },
})

const {
  getExtraSlots,
  getExtraThumbnailUrl,
  getUploadsFor,
  shareMode,
} = useTrackerStore()

const panelOpen = ref(false)
const failedThumbs = reactive({})
const chipsRef = ref(null)
const overflowing = ref(false)

const version = computed(() => props.shot?.versions?.at(-1) || null)
const slots = computed(() => getExtraSlots(props.shot, version.value))
const uploads = computed(() => getUploadsFor(props.shot, version.value))
const newUploads = computed(() => uploads.value.filter(upload => !upload.extraId))
const filledCount = computed(() => slots.value.filter(slot => slot.file).length)
const visible = computed(() => slots.value.length > 0 || newUploads.value.length > 0)
const summary = computed(() => {
  const needed = slots.value.length - filledCount.value
  const files = `${filledCount.value} ${filledCount.value === 1 ? 'file' : 'files'}`
  return needed ? `${files}, ${needed} needed` : files
})

function uploadFor(slot) {
  return uploads.value.find(upload => upload.extraId === slot.id) || null
}

function thumbnail(slot) {
  return failedThumbs[slot.id] ? '' : getExtraThumbnailUrl(version.value, slot.file)
}

// The row keeps one line of chips. When they run past its end, the end
// fades out to show that the panel has more.
function measureOverflow() {
  const el = chipsRef.value
  overflowing.value = Boolean(el && el.scrollWidth > el.clientWidth + 1)
}

let resizeObserver = null
watch(chipsRef, el => {
  resizeObserver?.disconnect()
  resizeObserver = null
  if (el && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(measureOverflow)
    resizeObserver.observe(el)
  }
  measureOverflow()
})
watch([slots, newUploads], () => nextTick(measureOverflow), { deep: true })
onBeforeUnmount(() => resizeObserver?.disconnect())
</script>

<style scoped>
.trc-extras-menu,
.trc-extras-menu :deep(.v-menu-trigger) {
  display: block;
}

/* Looks and behaves like the Brief and Latest notes rows above it. */
/* Always the height of the Brief and Latest notes rows: 22px chips plus padding make 33px. */
.trc-extras {
  position: relative;
  display: grid;
  grid-template-columns: var(--trc-lead-width, 36px) minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  width: 100%;
  height: 33px;
  padding: 5px 12px 6px 10px;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background var(--v-transition-fast), color var(--v-transition-fast);
}

.trc-extras::before {
  content: '';
  position: absolute;
  inset: 0 10px auto;
  height: 1px;
  background: rgba(255, 255, 255, 0.045);
  pointer-events: none;
}

.trc-extras:hover,
.trc-extras:focus-visible,
.trc-extras.is-open {
  background: color-mix(in srgb, var(--v-bg-hover) 70%, transparent);
  outline: none;
}

.trc-extras:focus-visible {
  box-shadow: inset 0 0 0 2px var(--v-accent-muted);
}

.trc-extras-lead {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  width: var(--trc-lead-width, 36px);
}

.trc-extras-icon {
  width: 20px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: color-mix(in srgb, var(--v-text-dim) 88%, transparent);
  transition: color var(--v-transition-fast);
}

.trc-extras-icon .icon {
  width: 15px;
  height: 15px;
}

.trc-extras-count {
  font-size: 10px;
  font-weight: 700;
  color: var(--v-text-muted);
  font-variant-numeric: tabular-nums;
}

.trc-extras-main {
  display: grid;
  grid-template-columns: var(--trc-label-width, 76px) minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.trc-extras-tag {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 600;
  line-height: 1.25;
  white-space: nowrap;
}

.trc-extras-chips {
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
}

.trc-extras-chips.is-overflowing {
  -webkit-mask-image: linear-gradient(90deg, #000 0%, #000 calc(100% - 40px), transparent 100%);
          mask-image: linear-gradient(90deg, #000 0%, #000 calc(100% - 40px), transparent 100%);
}

.trc-open-hint {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 13px;
  height: 13px;
  color: var(--v-text-muted);
  opacity: 0;
  transition: color var(--v-transition-fast), transform var(--v-transition-fast), opacity var(--v-transition-fast);
}

.trc-open-hint svg {
  width: 13px;
  height: 13px;
}

.trc-extras:hover .trc-open-hint,
.trc-extras:focus-visible .trc-open-hint,
.trc-extras.is-open .trc-open-hint {
  color: var(--v-text-secondary);
  opacity: 1;
  transform: translateX(2px);
}

.trc-extras:hover .trc-extras-icon,
.trc-extras:focus-visible .trc-extras-icon {
  color: var(--v-text-muted);
}

/* Chips only preview the extras; the row is what you click. */
.extra-chip {
  position: relative;
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 22px;
  padding: 0 8px 0 3px;
  border-radius: var(--v-radius-sm);
  background: var(--v-surface-inline);
  box-shadow: inset 0 0 0 1px var(--v-surface-border-soft);
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  transition: color var(--v-transition-fast);
}

.trc-extras:hover .extra-chip {
  color: var(--v-text);
}

.extra-chip-thumb {
  width: 28px;
  height: 16px;
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 3px;
  overflow: hidden;
  background: #000;
  color: var(--v-text-dim);
}

.extra-chip-thumb.is-empty {
  background: var(--v-surface-inline-strong);
}

.extra-chip-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.extra-chip-thumb .icon {
  width: 12px;
  height: 12px;
}

.extra-chip-note {
  color: var(--v-text-dim);
  font-weight: 500;
}

.extra-chip-note::before {
  content: '· ';
}

.extra-chip-flag {
  width: 12px;
  height: 12px;
  flex: none;
  color: var(--v-text-dim);
}

.extra-chip.is-offline .extra-chip-thumb {
  opacity: 0.4;
}

.extra-chip.is-offline .extra-chip-name {
  text-decoration: line-through;
  text-decoration-color: color-mix(in srgb, var(--v-text-dim) 70%, transparent);
}

.extra-chip.is-needed {
  padding: 0 8px;
  border: 1px dashed color-mix(in srgb, var(--v-warning) 55%, transparent);
  background: transparent;
  box-shadow: none;
  color: color-mix(in srgb, var(--v-warning) 82%, var(--v-text));
}

.extra-chip.is-needed .extra-chip-note {
  color: inherit;
  opacity: 0.72;
}

.extra-chip.is-uploading {
  padding: 0 8px;
  color: var(--v-text);
}

.extra-chip-progress {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, color-mix(in srgb, var(--v-accent) 22%, transparent) var(--progress), transparent var(--progress));
  pointer-events: none;
}

/* Stacked: the label sits above one line of chips, at the shared height
   of the Brief and Latest notes rows on these cards. */
.trc-extras.is-stacked {
  grid-template-columns: var(--trc-lead-width, 36px) minmax(0, 1fr);
  align-items: stretch;
  height: var(--trc-mobile-row-height, 54px);
  padding: 4px 12px 6px 8px;
}

.trc-extras.is-stacked .trc-extras-lead {
  align-self: center;
}

.trc-extras.is-stacked .trc-extras-main {
  grid-template-columns: minmax(0, 1fr);
  align-content: center;
  gap: 5px;
  min-height: 0;
}

.trc-extras.is-stacked .trc-open-hint {
  display: none;
}
</style>
