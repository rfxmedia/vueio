<template>
  <div class="shot-version-stack" :class="{ 'is-compact': compact }">
    <div class="version-wrapper">
      <MediaVersionSwitcher
        v-if="versions.length"
        class="shot-version-switcher"
        variant="control"
        :is-mobile="isMobile"
        :open="isOpen"
        :shot="shot"
        :versions="versionsDescending"
        :current-media="latestVersion"
        :current-version-label="currentVersionLabel"
        :can-add-versions="canAddVersions"
        :can-delete-versions="canDeleteVersions"
        :can-download-versions="canDownloadVersions"
        :can-compare-versions="canCompareVersions"
        :publication-controls-enabled="publicationControlsEnabled"
        :update-version-publication="handleUpdateVersionPublication"
        :share-mode="shareMode"
        :get-thumbnail-url="getThumbnailUrl"
        :get-media-duration-label="getMediaDurationLabel"
        :fetch-batch-media-info="fetchBatchMediaInfo"
        :format-version-label="formatVersionLabel"
        :format-version-date-short="formatVersionDateShort"
        @toggle="toggleOpen"
        @close="closeSwitcher"
        @select-version="handleSelectVersion"
        @download-version="handleDownloadVersion"
        @delete-version="handleDeleteVersion"
        @compare-versions="handleCompareVersions"
        @add-version="handleAddVersion"
      />

      <div
        v-if="versions.length"
        class="version-card v-card"
        :class="{ 'is-unavailable': latestVersion?.exists === false }"
        :title="hoverActionLabel"
        @click="openShotVideo(shot)"
      >
        <VMediaThumbnail :src="getThumbnailUrl(latestVersion)" :alt="shot.shot_id" />
        <div v-if="latestVersion?.exists === false" class="version-unavailable-label">
          <svg class="icon"><use href="#icon-file" /></svg>
          <span>Version unavailable</span>
        </div>
        <div class="version-hover" :class="{ 'is-image': isImageVersion }">
          <svg class="icon"><use :href="isImageVersion ? '#icon-image' : '#icon-play'" /></svg>
          <span class="version-hover-label">{{ hoverActionLabel }}</span>
        </div>
      </div>
      <button
        v-else
        class="version-card version-card-empty v-card"
        @click.stop="handleAddVersion"
      >
        <div class="version-empty-copy">
          <svg class="icon"><use href="#icon-video" /></svg>
          <span>{{ canAddVersions && !shareMode ? 'Add first version' : 'No version yet' }}</span>
        </div>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import VMediaThumbnail from '../media/VMediaThumbnail.vue'
import MediaVersionSwitcher from '../media/MediaVersionSwitcher.vue'

const props = defineProps({
  shot: { type: Object, required: true },
  canAddVersions: { type: Boolean, default: false },
  canDeleteVersions: { type: Boolean, default: false },
  canDownloadVersions: { type: Boolean, default: false },
  canCompareVersions: { type: Boolean, default: false },
  compareVersions: { type: Function, default: null },
  publicationControlsEnabled: { type: Boolean, default: false },
  updateVersionPublication: { type: Function, default: null },
  shareMode: { type: Boolean, default: false },
  isMobile: { type: Boolean, default: false },
  getShotVersions: { type: Function, required: true },
  openShotVideo: { type: Function, required: true },
  playShotVersion: { type: Function, required: true },
  openVersionUpload: { type: Function, required: true },
  deleteShotVersion: { type: Function, default: null },
  downloadVersion: { type: Function, default: null },
  getThumbnailUrl: { type: Function, required: true },
  getShotDurationLabel: { type: Function, required: true },
  getMediaDurationLabel: { type: Function, default: () => '' },
  fetchBatchMediaInfo: { type: Function, default: null },
  formatVersionLabel: { type: Function, required: true },
  formatVersionDateShort: { type: Function, required: true },
  compact: { type: Boolean, default: false },
})

const versions = computed(() => props.getShotVersions(props.shot))
const latestVersion = computed(() => versions.value[versions.value.length - 1] || null)
const versionsDescending = computed(() => [...versions.value].reverse())
const isImageVersion = computed(() => latestVersion.value?.is_image === true)
const hoverActionLabel = computed(() => (isImageVersion.value ? 'View Image' : 'Play Video'))
const switcherId = computed(() => `shot-version-switcher:${props.shot?.id || props.shot?.shot_id || props.shot?.shot_code || ''}`)
const currentVersionLabel = computed(() => {
  const total = versions.value.length
  if (!latestVersion.value) return `V${total || 1}`
  return props.formatVersionLabel(latestVersion.value, total)
})

const isOpen = ref(false)

function toggleOpen() {
  const nextOpen = !isOpen.value
  if (nextOpen) announceSwitcherOpen()
  isOpen.value = nextOpen
}

function closeSwitcher() {
  isOpen.value = false
}

function announceSwitcherOpen() {
  document.dispatchEvent(new CustomEvent('vueio:shot-version-switcher-open', {
    detail: { id: switcherId.value },
  }))
}

function handleSelectVersion(version) {
  if (!version) return
  closeSwitcher()
  const label = version.label || version.version || versions.value.findIndex(v => v === version) + 1
  props.playShotVersion(props.shot, version, label)
}

function handleAddVersion() {
  closeSwitcher()
  props.openVersionUpload(props.shot)
}

function handleCompareVersions() {
  closeSwitcher()
  props.compareVersions?.(props.shot)
}

function handleUpdateVersionPublication(version, state) {
  return props.updateVersionPublication?.(props.shot, version, state)
}

function handleDownloadVersion(version) {
  if (typeof props.downloadVersion !== 'function') return
  props.downloadVersion(version)
}

async function handleDeleteVersion(version) {
  if (typeof props.deleteShotVersion !== 'function') return
  closeSwitcher()
  await props.deleteShotVersion(props.shot, version)
}

function onOtherSwitcherOpen(event) {
  if (event?.detail?.id === switcherId.value) return
  closeSwitcher()
}

onMounted(() => {
  document.addEventListener('vueio:shot-version-switcher-open', onOtherSwitcherOpen)
})
onUnmounted(() => {
  document.removeEventListener('vueio:shot-version-switcher-open', onOtherSwitcherOpen)
})
</script>

<style>
.version-wrapper {
  position: relative;
  display: flex;
  align-items: stretch;
}

.shot-version-switcher {
  position: absolute;
  top: var(--v-space-3);
  left: var(--v-space-3);
  z-index: 2;
}

.shot-version-switcher.is-open {
  z-index: calc(var(--v-z-dropdown) + 1);
}

.version-card {
  position: relative;
  /* Own stacking context, so the thumbnail, hover overlay and hairline ring all
     stay under the version switcher pill that sits over this corner. */
  z-index: 0;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border-radius: var(--v-radius-lg);
  background: var(--v-bg-black);
  cursor: pointer;
  transition: border-color var(--v-transition-fast), box-shadow var(--v-transition-fast), transform var(--v-transition-fast);
}

.version-card:hover {
  border-color: color-mix(in srgb, var(--v-bg-black) 97%, white);
  box-shadow: var(--v-shadow-sm);
}

.version-card .v-media-thumb-image {
  transition:
    opacity var(--v-duration-normal) var(--v-ease-emphasized),
    filter var(--v-duration-normal) var(--v-ease-emphasized),
    transform var(--v-duration-slow) var(--v-ease-emphasized);
}

.version-card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.version-unavailable-label {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: var(--v-space-2);
  padding: var(--v-space-4);
  color: var(--v-text-muted);
  background: var(--v-bg-black);
  font-size: var(--v-text-sm);
  text-align: center;
}

.version-unavailable-label .icon {
  width: 24px;
  height: 24px;
}

.version-card.is-unavailable .version-hover {
  display: none;
}

.version-hover {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 10px;
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--v-overlay-scrim) 60%, transparent),
    var(--v-overlay-scrim)
  );
  opacity: 0;
  transition: opacity var(--v-transition-fast);
}

.version-hover .icon {
  width: 30px;
  height: 30px;
  color: var(--v-text);
  transform: translateY(3px) scale(0.94);
  filter: drop-shadow(0 3px 10px rgba(0, 0, 0, 0.45));
  transition: transform var(--v-duration-normal) var(--v-ease-emphasized);
}

.version-card:hover .version-hover .icon {
  transform: none;
}

.version-hover-label {
  color: var(--v-text);
  font-size: var(--v-text-2xs);
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.version-hover.is-image .icon {
  width: 28px;
  height: 28px;
}

.version-card:hover .version-hover {
  opacity: 1;
}

.version-card-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--v-control-bg) 62%, transparent);
}

.version-empty-copy {
  display: inline-flex;
  align-items: center;
  gap: var(--v-space-2);
  padding: 0 16px;
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 600;
}

.shot-version-stack {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-2);
}

.shot-version-stack.is-compact .shot-version-switcher {
  top: var(--v-space-3);
  left: var(--v-space-3);
}

.shot-version-stack.is-compact .version-card {
  border-radius: var(--v-radius-lg);
}

.shot-version-stack.is-compact .version-hover .icon {
  width: 26px;
  height: 26px;
}

.shot-version-stack.is-compact .version-empty-copy {
  gap: 6px;
  padding: 0 12px;
  font-size: var(--v-text-xs);
  text-align: center;
}
</style>
