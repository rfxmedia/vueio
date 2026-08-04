<template>
  <header class="settings-view-header">
    <div class="settings-view-heading">
      <div class="settings-view-icon" aria-hidden="true">
        <svg class="icon"><use :href="icon" /></svg>
      </div>
      <div class="settings-view-copy">
        <p class="settings-eyebrow">{{ eyebrow }}</p>
        <h2 class="settings-view-title">{{ title }}</h2>
        <p class="settings-view-description">{{ description }}</p>
      </div>
    </div>
    <div v-if="$slots.default" class="settings-view-actions">
      <slot />
    </div>
  </header>
</template>

<script setup>
defineProps({
  description: { type: String, required: true },
  eyebrow: { type: String, required: true },
  icon: { type: String, required: true },
  title: { type: String, required: true },
})
</script>

<style scoped>
.settings-view-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-4);
  min-width: 0;
  padding: 16px 18px;
  border-bottom: 1px solid var(--v-divider-subtle);
}

.settings-view-heading {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr);
  align-items: center;
  gap: var(--v-space-3);
  min-width: 0;
}

.settings-view-icon {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: var(--v-radius-md);
  color: var(--v-accent);
  background: color-mix(in srgb, var(--v-accent) 9%, var(--v-surface-inline));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--v-accent) 20%, transparent);
}

.settings-view-icon .icon {
  width: 17px;
  height: 17px;
}

.settings-view-copy {
  min-width: 0;
}

.settings-eyebrow {
  margin-bottom: 3px;
}

.settings-view-title {
  margin: 0;
  color: var(--v-text);
  font-size: var(--v-text-xl);
  line-height: 1.2;
}

.settings-view-description {
  margin: 4px 0 0;
  color: var(--v-text-muted);
  font-size: var(--v-text-base);
  line-height: 1.4;
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
    align-items: flex-start;
    flex-direction: column;
    gap: var(--v-space-3);
    padding: 13px;
  }

  .settings-view-heading {
    grid-template-columns: 34px minmax(0, 1fr);
    gap: 10px;
  }

  .settings-view-icon {
    width: 34px;
    height: 34px;
  }

  .settings-view-icon .icon {
    width: 15px;
    height: 15px;
  }

  .settings-view-actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
