<template>
  <label class="v-field" :class="{ 'v-field-inline': inline, 'is-disabled': disabled, 'has-error': !!error }">
    <span v-if="label" class="v-field-label">
      {{ label }}
      <span v-if="required" class="v-field-required" aria-hidden="true">*</span>
    </span>
    <div class="v-field-control">
      <slot />
    </div>
    <span v-if="error || hint" class="v-field-help" :class="{ 'is-error': !!error }">
      {{ error || hint }}
    </span>
  </label>
</template>

<script setup>
defineProps({
  label: { type: String, default: '' },
  hint: { type: String, default: '' },
  error: { type: String, default: '' },
  inline: { type: Boolean, default: false },
  required: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
</script>
