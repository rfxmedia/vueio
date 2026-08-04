<template>
  <div class="media-version-switcher-list-shell" :class="{ 'is-sheet': sheet }">
    <div v-if="versions.length" class="media-version-switcher-list" role="list" :aria-label="`${shotId || 'Shot'} versions`">
      <div
        v-for="(version, index) in versions"
        :key="version.id || version.path || version.file_path || index"
        class="media-version-switcher-row"
        :class="{
          'is-current': isCurrentVersion(version),
          'is-unavailable': version.exists === false,
          'has-utility': hasRowUtility(version),
        }"
        role="listitem"
      >
        <div
          class="media-version-switcher-thumb"
          @click="selectVersion(version)"
        >
          <VMediaThumbnail
            :src="getThumbnailUrl(version)"
            :alt="`${shotId || 'Shot'} ${getVersionLabel(version, index)}`"
          />
          <span v-if="isCurrentVersion(version)" class="media-version-switcher-current-state">Viewing</span>
          <span v-if="version.exists === false" class="media-version-switcher-unavailable">
            <svg class="icon"><use href="#icon-file" /></svg>
            Unavailable
          </span>
          <span v-if="getDurationLabel(version)" class="media-version-switcher-duration">
            {{ getDurationLabel(version) }}
          </span>
        </div>

        <div class="media-version-switcher-row-body">
          <div
            role="button"
            tabindex="0"
            class="media-version-switcher-row-main"
            :aria-current="isCurrentVersion(version) ? 'true' : undefined"
            :aria-label="`View ${getVersionLabel(version, index)}`"
            @click="selectVersion(version)"
            @keydown.enter.prevent="selectVersion(version)"
            @keydown.space.prevent="selectVersion(version)"
          >
            <div class="media-version-switcher-copy">
              <div class="media-version-switcher-row-top">
                <strong class="media-version-switcher-version">
                  {{ getVersionLabel(version, index) }}
                </strong>
                <span
                  v-if="getPublicationState(version)"
                  class="media-version-switcher-publication-state"
                  :class="`is-${getPublicationState(version)}`"
                >
                  <span class="media-version-switcher-publication-state-dot" aria-hidden="true"></span>
                  {{ getPublicationLabel(version) }}
                </span>
                <span v-if="version.exists === false" class="media-version-switcher-unavailable-state">Unavailable</span>
              </div>

              <div
                v-if="getVersionSummary(version)"
                class="media-version-switcher-notes"
                :class="{
                  'is-expanded': isVersionNotesExpanded(version, index),
                  'is-expandable': canExpandVersionNotes(version),
                }"
                :title="getVersionSummary(version)"
                :role="canExpandVersionNotes(version) ? 'button' : undefined"
                :tabindex="canExpandVersionNotes(version) ? 0 : undefined"
                :aria-expanded="canExpandVersionNotes(version) ? (isVersionNotesExpanded(version, index) ? 'true' : 'false') : undefined"
                :aria-label="canExpandVersionNotes(version) ? `${isVersionNotesExpanded(version, index) ? 'Collapse' : 'Expand'} version notes for ${getVersionLabel(version, index)}` : undefined"
                @click="handleVersionNotesClick(version, index, $event)"
                @keydown.enter="handleVersionNotesKeydown(version, index, $event)"
                @keydown.space="handleVersionNotesKeydown(version, index, $event)"
              >
                <span class="media-version-switcher-notes-header">
                  <span class="media-version-switcher-notes-label">Version Notes</span>
                  <svg v-if="canExpandVersionNotes(version)" class="icon media-version-switcher-notes-chevron" aria-hidden="true">
                    <use href="#icon-chevron-down" />
                  </svg>
                </span>
                <span class="media-version-switcher-summary">
                  {{ getVersionSummary(version) }}
                </span>
              </div>

              <div class="media-version-switcher-meta">
                <span class="media-version-switcher-date">{{ formatVersionDateShort(version.created_at) }}</span>
                <template v-if="getSizeLabel(version)">
                  <span class="media-version-switcher-meta-dot" aria-hidden="true">·</span>
                  <span class="media-version-switcher-size">{{ getSizeLabel(version) }}</span>
                </template>
              </div>
            </div>
          </div>

          <div v-if="hasRowUtility(version)" class="media-version-switcher-row-utility">
            <div
              v-if="canManagePublication(version) && getPublicationState(version) === 'pending'"
              class="media-version-switcher-publication-actions"
              :aria-label="`${getVersionLabel(version, index)} share visibility`"
            >
              <button
                type="button"
                class="media-version-switcher-publication-btn is-quiet"
                :disabled="Boolean(publicationSavingId)"
                @click.stop="updatePublication(version, 'internal')"
              >
                {{ publicationActionLabel(version, 'internal', 'Keep internal') }}
              </button>
              <button
                type="button"
                class="media-version-switcher-publication-btn is-primary"
                :disabled="Boolean(publicationSavingId)"
                @click.stop="updatePublication(version, 'published')"
              >
                <svg class="icon" aria-hidden="true"><use href="#icon-eye" /></svg>
                {{ publicationActionLabel(version, 'published', 'Publish') }}
              </button>
            </div>
            <div
              v-if="canDownloadVersions || canDeleteVersions || canTogglePublication(version)"
              class="media-version-switcher-row-actions"
            >
              <button
                v-if="canTogglePublication(version)"
                type="button"
                class="media-version-switcher-row-action-label"
                :class="`is-${getPublicationState(version)}`"
                :disabled="Boolean(publicationSavingId)"
                :aria-label="publicationToggleAriaLabel(version, index)"
                :title="publicationToggleAriaLabel(version, index)"
                @click.stop="updatePublication(version, getPublicationState(version) === 'published' ? 'internal' : 'published')"
              >
                <svg class="icon" aria-hidden="true">
                  <use :href="getPublicationState(version) === 'published' ? '#icon-eye-off' : '#icon-eye'" />
                </svg>
                <span>{{ publicationToggleLabel(version) }}</span>
              </button>
              <button
                v-if="canDownloadVersions && version.exists !== false"
                type="button"
                class="media-version-switcher-row-action v-icon-action is-compact"
                :aria-label="`Download ${getVersionLabel(version, index)}`"
                :title="`Download ${getVersionLabel(version, index)}`"
                @click.stop="handleDownloadVersion(version)"
              >
                <svg class="icon"><use href="#icon-download" /></svg>
              </button>
              <button
                v-if="canDeleteVersions"
                type="button"
                class="media-version-switcher-row-action v-icon-action is-compact is-danger"
                :aria-label="`Remove ${getVersionLabel(version, index)} from tracker history`"
                :title="`Remove ${getVersionLabel(version, index)} from tracker history`"
                @click.stop="handleDeleteVersion(version)"
              >
                <svg class="icon"><use href="#icon-trash" /></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="v-empty-state v-empty-state-compact">
      <p class="v-empty-state-title">No versions yet</p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { notify } from '../../utils/toasts'
import VMediaThumbnail from './VMediaThumbnail.vue'

const props = defineProps({
  shotId: { type: String, default: '' },
  versions: { type: Array, default: () => [] },
  currentVersionId: { type: String, default: '' },
  currentMediaAssetId: { type: String, default: '' },
  currentMediaPath: { type: String, default: '' },
  sheet: { type: Boolean, default: false },
  canDeleteVersions: { type: Boolean, default: false },
  canDownloadVersions: { type: Boolean, default: false },
  publicationControlsEnabled: { type: Boolean, default: false },
  updateVersionPublication: { type: Function, default: null },
  shareMode: { type: Boolean, default: false },
  getThumbnailUrl: { type: Function, required: true },
  getMediaDurationLabel: { type: Function, default: () => '' },
  formatVersionLabel: { type: Function, required: true },
  formatVersionDateShort: { type: Function, required: true },
})

const emit = defineEmits(['select-version', 'download-version', 'delete-version'])

const hasRowActions = computed(() => (
  props.canDownloadVersions
  || props.canDeleteVersions
  || (
    props.publicationControlsEnabled
    && typeof props.updateVersionPublication === 'function'
  )
))
const expandedVersionNotes = ref(new Set())
const publicationSavingId = ref('')
const publicationSavingState = ref('')
const VERSION_NOTES_COLLAPSE_THRESHOLD = 32

function resolveVersionFallback(version, index) {
  const reversedIndex = props.versions.length - index
  const numericLabel = Number(version?.label ?? version?.version)
  return Number.isFinite(numericLabel) && numericLabel > 0 ? numericLabel : reversedIndex
}

function isCurrentVersion(version) {
  if (!version) return false
  if (props.currentVersionId && version.id === props.currentVersionId) return true
  if (props.currentMediaAssetId && version.media_asset_id === props.currentMediaAssetId) return true
  const versionPath = version.path || version.file_path || ''
  return !!props.currentMediaPath && versionPath === props.currentMediaPath
}

function selectVersion(version) {
  if (!(version?.path || version?.file_path) || isCurrentVersion(version)) return
  emit('select-version', version)
}

function getVersionLabel(version, index) {
  return props.formatVersionLabel(version, resolveVersionFallback(version, index))
}

function getPublicationState(version) {
  if (props.shareMode) return ''
  const state = String(version?.share_state || '').trim().toLowerCase()
  if (['pending', 'internal'].includes(state)) return state
  return props.publicationControlsEnabled && state === 'published' ? state : ''
}

function getPublicationLabel(version) {
  return {
    published: 'Published',
    pending: 'Pending review',
    internal: 'Internal',
  }[getPublicationState(version)] || ''
}

function hasRowUtility(version) {
  return hasRowActions.value
}

function canManagePublication(version) {
  return (
    props.publicationControlsEnabled
    && typeof props.updateVersionPublication === 'function'
    && Boolean(getPublicationState(version))
  )
}

function canTogglePublication(version) {
  const state = getPublicationState(version)
  return canManagePublication(version) && (state === 'published' || state === 'internal')
}

function publicationActionLabel(version, state, fallback) {
  if (publicationSavingId.value !== version?.id || publicationSavingState.value !== state) return fallback
  return state === 'published' ? 'Publishing…' : 'Saving…'
}

function publicationToggleLabel(version) {
  const state = getPublicationState(version)
  if (state === 'published') return publicationActionLabel(version, 'internal', 'Unpublish')
  return publicationActionLabel(version, 'published', 'Publish')
}

function publicationToggleAriaLabel(version, index) {
  const label = getVersionLabel(version, index)
  return getPublicationState(version) === 'published'
    ? `Unpublish ${label} from shares`
    : `Publish ${label} to shares`
}

async function updatePublication(version, state) {
  if (publicationSavingId.value || !canManagePublication(version)) return
  publicationSavingId.value = version?.id || version?.path || version?.file_path || state
  publicationSavingState.value = state
  try {
    await props.updateVersionPublication(version, state)
  } catch (error) {
    console.error('Failed to update version publication')
    notify('Could not update who can see this version.', { tone: 'error' })
  } finally {
    publicationSavingId.value = ''
    publicationSavingState.value = ''
  }
}

function handleDownloadVersion(version) {
  if (version?.exists === false || !(version?.path || version?.file_path)) return
  emit('download-version', version)
}

function handleDeleteVersion(version) {
  emit('delete-version', version)
}

function getVersionKey(version, index) {
  return String(version?.id || version?.path || version?.file_path || index)
}

function isVersionNotesExpanded(version, index) {
  return canExpandVersionNotes(version) && expandedVersionNotes.value.has(getVersionKey(version, index))
}

function toggleVersionNotes(version, index) {
  if (!canExpandVersionNotes(version)) return
  const key = getVersionKey(version, index)
  const next = new Set(expandedVersionNotes.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  expandedVersionNotes.value = next
}

function canExpandVersionNotes(version) {
  const summary = getVersionSummary(version)
  return summary.includes('\n') || summary.length > VERSION_NOTES_COLLAPSE_THRESHOLD
}

function handleVersionNotesClick(version, index, event) {
  if (!canExpandVersionNotes(version)) return
  event.stopPropagation()
  toggleVersionNotes(version, index)
}

function handleVersionNotesKeydown(version, index, event) {
  if (!canExpandVersionNotes(version)) return
  event.stopPropagation()
  event.preventDefault()
  toggleVersionNotes(version, index)
}

function getVersionSummary(version) {
  return String(version?.notes || '').trim()
}

function getDurationLabel(version) {
  if (!version) return ''
  if (version.duration_formatted) return version.duration_formatted
  const path = version.path || version.file_path
  if (!path || typeof props.getMediaDurationLabel !== 'function') return ''
  return props.getMediaDurationLabel({ path, file_path: path }) || ''
}

function getSizeLabel(version) {
  return version?.size_formatted || ''
}
</script>

<style scoped>
.media-version-switcher-list-shell {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.media-version-switcher-list {
  display: flex;
  flex-direction: column;
  gap: var(--v-space-1);
  min-height: 0;
  overflow-y: auto;
  padding: var(--v-space-1);
}

.media-version-switcher-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: var(--v-space-3);
  border: 0;
  border-radius: var(--v-radius-md);
  background: transparent;
  color: var(--v-text);
  transition: background var(--v-transition-fast);
}

.media-version-switcher-row:hover,
.media-version-switcher-row:focus-within {
  background: var(--v-bg-hover);
}

.media-version-switcher-row.is-current {
  background: color-mix(in srgb, var(--v-accent-muted) 40%, transparent);
}

.media-version-switcher-row.is-current:hover,
.media-version-switcher-row.is-current:focus-within {
  background: color-mix(in srgb, var(--v-accent-muted) 55%, transparent);
}

.media-version-switcher-row-body {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.media-version-switcher-row-main {
  flex: 1 1 auto;
  min-width: 0;
  padding: 0;
  border: 0;
  background: none;
  color: var(--v-text);
  text-align: left;
  cursor: pointer;
}

.media-version-switcher-thumb {
  position: relative;
  flex: 0 0 132px;
  width: 132px;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border: 0;
  border-radius: var(--v-radius-md);
  background: var(--v-bg-black);
  padding: 0;
  cursor: pointer;
  color: inherit;
}

.media-version-switcher-thumb :deep(img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.media-version-switcher-duration {
  position: absolute;
  right: 4px;
  bottom: 4px;
  height: 16px;
  padding: 0 5px;
  border-radius: var(--v-radius-sm);
  background: rgba(0, 0, 0, 0.72);
  color: #fff;
  font-size: var(--v-text-2xs);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
  display: inline-flex;
  align-items: center;
}

.media-version-switcher-unavailable {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  background: var(--v-bg-black);
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 600;
}

.media-version-switcher-unavailable .icon {
  width: 14px;
  height: 14px;
}

.media-version-switcher-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.media-version-switcher-row-top {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--v-space-2);
  min-width: 0;
}

.media-version-switcher-version {
  font-size: var(--v-text-md);
  font-weight: 700;
  letter-spacing: 0;
  color: var(--v-text);
  font-variant-numeric: tabular-nums;
}

.media-version-switcher-current-state {
  position: absolute;
  top: 5px;
  left: 5px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 0 7px;
  border-radius: var(--v-radius-full);
  border: 1px solid color-mix(in srgb, var(--v-accent) 28%, transparent);
  background: color-mix(in srgb, var(--v-bg-black) 76%, transparent);
  color: var(--v-accent);
  font-size: var(--v-text-3xs);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  box-shadow: var(--v-surface-shadow-inset);
  backdrop-filter: blur(8px);
}

.media-version-switcher-unavailable-state {
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 600;
}

.media-version-switcher-publication-state {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  min-height: 18px;
  padding: 0 7px;
  border: 1px solid color-mix(in srgb, currentColor 16%, transparent);
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, currentColor 7%, transparent);
  color: var(--v-text-muted);
  font-size: var(--v-text-3xs);
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap;
}

.media-version-switcher-publication-state.is-pending {
  color: color-mix(in srgb, var(--v-warning) 72%, var(--v-text));
}

.media-version-switcher-publication-state.is-published {
  color: color-mix(in srgb, var(--v-accent) 78%, var(--v-text-secondary));
}

.media-version-switcher-publication-state.is-internal {
  color: var(--v-text-muted);
}

.media-version-switcher-publication-state-dot {
  width: 5px;
  height: 5px;
  flex: 0 0 auto;
  border-radius: var(--v-radius-full);
  background: currentColor;
  opacity: 0.9;
  box-shadow: 0 0 0 2px color-mix(in srgb, currentColor 12%, transparent);
}

.media-version-switcher-notes {
  display: grid;
  gap: 3px;
  min-width: 0;
  max-height: 44px;
  overflow: hidden;
  margin: 2px 0 1px;
  padding: 7px 10px;
  border: 1px solid color-mix(in srgb, var(--v-control-border) 72%, transparent);
  border-radius: var(--v-radius-lg);
  background: color-mix(in srgb, var(--v-control-bg) 78%, transparent);
  cursor: inherit;
  outline: none;
  transition:
    background var(--v-transition-fast),
    border-color var(--v-transition-fast),
    max-height var(--v-transition-fast);
}

.media-version-switcher-notes.is-expandable {
  cursor: pointer;
}

.media-version-switcher-notes.is-expandable:hover,
.media-version-switcher-notes.is-expandable:focus-visible {
  border-color: var(--v-control-border);
  background: color-mix(in srgb, var(--v-control-bg) 90%, transparent);
}

.media-version-switcher-notes.is-expanded {
  max-height: 132px;
}

.media-version-switcher-notes-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-2);
  min-width: 0;
}

.media-version-switcher-notes-label {
  color: var(--v-text-muted);
  font-size: var(--v-text-3xs);
  font-weight: 700;
  letter-spacing: 0.1em;
  line-height: 1;
  text-transform: uppercase;
}

.media-version-switcher-notes-chevron {
  width: 14px;
  height: 14px;
  flex: 0 0 auto;
  color: var(--v-text-muted);
  opacity: 0.84;
  transition:
    transform var(--v-transition-fast),
    color var(--v-transition-fast),
    opacity var(--v-transition-fast);
}

.media-version-switcher-notes.is-expandable:hover .media-version-switcher-notes-chevron,
.media-version-switcher-notes.is-expandable:focus-visible .media-version-switcher-notes-chevron {
  color: var(--v-text-secondary);
  opacity: 1;
}

.media-version-switcher-notes.is-expanded .media-version-switcher-notes-chevron {
  transform: rotate(180deg);
}

.media-version-switcher-summary {
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  font-size: var(--v-text-base);
  color: var(--v-text);
  font-weight: 560;
  letter-spacing: 0;
  text-align: left;
  font-family: var(--v-font);
  min-width: 0;
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  display: block;
  line-height: 1.25;
  -webkit-mask-image: linear-gradient(90deg, #000 0%, #000 calc(100% - 34px), transparent 100%);
  mask-image: linear-gradient(90deg, #000 0%, #000 calc(100% - 34px), transparent 100%);
}

.media-version-switcher-notes.is-expanded .media-version-switcher-summary {
  white-space: normal;
  overflow: visible;
  line-height: 1.35;
  -webkit-mask-image: none;
  mask-image: none;
}

.media-version-switcher-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  min-width: 0;
}

.media-version-switcher-meta-dot { opacity: 0.5; }

.media-version-switcher-date {
  white-space: nowrap;
}

.media-version-switcher-row-utility {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex: 0 0 auto;
}

.media-version-switcher-publication-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.media-version-switcher-publication-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 11px;
  border: 1px solid transparent;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text-secondary);
  font: inherit;
  font-size: var(--v-text-sm);
  font-weight: 600;
  letter-spacing: 0;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background var(--v-transition-fast),
    border-color var(--v-transition-fast),
    color var(--v-transition-fast);
}

.media-version-switcher-publication-btn .icon {
  width: 13px;
  height: 13px;
}

.media-version-switcher-publication-btn:disabled {
  opacity: 0.55;
  cursor: default;
}

.media-version-switcher-publication-btn.is-quiet {
  color: var(--v-text-muted);
  background: color-mix(in srgb, var(--v-control-bg) 70%, transparent);
  border-color: color-mix(in srgb, var(--v-control-border) 70%, transparent);
}

.media-version-switcher-publication-btn.is-quiet:hover:not(:disabled) {
  color: var(--v-text);
  background: color-mix(in srgb, var(--v-control-bg) 92%, transparent);
  border-color: var(--v-control-border);
}

.media-version-switcher-publication-btn.is-primary {
  color: var(--v-on-accent);
  background: var(--v-accent);
  border-color: color-mix(in srgb, var(--v-accent) 97%, white);
  font-weight: 700;
}

.media-version-switcher-publication-btn.is-primary:hover:not(:disabled) {
  background: var(--v-accent-hover);
  border-color: color-mix(in srgb, var(--v-accent-hover) 97%, white);
}

.media-version-switcher-row-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border-radius: var(--v-button-radius);
  background: color-mix(in srgb, var(--v-control-bg) 78%, transparent);
  border: 1px solid color-mix(in srgb, var(--v-control-border) 72%, transparent);
  opacity: 0.9;
  transition: opacity var(--v-transition-fast), border-color var(--v-transition-fast), background var(--v-transition-fast);
}

.media-version-switcher-row:hover .media-version-switcher-row-actions,
.media-version-switcher-row:focus-within .media-version-switcher-row-actions,
.media-version-switcher-row.is-current .media-version-switcher-row-actions {
  opacity: 1;
  background: color-mix(in srgb, var(--v-control-bg) 90%, transparent);
  border-color: var(--v-control-border);
}

.media-version-switcher-row-action-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 10px 0 8px;
  margin-right: 1px;
  border: 0;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text-secondary);
  font: inherit;
  font-size: var(--v-text-sm);
  font-weight: 600;
  letter-spacing: 0;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background var(--v-transition-fast),
    color var(--v-transition-fast);
}

.media-version-switcher-row-action-label .icon {
  width: 13px;
  height: 13px;
  flex: 0 0 auto;
  opacity: 0.88;
}

.media-version-switcher-row-action-label.is-published {
  color: var(--v-text-muted);
}

.media-version-switcher-row-action-label.is-internal {
  color: color-mix(in srgb, var(--v-accent) 82%, var(--v-text));
}

.media-version-switcher-row-action-label:hover:not(:disabled) {
  background: var(--v-surface-inline);
  color: var(--v-text);
}

.media-version-switcher-row-action-label.is-internal:hover:not(:disabled) {
  color: var(--v-accent);
}

.media-version-switcher-row-action-label:disabled {
  opacity: 0.55;
  cursor: default;
}

.media-version-switcher-row-action {
  position: relative;
  width: 32px;
  min-width: 32px;
  height: 32px;
  min-height: 32px;
  background: transparent;
  border-color: transparent;
  color: var(--v-text-muted);
}

.media-version-switcher-row-action:hover:not(:disabled) {
  background: var(--v-surface-inline);
  border-color: var(--v-control-border);
  color: var(--v-text);
}

.media-version-switcher-row-action.is-danger:hover:not(:disabled) {
  background: color-mix(in srgb, var(--v-danger) 12%, transparent);
  border-color: color-mix(in srgb, var(--v-danger) 22%, transparent);
  color: var(--v-danger);
}

/* Sheet (mobile) */
.media-version-switcher-list-shell.is-sheet {
  overflow: visible;
}

.media-version-switcher-list-shell.is-sheet .media-version-switcher-list {
  overflow: visible;
  gap: var(--v-space-1);
  padding: 0;
}

.media-version-switcher-list-shell.is-sheet .media-version-switcher-row {
  align-items: center;
  padding: var(--v-space-3);
  border-radius: var(--v-radius-lg);
}

.media-version-switcher-list-shell.is-sheet .media-version-switcher-thumb {
  flex-basis: 120px;
  width: 120px;
  border-radius: var(--v-radius-md);
}

.media-version-switcher-list-shell.is-sheet .media-version-switcher-version {
  font-size: var(--v-text-lg);
}

.media-version-switcher-list-shell.is-sheet .media-version-switcher-summary {
  font-size: var(--v-text-base);
}

.media-version-switcher-list-shell.is-sheet .media-version-switcher-notes {
  padding: 7px 9px;
}

.media-version-switcher-list-shell.is-sheet .media-version-switcher-meta {
  font-size: var(--v-text-sm);
}

@media (max-width: 768px) {
  .media-version-switcher-row {
    gap: 10px;
  }

  .media-version-switcher-row-body {
    gap: 8px;
  }

  .media-version-switcher-row-actions {
    opacity: 1;
  }

  .media-version-switcher-list-shell.is-sheet .media-version-switcher-thumb {
    flex-basis: 96px;
    width: 96px;
  }

  .media-version-switcher-row-action {
    width: 32px;
    min-width: 32px;
    height: 32px;
    min-height: 32px;
  }

  /* Keep the desktop row shape; collapse the label when space is tight. */
  .media-version-switcher-list-shell.is-sheet .media-version-switcher-row-action-label span {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  .media-version-switcher-list-shell.is-sheet .media-version-switcher-row-action-label {
    width: 32px;
    min-width: 32px;
    height: 32px;
    min-height: 32px;
    padding: 0;
    margin: 0;
    justify-content: center;
  }

  .media-version-switcher-list-shell.is-sheet .media-version-switcher-publication-actions {
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .media-version-switcher-list-shell.is-sheet .media-version-switcher-publication-btn {
    min-height: 32px;
    padding-inline: 10px;
  }
}
</style>
