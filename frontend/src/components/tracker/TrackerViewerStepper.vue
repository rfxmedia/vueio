<template>
  <div
    v-if="showTrackerViewerKeyboardGuide"
    class="tracker-viewer-navigation"
  >
    <VMenu
      v-if="!isMobile"
      :open="shortcutGuideOpen"
      align="end"
      min-width="348"
      teleport
      :offset="10"
      panel-role="dialog"
      panel-label="Keyboard shortcuts"
      panel-class="tracker-shortcuts-menu"
      :close-on-select="false"
      @update:open="(open) => { if (!open) shortcutGuideOpen = false }"
    >
      <template #trigger="{ triggerProps }">
        <button
          v-bind="triggerProps"
          type="button"
          class="v-btn v-btn-quiet v-btn-icon tracker-shortcuts-trigger"
          :class="{ active: shortcutGuideOpen }"
          aria-label="View keyboard shortcuts"
          title="Keyboard shortcuts"
          @click.stop="shortcutGuideOpen = !shortcutGuideOpen"
        >
          <svg class="icon" aria-hidden="true"><use href="#icon-command" /></svg>
        </button>
      </template>

      <div class="tracker-shortcuts-panel">
        <header class="tracker-shortcuts-header">
          <span class="tracker-shortcuts-mark" aria-hidden="true">
            <svg class="icon"><use href="#icon-command" /></svg>
          </span>
          <span class="tracker-shortcuts-heading">
            <strong>Keyboard shortcuts</strong>
            <span>Navigate without leaving the viewer.</span>
          </span>
        </header>

        <section class="tracker-shortcuts-section" aria-labelledby="tracker-shortcuts-shots">
          <h3 id="tracker-shortcuts-shots">Shots</h3>
          <dl class="tracker-shortcuts-list">
            <div class="tracker-shortcuts-row">
              <dt>Previous shot</dt>
              <dd><kbd>[</kbd><span>or</span><kbd class="is-wide">Numpad 4</kbd></dd>
            </div>
            <div class="tracker-shortcuts-row">
              <dt>Next shot</dt>
              <dd><kbd>]</kbd><span>or</span><kbd class="is-wide">Numpad 6</kbd></dd>
            </div>
          </dl>
        </section>

        <section
          v-if="currentTrackerViewerVersions.length > 1"
          class="tracker-shortcuts-section"
          aria-labelledby="tracker-shortcuts-versions"
        >
          <h3 id="tracker-shortcuts-versions">Versions</h3>
          <dl class="tracker-shortcuts-list">
            <div class="tracker-shortcuts-row">
              <dt>Newer version</dt>
              <dd><kbd>↑</kbd><span>or</span><kbd class="is-wide">Numpad 8</kbd></dd>
            </div>
            <div class="tracker-shortcuts-row">
              <dt>Older version</dt>
              <dd><kbd>↓</kbd><span>or</span><kbd class="is-wide">Numpad 2</kbd></dd>
            </div>
          </dl>
        </section>

        <section
          v-if="isViewingVideo"
          class="tracker-shortcuts-section"
          aria-labelledby="tracker-shortcuts-playback"
        >
          <h3 id="tracker-shortcuts-playback">Playback</h3>
          <dl class="tracker-shortcuts-list">
            <div class="tracker-shortcuts-row">
              <dt>Play or pause</dt>
              <dd><kbd class="is-wide">Space</kbd></dd>
            </div>
            <div class="tracker-shortcuts-row">
              <dt>Previous or next frame</dt>
              <dd><kbd>←</kbd><kbd>→</kbd></dd>
            </div>
            <div class="tracker-shortcuts-row">
              <dt>Jump one second</dt>
              <dd><kbd class="is-wide">Shift</kbd><span>+</span><kbd>←</kbd><kbd>→</kbd></dd>
            </div>
          </dl>
        </section>
      </div>
    </VMenu>

    <div
      v-if="showTrackerViewerStepper"
      class="v-view-toggle v-media-sequence-nav"
      role="group"
      aria-label="Vue Tracker media navigation"
    >
      <button
        type="button"
        class="v-view-toggle-btn v-media-sequence-btn"
        :disabled="!canStepToPreviousTrackerMedia"
        aria-label="Previous shot"
        title="Previous shot · [ or Numpad 4"
        @click="stepTrackerMedia(-1)"
      >
        <svg class="icon"><use href="#icon-back" /></svg>
      </button>
      <div class="v-media-sequence-count">{{ trackerViewerSequenceLabel }}</div>
      <button
        type="button"
        class="v-view-toggle-btn v-media-sequence-btn is-next"
        :disabled="!canStepToNextTrackerMedia"
        aria-label="Next shot"
        title="Next shot · ] or Numpad 6"
        @click="stepTrackerMedia(1)"
      >
        <svg class="icon"><use href="#icon-back" /></svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { VMenu } from '../primitives'
import { useTrackerStore } from '../../ownership/tracker'
import { useViewerStore } from '../../ownership/viewer'

const {
  showTrackerViewerStepper,
  showTrackerViewerKeyboardGuide,
  canStepToPreviousTrackerMedia,
  canStepToNextTrackerMedia,
  trackerViewerSequenceLabel,
  currentTrackerViewerVersions,
  stepTrackerMedia,
} = useTrackerStore()

const viewer = useViewerStore()
const { isMobile } = viewer.presentation
const { isViewingVideo } = viewer.media.core
const shortcutGuideOpen = ref(false)

watch(isMobile, (mobile) => {
  if (mobile) shortcutGuideOpen.value = false
})
</script>

<style>
.tracker-viewer-navigation {
  display: inline-flex;
  align-items: center;
  gap: var(--v-space-2);
}

.tracker-shortcuts-trigger {
  width: var(--v-control-pill-height-compact);
  min-width: var(--v-control-pill-height-compact);
  height: var(--v-control-pill-height-compact);
  min-height: var(--v-control-pill-height-compact);
  padding: 0;
  border-color: transparent;
  color: var(--v-text-muted);
}

.tracker-shortcuts-trigger:hover,
.tracker-shortcuts-trigger.active {
  border-color: var(--v-control-border-hover);
  background: var(--v-control-bg-hover);
  color: var(--v-text);
}

.tracker-shortcuts-trigger .icon {
  width: 15px;
  height: 15px;
}

.tracker-shortcuts-menu {
  width: 348px;
  padding: 0;
}

.tracker-shortcuts-panel {
  overflow: hidden;
  color: var(--v-text);
}

.tracker-shortcuts-header {
  display: flex;
  align-items: center;
  gap: var(--v-space-3);
  padding: var(--v-space-4);
  background: var(--v-surface-raised);
}

.tracker-shortcuts-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  border: 1px solid var(--v-surface-border-strong);
  border-radius: var(--v-button-radius);
  background: var(--v-surface-inset);
  color: var(--v-text-secondary);
  box-shadow: var(--v-surface-shadow-inset);
}

.tracker-shortcuts-mark .icon {
  width: 16px;
  height: 16px;
}

.tracker-shortcuts-heading {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.tracker-shortcuts-heading strong {
  font-size: var(--v-text-md);
  line-height: 1.2;
}

.tracker-shortcuts-heading > span {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  line-height: 1.35;
}

.tracker-shortcuts-section {
  padding: var(--v-space-3) var(--v-space-4);
  border-top: 1px solid var(--v-divider-subtle);
}

.tracker-shortcuts-section h3 {
  margin: 0 0 var(--v-space-2);
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  font-weight: 700;
  letter-spacing: 0.05em;
  line-height: 1.2;
  text-transform: uppercase;
}

.tracker-shortcuts-list {
  display: grid;
  gap: 2px;
  margin: 0;
}

.tracker-shortcuts-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  min-height: 30px;
  gap: var(--v-space-3);
}

.tracker-shortcuts-row dt,
.tracker-shortcuts-row dd {
  margin: 0;
}

.tracker-shortcuts-row dt {
  color: var(--v-text-secondary);
  font-size: var(--v-text-sm);
}

.tracker-shortcuts-row dd {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 5px;
  color: var(--v-text-dim);
  font-size: var(--v-text-2xs);
  white-space: nowrap;
}

.tracker-shortcuts-row kbd {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 25px;
  height: 23px;
  padding: 0 6px;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-radius-sm);
  background: var(--v-surface-inset);
  box-shadow: inset 0 -1px 0 var(--v-surface-border-strong);
  color: var(--v-text);
  font-family: var(--v-font-mono);
  font-size: var(--v-text-2xs);
  font-weight: 650;
  line-height: 1;
}

.tracker-shortcuts-row kbd.is-wide {
  min-width: auto;
}
</style>
