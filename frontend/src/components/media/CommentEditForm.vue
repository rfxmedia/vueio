<template>
  <div class="composer comment-edit-form" @click.stop>
    <textarea
      ref="textareaRef"
      v-model="text"
      class="composer__textarea"
      rows="1"
      aria-label="Edit comment"
      :disabled="saving"
      @input="resize"
      @keydown="handleKeydown"
    ></textarea>
    <div class="composer__actions">
      <button type="button" class="comment-inline-cancel" :disabled="saving" @click="emit('cancel')">Cancel</button>
      <button
        type="button"
        class="composer__action composer__action--submit"
        :disabled="saving || !canSave"
        :title="saving ? 'Saving' : 'Save'"
        :aria-label="saving ? 'Saving' : 'Save'"
        @click="save"
      >
        <svg class="icon" :class="{ 'is-spinning': saving }"><use :href="saving ? '#icon-loader' : '#icon-check'"/></svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'

const props = defineProps({
  comment: { type: Object, required: true },
  onSave: { type: Function, required: true },
})
const emit = defineEmits(['cancel'])

const textareaRef = ref(null)
const text = ref(props.comment.text || '')
const saving = ref(false)
// A comment keeps its drawing and attachments, so it may have no text.
const canSave = computed(() => text.value !== (props.comment.text || '')
  && Boolean(text.value.trim() || props.comment.annotation_data || props.comment.attachments?.length))

function resize() {
  const textarea = textareaRef.value
  if (!textarea) return
  textarea.style.height = 'auto'
  textarea.style.height = `${textarea.scrollHeight}px`
}

async function save() {
  if (saving.value || !canSave.value) return
  saving.value = true
  try {
    await props.onSave(props.comment, text.value)
  } finally {
    saving.value = false
  }
}

function handleKeydown(event) {
  if (event.isComposing) return
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('cancel')
  } else if (event.key === 'Enter' && event.ctrlKey) {
    event.preventDefault()
    void save()
  }
}

onMounted(() => {
  const textarea = textareaRef.value
  if (!textarea) return
  resize()
  textarea.focus()
  textarea.setSelectionRange(textarea.value.length, textarea.value.length)
})
</script>

<style scoped>
.comment-edit-form { margin-top: 2px; cursor: default; }
</style>
