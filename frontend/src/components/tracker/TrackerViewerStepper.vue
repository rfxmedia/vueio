<template>
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
      @click="stepTrackerMedia(1)"
    >
      <svg class="icon"><use href="#icon-back" /></svg>
    </button>
  </div>
</template>

<script setup>
import { useTrackerStore } from '../../ownership/tracker'

const {
  showTrackerViewerStepper,
  canStepToPreviousTrackerMedia,
  canStepToNextTrackerMedia,
  trackerViewerSequenceLabel,
  stepTrackerMedia,
} = useTrackerStore()
</script>
