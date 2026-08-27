import { getCurrentScope, onScopeDispose, ref } from 'vue'
import { buildPdfAnnotationTarget } from '../lib/annotations'
import { useAnnotationDrawing } from './useAnnotationDrawing'

const VIEWER_ANNOTATION_COLORS = Object.freeze([
  '#ff3b30',
  '#ff9500',
  '#ffcc00',
  '#34c759',
  '#007aff',
  '#af52de',
  '#ffffff',
])

function readReactiveValue(source) {
  return typeof source === 'function' ? source() : source?.value
}

export function useViewerAnnotationOverlay({
  videoEl,
  videoContainer,
  imageStage,
  currentTime,
  isPlaying,
  isViewingVideo,
  isViewingImage,
  isViewingPdf,
  videoInfo,
  onAnnotationPreviewVisibilityChange,
  windowTarget = typeof window === 'undefined' ? null : window,
  documentTarget = typeof document === 'undefined' ? null : document,
  schedule = setTimeout,
  now = () => Date.now(),
} = {}) {
  const annotationCanvas = ref(null)
  const previewCanvas = ref(null)
  const isDrawingMode = ref(false)
  const isDrawing = ref(false)
  const drawingColor = ref(VIEWER_ANNOTATION_COLORS[0])
  const pendingAnnotation = ref(null)
  const pendingAnnotationTimestamp = ref(null)
  const pendingAnnotationTarget = ref(null)
  const pdfAnnotationTarget = ref(null)
  const pdfFocusRequest = ref(null)

  let canvasResizeHandler = null
  let canvasResizeFrame = 0

  function setAnnotationPreviewVisible(visible) {
    onAnnotationPreviewVisibilityChange?.(Boolean(visible))
  }

  function clearAnnotationPreview() {
    const preview = previewCanvas.value
    if (preview) {
      preview.getContext('2d')?.clearRect(0, 0, preview.width, preview.height)
    }
    setAnnotationPreviewVisible(false)
  }

  function cleanupCanvasResize() {
    if (canvasResizeHandler) windowTarget?.removeEventListener?.('resize', canvasResizeHandler)
    canvasResizeHandler = null
    if (canvasResizeFrame) {
      windowTarget?.cancelAnimationFrame?.(canvasResizeFrame)
      canvasResizeFrame = 0
    }
  }

  function getVideoDisplayRect() {
    const container = videoContainer?.value
    if (!container) return null
    const rect = container.getBoundingClientRect()
    if (!rect.width || !rect.height) return null
    const videoWidth = Number(videoEl?.value?.videoWidth) || 0
    const videoHeight = Number(videoEl?.value?.videoHeight) || 0
    if (!videoWidth || !videoHeight) return rect

    const videoAspect = videoWidth / videoHeight
    const containerAspect = rect.width / rect.height
    if (videoAspect >= containerAspect) {
      return { width: rect.width, height: rect.width / videoAspect }
    }
    return { width: rect.height * videoAspect, height: rect.height }
  }

  function getImageDisplayRect() {
    const stage = imageStage?.value
    if (!stage) return null
    const width = Number(stage.offsetWidth || stage.clientWidth || 0)
    const height = Number(stage.offsetHeight || stage.clientHeight || 0)
    return width && height ? { width, height } : null
  }

  function getOverlayRect() {
    let rect = null
    if (readReactiveValue(isViewingVideo)) {
      rect = getVideoDisplayRect()
    } else if (readReactiveValue(isViewingImage)) {
      rect = getImageDisplayRect()
    } else if (readReactiveValue(isViewingPdf)) {
      rect = documentTarget?.querySelector?.('.viewer-pdf')?.getBoundingClientRect() || null
    }

    if (!rect?.width || !rect?.height) {
      rect = videoContainer?.value?.getBoundingClientRect() || null
    }
    return rect?.width && rect?.height ? rect : null
  }

  function syncCanvasSize(canvas, rect, { preserve = true } = {}) {
    if (!canvas || !rect) return
    const width = Math.max(1, Math.round(rect.width))
    const height = Math.max(1, Math.round(rect.height))
    const needsResize = canvas.width !== width || canvas.height !== height
    let snapshot = null

    if (preserve && needsResize && canvas.width && canvas.height) {
      snapshot = documentTarget?.createElement?.('canvas') || null
      if (snapshot) {
        snapshot.width = canvas.width
        snapshot.height = canvas.height
        snapshot.getContext('2d')?.drawImage(canvas, 0, 0)
      }
    }

    if (needsResize) {
      canvas.width = width
      canvas.height = height
    }

    canvas.style.width = `${rect.width}px`
    canvas.style.height = `${rect.height}px`

    if (snapshot) {
      canvas.getContext('2d')?.drawImage(snapshot, 0, 0, width, height)
    }
  }

  function updateOverlayCanvasSizes() {
    if (!annotationCanvas.value && !previewCanvas.value) return
    const rect = getOverlayRect()
    if (!rect) return
    syncCanvasSize(annotationCanvas.value, rect, { preserve: Boolean(getDrawingBounds()) })
    syncCanvasSize(previewCanvas.value, rect)
  }

  function scheduleOverlayCanvasResize() {
    if (canvasResizeFrame) return
    const requestFrame = windowTarget?.requestAnimationFrame?.bind(windowTarget)
    if (!requestFrame) {
      updateOverlayCanvasSizes()
      return
    }
    canvasResizeFrame = requestFrame(() => {
      canvasResizeFrame = 0
      updateOverlayCanvasSizes()
    })
  }

  function setupAnnotationCanvas() {
    const canvas = annotationCanvas.value
    if (!canvas) return

    cleanupCanvasResize()
    if (!readReactiveValue(isViewingPdf)) {
      updateOverlayCanvasSizes()
      canvasResizeHandler = scheduleOverlayCanvasResize
      windowTarget?.addEventListener?.('resize', canvasResizeHandler)
    }
    setDrawingContext(canvas.getContext('2d'))
  }

  function setAnnotationCanvasRef(canvas) {
    annotationCanvas.value = canvas || null
  }

  function setPreviewCanvasRef(canvas) {
    previewCanvas.value = canvas || null
  }

  function activateAnnotationCanvas(canvas, target = null) {
    annotationCanvas.value = canvas || null
    pdfAnnotationTarget.value = target || null
    if (canvas) setupAnnotationCanvas()
  }

  function handlePdfLoaded(info = {}) {
    if (!videoInfo) return
    videoInfo.value = {
      ...videoInfo.value,
      extension: 'pdf',
      pages: info.pageCount || info.pages || videoInfo.value?.pages || null,
    }
  }

  function handlePdfAnnotationTargetChange(target) {
    pdfAnnotationTarget.value = target || null
  }

  function requestPdfFocus(comment) {
    pdfFocusRequest.value = {
      id: comment?.id || null,
      annotationData: comment?.annotation_data || null,
      annotationTarget: comment?.annotation_target || null,
      requestedAt: now(),
    }
  }

  function resetPdfAnnotationState() {
    pdfAnnotationTarget.value = null
    pdfFocusRequest.value = null
  }

  function clearPendingAnnotationDraft() {
    pendingAnnotation.value = null
    pendingAnnotationTimestamp.value = null
    pendingAnnotationTarget.value = null
  }

  function getPendingAnnotationTimestampValue() {
    if (readReactiveValue(isViewingImage) || readReactiveValue(isViewingPdf)) return 0
    const videoTime = Number(videoEl?.value?.currentTime)
    if (Number.isFinite(videoTime)) return videoTime
    const fallbackTime = Number(readReactiveValue(currentTime))
    return Number.isFinite(fallbackTime) ? fallbackTime : 0
  }

  function commitCurrentDrawingToPendingAnnotation(drawingBounds = getDrawingBounds()) {
    const canvas = annotationCanvas.value
    if (!canvas || !drawingBounds) return false

    pendingAnnotation.value = canvas.toDataURL('image/png')
    pendingAnnotationTimestamp.value = getPendingAnnotationTimestampValue()
    pendingAnnotationTarget.value = readReactiveValue(isViewingPdf)
      ? buildPdfAnnotationTarget({
          page: pdfAnnotationTarget.value?.page || 1,
          rect: drawingBounds,
        })
      : null
    return true
  }

  const {
    setDrawingContext,
    getDrawingBounds,
    startPointerDrawing,
    movePointerDrawing,
    finishPointerDrawing,
    resetDrawingInput,
    clearCanvasPixels,
    consumeViewerClickSuppression,
  } = useAnnotationDrawing({
    annotationCanvas,
    isDrawingMode,
    drawingColor,
    isDrawing,
    onDrawingFinished: commitCurrentDrawingToPendingAnnotation,
    now,
  })

  function clearCanvas() {
    resetDrawingInput()
    clearCanvasPixels()
    clearPendingAnnotationDraft()
  }

  function cancelDrawing() {
    isDrawingMode.value = false
    clearCanvas()
    cleanupCanvasResize()
  }

  function startAnnotationForComment() {
    if (videoEl?.value && readReactiveValue(isPlaying)) videoEl.value.pause()
    setAnnotationPreviewVisible(false)
    clearPendingAnnotationDraft()
    isDrawingMode.value = true
    schedule(() => {
      setupAnnotationCanvas()
      clearCanvas()
    }, 50)
  }

  function clearPendingAnnotation(options = {}) {
    clearCanvas()
    if (options.exitDrawingMode) {
      isDrawingMode.value = false
      cleanupCanvasResize()
    }
  }

  if (getCurrentScope()) onScopeDispose(cleanupCanvasResize)

  return {
    annotationCanvas,
    previewCanvas,
    isDrawingMode,
    drawingColor,
    drawingColors: VIEWER_ANNOTATION_COLORS,
    pendingAnnotation,
    pendingAnnotationTimestamp,
    pendingAnnotationTarget,
    pdfFocusRequest,
    setAnnotationCanvasRef,
    setPreviewCanvasRef,
    setupAnnotationCanvas,
    activateAnnotationCanvas,
    cleanupCanvasResize,
    clearAnnotationPreview,
    handlePdfLoaded,
    handlePdfAnnotationTargetChange,
    requestPdfFocus,
    resetPdfAnnotationState,
    clearCanvas,
    cancelDrawing,
    startAnnotationForComment,
    clearPendingAnnotation,
    startPointerDrawing,
    movePointerDrawing,
    finishPointerDrawing,
    consumeViewerClickSuppression,
  }
}
