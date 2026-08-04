<template>
  <Teleport to="body">
    <div class="v-toast-viewport" aria-label="Notifications">
      <TransitionGroup name="v-toast-list">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="v-toast"
          :class="`is-${toast.tone}`"
          :role="toast.tone === 'error' ? 'alert' : 'status'"
        >
          <span class="v-toast-mark" aria-hidden="true">
            <svg v-if="toast.tone === 'success'" viewBox="0 0 16 16"><path d="m3.2 8.3 3 3L12.8 5" /></svg>
            <svg v-else-if="toast.tone === 'error'" viewBox="0 0 16 16"><path d="M8 3.1v5.2M8 11.7v.2" /></svg>
            <svg v-else viewBox="0 0 16 16"><path d="M8 7.1v4.1M8 4.2v.2" /></svg>
          </span>
          <span class="v-toast-message">{{ toast.message }}</span>
          <button type="button" class="v-toast-close" aria-label="Dismiss notification" @click="dismissToast(toast.id)">
            <svg viewBox="0 0 16 16"><path d="m4 4 8 8m0-8-8 8" /></svg>
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import { useToasts } from '../../utils/toasts'

const { toasts, dismissToast } = useToasts()
</script>

<style scoped>
.v-toast-viewport {
  position: fixed;
  right: 18px;
  bottom: 18px;
  z-index: var(--v-z-toast);
  display: flex;
  width: min(420px, calc(100vw - 36px));
  flex-direction: column;
  gap: var(--v-space-2);
  pointer-events: none;
}

.v-toast {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) 32px;
  align-items: start;
  gap: 10px;
  min-height: 52px;
  padding: 10px 10px 10px 12px;
  border: 1px solid var(--v-menu-border);
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-menu-bg) 96%, transparent);
  box-shadow: 0 16px 38px rgba(0, 0, 0, 0.28);
  color: var(--v-text);
  pointer-events: auto;
}

.v-toast-mark {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border-radius: var(--v-radius-sm);
  background: var(--v-control-bg);
  color: var(--v-info);
}

.v-toast.is-success .v-toast-mark {
  background: var(--v-accent-muted);
  color: var(--v-accent);
}

.v-toast.is-error .v-toast-mark {
  background: var(--v-danger-bg);
  color: var(--v-danger-text);
}

.v-toast-mark svg,
.v-toast-close svg {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.v-toast-message {
  padding: 3px 0;
  font-size: var(--v-text-sm);
  font-weight: 600;
  line-height: 1.45;
  white-space: pre-line;
}

.v-toast-close {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 0;
  border-radius: var(--v-button-radius);
  background: transparent;
  color: var(--v-text-muted);
  cursor: pointer;
}

.v-toast-close:hover,
.v-toast-close:focus-visible {
  background: var(--v-bg-hover);
  color: var(--v-text);
  outline: none;
}

.v-toast-list-enter-active,
.v-toast-list-leave-active,
.v-toast-list-move {
  transition: opacity var(--v-duration-normal) var(--v-ease-emphasized), transform var(--v-duration-normal) var(--v-ease-emphasized);
}

.v-toast-list-enter-from,
.v-toast-list-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.985);
}

@media (max-width: 768px) {
  .v-toast-viewport {
    right: 10px;
    bottom: calc(10px + env(safe-area-inset-bottom, 0px));
    width: calc(100vw - 20px);
  }

  .v-toast {
    grid-template-columns: 24px minmax(0, 1fr) 44px;
    align-items: center;
    min-height: 60px;
  }

  .v-toast-close {
    width: 44px;
    height: 44px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .v-toast-list-enter-active,
  .v-toast-list-leave-active,
  .v-toast-list-move {
    transition-duration: 1ms;
  }
}
</style>
