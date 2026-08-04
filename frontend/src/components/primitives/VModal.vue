<template>
  <Teleport to="body">
    <Transition :name="transitionName">
      <div v-if="modelValue" class="v-modal-backdrop" :class="backdropClasses" @click.self="requestClose">
        <div
          ref="modalRef"
          class="v-modal"
          :class="modalClasses"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="ariaLabelledby"
          :aria-label="ariaLabel"
          tabindex="-1"
          v-bind="$attrs"
        >
          <div v-if="title || $slots.header" :id="$slots.header ? titleId : undefined">
            <slot name="header" :title-id="titleId">
              <VModalHeader :title="title" :title-id="titleId" :closeable="closeable" @close="$emit('update:modelValue', false)" />
            </slot>
          </div>
          <div class="v-modal-body" :class="{ 'v-modal-body-full': fullHeight }">
            <slot />
          </div>
          <div v-if="$slots.footer" class="v-modal-footer">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
defineOptions({ inheritAttrs: false })

import { computed, nextTick, onBeforeUnmount, ref, useAttrs, useSlots, watch } from 'vue'
import VModalHeader from './VModalHeader.vue'

let modalIdSeed = 0
const modalStack = []

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'iframe',
  'object',
  'embed',
  '[contenteditable="true"]',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  size: { type: String, default: 'md' },
  closeable: { type: Boolean, default: true },
  fullHeight: { type: Boolean, default: false },
  presentation: { type: String, default: 'dialog' }, // dialog | sheet
  stickyHeader: { type: Boolean, default: true },
  stickyFooter: { type: Boolean, default: true },
  mobileFullHeight: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])
const attrs = useAttrs()
const slots = useSlots()

const modalRef = ref(null)
modalIdSeed += 1
const modalId = modalIdSeed
const titleId = `v-modal-title-${modalId}`
let lockApplied = false
let openerElement = null

const sizeClass = computed(() => ({
  sm: 'v-modal-sm',
  md: 'v-modal-md',
  lg: 'v-modal-lg',
  xl: 'v-modal-xl',
}[props.size] || 'v-modal-md'))

const modalClasses = computed(() => [
  sizeClass.value,
  props.presentation === 'sheet' ? 'is-sheet' : 'is-dialog',
  props.stickyHeader ? 'v-modal-sticky-header' : '',
  props.stickyFooter ? 'v-modal-sticky-footer' : '',
  props.mobileFullHeight ? 'is-mobile-full-height' : '',
])

const backdropClasses = computed(() => ({
  'is-sheet-backdrop': props.presentation === 'sheet' || props.mobileFullHeight,
}))

const transitionName = computed(() => (
  props.presentation === 'sheet' || props.mobileFullHeight
    ? 'v-sheet-rise'
    : 'v-overlay-fade'
))

const ariaLabelledby = computed(() => (
  attrs['aria-labelledby'] || ((props.title || slots.header) ? titleId : undefined)
))

const ariaLabel = computed(() => (
  attrs['aria-label'] || (props.title && slots.header && !attrs['aria-labelledby'] ? props.title : undefined)
))

function requestClose() {
  if (!props.closeable) return
  emit('update:modelValue', false)
}

function addToStack() {
  if (!modalStack.includes(modalId)) modalStack.push(modalId)
}

function removeFromStack() {
  const index = modalStack.indexOf(modalId)
  if (index !== -1) modalStack.splice(index, 1)
}

function isTopmostModal() {
  return modalStack[modalStack.length - 1] === modalId
}

function lockBodyScroll() {
  if (typeof document === 'undefined' || lockApplied) return
  const body = document.body
  const count = Number(body.dataset.vModalLockCount || 0) + 1
  body.dataset.vModalLockCount = String(count)
  body.classList.add('v-modal-open')
  lockApplied = true
}

function unlockBodyScroll() {
  if (typeof document === 'undefined' || !lockApplied) return
  const body = document.body
  const current = Number(body.dataset.vModalLockCount || 1) - 1
  if (current <= 0) {
    delete body.dataset.vModalLockCount
    body.classList.remove('v-modal-open')
  } else {
    body.dataset.vModalLockCount = String(current)
  }
  lockApplied = false
}

function isFocusableVisible(element) {
  return element instanceof HTMLElement
    && !element.hidden
    && window.getComputedStyle(element).visibility !== 'hidden'
    && Boolean(element.offsetWidth || element.offsetHeight || element.getClientRects().length)
}

function getFocusableElements() {
  if (!modalRef.value) return []
  return Array.from(modalRef.value.querySelectorAll(FOCUSABLE_SELECTOR)).filter(isFocusableVisible)
}

function focusModal() {
  const autofocusTarget = modalRef.value?.querySelector('[autofocus]')
  if (
    autofocusTarget instanceof HTMLElement
    && !autofocusTarget.hidden
    && !autofocusTarget.matches(':disabled')
  ) {
    autofocusTarget.focus({ preventScroll: true })
    return
  }
  modalRef.value?.focus({ preventScroll: true })
}

function restoreOpenerFocus() {
  if (openerElement instanceof HTMLElement && openerElement.isConnected) {
    openerElement.focus({ preventScroll: true })
  }
  openerElement = null
}

function handleWindowKeydown(event) {
  if (!isTopmostModal()) return

  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopImmediatePropagation()
    requestClose()
    return
  }

  if (event.key !== 'Tab') return

  const focusable = getFocusableElements()
  if (!focusable.length) {
    event.preventDefault()
    focusModal()
    return
  }

  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const activeElement = document.activeElement
  const focusIsOnModal = activeElement === modalRef.value
  const focusIsOutsideModal = !modalRef.value?.contains(activeElement)

  if (event.shiftKey && (activeElement === first || focusIsOnModal || focusIsOutsideModal)) {
    event.preventDefault()
    last.focus({ preventScroll: true })
  } else if (!event.shiftKey && (activeElement === last || focusIsOnModal || focusIsOutsideModal)) {
    event.preventDefault()
    first.focus({ preventScroll: true })
  }
}

function handleFocusIn(event) {
  if (!isTopmostModal() || !modalRef.value || modalRef.value.contains(event.target)) return

  const focusable = getFocusableElements()
  const target = focusable[0] || modalRef.value
  target.focus({ preventScroll: true })
}

watch(() => props.modelValue, async (open) => {
  if (typeof window === 'undefined') return
  if (open) {
    openerElement = document.activeElement instanceof HTMLElement ? document.activeElement : null
    addToStack()
    lockBodyScroll()
    window.addEventListener('keydown', handleWindowKeydown)
    document.addEventListener('focusin', handleFocusIn)
    await nextTick()
    focusModal()
    return
  }
  window.removeEventListener('keydown', handleWindowKeydown)
  document.removeEventListener('focusin', handleFocusIn)
  removeFromStack()
  unlockBodyScroll()
  await nextTick()
  restoreOpenerFocus()
}, { immediate: true })

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('keydown', handleWindowKeydown)
    document.removeEventListener('focusin', handleFocusIn)
  }
  removeFromStack()
  unlockBodyScroll()
  restoreOpenerFocus()
})
</script>

<style scoped>
.v-modal-sm { max-width: 420px; }
.v-modal-md { max-width: 640px; }
.v-modal-lg { max-width: 960px; }
.v-modal-xl { max-width: 1200px; }
.v-modal-body-full { max-height: none; }
</style>
