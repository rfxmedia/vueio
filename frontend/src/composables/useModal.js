import { ref } from 'vue'

export function useModal(initialOpen = false) {
  const isOpen = ref(Boolean(initialOpen))

  function open() {
    isOpen.value = true
  }

  function close() {
    isOpen.value = false
  }

  function setOpen(value) {
    isOpen.value = Boolean(value)
  }

  return {
    isOpen,
    open,
    close,
    setOpen,
  }
}
