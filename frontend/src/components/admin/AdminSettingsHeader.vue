<template>
  <header class="settings-view-header">
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
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-4) var(--v-space-6);
  min-width: 0;
  padding: 2px 0 var(--v-space-2);
}

.settings-view-heading {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  align-items: center;
  gap: var(--v-space-3);
  min-width: 0;
}

.settings-view-icon {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: var(--v-radius-md);
  color: var(--v-accent);
  background: var(--v-accent-muted);
}

.settings-view-icon .icon {
  width: 17px;
  height: 17px;
}

.settings-view-copy {
  min-width: 0;
}

.settings-eyebrow {
  margin-bottom: 2px;
}

.settings-view-title {
  margin: 0;
  color: var(--v-text);
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.015em;
  line-height: 1.2;
}

.settings-view-description {
  max-width: 640px;
  margin: 2px 0 0;
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
}

@media (max-width: 768px) {
  .settings-view-header {
    align-items: stretch;
    flex-direction: column;
    gap: var(--v-space-3);
  }

  .settings-view-heading {
    grid-template-columns: 32px minmax(0, 1fr);
    align-items: start;
  }

  .settings-view-icon {
    width: 32px;
    height: 32px;
  }

  .settings-view-icon .icon {
    width: 15px;
    height: 15px;
  }

  .settings-view-title {
    font-size: var(--v-text-2xl);
  }

  .settings-view-actions {
    justify-content: flex-start;
  }

  .settings-view-actions :deep(.v-btn) {
    flex: 1 1 auto;
    min-height: var(--v-btn-height-lg);
  }
}
</style>
