import { ref } from 'vue'

const DEFAULT_CLICK_SUPPRESSION_MS = 250

export function useAnnotationDrawing({
  annotationCanvas,
  isDrawingMode,
  drawingColor,
  isDrawing = ref(false),
  onDrawingFinished,
  now = () => Date.now(),
  clickSuppressionMs = DEFAULT_CLICK_SUPPRESSION_MS,
}) {
  let drawingContext = null
  let activePointerId = null
  let activePointerTarget = null
  let lastPoint = null
  let suppressViewerClickUntil = 0

  function setDrawingContext(context) {
    drawingContext = context || null
  }

  function getCanvasPoint(event) {
    const canvas = annotationCanvas.value
    if (!canvas) return null
    const rect = canvas.getBoundingClientRect()
    if (!rect.width || !rect.height) return null
    return {
      x: (event.clientX - rect.left) * (canvas.width / rect.width),
      y: (event.clientY - rect.top) * (canvas.height / rect.height),
    }
  }

  function isActivePointer(event) {
    return activePointerId === null || event.pointerId === activePointerId
  }

  function capturePointer(event) {
    activePointerId = event.pointerId
    activePointerTarget = event.currentTarget || null
    try {
      activePointerTarget?.setPointerCapture?.(activePointerId)
    } catch {
      // Pointer capture is optional (and unavailable on some virtual canvases).
    }
  }

  function releasePointer() {
    try {
      if (activePointerTarget?.hasPointerCapture?.(activePointerId)) {
        activePointerTarget.releasePointerCapture(activePointerId)
      }
    } catch {
      // The browser may have already released capture on pointer cancellation.
    }
    activePointerId = null
    activePointerTarget = null
  }

  function startPointerDrawing(event) {
    if (!isDrawingMode.value || !drawingContext || event?.isPrimary === false || isDrawing.value) return false
    const point = getCanvasPoint(event)
    if (!point) return false

    event.preventDefault?.()
    isDrawing.value = true
    lastPoint = point
    capturePointer(event)
    return true
  }

  function movePointerDrawing(event) {
    if (!isDrawing.value || !isDrawingMode.value || !drawingContext || !isActivePointer(event)) return false
    const point = getCanvasPoint(event)
    if (!point || !lastPoint) return false

    event.preventDefault?.()
    drawingContext.beginPath()
    drawingContext.strokeStyle = drawingColor.value
    drawingContext.lineWidth = 4
    drawingContext.lineCap = 'round'
    drawingContext.lineJoin = 'round'
    drawingContext.moveTo(lastPoint.x, lastPoint.y)
    drawingContext.lineTo(point.x, point.y)
    drawingContext.stroke()
    lastPoint = point
    return true
  }

  function finishPointerDrawing(event) {
    if (!isDrawing.value || !isActivePointer(event)) return false

    event?.preventDefault?.()
    const wasDrawing = isDrawing.value
    isDrawing.value = false
    lastPoint = null
    releasePointer()

    if (!wasDrawing || !isDrawingMode.value) return false
    onDrawingFinished?.()
    suppressViewerClickUntil = now() + clickSuppressionMs
    return true
  }

  function resetDrawingInput() {
    isDrawing.value = false
    lastPoint = null
    releasePointer()
  }

  function clearCanvasPixels() {
    const canvas = annotationCanvas.value
    if (!drawingContext || !canvas) return false
    drawingContext.clearRect(0, 0, canvas.width, canvas.height)
    return true
  }

  function consumeViewerClickSuppression() {
    if (now() >= suppressViewerClickUntil) return false
    suppressViewerClickUntil = 0
    return true
  }

  return {
    isDrawing,
    setDrawingContext,
    startPointerDrawing,
    movePointerDrawing,
    finishPointerDrawing,
    resetDrawingInput,
    clearCanvasPixels,
    consumeViewerClickSuppression,
  }
}
