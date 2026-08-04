<template>
  <label class="v-checkbox" :class="{ 'is-disabled': disabled }">
    <input
      class="v-checkbox-input"
      type="checkbox"
      :checked="modelValue"
      :disabled="disabled"
      v-bind="$attrs"
      @change="$emit('update:modelValue', $event.target.checked)"
    />
    <span class="v-checkbox-box" aria-hidden="true">
      <svg class="icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M3.5 8.5 6.5 11.5 12.5 4.5" />
      </svg>
    </span>
    <span class="v-checkbox-copy">
      <span v-if="label || $slots.default" class="v-checkbox-label">
        <slot>{{ label }}</slot>
      </span>
      <span v-if="hint" class="v-checkbox-hint">{{ hint }}</span>
    </span>
  </label>
</template>

<script setup>
defineProps({
  modelValue: { type: Boolean, default: false },
  label: { type: String, default: '' },
  hint: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})

defineEmits(['update:modelValue'])
</script>
