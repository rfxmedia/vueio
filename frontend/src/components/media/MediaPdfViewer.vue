<template>
  <div class="pdf-viewer" @click.stop>
    <div class="pdf-toolbar">
      <div class="pdf-toolbar-title">
        <svg class="icon"><use href="#icon-pdf" /></svg>
        <span class="v-truncate">{{ fileName || 'PDF' }}</span>
      </div>
      <div class="pdf-toolbar-actions">
        <span v-if="pageCount" class="pdf-page-status">Page {{ currentPage }} / {{ pageCount }}</span>
        <button
          type="button"
          class="pdf-download-button"
          :disabled="!canDownload"
          title="Download PDF"
          aria-label="Download PDF"
          @click.stop="downloadCurrentPdf"
        >
          <svg class="icon"><use href="#icon-download" /></svg>
        </button>
      </div>
    </div>

    <div ref="scrollEl" class="pdf-scroll" @scroll="handleScroll">
      <div v-if="loading" class="pdf-state">
        <svg class="icon pdf-state-spinner"><use href="#icon-loader" /></svg>
        <span>Loading PDF...</span>
      </div>
      <div v-else-if="errorMessage" class="pdf-state is-error">
        <svg class="icon"><use href="#icon-pdf" /></svg>
        <span>{{ errorMessage }}</span>
      </div>
      <div v-else class="pdf-pages">
        <section
          v-for="page in pages"
          :key="page.pageNumber"
          :ref="(el) => setPageShellRef(page.pageNumber, el)"
          class="pdf-page-shell"
          :class="{ 'is-focused': focusedPage === page.pageNumber }"
          :data-page-number="page.pageNumber"
        >
          <div class="pdf-page-label">Page {{ page.pageNumber }}</div>
          <div class="pdf-page-canvas-wrap" :style="pageCanvasWrapStyle(page)">
            <canvas
              :ref="(el) => setPageCanvasRef(page.pageNumber, el)"
              class="pdf-page-canvas"
            ></canvas>
            <canvas
              :ref="(el) => setPreviewCanvasRef(page.pageNumber, el)"
              class="pdf-annotation-preview-canvas"
              :class="{ visible: focusedPage === page.pageNumber && focusedAnnotationData }"
            ></canvas>
            <button
              v-for="marker in markersForPage(page.pageNumber)"
              :key="marker.comment.id"
              type="button"
              class="pdf-annotation-marker"
              :style="markerStyle(marker)"
              :aria-label="markerLabel(marker)"
              :title="markerLabel(marker)"
              @click.stop="selectPdfComment(marker.comment)"
            ></button>
            <canvas
              v-if="isDrawingMode && activeAnnotationPage === page.pageNumber"
              :ref="(el) => setAnnotationCanvasRef(page.pageNumber, el)"
              class="pdf-annotation-canvas drawing-mode"
              @pointerdown.stop.prevent="handleAnnotationPointerDown(page.pageNumber, $event)"
              @pointermove.stop.prevent="movePointerDrawing"
              @pointerup.stop.prevent="finishPointerDrawing"
              @pointercancel.stop.prevent="finishPointerDrawing"
            ></canvas>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist'
import { getPdfAnnotationTarget, isSafePngDataUrl } from '../../lib/annotations'

GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

const props = defineProps({
  sourceUrl: { type: String, default: '' },
  fileName: { type: String, default: '' },
  comments: { type: Array, default: () => [] },
  isDrawingMode: { type: Boolean, default: false },
  focusRequest: { type: Object, default: null },
  canDownload: { type: Boolean, default: true },
  startPointerDrawing: { type: Function, required: true },
  movePointerDrawing: { type: Function, required: true },
  finishPointerDrawing: { type: Function, required: true },
  onActivateAnnotationCanvas: { type: Function, default: null },
  onAnnotationTargetChange: { type: Function, default: null },
  onLoaded: { type: Function, default: null },
  onDownload: { type: Function, default: null },
  onCommentSelect: { type: Function, default: null },
})

const scrollEl = ref(null)
const pdfDoc = shallowRef(null)
const pages = ref([])
const loading = ref(false)
const errorMessage = ref('')
const currentPage = ref(1)
const activeAnnotationPage = ref(1)
const focusedPage = ref(null)
const focusedAnnotationData = ref('')

const pageShellRefs = new Map()
const pageCanvasRefs = new Map()
const annotationCanvasRefs = new Map()
const previewCanvasRefs = new Map()

let loadingTask = null
let renderToken = 0
let resizeObserver = null
let resizeTimer = 0
let scrollFrame = 0

const pageCount = computed(() => pages.value.length)
const flatComments = computed(() => flattenComments(props.comments))
const pdfMarkers = computed(() => flatComments.value
  .map((comment) => ({ comment, target: getPdfAnnotationTarget(comment) }))
  .filter((item) => item.target))

function flattenComments(items) {
  const flat = []
  for (const item of items || []) {
    if (!item) continue
    flat.push(item)
    for (const reply of item.replies || []) flat.push(reply)
  }
  return flat
}

function pageCanvasWrapStyle(page) {
  if (!page.cssWidth || !page.cssHeight) return {}
  return {
    width: `${page.cssWidth}px`,
    height: `${page.cssHeight}px`,
  }
}

function setPageShellRef(pageNumber, el) {
  setMapRef(pageShellRefs, pageNumber, el)
}

function setPageCanvasRef(pageNumber, el) {
  setMapRef(pageCanvasRefs, pageNumber, el)
}

function setAnnotationCanvasRef(pageNumber, el) {
  setMapRef(annotationCanvasRefs, pageNumber, el)
  if (el && props.isDrawingMode && activeAnnotationPage.value === pageNumber) {
    activateAnnotationPage(pageNumber)
  }
}

function setPreviewCanvasRef(pageNumber, el) {
  setMapRef(previewCanvasRefs, pageNumber, el)
  if (el) syncOverlayCanvas(pageNumber)
}

function setMapRef(map, key, el) {
  if (el) map.set(key, el)
  else map.delete(key)
}

async function loadPdf() {
  cleanupPdf()
  pages.value = []
  errorMessage.value = ''
  focusedPage.value = null
  focusedAnnotationData.value = ''
  currentPage.value = 1
  activeAnnotationPage.value = 1

  if (!props.sourceUrl) return

  loading.value = true
  const task = getDocument({ url: props.sourceUrl, withCredentials: true })
  loadingTask = task

  try {
    const doc = await task.promise
    if (loadingTask !== task) {
      await safeDestroyDocument(doc)
      return
    }
    pdfDoc.value = doc
    pages.value = Array.from({ length: doc.numPages }, (_, index) => ({
      pageNumber: index + 1,
      cssWidth: 0,
      cssHeight: 0,
      rendered: false,
    }))
    props.onLoaded?.({ pageCount: doc.numPages })
    loading.value = false
    await nextTick()
    await renderAllPages()
    handleFocusRequest(props.focusRequest)
  } catch (error) {
    if (loadingTask === task) {
      console.error('Failed to load PDF')
      errorMessage.value = 'Could not load this PDF.'
    }
  } finally {
    if (loadingTask === task) {
      loading.value = false
      loadingTask = null
    }
  }
}

async function renderAllPages() {
  const doc = pdfDoc.value
  const scroller = scrollEl.value
  if (!doc || !scroller) return

  const token = ++renderToken
  const availableWidth = getAvailablePageWidth()
  for (const page of pages.value) {
    if (token !== renderToken) return
    await renderPage(doc, page.pageNumber, availableWidth, token)
  }
  updateCurrentPageFromScroll()
}

async function renderPage(doc, pageNumber, availableWidth, token) {
  const canvas = pageCanvasRefs.get(pageNumber)
  if (!canvas || token !== renderToken) return

  const page = await doc.getPage(pageNumber)
  if (token !== renderToken) return

  const baseViewport = page.getViewport({ scale: 1 })
  const cssScale = availableWidth / baseViewport.width
  const outputScale = Math.max(1, Math.min(2, window.devicePixelRatio || 1))
  const displayViewport = page.getViewport({ scale: cssScale })
  const renderViewport = page.getViewport({ scale: cssScale * outputScale })
  const pageInfo = pages.value[pageNumber - 1]

  if (pageInfo) {
    pageInfo.cssWidth = displayViewport.width
    pageInfo.cssHeight = displayViewport.height
    pageInfo.rendered = false
  }

  canvas.width = Math.floor(renderViewport.width)
  canvas.height = Math.floor(renderViewport.height)
  canvas.style.width = `${displayViewport.width}px`
  canvas.style.height = `${displayViewport.height}px`

  const context = canvas.getContext('2d')
  if (!context) return
  context.clearRect(0, 0, canvas.width, canvas.height)

  await page.render({ canvasContext: context, viewport: renderViewport }).promise
  if (token !== renderToken) return
  if (pageInfo) pageInfo.rendered = true
  syncOverlayCanvas(pageNumber)

  if (focusedPage.value === pageNumber && focusedAnnotationData.value) {
    drawPreviewAnnotation(pageNumber, focusedAnnotationData.value)
  }
}

function getAvailablePageWidth() {
  const scroller = scrollEl.value
  const width = Number(scroller?.clientWidth || 0)
  if (!width) return 860
  return Math.max(280, Math.min(1120, width - 40))
}

function syncOverlayCanvas(pageNumber) {
  const pageCanvas = pageCanvasRefs.get(pageNumber)
  if (!pageCanvas) return
  for (const overlay of [annotationCanvasRefs.get(pageNumber), previewCanvasRefs.get(pageNumber)]) {
    if (!overlay) continue
    overlay.width = pageCanvas.width
    overlay.height = pageCanvas.height
    overlay.style.width = pageCanvas.style.width
    overlay.style.height = pageCanvas.style.height
  }
}

function scheduleRerender() {
  if (!pdfDoc.value) return
  window.clearTimeout(resizeTimer)
  resizeTimer = window.setTimeout(() => {
    renderAllPages()
  }, 120)
}

function cleanupPdf() {
  renderToken += 1
  if (loadingTask) {
    try { loadingTask.destroy() } catch {}
    loadingTask = null
  }
  if (pdfDoc.value) {
    void safeDestroyDocument(pdfDoc.value)
    pdfDoc.value = null
  }
}

async function safeDestroyDocument(doc) {
  try {
    await doc?.destroy?.()
  } catch {}
}

function handleScroll() {
  if (scrollFrame) return
  scrollFrame = window.requestAnimationFrame(() => {
    scrollFrame = 0
    updateCurrentPageFromScroll()
  })
}

function updateCurrentPageFromScroll() {
  const scroller = scrollEl.value
  if (!scroller || !pages.value.length) return
  const anchor = scroller.scrollTop + scroller.clientHeight * 0.35
  let nextPage = pages.value[0].pageNumber
  for (const page of pages.value) {
    const shell = pageShellRefs.get(page.pageNumber)
    if (!shell) continue
    if (shell.offsetTop <= anchor) nextPage = page.pageNumber
    else break
  }
  currentPage.value = nextPage
  if (!props.isDrawingMode) activeAnnotationPage.value = nextPage
}

function activateAnnotationPage(pageNumber = activeAnnotationPage.value) {
  const canvas = annotationCanvasRefs.get(pageNumber)
  if (!canvas) return
  syncOverlayCanvas(pageNumber)
  const target = { kind: 'pdf-region', page: pageNumber }
  props.onAnnotationTargetChange?.(target)
  props.onActivateAnnotationCanvas?.(canvas, target)
}

function handleAnnotationPointerDown(pageNumber, event) {
  activeAnnotationPage.value = pageNumber
  activateAnnotationPage(pageNumber)
  props.startPointerDrawing(event)
}

function handleFocusRequest(request) {
  clearPreviewCanvases()
  focusedPage.value = null
  focusedAnnotationData.value = ''

  const target = getPdfAnnotationTarget(request?.annotationTarget)
  if (!target) return

  focusedPage.value = target.page
  focusedAnnotationData.value = request?.annotationData || ''
  nextTick(() => {
    scrollToTarget(target)
    if (focusedAnnotationData.value) {
      drawPreviewAnnotation(target.page, focusedAnnotationData.value)
    }
  })
}

function scrollToTarget(target) {
  const scroller = scrollEl.value
  const shell = pageShellRefs.get(target.page)
  if (!scroller || !shell) return
  const rect = target.rect || { x: 0, y: 0, width: 1, height: 1 }
  const targetCenter = shell.offsetTop + (rect.y + rect.height / 2) * shell.offsetHeight
  const nextTop = Math.max(0, targetCenter - scroller.clientHeight * 0.38)
  scroller.scrollTo({ top: nextTop, behavior: 'smooth' })
}

function drawPreviewAnnotation(pageNumber, annotationData) {
  const canvas = previewCanvasRefs.get(pageNumber)
  if (!canvas || !isSafePngDataUrl(annotationData)) return
  syncOverlayCanvas(pageNumber)
  const context = canvas.getContext('2d')
  if (!context) return
  context.clearRect(0, 0, canvas.width, canvas.height)

  const image = new Image()
  image.onload = () => {
    context.clearRect(0, 0, canvas.width, canvas.height)
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
  }
  image.src = annotationData
}

function clearPreviewCanvases() {
  for (const canvas of previewCanvasRefs.values()) {
    const context = canvas.getContext('2d')
    context?.clearRect(0, 0, canvas.width, canvas.height)
  }
}

function markersForPage(pageNumber) {
  return pdfMarkers.value.filter((marker) => marker.target.page === pageNumber)
}

function markerStyle(marker) {
  const rect = marker.target.rect || { x: 0.5, y: 0.5, width: 0.04, height: 0.04 }
  return {
    left: `${rect.x * 100}%`,
    top: `${rect.y * 100}%`,
    width: `${Math.max(rect.width * 100, 2)}%`,
    height: `${Math.max(rect.height * 100, 2)}%`,
  }
}

function markerLabel(marker) {
  const author = String(marker.comment?.user_name || 'comment').trim()
  return `${author} annotation on page ${marker.target.page}`
}

function selectPdfComment(comment) {
  props.onCommentSelect?.(comment)
}

function downloadCurrentPdf() {
  props.onDownload?.()
}

watch(() => props.sourceUrl, loadPdf, { immediate: true })

watch(() => props.isDrawingMode, (isDrawing) => {
  if (!isDrawing) {
    props.onAnnotationTargetChange?.(null)
    return
  }
  activeAnnotationPage.value = currentPage.value || 1
  nextTick(() => activateAnnotationPage(activeAnnotationPage.value))
})

watch(() => props.focusRequest, (request) => {
  handleFocusRequest(request)
})

onMounted(() => {
  if (scrollEl.value && 'ResizeObserver' in window) {
    resizeObserver = new ResizeObserver(scheduleRerender)
    resizeObserver.observe(scrollEl.value)
  }
})

onBeforeUnmount(() => {
  cleanupPdf()
  clearPreviewCanvases()
  window.clearTimeout(resizeTimer)
  if (scrollFrame) window.cancelAnimationFrame(scrollFrame)
  resizeObserver?.disconnect?.()
})
</script>

<style>
.pdf-viewer {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--v-bg-black);
}

.pdf-toolbar {
  flex: 0 0 auto;
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v-space-3);
  padding: 8px 10px 8px 14px;
  border-bottom: 1px solid color-mix(in srgb, var(--v-border) 76%, transparent);
  background: color-mix(in srgb, var(--v-bg-black) 88%, var(--v-surface-panel));
}

.pdf-toolbar-title,
.pdf-toolbar-actions {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--v-space-2);
}

.pdf-toolbar-title {
  color: var(--v-text);
  font-size: var(--v-text-sm);
  font-weight: 650;
}

.pdf-toolbar-title .icon {
  flex: 0 0 auto;
  width: 17px;
  height: 17px;
  color: var(--v-accent);
}

.pdf-page-status {
  white-space: nowrap;
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 600;
}

.pdf-download-button {
  width: var(--v-icon-btn-size);
  height: var(--v-icon-btn-size);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--v-control-border);
  border-radius: var(--v-icon-btn-radius);
  color: var(--v-text);
  background: var(--v-control-bg);
  cursor: pointer;
  transition:
    background var(--v-duration-fast) var(--v-ease-emphasized),
    border-color var(--v-duration-fast) var(--v-ease-emphasized),
    color var(--v-duration-fast) var(--v-ease-emphasized);
}

.pdf-download-button:hover:not(:disabled),
.pdf-download-button:focus-visible {
  color: var(--v-text);
  border-color: var(--v-control-border-hover);
  background: var(--v-control-bg-hover);
  outline: none;
}

.pdf-download-button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.pdf-download-button .icon {
  width: 16px;
  height: 16px;
}

.pdf-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--v-bg-black) 88%, var(--v-surface-panel)), var(--v-bg-black) 220px);
}

.pdf-pages {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
  padding: var(--v-space-5);
}

.pdf-page-shell {
  width: min-content;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  gap: 7px;
  scroll-margin-block: 36px;
}

.pdf-page-label {
  color: var(--v-text-muted);
  font-size: var(--v-text-xs);
  font-weight: 650;
}

.pdf-page-canvas-wrap {
  position: relative;
  max-width: 100%;
  overflow: hidden;
  border-radius: var(--v-radius-md);
  background: #fff;
  box-shadow: 0 18px 42px rgba(0, 0, 0, 0.28);
}

.pdf-page-shell.is-focused .pdf-page-canvas-wrap {
  box-shadow:
    0 0 0 2px color-mix(in srgb, var(--v-accent) 56%, transparent),
    0 18px 42px rgba(0, 0, 0, 0.3);
}

.pdf-page-canvas {
  display: block;
  max-width: 100%;
  height: auto;
}

.pdf-annotation-canvas,
.pdf-annotation-preview-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.pdf-annotation-preview-canvas {
  z-index: 2;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--v-duration-fast) var(--v-ease-emphasized);
}

.pdf-annotation-preview-canvas.visible {
  opacity: 1;
}

.pdf-annotation-canvas {
  z-index: 5;
  cursor: crosshair;
  touch-action: none;
}

.pdf-annotation-marker {
  position: absolute;
  z-index: 3;
  min-width: 16px;
  min-height: 16px;
  border: 2px solid color-mix(in srgb, var(--v-accent) 86%, white);
  border-radius: var(--v-radius-md);
  background: color-mix(in srgb, var(--v-accent) 16%, transparent);
  box-shadow: 0 0 0 1px rgba(6, 10, 14, 0.4), 0 8px 20px rgba(0, 0, 0, 0.18);
  cursor: pointer;
  transition:
    background var(--v-duration-fast) var(--v-ease-emphasized),
    transform var(--v-duration-fast) var(--v-ease-emphasized);
}

.pdf-annotation-marker:hover,
.pdf-annotation-marker:focus-visible {
  background: color-mix(in srgb, var(--v-accent) 28%, transparent);
  outline: none;
  transform: scale(1.04);
}

.pdf-state {
  height: 100%;
  min-height: 260px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--v-space-2);
  color: var(--v-text-muted);
  font-size: var(--v-text-sm);
  font-weight: 600;
}

.pdf-state.is-error {
  color: var(--v-danger);
}

.pdf-state-spinner {
  animation: v-spin 0.9s linear infinite;
}

@media (max-width: 720px) {
  .pdf-toolbar {
    min-height: 40px;
    padding: 7px 8px 7px 10px;
  }

  .pdf-page-status {
    display: none;
  }

  .pdf-pages {
    gap: var(--v-space-3);
    padding: var(--v-space-3);
  }

  .pdf-page-canvas-wrap {
    border-radius: var(--v-radius-sm);
  }
}
</style>
