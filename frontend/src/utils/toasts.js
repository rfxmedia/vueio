import { readonly, ref } from 'vue'

const toasts = ref([])
const timers = new Map()
let nextToastId = 0

function inferTone(message) {
  const value = String(message || '').toLowerCase()
  if (/\b(fail|failed|error|invalid|unable|corrupt|disabled|required)\b/.test(value)) return 'error'
  if (/\b(saved|success|copied|created|updated|sent|changed|restored|regenerated)\b/.test(value)) return 'success'
  return 'info'
}

export function dismissToast(id) {
  const timer = timers.get(id)
  if (timer) clearTimeout(timer)
  timers.delete(id)
  toasts.value = toasts.value.filter((item) => item.id !== id)
}

export function notify(message, options = {}) {
  const text = String(message || '').trim()
  if (!text) return null

  const tone = options.tone || inferTone(text)
  const id = ++nextToastId
  const duration = options.duration ?? (tone === 'error' ? 6500 : 3600)
  const item = { id, message: text, tone }

  toasts.value = [...toasts.value.slice(-3), item]
  if (duration > 0) {
    timers.set(id, setTimeout(() => dismissToast(id), duration))
  }
  return id
}

export function useToasts() {
  return {
    toasts: readonly(toasts),
    dismissToast,
  }
}
