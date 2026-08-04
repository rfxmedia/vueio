<template>
  <div class="v-dropdown-wrapper v-menu" :class="menuClasses" @click.stop>
    <div ref="triggerRef" class="v-menu-trigger">
      <slot name="trigger" :trigger-props="triggerProps" />
    </div>
    <Transition name="v-menu-pop">
      <div
        v-if="open && !teleport"
        :id="panelId"
        ref="panelRef"
        class="v-dropdown v-menu-panel"
        :class="panelClasses"
        :style="panelStyle"
        :role="panelRole"
        @click.stop="handlePanelClick"
      >
        <slot />
      </div>
    </Transition>
    <Teleport v-if="teleport" :to="teleportTo">
      <Transition name="v-menu-pop">
        <div
          v-if="open"
          :id="panelId"
          ref="panelRef"
          class="v-dropdown v-menu-panel is-teleported"
          :class="panelClasses"
          :style="[panelStyle, floatingPanelStyle]"
          :role="panelRole"
          @click.stop="handlePanelClick"
        >
          <slot />
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

let menuId = 0

const props = defineProps({
  open: { type: Boolean, default: false },
  align: { type: String, default: 'end' }, // start | center | end
  minWidth: { type: [Number, String], default: '' },
  panelClass: { type: [Array, Object, String], default: '' },
  teleport: { type: Boolean, default: false },
  teleportTo: { type: String, default: 'body' },
  offset: { type: Number, default: 6 },
  panelRole: { type: String, default: 'menu' },
  closeOnSelect: { type: Boolean, default: true },
})

const emit = defineEmits(['update:open', 'close'])

const menuClasses = computed(() => [`v-menu-align-${props.align}`])
const panelClasses = computed(() => [`v-menu-align-${props.align}`, props.panelClass])
const triggerRef = ref(null)
const panelRef = ref(null)
menuId += 1
const panelId = `v-menu-${menuId}`
const floatingPosition = ref(null)
const triggerProps = computed(() => ({
  'aria-haspopup': props.panelRole === 'menu' ? 'menu' : props.panelRole,
  'aria-expanded': props.open ? 'true' : 'false',
  'aria-controls': props.open ? panelId : undefined,
}))
const panelStyle = computed(() => {
  if (!props.minWidth) return undefined
  const raw = props.minWidth
  let value
  if (typeof raw === 'number') {
    value = `${raw}px`
  } else if (typeof raw === 'string' && /^\d+(\.\d+)?$/.test(raw.trim())) {
    value = `${raw.trim()}px`
  } else {
    value = raw
  }
  return { minWidth: value }
})

const floatingPanelStyle = computed(() => {
  if (!props.teleport || !floatingPosition.value) return undefined
  return {
    position: 'fixed',
    top: `${floatingPosition.value.top}px`,
    left: `${floatingPosition.value.left}px`,
    right: 'auto',
    marginTop: 0,
  }
})

function updateFloatingPosition() {
  if (!props.teleport || !props.open || !triggerRef.value) return
  const rect = triggerRef.value.getBoundingClientRect()
  const panelWidth = panelRef.value?.offsetWidth || Number.parseFloat(String(props.minWidth)) || rect.width
  const panelHeight = panelRef.value?.offsetHeight || 0
  const viewportPadding = 8
  let left = rect.right - panelWidth
  if (props.align === 'start') left = rect.left
  if (props.align === 'center') left = rect.left + (rect.width / 2) - (panelWidth / 2)
  left = Math.max(viewportPadding, Math.min(left, window.innerWidth - panelWidth - viewportPadding))
  let top = rect.bottom + props.offset
  if (panelHeight && top + panelHeight > window.innerHeight - viewportPadding) {
    const flippedTop = rect.top - props.offset - panelHeight
    top = flippedTop >= viewportPadding
      ? flippedTop
      : Math.max(viewportPadding, window.innerHeight - panelHeight - viewportPadding)
  }
  floatingPosition.value = {
    left,
    top,
  }
}

function requestClose({ restoreFocus = false } = {}) {
  if (!props.open) return
  emit('update:open', false)
  emit('close')
  if (restoreFocus) {
    nextTick(() => triggerRef.value?.querySelector?.('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')?.focus())
  }
}

function getMenuItems() {
  if (props.panelRole !== 'menu' || !panelRef.value) return []
  return Array.from(panelRef.value.querySelectorAll(
    '[role="menuitem"]:not([aria-disabled="true"]), button:not([disabled]), a[href]',
  )).filter((item, index, items) => items.indexOf(item) === index)
}

function focusMenuItem(direction) {
  const items = getMenuItems()
  if (!items.length) return false

  const currentIndex = items.indexOf(document.activeElement)
  let nextIndex
  if (direction === 'first') nextIndex = 0
  else if (direction === 'last') nextIndex = items.length - 1
  else if (direction === 'next') nextIndex = currentIndex < 0 ? 0 : (currentIndex + 1) % items.length
  else nextIndex = currentIndex < 0 ? items.length - 1 : (currentIndex - 1 + items.length) % items.length

  items[nextIndex]?.focus({ preventScroll: true })
  return true
}

function handlePanelClick(event) {
  if (!props.closeOnSelect) return
  if (event.target.closest('button:not([disabled]), a[href], [role="menuitem"]')) requestClose()
}

function handleDocumentPointerDown(event) {
  if (!props.open) return
  if (triggerRef.value?.contains(event.target) || panelRef.value?.contains(event.target)) return
  requestClose()
}

function handleDocumentKeydown(event) {
  if (!props.open) return

  if (event.key === 'Escape') {
    event.preventDefault()
    requestClose({ restoreFocus: true })
    return
  }

  if (event.key === 'Tab') {
    requestClose()
    return
  }

  const direction = {
    ArrowDown: 'next',
    ArrowUp: 'previous',
    Home: 'first',
    End: 'last',
  }[event.key]
  if (!direction || !focusMenuItem(direction)) return
  event.preventDefault()
}

watch(() => props.open, async (isOpen) => {
  if (!isOpen || !props.teleport) return
  await nextTick()
  updateFloatingPosition()
  await nextTick()
  updateFloatingPosition()
}, { flush: 'post' })

watch(() => [props.align, props.minWidth, props.offset], () => updateFloatingPosition())

onMounted(() => {
  if (typeof window === 'undefined') return
  window.addEventListener('resize', updateFloatingPosition)
  window.addEventListener('scroll', updateFloatingPosition, true)
  document.addEventListener('pointerdown', handleDocumentPointerDown, true)
  document.addEventListener('keydown', handleDocumentKeydown)
})

onBeforeUnmount(() => {
  if (typeof window === 'undefined') return
  window.removeEventListener('resize', updateFloatingPosition)
  window.removeEventListener('scroll', updateFloatingPosition, true)
  document.removeEventListener('pointerdown', handleDocumentPointerDown, true)
  document.removeEventListener('keydown', handleDocumentKeydown)
})
</script>
