<template>
  <span
    class="file-type-glyph"
    :class="{ 'is-compact': compact, 'is-three-d': visual.kind === 'three-d' }"
    :style="{ '--file-type-color': visual.color }"
    :title="visual.label"
    :aria-label="`${visual.label} file`"
    role="img"
  >
    <template v-if="visual.kind === 'three-d'">
      <svg class="file-type-glyph-cube" viewBox="0 0 24 24" aria-hidden="true">
        <path d="m12 2.8 8 4.6v9.2l-8 4.6-8-4.6V7.4l8-4.6Z" />
        <path d="m4 7.4 8 4.6 8-4.6M12 12v9.2" />
      </svg>
      <span class="file-type-glyph-extension">{{ visual.mark }}</span>
    </template>
    <span v-else class="file-type-glyph-mark">{{ visual.mark }}</span>
  </span>
</template>

<script setup>
defineProps({
  visual: { type: Object, required: true },
  compact: { type: Boolean, default: false },
})
</script>

<style scoped>
.file-type-glyph {
  --file-type-color: var(--v-text-secondary);
  display: inline-flex;
  position: relative;
  width: 54px;
  height: 54px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--file-type-color) 40%, var(--v-surface-border-soft));
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--file-type-color) 10%, var(--v-surface-inset));
  box-shadow: var(--v-surface-shadow-inset);
  color: var(--file-type-color);
}

.file-type-glyph::after {
  content: "";
  position: absolute;
  inset: auto 8px 7px;
  height: 2px;
  border-radius: var(--v-radius-full);
  background: currentColor;
  opacity: 0.68;
}

.file-type-glyph-mark {
  transform: translateY(-2px);
  font-size: 20px;
  font-weight: 760;
  letter-spacing: -0.8px;
  line-height: 1;
}

.file-type-glyph-cube {
  width: 23px;
  height: 23px;
  transform: translateY(-5px);
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.35;
}

.file-type-glyph-extension {
  position: absolute;
  bottom: 5px;
  max-width: calc(100% - 8px);
  overflow: hidden;
  font-size: 8px;
  font-weight: 780;
  letter-spacing: 0.7px;
  line-height: 1;
  text-overflow: clip;
}

.file-type-glyph.is-three-d::after {
  content: none;
}

.file-type-glyph.is-compact {
  width: 28px;
  height: 28px;
  border-radius: var(--v-radius-sm);
}

.file-type-glyph.is-compact::after {
  inset: auto 5px 3px;
  height: 1px;
}

.file-type-glyph.is-compact .file-type-glyph-mark {
  transform: translateY(-1px);
  font-size: var(--v-text-xs);
  letter-spacing: -0.35px;
}

.file-type-glyph.is-compact .file-type-glyph-cube {
  width: 15px;
  height: 15px;
  transform: translateY(-4px);
  stroke-width: 1.5;
}

.file-type-glyph.is-compact .file-type-glyph-extension {
  bottom: 3px;
  font-size: 5px;
  letter-spacing: 0.25px;
}
</style>
