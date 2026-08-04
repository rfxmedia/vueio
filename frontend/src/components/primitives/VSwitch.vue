<template>
  <label class="v-switch" :class="{ 'is-disabled': disabled, 'is-checked': modelValue }">
    <input
      class="v-switch-input"
      type="checkbox"
      :checked="modelValue"
      :disabled="disabled"
      v-bind="$attrs"
      @change="$emit('update:modelValue', $event.target.checked)"
    />
    <span class="v-switch-track" aria-hidden="true">
      <span class="v-switch-thumb"></span>
    </span>
    <span class="v-switch-copy">
      <span v-if="label || $slots.default" class="v-switch-label">
        <slot>{{ label }}</slot>
      </span>
      <span v-if="hint" class="v-switch-hint">{{ hint }}</span>
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
