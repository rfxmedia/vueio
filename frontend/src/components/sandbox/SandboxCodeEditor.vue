<template>
  <div class="sce" :class="{ 'is-plain': plain }">
    <pre ref="gutterRef" class="sce-gutter" aria-hidden="true">{{ lineNumbers }}</pre>
    <div class="sce-body">
      <pre ref="highlightRef" class="sce-highlight" aria-hidden="true"><code v-html="highlighted"></code></pre>
      <textarea
        ref="inputRef"
        class="sce-input"
        :value="modelValue"
        :placeholder="placeholder"
        :aria-label="label"
        spellcheck="false"
        autocapitalize="off"
        autocomplete="off"
        autocorrect="off"
        wrap="off"
        @input="onInput"
        @scroll="syncScroll"
        @keydown="onKeydown"
      ></textarea>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { HIGHLIGHT_MAX_CHARS, highlightHtml } from '../../utils/sandboxHighlight'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  label: { type: String, default: 'Page code' },
})
const emit = defineEmits(['update:modelValue', 'save'])

const INDENT = '  '
const inputRef = ref(null)
const highlightRef = ref(null)
const gutterRef = ref(null)
const highlighted = ref('')
// After Escape, Tab moves focus out of the editor instead of indenting.
let tabLeavesEditor = false
let frame = 0

const plain = computed(() => props.modelValue.length > HIGHLIGHT_MAX_CHARS)
// Counting is cheap; the numbers are rebuilt only when the count changes.
const lineCount = computed(() => {
  const text = props.modelValue
  let count = 1
  for (let index = text.indexOf('\n'); index !== -1; index = text.indexOf('\n', index + 1)) count += 1
  return count
})
const lineNumbers = computed(() => Array.from({ length: lineCount.value }, (_value, index) => index + 1).join('\n'))

// Color the code on the next frame, at most once per frame. The trailing
// newline keeps the last line of the copy as tall as the text area's.
function scheduleHighlight() {
  if (frame) return
  frame = requestAnimationFrame(() => {
    frame = 0
    // A large page shows the text area's own text; the colored copy stays empty.
    highlighted.value = plain.value ? '' : `${highlightHtml(props.modelValue)}\n`
  })
}
watch(() => props.modelValue, scheduleHighlight, { immediate: true })
onBeforeUnmount(() => cancelAnimationFrame(frame))

function syncScroll() {
  const input = inputRef.value
  if (!input) return
  if (highlightRef.value) {
    highlightRef.value.scrollTop = input.scrollTop
    highlightRef.value.scrollLeft = input.scrollLeft
  }
  if (gutterRef.value) gutterRef.value.scrollTop = input.scrollTop
}

function onInput(event) {
  emit('update:modelValue', event.target.value)
}

// insertText keeps the browser's own undo history working.
function insertText(text) {
  const input = inputRef.value
  if (!document.execCommand('insertText', false, text)) {
    input.setRangeText(text, input.selectionStart, input.selectionEnd, 'end')
    emit('update:modelValue', input.value)
  }
}

function indentLines(outdent) {
  const input = inputRef.value
  const { value, selectionStart, selectionEnd } = input
  const start = value.lastIndexOf('\n', selectionStart - 1) + 1
  const endBreak = value.indexOf('\n', selectionEnd - (selectionEnd > selectionStart && value[selectionEnd - 1] === '\n' ? 1 : 0))
  const end = endBreak < 0 ? value.length : endBreak
  const lines = value.slice(start, end).split('\n')
  const changed = lines.map(line => (outdent ? line.replace(/^( {1,2}|\t)/, '') : INDENT + line)).join('\n')
  input.setSelectionRange(start, end)
  insertText(changed)
  input.setSelectionRange(start, start + changed.length)
}

function onKeydown(event) {
  const input = inputRef.value
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    emit('save')
    return
  }
  if (event.key === 'Escape') {
    tabLeavesEditor = true
    return
  }
  if (event.key === 'Tab' && !tabLeavesEditor && !event.altKey && !event.metaKey && !event.ctrlKey) {
    event.preventDefault()
    const multiline = input.value.slice(input.selectionStart, input.selectionEnd).includes('\n')
    if (event.shiftKey || multiline) indentLines(event.shiftKey)
    else insertText(INDENT)
    return
  }
  tabLeavesEditor = false
  if (event.key === 'Enter' && !event.shiftKey && !event.altKey && !event.metaKey && !event.ctrlKey && !event.isComposing) {
    const lineStart = input.value.lastIndexOf('\n', input.selectionStart - 1) + 1
    const indent = input.value.slice(lineStart, input.selectionStart).match(/^[ \t]*/)[0]
    if (!indent) return
    event.preventDefault()
    insertText(`\n${indent}`)
  }
}

function focus({ selectAll = false } = {}) {
  const input = inputRef.value
  if (!input) return
  input.focus({ preventScroll: true })
  if (selectAll) input.select()
}

defineExpose({ focus })
</script>

<style scoped>
.sce {
  --sce-line: 20px;
  --sce-pad: 14px;
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
  /* The code never sets the editor's size; the editor fills its pane. */
  contain: size;
  background: var(--v-surface-inset);
  font-family: ui-monospace, 'SF Mono', 'Cascadia Code', 'JetBrains Mono', Menlo, Consolas, monospace;
  font-size: 12.5px;
  line-height: var(--sce-line);
  tab-size: 2;
}

.sce-gutter {
  flex: none;
  min-width: 46px;
  margin: 0;
  padding: var(--sce-pad) 10px var(--sce-pad) 12px;
  overflow: hidden;
  border-right: 1px solid var(--v-divider-subtle);
  color: color-mix(in srgb, var(--v-text-dim) 70%, transparent);
  font: inherit;
  text-align: right;
  user-select: none;
  white-space: pre;
}

.sce-body {
  position: relative;
  flex: 1;
  min-width: 0;
}

.sce-highlight,
.sce-input {
  position: absolute;
  inset: 0;
  box-sizing: border-box;
  margin: 0;
  padding: var(--sce-pad) 18px var(--sce-pad) 14px;
  border: 0;
  font: inherit;
  letter-spacing: 0;
  white-space: pre;
  word-wrap: normal;
  overflow-wrap: normal;
  tab-size: inherit;
}

.sce-highlight {
  overflow: hidden;
  color: var(--v-text-secondary);
  pointer-events: none;
}

.sce-highlight code {
  font: inherit;
}

.sce-input {
  width: 100%;
  height: 100%;
  overflow: auto;
  outline: none;
  resize: none;
  background: transparent;
  color: transparent;
  caret-color: var(--v-text);
}

.sce.is-plain .sce-input {
  color: var(--v-text-secondary);
}

.sce.is-plain .sce-highlight {
  visibility: hidden;
}

.sce-input::placeholder {
  color: var(--v-text-dim);
}

.sce-input::selection {
  background: color-mix(in srgb, var(--v-sandbox) 34%, transparent);
  color: transparent;
}

.sce.is-plain .sce-input::selection {
  color: var(--v-text);
}

.sce :deep(.hl-tag) { color: #8ec5ff; }
.sce :deep(.hl-attr) { color: #c6a7ff; }
.sce :deep(.hl-string) { color: #9fe3b4; }
.sce :deep(.hl-comment) { color: color-mix(in srgb, var(--v-text-dim) 80%, transparent); font-style: italic; }
.sce :deep(.hl-keyword) { color: #ff9ec7; }
.sce :deep(.hl-number) { color: #f6c27a; }
</style>
