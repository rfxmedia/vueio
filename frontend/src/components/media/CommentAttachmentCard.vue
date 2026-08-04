<template>
  <button
    type="button"
    class="comment-attachment"
    :class="{ 'is-reference': isReference, 'is-image': !isReference && attachment.kind === 'image', 'is-file': !isReference && attachment.kind !== 'image' }"
    :title="attachment.name || 'Open attachment'"
    @click.stop="$emit('open', attachment)"
  >
    <template v-if="isReference">
      <span class="comment-attachment__icon" aria-hidden="true">
        <svg class="icon"><use :href="referenceIcon" /></svg>
      </span>
      <span class="comment-attachment__copy">
        <strong class="comment-attachment__name v-truncate">{{ attachment.name || 'Project asset' }}</strong>
        <span class="comment-attachment__meta">{{ referenceLabel }}</span>
      </span>
      <svg class="icon comment-attachment__open" aria-hidden="true"><use href="#icon-external-link" /></svg>
    </template>
    <template v-else-if="attachment.kind === 'image'">
      <img :src="url" :alt="attachment.name || ''" />
    </template>
    <template v-else>
      <span class="comment-attachment__icon is-muted" aria-hidden="true">
        <svg class="icon"><use href="#icon-play" /></svg>
      </span>
      <span class="comment-attachment__copy">
        <strong class="comment-attachment__name v-truncate">{{ attachment.name || 'Video' }}</strong>
        <span class="comment-attachment__meta">Video</span>
      </span>
    </template>
  </button>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  attachment: { type: Object, required: true },
  url: { type: String, default: '' },
})

defineEmits(['open'])

const isReference = computed(() => props.attachment?.attachment_type === 'reference')
const referenceLabel = computed(() => ({
  media_asset: props.attachment?.kind === 'pdf' ? 'Project PDF' : 'Project file',
  tracker: 'Vue Tracker',
  page: 'Dashboard',
}[props.attachment?.target_type] || 'Project asset'))
const referenceIcon = computed(() => ({
  tracker: '#icon-project',
  page: '#icon-layout',
}[props.attachment?.target_type] || ({
  pdf: '#icon-pdf',
  image: '#icon-image',
  video: '#icon-video',
}[props.attachment?.kind] || '#icon-file')))
</script>

<style scoped>
.comment-attachment {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 100%;
  padding: 0;
  border: 1px solid color-mix(in srgb, var(--v-control-border) 68%, transparent);
  border-radius: var(--v-radius-sm);
  background: var(--v-surface-tint-strong);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color var(--v-transition-fast), background var(--v-transition-fast);
}

.comment-attachment:hover {
  border-color: var(--v-control-border-hover);
  background: color-mix(in srgb, var(--v-surface-inline-strong) 62%, transparent);
}

.comment-attachment.is-image {
  width: 72px;
  height: 48px;
  overflow: hidden;
  padding: 0;
}

.comment-attachment.is-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.comment-attachment.is-file,
.comment-attachment.is-reference {
  max-width: min(100%, 220px);
  min-height: 36px;
  padding: 5px 7px;
}

.comment-attachment__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  flex: 0 0 auto;
  border-radius: 6px;
  border: 1px solid color-mix(in srgb, var(--v-accent) 22%, var(--v-control-border));
  background: color-mix(in srgb, var(--v-accent) 10%, transparent);
  color: var(--v-accent);
}

.comment-attachment__icon.is-muted {
  border-color: color-mix(in srgb, var(--v-control-border) 80%, transparent);
  background: color-mix(in srgb, var(--v-surface-raised) 70%, transparent);
  color: var(--v-text-secondary);
}

.comment-attachment__icon .icon,
.comment-attachment__open {
  width: 12px;
  height: 12px;
}

.comment-attachment__copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.comment-attachment__name {
  color: var(--v-text);
  font-size: var(--v-text-xs);
  font-weight: 600;
  line-height: 1.2;
}

.comment-attachment__meta {
  color: var(--v-text-muted);
  font-size: var(--v-text-2xs);
  line-height: 1.2;
}

.comment-attachment__open {
  margin-left: auto;
  color: var(--v-text-dim);
  flex: 0 0 auto;
}
</style>
