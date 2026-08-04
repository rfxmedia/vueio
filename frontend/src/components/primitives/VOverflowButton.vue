<template>
  <button
    type="button"
    class="v-btn v-btn-quiet v-btn-icon v-btn-sm v-overflow-trigger"
    :class="{ 'v-btn-active': active, 'is-floating': floating }"
    :disabled="disabled"
    :aria-label="label"
    v-bind="$attrs"
  >
    <slot>
      <svg class="icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <circle cx="12" cy="5" r="1.8" />
        <circle cx="12" cy="12" r="1.8" />
        <circle cx="12" cy="19" r="1.8" />
      </svg>
    </slot>
  </button>
</template>

<script setup>
defineOptions({ inheritAttrs: false })

defineProps({
  label: { type: String, default: 'More actions' },
  active: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  floating: { type: Boolean, default: false },
})
</script>
