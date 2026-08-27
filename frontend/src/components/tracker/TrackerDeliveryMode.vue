<template>
  <section class="tracker-delivery" :class="{ 'has-image': !!projectThumbnailUrl, 'is-busy': trackerDownloadBusy }">
    <!-- Cinematic image stage -->
    <div class="td-stage" aria-hidden="true">
      <div class="td-stage-image" :class="{ 'is-empty': !projectThumbnailUrl }">
        <img
          v-if="projectThumbnailUrl"
          :src="projectThumbnailUrl"
          alt=""
          @error="handleImageError"
        />
        <div v-else class="td-stage-empty">
          <svg class="icon"><use href="#icon-package" /></svg>
        </div>
      </div>
      <div class="td-stage-vignette td-stage-vignette--scrim"></div>
      <div class="td-stage-vignette td-stage-vignette--right"></div>
      <div class="td-stage-vignette td-stage-vignette--bottom"></div>
      <div class="td-stage-vignette td-stage-vignette--top"></div>
      <div class="td-stage-aurora"></div>
      <div class="td-stage-grain"></div>
    </div>

    <!-- Hero content -->
    <div class="td-shell">
      <article class="td-hero">
        <header class="td-mark" :title="teamName">
          <div v-if="deliveryLogoUrl" class="td-mark-logo">
            <img :src="deliveryLogoUrl" alt="" @error="handleLogoError" />
          </div>
          <div v-else class="td-mark-monogram" aria-hidden="true">{{ teamMonogram }}</div>
          <span class="td-mark-divider" aria-hidden="true"></span>
          <span class="td-mark-team">{{ teamName }}</span>
        </header>

        <p class="td-eyebrow">
          <span class="td-eyebrow-dot" aria-hidden="true"></span>
          <span class="td-eyebrow-label">Private delivery</span>
          <span class="td-eyebrow-rule" aria-hidden="true"></span>
          <span class="td-eyebrow-meta">{{ preparedLabel }}</span>
        </p>

        <h1 class="td-title">{{ projectTitle }}</h1>

        <p class="td-message">{{ deliveryMessage }}</p>

        <p v-if="deliveryNotes" class="td-notes">{{ deliveryNotes }}</p>

        <ul class="td-stats" aria-label="Delivery summary">
          <li class="td-stat">
            <span class="td-stat-value">{{ shotCountValue }}</span>
            <span class="td-stat-label">{{ shotCountLabel }}</span>
          </li>
          <li class="td-stat">
            <span class="td-stat-value">{{ trackerName }}</span>
            <span class="td-stat-label">tracker</span>
          </li>
          <li class="td-stat">
            <span class="td-stat-value">
              <span class="td-stat-pulse" aria-hidden="true"></span>
              Files
            </span>
            <span class="td-stat-label">prepared</span>
          </li>
        </ul>

        <div class="td-actions">
          <button
            type="button"
            class="td-cta-primary"
            :class="{ 'is-disabled': !canDownloadTrackerLatest && !trackerDownloadBusy, 'is-busy': trackerDownloadBusy }"
            :disabled="!canDownloadTrackerLatest || trackerDownloadBusy"
            :aria-busy="trackerDownloadBusy ? 'true' : 'false'"
            :style="trackerDownloadBusy ? { '--td-progress': downloadPercent + '%' } : null"
            @click="handleDownloadClick"
          >
            <span class="td-cta-shimmer" aria-hidden="true"></span>
            <span class="td-cta-content">
              <span class="td-cta-icon">
                <svg v-if="trackerDownloadBusy" class="icon spinning" aria-hidden="true"><use href="#icon-loader" /></svg>
                <svg v-else class="icon" aria-hidden="true"><use href="#icon-download" /></svg>
              </span>
              <span class="td-cta-text">{{ downloadLabel }}</span>
              <span v-if="trackerDownloadBusy && downloadPercent > 0" class="td-cta-percent">{{ downloadPercent }}%</span>
            </span>
            <span v-if="trackerDownloadBusy" class="td-cta-progress" aria-hidden="true"></span>
          </button>

          <button type="button" class="td-cta-secondary" @click="handleViewTrackerClick">
            <svg class="icon" aria-hidden="true"><use href="#icon-list" /></svg>
            <span>View tracker</span>
            <span class="td-cta-secondary-arrow" aria-hidden="true">
              <svg viewBox="0 0 16 16" fill="none">
                <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </span>
          </button>
        </div>

        <p class="td-action-note">{{ actionNote }}</p>

        <div v-if="deliveryLinks.length" class="td-links" aria-label="Delivery links">
          <a
            v-for="link in deliveryLinks"
            :key="`${link.label}-${link.url}`"
            class="td-link"
            :href="link.url"
            target="_blank"
            rel="noopener noreferrer"
          >
            <span class="td-link-label">{{ link.label }}</span>
            <svg class="icon" aria-hidden="true"><use href="#icon-external-link" /></svg>
          </a>
        </div>

      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  project: { type: Object, default: null },
  currentTracker: { type: Object, default: null },
  teamName: { type: String, default: 'Vue' },
  deliveryMessage: { type: String, default: '' },
  deliveryNotes: { type: String, default: '' },
  deliveryLinks: { type: Array, default: () => [] },
  deliveryLogoUrl: { type: String, default: '' },
  projectThumbnailUrl: { type: String, default: '' },
  canDownloadTrackerLatest: { type: Boolean, default: false },
  trackerDownloadBusy: { type: Boolean, default: false },
  trackerDownloadProgress: { type: Object, default: null },
  downloadTrackerLatestVersions: { type: Function, default: () => {} },
})

const emit = defineEmits(['view-tracker'])

const imageFailed = ref(false)
const logoFailed = ref(false)

const projectTitle = computed(() => props.project?.title || 'Project Delivery')
const teamName = computed(() => String(props.teamName || '').trim() || 'Vue')
const teamMonogram = computed(() => {
  const tokens = teamName.value.split(/\s+/).filter(Boolean)
  if (tokens.length === 0) return 'V'
  if (tokens.length === 1) {
    const single = tokens[0]
    if (single.length <= 3) return single.toUpperCase()
    return single.slice(0, 1).toUpperCase()
  }
  return tokens.slice(0, 2).map((t) => t[0]).join('').toUpperCase()
})
const trackerName = computed(() => props.currentTracker?.name || 'Tracker')
const shotCount = computed(() => Number(props.currentTracker?.shot_count || props.currentTracker?.shots?.length || 0))
const shotCountValue = computed(() => shotCount.value.toLocaleString())
const shotCountLabel = computed(() => (shotCount.value === 1 ? 'shot' : 'shots'))

const preparedLabel = computed(() => {
  try {
    const formatter = new Intl.DateTimeFormat(undefined, { month: 'long', day: 'numeric', year: 'numeric' })
    return formatter.format(new Date())
  } catch {
    return ''
  }
})

const actionNote = computed(() => {
  if (!props.canDownloadTrackerLatest && !props.trackerDownloadBusy) return 'Downloads are not enabled for this delivery.'
  if (props.trackerDownloadBusy) return 'Packaging the latest approved files for handoff.'
  return 'Latest versions packaged and ready for handoff.'
})

const downloadPercent = computed(() => {
  const raw = Number(props.trackerDownloadProgress?.progress || 0)
  return Math.max(0, Math.min(100, Math.round(raw)))
})

const downloadLabel = computed(() => {
  if (!props.canDownloadTrackerLatest && !props.trackerDownloadBusy) return 'No downloads available'
  if (!props.trackerDownloadBusy) return 'Download all'
  const message = props.trackerDownloadProgress?.message || 'Packaging'
  if (downloadPercent.value >= 100) return 'Starting download'
  if (downloadPercent.value > 0) return message
  return `${message}…`
})

function handleDownloadClick() {
  props.downloadTrackerLatestVersions()
}

function handleViewTrackerClick() {
  emit('view-tracker')
}

function handleImageError(event) {
  imageFailed.value = true
  if (event?.target) event.target.style.display = 'none'
}

function handleLogoError(event) {
  logoFailed.value = true
  if (event?.target) event.target.style.display = 'none'
}
</script>

<style scoped>
/* ─── Shell adjustments while delivery is active ────────────────────────── */
:global(.main-wrapper:has(.tracker-delivery) .unified-nav) {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 56px;
  padding-inline: clamp(16px, 4vw, 36px);
  background: linear-gradient(180deg, color-mix(in srgb, var(--v-bg-black) 56%, transparent), transparent);
  border-bottom: 0;
  z-index: 80;
  pointer-events: auto;
}

:global(.main-wrapper:has(.tracker-delivery) .unified-nav .nav-brand) {
  opacity: 0.78;
}

:global(.main-wrapper:has(.tracker-delivery) .unified-nav .share-badge) {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 9px;
  border: 1px solid color-mix(in srgb, var(--v-accent) 26%, transparent);
  border-radius: var(--v-radius-full);
  color: color-mix(in srgb, var(--v-accent) 78%, var(--v-text));
  background: color-mix(in srgb, var(--v-bg-black) 74%, transparent);
  font-size: var(--v-text-2xs);
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

:global(.main-wrapper:has(.tracker-delivery) .unified-nav .share-origin-badge) {
  max-width: min(56vw, 460px);
  height: 22px;
  border-color: color-mix(in srgb, var(--v-accent) 18%, transparent);
  background: color-mix(in srgb, var(--v-bg-black) 66%, transparent);
  color: color-mix(in srgb, var(--v-text-secondary) 82%, transparent);
}

:global(.main-wrapper:has(.tracker-delivery) .unified-nav .nav-center:not(.share-origin-center)),
:global(.main-wrapper:has(.tracker-delivery) .unified-nav .nav-right) {
  opacity: 0;
  pointer-events: none;
}

:global(.project-detail:has(.tracker-delivery) .project-header-bar) {
  display: none;
}

:global(.project-detail:has(.tracker-delivery)) {
  background: var(--v-bg-black);
}

/* ─── Section root ──────────────────────────────────────────────────────── */
.tracker-delivery {
  --td-ease: cubic-bezier(0.16, 1, 0.3, 1);
  --td-content-w: clamp(420px, 38vw, 580px);
  --td-content-pad-x: clamp(28px, 6vw, 96px);
  --td-content-pad-y: clamp(72px, 11vh, 132px);
  --td-accent-soft: color-mix(in srgb, var(--v-accent) 56%, transparent);

  position: relative;
  flex: 1;
  min-height: 100svh;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  overflow: hidden;
  isolation: isolate;
  padding: var(--td-content-pad-y) var(--td-content-pad-x);
  background: var(--v-bg-black);
  color: var(--v-text);
}

/* ─── Atmospheric image stage ───────────────────────────────────────────── */
.td-stage {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}

.td-stage-image {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: radial-gradient(ellipse at 30% 35%, color-mix(in srgb, var(--v-surface-panel) 36%, var(--v-bg-black)), var(--v-bg-black) 72%);
}

.td-stage-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
  filter: saturate(1.04) contrast(1.06) brightness(0.96);
  transform-origin: 38% 50%;
  animation:
    td-image-arrive 1500ms var(--td-ease) both,
    td-image-breathe 26s ease-in-out 1500ms infinite alternate;
}

.td-stage-empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: color-mix(in srgb, var(--v-accent) 64%, var(--v-text));
  opacity: 0.42;
}

.td-stage-empty .icon {
  width: 124px;
  height: 124px;
  filter: drop-shadow(0 24px 64px color-mix(in srgb, var(--v-accent) 28%, transparent));
}

/* Soft side-to-content gradient that lets the image breathe on the left */
.td-stage-vignette {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.td-stage-vignette--scrim {
  background:
    radial-gradient(120% 120% at 100% 50%, color-mix(in srgb, var(--v-bg-black) 78%, transparent) 0%, color-mix(in srgb, var(--v-bg-black) 38%, transparent) 36%, transparent 64%);
  z-index: 1;
}

.td-stage-vignette--right {
  background: linear-gradient(90deg, transparent 0%, transparent 38%, color-mix(in srgb, var(--v-bg-black) 32%, transparent) 56%, color-mix(in srgb, var(--v-bg-black) 78%, transparent) 76%, color-mix(in srgb, var(--v-bg-black) 92%, transparent) 100%);
  z-index: 1;
}

.td-stage-vignette--top {
  height: 35%;
  bottom: auto;
  background: linear-gradient(180deg, color-mix(in srgb, var(--v-bg-black) 80%, transparent) 0%, color-mix(in srgb, var(--v-bg-black) 24%, transparent) 60%, transparent 100%);
  z-index: 1;
}

.td-stage-vignette--bottom {
  top: auto;
  height: 38%;
  background: linear-gradient(180deg, transparent 0%, color-mix(in srgb, var(--v-bg-black) 38%, transparent) 40%, color-mix(in srgb, var(--v-bg-black) 84%, transparent) 100%);
  z-index: 1;
}

/* Subtle accent aurora behind the title — feels like brand light spilling in */
.td-stage-aurora {
  position: absolute;
  top: 38%;
  right: -8%;
  width: 720px;
  height: 720px;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 50%, color-mix(in srgb, var(--v-accent) 18%, transparent) 0%, color-mix(in srgb, var(--v-accent) 4%, transparent) 38%, transparent 70%);
  filter: blur(20px);
  z-index: 1;
  opacity: 0;
  animation: td-aurora-glow 1800ms var(--td-ease) 220ms both;
  pointer-events: none;
}

.td-stage-grain {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  mix-blend-mode: soft-light;
  opacity: 0.10;
  background-image: repeating-radial-gradient(circle at 17% 23%, rgba(255, 255, 255, 0.18) 0 0.6px, transparent 0.8px 3px);
}

/* ─── Content shell ─────────────────────────────────────────────────────── */
.td-shell {
  position: relative;
  z-index: 2;
  width: var(--td-content-w);
  max-width: 100%;
  display: flex;
  align-items: center;
  justify-content: flex-start;
}

.td-hero {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 22px;
}

/* ─── Brand mark row ────────────────────────────────────────────────────── */
.td-mark {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 44px;
  margin-bottom: 6px;
  opacity: 0;
  animation: td-rise 720ms var(--td-ease) 80ms forwards;
}

.td-mark-logo {
  display: flex;
  align-items: center;
  max-width: 168px;
  max-height: 56px;
}

.td-mark-logo img {
  display: block;
  max-width: 100%;
  max-height: 56px;
  object-fit: contain;
  filter: drop-shadow(0 10px 30px rgba(0, 0, 0, 0.45));
}

.td-mark-monogram {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  height: 44px;
  padding: 0 12px;
  border-radius: var(--v-radius-lg);
  border: 1px solid color-mix(in srgb, var(--v-text) 14%, transparent);
  background:
    linear-gradient(140deg, color-mix(in srgb, var(--v-accent) 22%, transparent) 0%, transparent 60%),
    color-mix(in srgb, var(--v-bg-black) 78%, transparent);
  color: var(--v-text);
  font-size: var(--v-text-xl);
  font-weight: 800;
  letter-spacing: 0.04em;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.07),
    0 12px 32px rgba(0, 0, 0, 0.36);
}

.td-mark-divider {
  width: 1px;
  height: 22px;
  background: linear-gradient(180deg, transparent, color-mix(in srgb, var(--v-text-secondary) 38%, transparent), transparent);
}

.td-mark-team {
  color: color-mix(in srgb, var(--v-text-secondary) 84%, var(--v-text));
  font-size: var(--v-text-base);
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

/* ─── Eyebrow with pulsing dot + prepared date ─────────────────────────── */
.td-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  color: color-mix(in srgb, var(--v-accent) 64%, var(--v-text-secondary));
  font-size: var(--v-text-xs);
  font-weight: 750;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  line-height: 1;
  opacity: 0;
  animation: td-rise 720ms var(--td-ease) 160ms forwards;
}

.td-eyebrow-dot {
  position: relative;
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--v-accent);
  box-shadow: 0 0 0 0 color-mix(in srgb, var(--v-accent) 60%, transparent);
  animation: td-dot-pulse 2400ms var(--td-ease) infinite;
}

.td-eyebrow-rule {
  flex: 0 0 auto;
  width: 14px;
  height: 1px;
  background: color-mix(in srgb, var(--v-text-secondary) 28%, transparent);
}

.td-eyebrow-meta {
  color: color-mix(in srgb, var(--v-text-secondary) 64%, transparent);
  font-weight: 600;
  letter-spacing: 0.12em;
}

/* ─── Hero title ───────────────────────────────────────────────────────── */
.td-title {
  margin: 0;
  color: var(--v-text);
  font-size: clamp(46px, 5.6vw, 84px);
  font-weight: 820;
  letter-spacing: 0;
  line-height: 0.94;
  text-wrap: balance;
  max-width: 13ch;
  text-shadow: 0 24px 60px rgba(0, 0, 0, 0.42);
  opacity: 0;
  animation: td-rise 880ms var(--td-ease) 240ms forwards;
}

/* ─── Body copy ────────────────────────────────────────────────────────── */
.td-message {
  margin: 0;
  color: color-mix(in srgb, var(--v-text-secondary) 88%, var(--v-text));
  font-size: clamp(16px, 1.2vw, 19px);
  line-height: 1.55;
  max-width: 42ch;
  opacity: 0;
  animation: td-rise 800ms var(--td-ease) 320ms forwards;
}

.td-notes {
  margin: 0;
  max-width: 46ch;
  padding: 12px 14px 12px 16px;
  border-radius: var(--v-radius-md);
  border: 1px solid color-mix(in srgb, var(--v-text) 8%, transparent);
  border-left: 2px solid color-mix(in srgb, var(--v-accent) 60%, transparent);
  background: color-mix(in srgb, var(--v-bg-black) 62%, transparent);
  color: color-mix(in srgb, var(--v-text-secondary) 92%, var(--v-text));
  font-size: var(--v-text-md);
  line-height: 1.6;
  white-space: pre-wrap;
  opacity: 0;
  animation: td-rise 800ms var(--td-ease) 380ms forwards;
}

/* ─── Stat tiles ───────────────────────────────────────────────────────── */
.td-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 4px 0 0;
  padding: 0;
  list-style: none;
}

.td-stat {
  --td-stat-delay: 0ms;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 11px 16px 12px;
  min-width: 96px;
  border-radius: var(--v-radius-lg);
  border: 1px solid color-mix(in srgb, var(--v-text) 10%, transparent);
  background:
    linear-gradient(140deg, color-mix(in srgb, var(--v-text) 4%, transparent), transparent 60%),
    color-mix(in srgb, var(--v-bg-black) 70%, transparent);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 14px 28px rgba(0, 0, 0, 0.18);
  opacity: 0;
  transform: translateY(8px);
  animation: td-rise 720ms var(--td-ease) var(--td-stat-delay) forwards;
}

.td-stat:nth-child(1) { --td-stat-delay: 440ms; }
.td-stat:nth-child(2) { --td-stat-delay: 500ms; }
.td-stat:nth-child(3) { --td-stat-delay: 560ms; }

.td-stat-value {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--v-text);
  font-size: var(--v-text-2xl);
  font-weight: 760;
  line-height: 1.1;
  letter-spacing: 0;
}

.td-stat-label {
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.td-stat-pulse {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--v-accent);
  box-shadow: 0 0 8px color-mix(in srgb, var(--v-accent) 70%, transparent);
  animation: td-dot-pulse 2400ms var(--td-ease) 600ms infinite;
}

/* ─── Actions ──────────────────────────────────────────────────────────── */
.td-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--v-space-3);
  margin-top: var(--v-space-2);
  opacity: 0;
  animation: td-rise 800ms var(--td-ease) 620ms forwards;
}

/* Primary CTA — large pill with subtle shimmer + progress fill */
.td-cta-primary {
  --td-progress: 0%;
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 56px;
  padding: 0 28px;
  border: 0;
  border-radius: var(--v-button-radius);
  background:
    linear-gradient(140deg, color-mix(in srgb, var(--v-accent) 100%, white 6%) 0%, var(--v-accent) 60%, color-mix(in srgb, var(--v-accent) 90%, var(--v-bg-black)) 100%);
  color: #08130b;
  font-family: var(--v-font);
  font-size: var(--v-text-md);
  font-weight: 800;
  letter-spacing: 0;
  cursor: pointer;
  overflow: hidden;
  isolation: isolate;
  box-shadow:
    0 18px 48px color-mix(in srgb, var(--v-accent) 22%, transparent),
    0 0 0 1px color-mix(in srgb, var(--v-accent) 56%, transparent),
    inset 0 1px 0 rgba(255, 255, 255, 0.36),
    inset 0 -1px 0 rgba(0, 0, 0, 0.22);
  transition:
    box-shadow 280ms var(--td-ease),
    filter 220ms var(--td-ease);
}

.td-cta-primary:hover:not(:disabled) {
  filter: brightness(1.04);
  box-shadow:
    0 24px 64px color-mix(in srgb, var(--v-accent) 30%, transparent),
    0 0 0 1px color-mix(in srgb, var(--v-accent) 64%, transparent),
    inset 0 1px 0 rgba(255, 255, 255, 0.42),
    inset 0 -1px 0 rgba(0, 0, 0, 0.22);
}

.td-cta-primary:focus-visible {
  outline: none;
  box-shadow:
    0 0 0 3px color-mix(in srgb, var(--v-accent) 36%, transparent),
    0 18px 48px color-mix(in srgb, var(--v-accent) 22%, transparent),
    inset 0 1px 0 rgba(255, 255, 255, 0.36),
    inset 0 -1px 0 rgba(0, 0, 0, 0.22);
}

.td-cta-primary.is-disabled,
.td-cta-primary:disabled {
  cursor: not-allowed;
  filter: saturate(0.4) brightness(0.6);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.16),
    inset 0 -1px 0 rgba(0, 0, 0, 0.22),
    0 0 0 1px color-mix(in srgb, var(--v-text-secondary) 24%, transparent);
}

.td-cta-shimmer {
  position: absolute;
  inset: 0;
  z-index: 1;
  background: linear-gradient(110deg, transparent 30%, rgba(255, 255, 255, 0.4) 48%, transparent 66%);
  transform: translateX(-110%);
  pointer-events: none;
}

.td-cta-primary:not(:disabled) .td-cta-shimmer {
  animation: td-shimmer 4400ms ease-in-out 1100ms infinite;
}

.td-cta-content {
  position: relative;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 11px;
}

.td-cta-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--v-radius-full);
  background: rgba(8, 19, 11, 0.16);
}

.td-cta-icon .icon {
  width: 16px;
  height: 16px;
}

.td-cta-icon .icon.spinning {
  animation: td-spin 900ms linear infinite;
}

.td-cta-text {
  white-space: nowrap;
}

.td-cta-percent {
  display: inline-block;
  padding: 2px 8px;
  margin-left: var(--v-space-1);
  border-radius: var(--v-radius-full);
  background: rgba(8, 19, 11, 0.18);
  color: rgba(8, 19, 11, 0.86);
  font-size: var(--v-text-xs);
  font-weight: 800;
  letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
}

.td-cta-progress {
  position: absolute;
  inset: 0;
  z-index: 0;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.18) 0%, rgba(255, 255, 255, 0.32) 100%);
  clip-path: inset(0 calc(100% - var(--td-progress)) 0 0);
  transition: clip-path 320ms var(--td-ease);
  pointer-events: none;
}

.td-cta-primary.is-busy .td-cta-shimmer {
  animation-duration: 1600ms;
}

/* Secondary CTA — quietly elegant ghost */
.td-cta-secondary {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  min-height: 56px;
  padding: 0 22px 0 20px;
  border-radius: var(--v-button-radius);
  border: 1px solid color-mix(in srgb, var(--v-text) 14%, transparent);
  background: color-mix(in srgb, var(--v-bg-black) 58%, transparent);
  color: var(--v-text);
  font-family: var(--v-font);
  font-size: var(--v-text-md);
  font-weight: 700;
  letter-spacing: 0;
  cursor: pointer;
  transition:
    border-color 220ms var(--td-ease),
    background 220ms var(--td-ease),
    color 220ms var(--td-ease);
}

.td-cta-secondary .icon {
  width: 16px;
  height: 16px;
  color: color-mix(in srgb, var(--v-accent) 68%, var(--v-text-secondary));
}

.td-cta-secondary:hover {
  border-color: color-mix(in srgb, var(--v-accent) 36%, transparent);
  background: color-mix(in srgb, var(--v-bg-black) 48%, transparent);
  color: var(--v-text);
}

.td-cta-secondary:focus-visible {
  outline: none;
  border-color: color-mix(in srgb, var(--v-accent) 56%, transparent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--v-accent) 24%, transparent);
}

.td-cta-secondary-arrow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  margin-left: 2px;
  color: color-mix(in srgb, var(--v-text-secondary) 90%, var(--v-text));
  transition: transform 220ms var(--td-ease), color 220ms var(--td-ease);
}

.td-cta-secondary-arrow svg {
  width: 100%;
  height: 100%;
}

.td-cta-secondary:hover .td-cta-secondary-arrow {
  color: var(--v-accent);
  transform: translateX(2px);
}

.td-action-note {
  margin: -2px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  line-height: 1.5;
  letter-spacing: 0.005em;
  opacity: 0;
  animation: td-rise 720ms var(--td-ease) 720ms forwards;
}

/* ─── Delivery links ───────────────────────────────────────────────────── */
.td-links {
  display: flex;
  flex-wrap: wrap;
  gap: var(--v-space-2);
  margin-top: 6px;
  opacity: 0;
  animation: td-rise 720ms var(--td-ease) 800ms forwards;
}

.td-link {
  display: inline-flex;
  align-items: center;
  gap: var(--v-space-2);
  min-height: 34px;
  padding: 0 13px;
  border-radius: var(--v-button-radius);
  border: 1px solid color-mix(in srgb, var(--v-text) 10%, transparent);
  background: color-mix(in srgb, var(--v-bg-black) 62%, transparent);
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
  font-weight: 650;
  letter-spacing: 0.02em;
  text-decoration: none;
  transition:
    color 200ms var(--td-ease),
    border-color 200ms var(--td-ease),
    background 200ms var(--td-ease);
}

.td-link:hover {
  color: var(--v-text);
  border-color: color-mix(in srgb, var(--v-accent) 32%, transparent);
  background: color-mix(in srgb, var(--v-bg-black) 56%, transparent);
}

.td-link .icon {
  width: 12px;
  height: 12px;
  color: color-mix(in srgb, var(--v-accent) 68%, var(--v-text-muted));
  transition: transform 200ms var(--td-ease);
}

.td-link:hover .icon {
  transform: translate(1px, -1px);
}

/* ─── Keyframes ────────────────────────────────────────────────────────── */
@keyframes td-rise {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes td-image-arrive {
  from { opacity: 0; transform: scale(1.06); filter: saturate(0.78) contrast(1.02) brightness(0.7) blur(8px); }
  to { opacity: 1; transform: scale(1.0); filter: saturate(1.04) contrast(1.06) brightness(0.96) blur(0); }
}

@keyframes td-image-breathe {
  from { transform: scale(1.0); }
  to { transform: scale(1.045); }
}

@keyframes td-aurora-glow {
  from { opacity: 0; transform: translate3d(40px, 12px, 0) scale(0.92); }
  to { opacity: 1; transform: translate3d(0, 0, 0) scale(1); }
}

@keyframes td-dot-pulse {
  0%   { box-shadow: 0 0 0 0 color-mix(in srgb, var(--v-accent) 64%, transparent); }
  60%  { box-shadow: 0 0 0 7px color-mix(in srgb, var(--v-accent) 0%, transparent); }
  100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--v-accent) 0%, transparent); }
}

@keyframes td-shimmer {
  0%   { transform: translateX(-110%); }
  60%  { transform: translateX(110%); }
  100% { transform: translateX(110%); }
}

@keyframes td-spin {
  to { transform: rotate(360deg); }
}

/* ─── Tablet ───────────────────────────────────────────────────────────── */
@media (max-width: 1180px) and (min-width: 821px) {
  .tracker-delivery {
    --td-content-w: clamp(380px, 46vw, 540px);
    --td-content-pad-x: clamp(28px, 5vw, 64px);
    --td-content-pad-y: clamp(64px, 9vh, 110px);
    justify-content: flex-end;
  }

  .td-title {
    font-size: clamp(44px, 5.4vw, 64px);
  }

  .td-stage-vignette--right {
    background: linear-gradient(90deg, transparent 0%, transparent 28%, color-mix(in srgb, var(--v-bg-black) 42%, transparent) 52%, color-mix(in srgb, var(--v-bg-black) 86%, transparent) 80%, color-mix(in srgb, var(--v-bg-black) 94%, transparent) 100%);
  }
}

/* ─── Mobile ───────────────────────────────────────────────────────────── */
@media (max-width: 820px) {
  :global(.main-wrapper:has(.tracker-delivery) .unified-nav) {
    height: 50px;
    padding-inline: 14px;
    background: linear-gradient(180deg, color-mix(in srgb, var(--v-bg-black) 76%, transparent), transparent);
  }

  :global(.main-wrapper:has(.tracker-delivery) .unified-nav .share-origin-badge) {
    max-width: calc(100vw - 28px);
  }

  .tracker-delivery {
    --td-content-w: 100%;
    --td-content-pad-x: 22px;
    align-items: flex-end;
    justify-content: center;
    padding: 0 var(--td-content-pad-x) max(20px, env(safe-area-inset-bottom));
    min-height: 100svh;
  }

  /* Image becomes a hero on top, fading into content */
  .td-stage-image img {
    transform-origin: 50% 35%;
  }

  .td-stage-vignette--scrim {
    background:
      radial-gradient(120% 80% at 50% 100%, color-mix(in srgb, var(--v-bg-black) 92%, transparent) 0%, color-mix(in srgb, var(--v-bg-black) 56%, transparent) 28%, transparent 60%);
  }

  .td-stage-vignette--right {
    background:
      linear-gradient(180deg, transparent 0%, transparent 30%, color-mix(in srgb, var(--v-bg-black) 36%, transparent) 50%, color-mix(in srgb, var(--v-bg-black) 88%, transparent) 76%, color-mix(in srgb, var(--v-bg-black) 96%, transparent) 100%);
  }

  .td-stage-vignette--top {
    height: 24%;
    background: linear-gradient(180deg, color-mix(in srgb, var(--v-bg-black) 78%, transparent) 0%, transparent 100%);
  }

  .td-stage-vignette--bottom {
    height: 56%;
  }

  .td-stage-aurora {
    top: auto;
    bottom: -12%;
    right: 50%;
    transform: translateX(50%);
    width: 540px;
    height: 540px;
  }

  .td-shell {
    width: 100%;
    max-width: 480px;
    margin: 0 auto;
    padding-top: 36svh;
  }

  .td-hero {
    gap: 18px;
  }

  .td-mark {
    min-height: 40px;
    gap: var(--v-space-3);
  }

  .td-mark-monogram {
    min-width: 40px;
    height: 40px;
    border-radius: var(--v-radius-md);
    font-size: var(--v-text-md);
  }

  .td-mark-logo {
    max-height: 48px;
    max-width: 140px;
  }

  .td-mark-logo img {
    max-height: 48px;
  }

  .td-eyebrow {
    font-size: var(--v-text-2xs);
    letter-spacing: 0.16em;
  }

  .td-eyebrow-rule {
    width: 10px;
  }

  .td-title {
    font-size: clamp(38px, 10vw, 52px);
    max-width: 13ch;
  }

  .td-message {
    font-size: var(--v-text-lg);
    max-width: 36ch;
  }

  .td-notes {
    font-size: var(--v-text-base);
    padding: 11px 14px 11px 14px;
  }

  .td-stats {
    gap: var(--v-space-2);
  }

  .td-stat {
    flex: 1 1 calc(33.333% - 8px);
    min-width: 0;
    padding: 9px 12px 10px;
    border-radius: var(--v-radius-md);
  }

  .td-stat-value {
    font-size: var(--v-text-lg);
  }

  .td-stat-label {
    font-size: var(--v-text-3xs);
    letter-spacing: 0.12em;
  }

  .td-actions {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
    margin-top: var(--v-space-1);
  }

  .td-cta-primary,
  .td-cta-secondary {
    width: 100%;
    min-height: 52px;
  }

  .td-cta-primary {
    padding: 0 22px;
    font-size: var(--v-text-md);
  }

  .td-cta-secondary {
    justify-content: center;
    padding: 0 18px;
  }

  .td-cta-secondary-arrow {
    margin-left: auto;
  }

  .td-action-note {
    text-align: center;
    margin-top: 0;
  }

  .td-links {
    justify-content: flex-start;
  }

}

/* ─── Small screens — keep typography compact ──────────────────────────── */
@media (max-width: 380px) {
  .td-stat {
    flex-basis: calc(50% - 4px);
  }
}

/* ─── Reduced motion ───────────────────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  .td-stage-image img,
  .td-stage-aurora,
  .td-mark,
  .td-eyebrow,
  .td-title,
  .td-message,
  .td-notes,
  .td-stat,
  .td-actions,
  .td-action-note,
  .td-links {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
  }

  .td-eyebrow-dot,
  .td-stat-pulse {
    animation: none !important;
  }

  .td-cta-shimmer {
    display: none !important;
  }
}
</style>
