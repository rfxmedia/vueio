<template>
  <div class="voice-recording" role="status" aria-label="Recording voice note">
    <span class="voice-recording__dot" aria-hidden="true"></span>
    <div class="voice-recording__levels" aria-hidden="true">
      <span
        v-for="(level, index) in levels"
        :key="index"
        :style="{ height: `${Math.max(12, level * 100)}%` }"
      ></span>
    </div>
    <time class="voice-recording__time">{{ elapsedLabel }}</time>
    <button type="button" class="voice-recording__action" aria-label="Stop recording" title="Stop recording" @click="$emit('stop')">
      <span class="voice-recording__stop"></span>
    </button>
    <button type="button" class="voice-recording__action is-cancel" aria-label="Cancel recording" title="Cancel recording" @click="$emit('cancel')">
      <svg class="icon"><use href="#icon-close" /></svg>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  levels: { type: Array, default: () => [] },
  elapsed: { type: Number, default: 0 },
})

defineEmits(['stop', 'cancel'])

const elapsedLabel = computed(() => {
  const total = Math.max(0, Math.floor(Number(props.elapsed) || 0))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
})
</script>

<style>
.voice-recording {
  display: grid;
  grid-template-columns: 8px minmax(64px, 1fr) auto 28px 28px;
  align-items: center;
  gap: 6px;
  min-height: 40px;
}

.voice-recording__dot {
  width: 7px;
  height: 7px;
  border-radius: var(--v-radius-full);
  background: var(--v-danger);
  animation: voice-recording-pulse 1.2s var(--v-ease-soft) infinite;
}

.voice-recording__levels {
  min-width: 0;
  height: 24px;
  display: flex;
  align-items: center;
  gap: 2px;
}

.voice-recording__levels span {
  flex: 1 1 2px;
  max-width: 4px;
  border-radius: var(--v-radius-full);
  background: color-mix(in srgb, var(--v-accent) 74%, var(--v-text-muted));
  transition: height 90ms linear;
}

.voice-recording__time {
  color: var(--v-text-secondary);
  font-size: var(--v-text-xs);
  font-variant-numeric: tabular-nums;
}

.voice-recording__action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-button-radius);
  background: var(--v-surface-inline);
  color: var(--v-text-secondary);
  cursor: pointer;
}

.voice-recording__action:hover {
  border-color: var(--v-control-border-hover);
  background: var(--v-surface-inline-strong);
  color: var(--v-text);
}

.voice-recording__action.is-cancel:hover {
  border-color: var(--v-danger-border-hover);
  background: var(--v-danger-bg-hover);
  color: var(--v-danger);
}

.voice-recording__action .icon { width: 12px; height: 12px; }
.voice-recording__stop { width: 9px; height: 9px; border-radius: 2px; background: var(--v-accent); }

@keyframes voice-recording-pulse { 50% { opacity: 0.35; } }

@media (max-width: 768px) {
  .voice-recording { min-height: 44px; }
}

@media (max-width: 430px) {
  .voice-recording { grid-template-columns: 8px minmax(48px, 1fr) auto 28px 28px; gap: 5px; }
}

@media (prefers-reduced-motion: reduce) {
  .voice-recording__dot { animation: none; }
}
</style>
