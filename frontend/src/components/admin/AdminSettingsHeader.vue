<template>
  <header class="settings-view-header" :class="{ 'is-compact': !eyebrow && !description }">
    <div class="settings-view-heading">
      <div class="settings-view-icon" aria-hidden="true">
        <svg class="icon"><use :href="icon" /></svg>
      </div>
      <div class="settings-view-copy">
        <p v-if="eyebrow" class="settings-eyebrow">{{ eyebrow }}</p>
        <h2 class="settings-view-title">{{ title }}</h2>
        <p v-if="description" class="settings-view-description">{{ description }}</p>
      </div>
    </div>
    <div v-if="$slots.default" class="settings-view-actions">
      <slot />
    </div>
  </header>
</template>

<script setup>
defineProps({
  description: { type: String, default: '' },
  eyebrow: { type: String, default: '' },
  icon: { type: String, required: true },
  title: { type: String, required: true },
})
</script>

<style scoped>
.settings-view-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--v-space-6);
  min-width: 0;
  padding: 0 0 var(--v-space-4);
  border-bottom: 1px solid var(--v-divider-subtle);
}

.settings-view-heading {
  display: grid;
  grid-template-columns: var(--v-control-pill-height) minmax(0, 1fr);
  align-items: start;
  gap: var(--v-space-3);
  min-width: 0;
}

.settings-view-icon {
  width: var(--v-control-pill-height);
  height: var(--v-control-pill-height);
  display: grid;
  place-items: center;
  border-radius: var(--v-radius-md);
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 8%, var(--v-surface-tint));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-accent) 16%, transparent);
}

.settings-view-icon .icon {
  width: 15px;
  height: 15px;
}

.settings-view-copy {
  min-width: 0;
}

.settings-eyebrow {
  margin-bottom: 4px;
}

.settings-view-title {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-2xl);
  font-weight: 740;
  letter-spacing: -0.018em;
  line-height: 1.15;
}

.settings-view-description {
  max-width: 680px;
  margin: 6px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-base);
  line-height: 1.45;
}

.settings-view-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: var(--v-space-2);
  flex: 0 0 auto;
  padding-top: 3px;
}

.settings-view-header.is-compact,
.is-compact .settings-view-heading {
  align-items: center;
}

@media (max-width: 768px) {
  .settings-view-header {
    align-items: flex-start;
    flex-direction: column;
    gap: var(--v-space-3);
    padding: 0 0 var(--v-space-3);
  }

  .settings-view-heading {
    grid-template-columns: 30px minmax(0, 1fr);
    gap: var(--v-space-3);
  }

  .settings-view-icon {
    width: 30px;
    height: 30px;
  }

  .settings-view-icon .icon {
    width: 14px;
    height: 14px;
  }

  .settings-view-title {
    font-size: var(--v-text-2xl);
  }

  .settings-view-description {
    font-size: var(--v-text-base);
  }

  .settings-view-actions {
    width: 100%;
    justify-content: flex-start;
    padding-top: 0;
  }

  .settings-view-header.is-compact {
    flex-direction: row;
  }

  .is-compact .settings-view-actions {
    width: auto;
  }

  .settings-view-actions :deep(.v-btn) {
    flex: 1 1 auto;
    min-height: var(--v-btn-height-lg);
  }
}
</style>
