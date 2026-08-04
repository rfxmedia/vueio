<template>
  <div class="v-modal-header" v-bind="$attrs">
    <slot>
      <div v-if="eyebrow || title || subtitle" class="v-modal-header-copy">
        <span v-if="eyebrow" class="v-modal-header-eyebrow">{{ eyebrow }}</span>
        <h2 v-if="title" :id="titleId || undefined" class="v-modal-header-title">{{ title }}</h2>
        <p v-if="subtitle" class="v-modal-header-subtitle">{{ subtitle }}</p>
      </div>
    </slot>
    <button
      v-if="closeable"
      class="v-btn v-btn-quiet v-btn-icon v-btn-sm"
      type="button"
      aria-label="Close"
      @click="$emit('close')"
    >
      <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
    </button>
  </div>
</template>

<script setup>
defineProps({
  eyebrow: { type: String, default: '' },
  title: { type: String, default: '' },
  titleId: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  closeable: { type: Boolean, default: true },
})
defineEmits(['close'])
</script>
