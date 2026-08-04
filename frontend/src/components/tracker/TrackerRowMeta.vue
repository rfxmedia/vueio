<template>
  <div class="tracker-row-meta">
    <input
      v-if="canEditShotName && !shareMode"
      class="tracker-row-id-input"
      :value="shot.shot_id"
      @input="shot.shot_id = $event.target.value"
      @blur="saveShot(shot)"
      @keydown.enter="$event.target.blur()"
    />
    <span v-else class="tracker-row-id-text">{{ shot.shot_id }}</span>

    <span class="tracker-row-updated">{{ formattedUpdated }}</span>
  </div>
</template>

<script setup>
defineProps({
  shot: { type: Object, required: true },
  formattedUpdated: { type: String, required: true },
  canEditShotName: { type: Boolean, default: false },
  shareMode: { type: Boolean, default: false },
  saveShot: { type: Function, required: true },
})
</script>

<style scoped>
.tracker-row-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  width: 100%;
}


.tracker-row-id-input,
.tracker-row-id-text {
  display: block;
  min-width: 0;
  font-size: var(--v-text-md);
  line-height: 1.2;
  font-weight: 640;
  letter-spacing: 0;
  color: var(--v-text);
  font-variant-numeric: tabular-nums;
}

.tracker-row-id-input {
  transition: color var(--v-transition-fast), box-shadow var(--v-transition-fast);
}

.tracker-row-id-input:focus {
  color: var(--v-text);
  box-shadow: 0 1px 0 var(--v-accent);
}

.tracker-row-id-input {
  width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  border-radius: 0;
}

.tracker-row-id-input:hover,
.tracker-row-id-input:focus {
  background: transparent;
}

/* Inline edits should look editable the moment they take focus. */
.tracker-row-id-input:focus {
  outline: none;
  box-shadow: 0 1px 0 color-mix(in srgb, var(--v-accent) 70%, transparent);
}

.tracker-row-id-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tracker-row-updated {
  color: color-mix(in srgb, var(--v-text-muted) 72%, var(--v-bg-base));
  font-family: var(--v-font);
  font-size: var(--v-text-xs);
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
  line-height: 1.4;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 768px) {
  .tracker-row-meta {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    flex-wrap: nowrap;
    gap: var(--v-space-3);
    min-height: 0;
  }

  .tracker-row-id-input,
  .tracker-row-id-text {
    display: inline;
    flex: 1 1 auto;
    width: auto;
    min-width: 0;
    max-width: none;
    font-size: var(--v-text-lg);
    line-height: 1.2;
    font-weight: 700;
    letter-spacing: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .tracker-row-id-input {
    min-width: 2.5ch;
    padding: 0;
    flex: 0 1 auto;
  }

  .tracker-row-updated {
    flex: 0 0 auto;
    margin-left: auto;
    font-size: var(--v-text-2xs);
    font-weight: 500;
    letter-spacing: 0.02em;
    line-height: 1.2;
    white-space: nowrap;
    text-align: right;
  }

  .tracker-row-updated::before {
    content: none;
  }
}
</style>
