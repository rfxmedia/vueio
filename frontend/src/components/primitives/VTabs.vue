<template>
  <div
    ref="tablistRef"
    class="v-tabs"
    :class="[`v-tabs--${variant}`, { 'v-tabs--full': fullWidth }]"
    role="tablist"
    aria-orientation="horizontal"
  >
    <button
      v-for="(tab, index) in tabs"
      :key="tab.value"
      :ref="el => setTabRef(el, index)"
      class="v-tab-btn"
      :class="{ active: isActive(tab) }"
      type="button"
      role="tab"
      :aria-selected="isActive(tab) ? 'true' : 'false'"
      :aria-disabled="tab.disabled ? 'true' : undefined"
      :aria-controls="tab.panelId || tab.controls || undefined"
      :tabindex="tabIndexFor(tab)"
      :disabled="tab.disabled"
      @click="selectTab(tab)"
      @keydown="handleKeydown($event, index)"
    >
      <svg v-if="tab.icon" class="icon v-tab-btn__icon" aria-hidden="true"><use :href="tab.icon" /></svg>
      <span class="v-tab-btn__label">{{ tab.label }}</span>
      <span v-if="tab.count !== undefined" class="v-tab-btn__count">{{ tab.count }}</span>
      <span
        v-if="tab.attention"
        class="v-tab-btn__attention"
        aria-hidden="true"
      ></span>
      <span v-if="tab.attention" class="v-sr-only">Needs review</span>
    </button>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUpdate, ref, watch } from 'vue'

const props = defineProps({
  tabs: { type: Array, required: true },
  modelValue: { type: String, default: '' },
  variant: { type: String, default: 'rail' }, // rail | segmented | chip
  fullWidth: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const tablistRef = ref(null)
const tabRefs = ref([])

const enabledTabs = computed(() => props.tabs.filter(tab => !tab.disabled))
const activeEnabledValue = computed(() => {
  const activeTab = enabledTabs.value.find(tab => tab.value === props.modelValue)
  return activeTab?.value ?? enabledTabs.value[0]?.value ?? ''
})

function isActive(tab) {
  return props.modelValue === tab.value
}

function tabIndexFor(tab) {
  return !tab.disabled && tab.value === activeEnabledValue.value ? 0 : -1
}

function setTabRef(el, index) {
  if (!el) return
  tabRefs.value[index] = el
  if (props.tabs[index]?.value === props.modelValue) {
    nextTick(() => scrollTabIntoView(el))
  }
}

function selectTab(tab) {
  if (tab.disabled) return
  emit('update:modelValue', tab.value)
}

function moveFocus(currentIndex, direction) {
  const enabledIndexes = props.tabs
    .map((tab, index) => (tab.disabled ? -1 : index))
    .filter(index => index !== -1)

  if (!enabledIndexes.length) return

  const currentEnabledIndex = enabledIndexes.indexOf(currentIndex)
  const safeCurrentIndex = currentEnabledIndex === -1 ? 0 : currentEnabledIndex
  const nextEnabledIndex = (safeCurrentIndex + direction + enabledIndexes.length) % enabledIndexes.length
  focusTab(enabledIndexes[nextEnabledIndex])
}

async function focusTab(index) {
  const tab = props.tabs[index]
  if (!tab || tab.disabled) return
  emit('update:modelValue', tab.value)
  await nextTick()
  tabRefs.value[index]?.focus({ preventScroll: true })
  scrollTabIntoView(tabRefs.value[index])
}

function handleKeydown(event, index) {
  if (event.key === 'ArrowRight') {
    event.preventDefault()
    moveFocus(index, 1)
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault()
    moveFocus(index, -1)
  } else if (event.key === 'Home') {
    event.preventDefault()
    const firstIndex = props.tabs.findIndex(tab => !tab.disabled)
    focusTab(firstIndex)
  } else if (event.key === 'End') {
    event.preventDefault()
    const lastIndex = props.tabs.map(tab => !tab.disabled).lastIndexOf(true)
    focusTab(lastIndex)
  }
}

function scrollTabIntoView(tabEl) {
  const rail = tablistRef.value
  if (!rail || !tabEl) return

  const railLeft = rail.scrollLeft
  const railRight = railLeft + rail.clientWidth
  const tabLeft = tabEl.offsetLeft
  const tabRight = tabLeft + tabEl.offsetWidth

  if (tabLeft < railLeft) {
    rail.scrollLeft = tabLeft
  } else if (tabRight > railRight) {
    rail.scrollLeft = tabRight - rail.clientWidth
  }
}

onBeforeUpdate(() => {
  tabRefs.value = []
})

watch(() => props.modelValue, async () => {
  await nextTick()
  const activeIndex = props.tabs.findIndex(tab => tab.value === props.modelValue)
  scrollTabIntoView(tabRefs.value[activeIndex])
}, { immediate: true, flush: 'post' })
</script>

<style scoped>
@media (max-width: 768px) {
  .v-tabs:not(.v-tabs--full) {
    max-width: 100%;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    -webkit-overflow-scrolling: touch;
  }

.v-tabs:not(.v-tabs--full) .v-tab-btn {
    flex: 0 0 auto;
  }
}

.v-tab-btn__icon {
  width: 13px;
  height: 13px;
  flex: 0 0 auto;
  opacity: 0.85;
}

.v-tab-btn__attention {
  width: 6px;
  height: 6px;
  flex: 0 0 auto;
  border-radius: var(--v-radius-full);
  background: var(--v-warning);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--v-warning) 14%, transparent);
}
</style>
