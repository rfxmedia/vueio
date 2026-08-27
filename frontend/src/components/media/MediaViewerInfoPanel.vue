<template>
  <div class="file-info-panel">
    <header class="info-header">
      <span class="info-header-glyph" aria-hidden="true">
        <svg class="icon"><use :href="mediaGlyph" /></svg>
      </span>
      <div class="info-header-copy">
        <h2 class="info-title" :title="currentMedia?.name">{{ currentMedia?.name }}</h2>
        <p class="info-meta">
          <span>{{ formatUploadDate() }}</span>
          <template v-if="currentMedia?.uploaded_by">
            <span class="info-meta-dot" aria-hidden="true">·</span>
            <strong>{{ currentMedia.uploaded_by }}</strong>
          </template>
        </p>
      </div>
    </header>

    <dl v-if="keyStats.length > 1" class="info-keystats">
      <div v-for="stat in keyStats" :key="stat.label" class="info-keystat">
        <dd>{{ stat.value }}</dd>
        <dt class="v-eyebrow">{{ stat.label }}</dt>
      </div>
    </dl>

    <section
      v-if="showPublicationCard"
      class="info-publication-card"
      :class="[
        `is-${versionShareState}`,
        { 'is-decision': versionShareState === 'pending' && canManageVersionPublication },
      ]"
      aria-labelledby="info-publication-title"
    >
      <div class="info-publication-header">
        <div class="info-publication-heading">
          <span class="info-publication-state">
            <span class="info-publication-state-dot" aria-hidden="true"></span>
            {{ publicationPresentation.label }}
          </span>
          <h3 id="info-publication-title">{{ publicationPresentation.title }}</h3>
        </div>
        <div
          v-if="canManageVersionPublication && versionShareState === 'published' && !publicationRemovalConfirmation"
          class="info-publication-inline-actions"
        >
          <button
            v-if="!isCurrentPublishedVersion"
            type="button"
            class="v-btn v-btn-primary v-btn-sm"
            :disabled="Boolean(publicationSaving)"
            @click="setPublicationState('published')"
          >
            <span>{{ publicationSaving === 'published' ? 'Making current…' : 'Make current' }}</span>
          </button>
          <button
            type="button"
            class="v-btn v-btn-quiet v-btn-sm"
            :disabled="Boolean(publicationSaving)"
            @click="publicationRemovalConfirmation = true"
          >
            Remove from shares
          </button>
        </div>
      </div>
      <p v-if="publicationPresentation.description">{{ publicationPresentation.description }}</p>
      <div
        v-if="canManageVersionPublication && (versionShareState !== 'published' || publicationRemovalConfirmation)"
        class="info-publication-actions"
      >
        <button
          v-if="versionShareState !== 'published'"
          type="button"
          class="v-btn v-btn-primary v-btn-sm"
          :disabled="Boolean(publicationSaving)"
          @click="setPublicationState('published')"
        >
          <svg class="icon"><use href="#icon-eye" /></svg>
          <span>{{ publicationSaving === 'published' ? 'Publishing…' : publicationPublishLabel }}</span>
        </button>
        <button
          v-if="versionShareState === 'pending'"
          type="button"
          class="v-btn v-btn-quiet v-btn-sm"
          :disabled="Boolean(publicationSaving)"
          @click="setPublicationState('internal')"
        >
          {{ publicationSaving === 'internal' ? 'Saving…' : 'Keep internal' }}
        </button>
        <template v-if="versionShareState === 'published' && publicationRemovalConfirmation">
          <button
            type="button"
            class="v-btn v-btn-quiet v-btn-sm"
            :disabled="Boolean(publicationSaving)"
            @click="publicationRemovalConfirmation = false"
          >
            Cancel
          </button>
          <button
            type="button"
            class="v-btn v-btn-danger v-btn-sm"
            :disabled="Boolean(publicationSaving)"
            @click="setPublicationState('internal')"
          >
            {{ publicationSaving === 'internal' ? 'Removing…' : 'Confirm removal' }}
          </button>
        </template>
      </div>
    </section>

    <section v-if="showChangelogCard" class="info-summary-card">
      <div class="info-summary-card-header">
        <h3 class="info-card-title">Changelog</h3>
        <button
          v-if="canEditVersionSummary && !editingSummary"
          type="button"
          class="info-summary-edit-button v-icon-action is-compact"
          :aria-label="`${versionSummary ? 'Edit' : 'Add'} changelog`"
          :title="`${versionSummary ? 'Edit' : 'Add'} changelog`"
          @click="beginSummaryEdit"
        >
          <svg class="icon"><use href="#icon-edit-3" /></svg>
        </button>
      </div>

      <form
        v-if="editingSummary"
        class="info-summary-edit-form"
        @submit.prevent="saveSummaryEdit"
      >
        <input
          ref="summaryInput"
          v-model="summaryDraft"
          class="v-input info-summary-input"
          maxlength="120"
          placeholder="Add changelog"
          :disabled="savingSummary"
          @keydown.escape.prevent="cancelSummaryEdit"
        />
        <button
          type="submit"
          class="info-summary-save v-icon-action is-compact"
          :disabled="savingSummary"
          aria-label="Save changelog"
          title="Save changelog"
        >
          <svg class="icon"><use href="#icon-check" /></svg>
        </button>
        <button
          type="button"
          class="info-summary-cancel v-icon-action is-compact"
          :disabled="savingSummary"
          aria-label="Cancel changelog edit"
          title="Cancel"
          @click="cancelSummaryEdit"
        >
          <svg class="icon"><use href="#icon-close" /></svg>
        </button>
      </form>

      <button
        v-else-if="versionSummary && canEditVersionSummary"
        type="button"
        class="info-summary-text is-editable"
        @click="beginSummaryEdit"
      >
        {{ versionSummary }}
      </button>
      <p v-else-if="versionSummary" class="info-summary-text">{{ versionSummary }}</p>
      <button
        v-else-if="canEditVersionSummary"
        type="button"
        class="info-summary-empty"
        @click="beginSummaryEdit"
      >
        Add a changelog
      </button>
      <p v-else class="info-summary-empty is-readonly">No changelog yet</p>
    </section>

    <section
      v-for="group in specGroups"
      :key="group.key"
      class="info-section"
    >
      <h3 class="info-section-title v-section-label v-section-label--ruled">{{ group.label }}</h3>
      <dl class="info-list">
        <div
          v-for="row in group.rows"
          :key="row.label"
          class="info-row"
          :class="{ 'info-row-mono': row.mono }"
        >
          <dt>{{ row.label }}</dt>
          <dd>{{ row.value }}</dd>
        </div>
      </dl>
    </section>

    <section v-if="isAdmin && adminFilePath" class="info-section info-path-utility" aria-labelledby="info-file-path-label">
      <h3 id="info-file-path-label" class="info-section-title v-section-label v-section-label--ruled">
        Location
        <span class="info-path-access">Admin only</span>
      </h3>
      <div class="info-path-control">
        <svg class="icon info-path-icon" aria-hidden="true"><use href="#icon-folder" /></svg>
        <code class="info-path-value" :title="adminFilePath">{{ adminFilePath }}</code>
        <button
          type="button"
          class="info-path-copy v-btn v-btn-quiet v-btn-sm"
          :class="{ 'is-copied': pathCopied }"
          :aria-label="pathCopied ? 'File path copied' : 'Copy file path'"
          :title="pathCopied ? 'Copied' : 'Copy file path'"
          @click="copyAdminFilePath"
        >
          <svg class="icon" aria-hidden="true"><use :href="pathCopied ? '#icon-check' : '#icon-copy'" /></svg>
          <span>{{ pathCopied ? 'Copied' : 'Copy' }}</span>
        </button>
      </div>
      <span class="v-sr-only" aria-live="polite">{{ pathCopied ? 'File path copied to clipboard' : '' }}</span>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onUnmounted, ref, toRefs, watch } from 'vue'
import { formatUploadDateLabel } from '../../utils/formatters'
import { notify } from '../../utils/toasts'

const props = defineProps({
  currentMedia: { type: Object, default: null },
  currentShot: { type: Object, default: null },
  mediaInfo: { type: Object, default: () => ({}) },
  isAdmin: { type: Boolean, default: false },
  isViewingVideo: { type: Boolean, default: false },
  isViewingPdf: { type: Boolean, default: false },
  canEditVersionSummary: { type: Boolean, default: false },
  updateVersionSummary: { type: Function, default: null },
  canManageVersionPublication: { type: Boolean, default: false },
  versionReviewEnabled: { type: Boolean, default: false },
  updateVersionPublication: { type: Function, default: null },
  formatTimecode: { type: Function, required: true }
})

const { currentMedia, mediaInfo, isViewingVideo, isViewingPdf, formatTimecode } = toRefs(props)

function formatUploadDate() {
  return formatUploadDateLabel(props.mediaInfo?.created_at)
}

const editingSummary = ref(false)
const savingSummary = ref(false)
const summaryDraft = ref('')
const summaryInput = ref(null)
const pathCopied = ref(false)
const publicationSaving = ref('')
const publicationRemovalConfirmation = ref(false)
let pathCopiedTimer = null

const currentVersionId = computed(() => (
  props.currentMedia?.horizons_shot_version_id || props.currentMedia?.version_id || ''
))

const currentVersion = computed(() => {
  const versionId = currentVersionId.value
  const versions = props.currentShot?.versions || []
  if (versionId) {
    const matched = versions.find(version => version?.id === versionId)
    if (matched) return matched
  }
  const mediaPath = props.currentMedia?.path || props.currentMedia?.file_path || ''
  if (mediaPath) {
    const matched = versions.find(version => (version?.path || version?.file_path || '') === mediaPath)
    if (matched) return matched
  }
  return props.currentMedia
})

const versionSummary = computed(() => {
  const source = currentVersion.value && Object.prototype.hasOwnProperty.call(currentVersion.value, 'notes')
    ? currentVersion.value.notes
    : props.currentMedia?.notes
  return String(source || '').trim()
})

const versionShareState = computed(() => {
  const state = String(currentVersion.value?.share_state || '').trim().toLowerCase()
  return ['published', 'pending', 'internal'].includes(state) ? state : 'published'
})
const shotVersions = computed(() => props.currentShot?.versions || [])
const latestShotVersion = computed(() => {
  const latestLabel = String(props.currentShot?.latest_version_label ?? '').trim()
  const matched = latestLabel
    ? shotVersions.value.find(version => String(version?.label ?? version?.version ?? '').trim() === latestLabel)
    : null
  return matched || shotVersions.value[shotVersions.value.length - 1] || null
})
const isLatestVersion = computed(() => (
  Boolean(currentVersion.value?.id)
  && currentVersion.value.id === latestShotVersion.value?.id
))
const shotDisplayName = computed(() => (
  props.currentShot?.shot_id || props.currentShot?.shot_code || 'the shot'
))
const publicationPublishLabel = computed(() => (
  isLatestVersion.value ? 'Publish to Review' : 'Publish older version'
))
const hasHeldVersions = computed(() => (
  shotVersions.value.some(version => (
    ['pending', 'internal'].includes(String(version?.share_state || '').trim().toLowerCase())
  ))
))
const hasOtherPublishedVersion = computed(() => (
  shotVersions.value.some(version => (
    version?.id !== currentVersion.value?.id
    && String(version?.share_state || '').trim().toLowerCase() === 'published'
  ))
))
const currentPublishedVersion = computed(() => {
  const published = shotVersions.value
    .filter(version => String(version?.share_state || '').trim().toLowerCase() === 'published')
    .sort((a, b) => (
      Number(a?.published_at ?? a?.created_at ?? 0) - Number(b?.published_at ?? b?.created_at ?? 0)
      || Number(a?.created_at || 0) - Number(b?.created_at || 0)
      || String(a?.id || '').localeCompare(String(b?.id || ''))
    ))
  return published[published.length - 1] || null
})
const isCurrentPublishedVersion = computed(() => (
  versionShareState.value === 'published'
  && currentPublishedVersion.value?.id === currentVersion.value?.id
))

const showPublicationCard = computed(() => (
  Boolean(currentVersion.value?.share_state)
  && (
    versionShareState.value !== 'published'
    || !isCurrentPublishedVersion.value
    || (
      props.canManageVersionPublication
      && (props.versionReviewEnabled || hasHeldVersions.value)
    )
  )
))

const publicationPresentation = computed(() => {
  if (versionShareState.value === 'pending') {
    if (!isLatestVersion.value) {
      return {
        title: 'Older version awaiting publication',
        label: 'Awaiting publication',
        description: props.canManageVersionPublication
          ? 'A newer version exists. Publishing this version will not change the shot status.'
          : 'A newer version exists. This version remains hidden from shares.',
      }
    }
    return {
      title: props.canManageVersionPublication ? 'Ready to publish' : 'Awaiting publication',
      label: 'Awaiting publication',
      description: hasOtherPublishedVersion.value
        ? (
          props.canManageVersionPublication
            ? `Publishing will update shares and move ${shotDisplayName.value} to Review.`
            : 'Clients still see the last published version.'
        )
        : (
          props.canManageVersionPublication
            ? `Publishing will make this version visible and move ${shotDisplayName.value} to Review.`
            : 'Hidden from shares until it’s published.'
        ),
    }
  }
  if (versionShareState.value === 'internal') {
    return {
      title: 'Internal version',
      label: 'Internal',
      description: props.canManageVersionPublication
        ? (
          isLatestVersion.value
            ? `Publish to make it visible and move ${shotDisplayName.value} to Review.`
            : 'A newer version exists. Publishing this version will not change the shot status.'
        )
        : 'Hidden from shares.',
    }
  }
  if (!isCurrentPublishedVersion.value) {
    return {
      title: 'Published history',
      label: 'Published',
      description: props.canManageVersionPublication
        ? 'Available in share history.'
        : '',
    }
  }
  return {
    title: 'Visible to shares',
    label: 'Published',
    description: publicationRemovalConfirmation.value
      ? (
        hasOtherPublishedVersion.value
          ? 'Shares will fall back to the previous published version.'
          : 'This shot will disappear from shares.'
      )
      : '',
  }
})

const rawFileName = computed(() => {
  const source = props.currentMedia?.path
    || props.currentMedia?.file_path
    || currentVersion.value?.path
    || currentVersion.value?.file_path
    || ''
  const filename = String(source).split(/[\\/]/).filter(Boolean).pop() || ''
  try {
    return decodeURIComponent(filename)
  } catch {
    return filename
  }
})

const mediaGlyph = computed(() => {
  if (props.isViewingVideo) return '#icon-video'
  if (props.isViewingPdf) return '#icon-file'
  return '#icon-image'
})

const fileExtension = computed(() => String(
  props.mediaInfo?.extension || props.currentMedia?.path?.split('.').pop() || '',
).toUpperCase())

const fileSize = computed(() => (
  props.mediaInfo?.size_formatted || props.currentMedia?.size_formatted || ''
))

/* Absent metadata should read as absent, not as "undefined fps". */
function spec(label, value, { suffix = '', mono = false } = {}) {
  if (value === null || value === undefined) return null
  const text = String(value).trim()
  if (!text || text === 'undefined' || text === 'null' || text === 'NaN') return null
  return { label, value: suffix ? `${text}${suffix}` : text, mono }
}

const specGroups = computed(() => {
  const info = props.mediaInfo || {}
  const groups = []

  if (props.isViewingVideo) {
    groups.push({
      key: 'video',
      label: 'Video',
      rows: [
        spec('Codec', info.codec),
        spec('Resolution', info.resolution, { mono: true }),
        spec('Duration', info.duration ? formatTimecode.value(info.duration) : '', { mono: true }),
        spec('Frame rate', info.fps, { suffix: ' fps', mono: true }),
        spec('Frames', info.frames, { mono: true }),
        spec('Bit depth', info.bit_depth, { suffix: '-bit', mono: true }),
        spec('Pixel format', info.pixel_format),
        spec('Color space', info.color_space),
        spec('Transfer', info.color_transfer),
        spec('Primaries', info.color_primaries),
        spec('Bitrate', info.video_bitrate, { mono: true }),
      ],
    })

    groups.push({
      key: 'audio',
      label: 'Audio',
      rows: [
        spec('Codec', info.audio?.codec),
        spec('Channels', info.audio?.channel_layout),
        spec('Sample rate', info.audio?.sample_rate, { mono: true }),
        spec('Bit depth', info.audio?.bit_depth, { suffix: '-bit', mono: true }),
        spec('Bitrate', info.audio?.bitrate, { mono: true }),
      ],
    })
  }

  groups.push({
    key: 'file',
    label: 'File',
    rows: [
      spec('Filename', rawFileName.value, { mono: true }),
      spec('Type', props.isViewingVideo ? null : fileExtension.value),
      spec('Resolution', props.isViewingVideo || props.isViewingPdf ? null : info.resolution, { mono: true }),
      spec('Pages', props.isViewingPdf ? info.pages : null, { mono: true }),
      spec('Size', fileSize.value, { mono: true }),
      spec('Bitrate', props.isViewingVideo ? info.container_bitrate : null, { mono: true }),
    ],
  })

  return groups
    .map(group => ({ ...group, rows: group.rows.filter(Boolean) }))
    .filter(group => group.rows.length)
})

/* The three numbers people actually come here for, pulled above the spec sheet. */
const keyStats = computed(() => {
  const info = props.mediaInfo || {}
  const stats = props.isViewingVideo
    ? [
      spec('Resolution', info.resolution),
      spec('Duration', info.duration ? formatTimecode.value(info.duration) : ''),
      spec('Frame rate', info.fps, { suffix: ' fps' }),
    ]
    : props.isViewingPdf
      ? [
        spec('Pages', info.pages),
        spec('Size', fileSize.value),
        spec('Type', fileExtension.value),
      ]
      : [
        spec('Resolution', info.resolution),
        spec('Size', fileSize.value),
        spec('Type', fileExtension.value),
      ]
  return stats.filter(Boolean)
})

const adminFilePath = computed(() => {
  return String(
    props.currentMedia?.file_path
    || props.currentMedia?.source_path
    || props.currentMedia?.path
    || currentVersion.value?.file_path
    || currentVersion.value?.path
    || '',
  )
})

const showChangelogCard = computed(() => Boolean(currentVersion.value || versionSummary.value || props.canEditVersionSummary))

function fallbackCopyText(value) {
  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  const copied = document.execCommand?.('copy')
  textarea.remove()
  if (!copied) throw new Error('Clipboard is unavailable')
}

async function copyAdminFilePath() {
  if (!props.isAdmin || !adminFilePath.value) return
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(adminFilePath.value)
    } else {
      fallbackCopyText(adminFilePath.value)
    }
    pathCopied.value = true
    window.clearTimeout(pathCopiedTimer)
    pathCopiedTimer = window.setTimeout(() => {
      pathCopied.value = false
    }, 1800)
  } catch (error) {
    console.error('Failed to copy file path')
    notify('Could not copy the file path.', { tone: 'error' })
  }
}

function canSaveSummary() {
  return props.canEditVersionSummary && typeof props.updateVersionSummary === 'function' && currentVersion.value
}

function beginSummaryEdit() {
  if (!canSaveSummary()) return
  summaryDraft.value = versionSummary.value
  editingSummary.value = true
  nextTick(() => {
    summaryInput.value?.focus?.()
    summaryInput.value?.select?.()
  })
}

function cancelSummaryEdit() {
  editingSummary.value = false
  summaryDraft.value = ''
}

async function saveSummaryEdit() {
  if (!canSaveSummary()) return
  const nextSummary = summaryDraft.value.trim()
  if (nextSummary === versionSummary.value) {
    cancelSummaryEdit()
    return
  }
  savingSummary.value = true
  try {
    await props.updateVersionSummary(currentVersion.value, nextSummary)
    cancelSummaryEdit()
  } catch (error) {
    console.error('Failed to update version summary')
    window.alert?.('Failed to update changelog. Please try again.')
  } finally {
    savingSummary.value = false
  }
}

async function setPublicationState(state) {
  if (
    publicationSaving.value
    || !props.canManageVersionPublication
    || typeof props.updateVersionPublication !== 'function'
    || !currentVersion.value
  ) return
  publicationSaving.value = state
  try {
    await props.updateVersionPublication(currentVersion.value, state)
  } catch (error) {
    console.error('Failed to update version publication')
    notify('Could not update who can see this version.', { tone: 'error' })
  } finally {
    publicationSaving.value = ''
    publicationRemovalConfirmation.value = false
  }
}

watch(() => currentVersion.value?.id, () => {
  publicationRemovalConfirmation.value = false
})

onUnmounted(() => window.clearTimeout(pathCopiedTimer))
</script>

<style>
.file-info-panel {
  --info-gutter: 16px;
  --info-label-width: 104px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 var(--info-gutter) 32px;
}

/* ─── Identity ───────────────────────────────────────────────
   Stays put while the spec sheet scrolls, so you always know
   which file you are reading. */
.info-header {
  position: sticky;
  top: 0;
  z-index: 2;
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  margin: 0 calc(var(--info-gutter) * -1);
  padding: 13px var(--info-gutter) 12px;
  background: color-mix(in srgb, var(--v-surface-panel) 34%, var(--v-bg-base));
  border-bottom: 1px solid var(--v-divider);
}

.info-header-glyph {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: var(--v-radius-md);
  border: 1px solid color-mix(in srgb, var(--v-control-border) 74%, transparent);
  background: color-mix(in srgb, var(--v-surface-inset) 72%, transparent);
  color: var(--v-text-muted);
}

.info-header-glyph .icon {
  width: 15px;
  height: 15px;
}

.info-header-copy {
  min-width: 0;
}

.info-title {
  margin: 0 0 3px;
  font-size: var(--v-text-md);
  font-weight: 640;
  line-height: 1.25;
  letter-spacing: 0;
  color: var(--v-text);
  /* Two lines then ellipsis. Long version names should not push the panel down. */
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  overflow-wrap: anywhere;
}

.info-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 0;
  min-width: 0;
  font-size: var(--v-text-xs);
  color: var(--v-text-muted);
  letter-spacing: 0;
}

.info-meta-dot {
  opacity: 0.5;
}

.info-meta strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  color: var(--v-text-secondary);
}

/* ─── Key stats ──────────────────────────────────────────────
   Echoes the tracker header's "48 shots · 3:14 · 4,758 frames". */
.info-keystats {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: 1fr;
  margin: 0 calc(var(--info-gutter) * -1);
  padding: 14px var(--info-gutter);
  border-bottom: 1px solid var(--v-divider);
}

.info-keystat {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 0 6px;
  text-align: center;
}

.info-keystat + .info-keystat {
  border-left: 1px solid var(--v-divider-subtle);
}

.info-keystat dd {
  margin: 0;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 650;
  line-height: 1.15;
  font-variant-numeric: tabular-nums;
}

.info-keystat dt {
  line-height: 1;
}

/* ─── Admin file path ────────────────────────────────────── */
.info-path-access {
  margin-left: auto;
  padding: 2px 6px;
  flex: 0 0 auto;
  border-radius: var(--v-radius-sm);
  background: color-mix(in srgb, var(--v-warning) 12%, transparent);
  color: color-mix(in srgb, var(--v-warning) 78%, var(--v-text));
  font-size: var(--v-text-3xs);
  font-weight: 700;
  letter-spacing: 0.08em;
}

.info-path-control {
  min-height: 40px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  padding: 4px 4px 4px 11px;
  border-radius: var(--v-radius-md);
  border: 1px solid color-mix(in srgb, var(--v-control-border) 72%, transparent);
  background: var(--v-surface-inset);
}

.info-path-icon {
  width: 14px;
  height: 14px;
  color: var(--v-accent);
}

.info-path-value {
  min-width: 0;
  overflow: hidden;
  color: var(--v-text-secondary);
  font: 500 var(--v-text-xs)/1.35 var(--v-font-mono, monospace);
  text-overflow: ellipsis;
  white-space: nowrap;
  user-select: text;
}

.info-path-copy {
  min-width: 68px;
  gap: 6px;
}

.info-path-copy .icon {
  width: 12px;
  height: 12px;
}

.info-path-copy.is-copied {
  background: color-mix(in srgb, var(--v-accent) 13%, var(--v-surface-inline));
  color: var(--v-accent);
}

.info-publication-card {
  --info-share: var(--v-accent);
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin: 14px 0 0;
  padding: 11px 12px;
  overflow: hidden;
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--info-share) 7%, color-mix(in srgb, var(--v-bg-base) 24%, transparent));
  border: 1px solid color-mix(in srgb, var(--info-share) 22%, transparent);
}

.info-publication-card.is-pending {
  --info-share: var(--v-warning);
}

.info-publication-card.is-internal {
  --info-share: var(--v-text-muted);
}

.info-publication-card.is-decision {
  gap: 9px;
  padding: 12px;
}

.info-publication-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-2);
  min-width: 0;
}

.info-publication-heading {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.info-publication-heading h3 {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-base);
  font-weight: 650;
  letter-spacing: 0;
  line-height: 1.25;
}

.info-publication-state {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: color-mix(in srgb, var(--info-share) 78%, var(--v-text));
  font-size: var(--v-text-2xs);
  font-weight: 650;
  letter-spacing: 0.06em;
  line-height: 1.2;
  text-transform: uppercase;
}

.info-publication-state-dot {
  width: 5px;
  height: 5px;
  flex: 0 0 auto;
  border-radius: var(--v-radius-full);
  background: currentColor;
}

.info-publication-card p {
  margin: 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.35;
}

.info-publication-inline-actions,
.info-publication-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.info-publication-inline-actions {
  flex: 0 0 auto;
  justify-content: flex-end;
}

.info-publication-inline-actions .v-btn,
.info-publication-actions .v-btn {
  min-height: 28px;
  padding-inline: 9px;
}

@media (max-width: 480px) {
  .info-publication-header {
    flex-direction: column;
    align-items: stretch;
  }

  .info-publication-inline-actions,
  .info-publication-actions {
    width: 100%;
  }

  .info-publication-inline-actions .v-btn,
  .info-publication-actions .v-btn {
    flex: 1 1 auto;
    min-height: 36px;
  }
}

.info-section {
  padding: 18px 2px 2px;
}

/* Styling comes from .v-section-label. */
.info-section-title {
  margin-bottom: 8px;
}

.info-path-access {
  order: 91;
}

.info-summary-card {
  margin: 0;
  padding: 16px 2px 18px;
  border-bottom: 1px solid var(--v-divider);
}

.info-summary-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 22px;
  margin-bottom: 7px;
}

/* Card headings are labels, not section dividers, so they do not need a trailing rule. */
.info-card-title {
  margin: 0;
  font-family: var(--v-font);
  font-size: var(--v-text-2xs);
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--v-text-muted);
}

.info-summary-edit-button,
.info-summary-save,
.info-summary-cancel {
  width: 30px;
  min-width: 30px;
  height: 30px;
  min-height: 30px;
  color: var(--v-text-muted);
}

.info-summary-edit-button:hover:not(:disabled),
.info-summary-save:hover:not(:disabled) {
  color: var(--v-accent);
}

.info-summary-edit-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 6px;
}

.info-summary-input {
  height: 34px;
  min-width: 0;
  font-size: var(--v-text-base);
}

.info-summary-text {
  display: block;
  width: 100%;
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--v-text);
  font: 600 var(--v-text-md)/1.38 var(--v-font);
  letter-spacing: 0;
  text-align: left;
  word-break: break-word;
}

.info-summary-text.is-editable {
  cursor: text;
}

.info-summary-text.is-editable:hover {
  color: var(--v-text);
}

.info-summary-empty {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 34px;
  padding: 0 10px;
  border: 1px solid color-mix(in srgb, var(--v-control-border) 76%, transparent);
  border-radius: var(--v-radius-md);
  background: var(--v-surface-inset);
  color: var(--v-text-secondary);
  font: 600 var(--v-text-sm)/1 var(--v-font);
  letter-spacing: 0;
  text-align: left;
  cursor: pointer;
}

.info-summary-empty:hover {
  border-color: var(--v-control-border-hover);
  color: var(--v-text);
}

.info-summary-empty.is-readonly {
  cursor: default;
  color: var(--v-text-muted);
}

.info-summary-empty.is-readonly:hover {
  border-color: color-mix(in srgb, var(--v-control-border) 76%, transparent);
  color: var(--v-text-muted);
}

/* Fixed label column: values line up in one edge you can run your eye down,
   instead of floating right against ragged labels. */
.info-list {
  margin: 0;
  display: flex;
  flex-direction: column;
}

.info-row {
  display: grid;
  grid-template-columns: var(--info-label-width) minmax(0, 1fr);
  align-items: baseline;
  gap: 12px;
  padding: 6px 4px;
  border-radius: var(--v-radius-sm);
}

.info-row:hover {
  background: color-mix(in srgb, var(--v-bg-hover) 42%, transparent);
}

.info-row dt {
  margin: 0;
  font-size: var(--v-text-sm);
  color: var(--v-text-muted);
  letter-spacing: 0;
}

.info-row dd {
  margin: 0;
  min-width: 0;
  font-size: var(--v-text-sm);
  font-weight: 550;
  color: var(--v-text);
  font-family: var(--v-font);
  line-height: 1.4;
  text-align: left;
  overflow-wrap: anywhere;
  user-select: text;
}

.info-row-mono dd {
  font-variant-numeric: tabular-nums;
}

@media (max-width: 768px) {
  .file-info-panel {
    --info-gutter: var(--v-viewer-mobile-content-gutter);
    --info-label-width: 108px;
    padding-bottom: 32px;
  }

  .info-header { position: static; padding-top: 15px; }
  .info-title { font-size: var(--v-text-lg); }
  .info-keystats { padding-block: 14px; }
  .info-keystat dd { font-size: var(--v-text-lg); }
  .info-row { padding-block: 9px; }
  .info-row dt,
  .info-row dd { font-size: var(--v-text-base); }
}
</style>
