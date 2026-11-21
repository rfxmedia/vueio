<template>
  <div class="sandbox-frame" :class="{ 'is-shown': shown }">
    <!-- The frame page runs in a sandbox with its own empty origin, so the
         sandbox page cannot reach Vue.io. The engine sends the same policy. -->
    <iframe
      ref="frameRef"
      class="sandbox-frame-el"
      src="/api/sandbox-frame"
      sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals allow-downloads"
      allow="clipboard-write; fullscreen"
      referrerpolicy="no-referrer"
      :title="title || 'Sandbox page'"
    ></iframe>
    <div v-if="!shown" class="sandbox-frame-loading" aria-hidden="true">
      <span class="sandbox-frame-spinner"></span>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  html: { type: String, default: '' },
  title: { type: String, default: '' },
  // Keep the reader's scroll position, for live previews and live updates.
  keepScroll: { type: Boolean, default: false },
})
const emit = defineEmits(['shown'])

const frameRef = ref(null)
const shown = ref(false)
let ready = false

function render() {
  const target = frameRef.value?.contentWindow
  if (!ready || !target) return
  // The frame has an opaque origin, so '*' is the only target that reaches
  // it. Only this frame can receive it: its page cannot navigate it away.
  target.postMessage({ type: 'vueio-sandbox-render', html: props.html, keepScroll: props.keepScroll, title: props.title }, '*')
}

function onMessage(event) {
  if (!frameRef.value || event.source !== frameRef.value.contentWindow) return
  const type = event.data?.type
  if (type === 'vueio-sandbox-ready') {
    ready = true
    render()
  } else if (type === 'vueio-sandbox-shown') {
    shown.value = true
    emit('shown')
  }
}

watch(() => props.html, render)
onMounted(() => window.addEventListener('message', onMessage))
onBeforeUnmount(() => window.removeEventListener('message', onMessage))

function requestFullscreen() {
  frameRef.value?.parentElement?.requestFullscreen?.()
}

defineExpose({ requestFullscreen })
</script>

<style scoped>
.sandbox-frame {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: #fff;
}

.sandbox-frame-el {
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
  opacity: 0;
  transition: opacity 180ms ease;
}

.sandbox-frame.is-shown .sandbox-frame-el {
  opacity: 1;
}

.sandbox-frame-loading {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: var(--v-surface-inset);
}

.sandbox-frame-spinner {
  width: 22px;
  height: 22px;
  border: 2px solid color-mix(in srgb, var(--v-sandbox) 30%, transparent);
  border-top-color: var(--v-sandbox);
  border-radius: 50%;
  animation: sandbox-frame-spin 800ms linear infinite;
}

@keyframes sandbox-frame-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .sandbox-frame-spinner { animation-duration: 2400ms; }
}
</style>
