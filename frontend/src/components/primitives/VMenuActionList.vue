<template>
  <template v-for="(action, index) in visibleActions" :key="action.key ?? index">
    <div v-if="action.divider" class="v-dropdown-divider"></div>
    <button
      v-else
      type="button"
      class="v-dropdown-item"
      :class="{ 'v-dropdown-item-danger': action.danger, active: action.active }"
      :disabled="action.disabled"
      :title="action.title"
      @click="action.run?.()"
    >
      <svg v-if="action.icon" class="icon"><use :href="action.icon" /></svg>
      <span>{{ action.label }}</span>
    </button>
  </template>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // [{ label, icon, run, show?, danger?, disabled?, title?, active? } | { divider: true }]
  actions: { type: Array, default: () => [] },
})

/* Dividers describe intent ("separate these groups"), not position. Hiding an
   action used to be able to leave a leading, trailing or doubled rule behind,
   so each one needed its own hand-written condition. Resolving them here means
   a menu only has to say where the groups are. */
const visibleActions = computed(() => {
  const out = []
  for (const action of props.actions) {
    // Truthiness, not `=== false`: `show: a && b.c` yields undefined when b.c is
    // undefined, which must hide the action exactly as v-if would have.
    if (!action || ('show' in action && !action.show)) continue
    if (action.divider) {
      if (out.length && !out[out.length - 1].divider) out.push(action)
      continue
    }
    out.push(action)
  }
  while (out.length && out[out.length - 1].divider) out.pop()
  return out
})
</script>
