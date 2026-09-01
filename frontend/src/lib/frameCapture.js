import { getCommentAvatarFill, getCommentInitials } from '../utils/commentDisplay'
import { drawVideoColorPreviewFrame, isVideoColorPreviewActive } from './videoColorPreview'

export function canvasToPngBlob(canvas) {
  return new Promise((resolve, reject) => {
    try {
      canvas.toBlob((blob) => {
        if (blob) {
          resolve(blob)
          return
        }
        reject(new Error('Could not encode current frame'))
      }, 'image/png')
    } catch (error) {
      reject(error)
    }
  })
}

function drawVisibleOverlayCanvas(targetCtx, sourceCanvas, targetWidth, targetHeight) {
  if (!sourceCanvas?.width || !sourceCanvas?.height) return
  targetCtx.drawImage(
    sourceCanvas,
    0,
    0,
    sourceCanvas.width,
    sourceCanvas.height,
    0,
    0,
    targetWidth,
    targetHeight,
  )
}

function drawRoundedRect(ctx, x, y, width, height, radius) {
  const r = Math.max(0, Math.min(radius, width / 2, height / 2))
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.lineTo(x + width - r, y)
  ctx.quadraticCurveTo(x + width, y, x + width, y + r)
  ctx.lineTo(x + width, y + height - r)
  ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height)
  ctx.lineTo(x + r, y + height)
  ctx.quadraticCurveTo(x, y + height, x, y + height - r)
  ctx.lineTo(x, y + r)
  ctx.quadraticCurveTo(x, y, x + r, y)
  ctx.closePath()
}

function truncateCanvasText(ctx, text, maxWidth) {
  const source = String(text || '').trim()
  if (!source || ctx.measureText(source).width <= maxWidth) return source
  let candidate = source
  while (candidate && ctx.measureText(`${candidate}...`).width > maxWidth) {
    candidate = candidate.slice(0, -1).trimEnd()
  }
  return candidate ? `${candidate}...` : '...'
}

function appendCanvasEllipsis(ctx, text, maxWidth) {
  const source = String(text || '').replace(/\s+$/g, '')
  if (!source) return '...'
  return truncateCanvasText(ctx, source, maxWidth)
}

function splitCanvasWord(ctx, word, maxWidth) {
  const chunks = []
  let chunk = ''
  for (const char of Array.from(String(word || ''))) {
    const nextChunk = `${chunk}${char}`
    if (chunk && ctx.measureText(nextChunk).width > maxWidth) {
      chunks.push(chunk)
      chunk = char
    } else {
      chunk = nextChunk
    }
  }
  if (chunk) chunks.push(chunk)
  return chunks
}

function wrapCanvasText(ctx, text, maxWidth, maxLines) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim()
  if (!normalized) return []
  const lines = []
  const pushLine = (line) => {
    if (!line) return false
    if (lines.length >= maxLines) return true
    lines.push(line)
    return lines.length >= maxLines
  }

  let currentLine = ''
  let truncated = false
  for (const word of normalized.split(' ')) {
    const candidate = currentLine ? `${currentLine} ${word}` : word
    if (ctx.measureText(candidate).width <= maxWidth) {
      currentLine = candidate
      continue
    }

    if (currentLine) {
      truncated = pushLine(currentLine)
      currentLine = ''
      if (truncated) break
    }

    if (ctx.measureText(word).width <= maxWidth) {
      currentLine = word
      continue
    }

    for (const chunk of splitCanvasWord(ctx, word, maxWidth)) {
      truncated = pushLine(chunk)
      if (truncated) break
    }
    if (truncated) break
  }

  if (!truncated && currentLine) pushLine(currentLine)
  if (truncated && lines.length) {
    lines[lines.length - 1] = appendCanvasEllipsis(ctx, lines[lines.length - 1], maxWidth)
  }
  return lines
}

function drawFrameCapturePill(ctx, label, x, y, scale) {
  const text = String(label || '').trim()
  if (!text) return 0
  const paddingX = Math.round(8 * scale)
  const height = Math.round(19 * scale)
  const width = Math.ceil(ctx.measureText(text).width) + paddingX * 2
  drawRoundedRect(ctx, x, y, width, height, height / 2)
  ctx.fillStyle = 'rgba(212, 165, 72, 0.18)'
  ctx.fill()
  ctx.strokeStyle = 'rgba(212, 165, 72, 0.34)'
  ctx.lineWidth = Math.max(1, Math.round(scale))
  ctx.stroke()
  ctx.fillStyle = 'rgba(244, 206, 123, 0.96)'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, x + paddingX, y + height / 2)
  return width
}

function drawFrameCaptureComment(ctx, comment, frameWidth, frameHeight) {
  if (!comment) return

  const scale = Math.max(0.78, Math.min(1.65, frameWidth / 1920))
  const margin = Math.round(30 * scale)
  const padding = Math.round(17 * scale)
  const gap = Math.round(12 * scale)
  const avatarSize = Math.round(34 * scale)
  const radius = Math.round(16 * scale)
  const cardWidth = Math.min(
    frameWidth - (margin * 2),
    Math.max(Math.round(340 * scale), Math.min(frameWidth * 0.44, Math.round(650 * scale))),
  )
  const contentWidth = Math.max(80, cardWidth - (padding * 2) - avatarSize - gap)
  const author = String(comment.user_name || 'Comment').trim() || 'Comment'
  const bodyText = String(comment.text || '').trim() || (comment.annotation_data ? 'Drawing annotation' : 'Comment')

  ctx.save()

  const fontFamily = 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
  const authorFontSize = Math.round(14 * scale)
  const metaFontSize = Math.round(11 * scale)
  const bodyFontSize = Math.round(13 * scale)
  const lineHeight = Math.round(20 * scale)
  const headerHeight = Math.round(21 * scale)

  ctx.font = `500 ${bodyFontSize}px ${fontFamily}`
  const lines = wrapCanvasText(ctx, bodyText, contentWidth, 6)
  const bodyHeight = Math.max(lineHeight, lines.length * lineHeight)
  const contentHeight = Math.max(avatarSize, headerHeight + Math.round(8 * scale) + bodyHeight)
  const cardHeight = Math.min(frameHeight - (margin * 2), padding * 2 + contentHeight)
  const x = frameWidth - margin - cardWidth
  const y = frameHeight - margin - cardHeight

  ctx.shadowColor = 'rgba(0, 0, 0, 0.42)'
  ctx.shadowBlur = Math.round(28 * scale)
  ctx.shadowOffsetY = Math.round(10 * scale)
  drawRoundedRect(ctx, x, y, cardWidth, cardHeight, radius)
  ctx.fillStyle = 'rgba(18, 20, 22, 0.9)'
  ctx.fill()
  ctx.shadowColor = 'transparent'
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.14)'
  ctx.lineWidth = Math.max(1, Math.round(scale))
  ctx.stroke()

  const avatarX = x + padding
  const avatarY = y + padding
  const avatarCenterX = avatarX + avatarSize / 2
  const avatarCenterY = avatarY + avatarSize / 2
  ctx.beginPath()
  ctx.arc(avatarCenterX, avatarCenterY, avatarSize / 2, 0, Math.PI * 2)
  ctx.fillStyle = getCommentAvatarFill(author)
  ctx.fill()
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.18)'
  ctx.lineWidth = Math.max(1, Math.round(scale))
  ctx.stroke()
  ctx.font = `700 ${Math.round(12 * scale)}px ${fontFamily}`
  ctx.fillStyle = '#fff'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(getCommentInitials(author), avatarCenterX, avatarCenterY + Math.round(0.5 * scale))

  const textX = avatarX + avatarSize + gap
  const headerY = y + padding
  const timeLabel = String(comment.capture_time_label || '').trim()
  const numberLabel = String(comment.capture_number_label || '').trim()
  ctx.textAlign = 'left'
  const pillFont = `650 ${metaFontSize}px ${fontFamily}`
  ctx.font = pillFont
  const timePillWidth = timeLabel ? Math.ceil(ctx.measureText(timeLabel).width) + Math.round(16 * scale) : 0
  const numberPillWidth = numberLabel ? Math.ceil(ctx.measureText(numberLabel).width) + Math.round(16 * scale) : 0
  const pillGap = Math.round(6 * scale)
  const pillTotalWidth = timePillWidth + numberPillWidth + (timePillWidth && numberPillWidth ? pillGap : 0)
  const authorMaxWidth = Math.max(Math.round(72 * scale), contentWidth - pillTotalWidth - Math.round(10 * scale))
  ctx.font = `700 ${authorFontSize}px ${fontFamily}`
  ctx.fillStyle = 'rgba(255, 255, 255, 0.96)'
  ctx.textBaseline = 'middle'
  const authorText = truncateCanvasText(ctx, author, authorMaxWidth)
  ctx.fillText(authorText, textX, headerY + headerHeight / 2)

  let pillX = textX + Math.min(ctx.measureText(authorText).width + Math.round(8 * scale), authorMaxWidth + Math.round(8 * scale))
  ctx.font = pillFont
  if (timeLabel) {
    pillX += drawFrameCapturePill(ctx, timeLabel, pillX, headerY + Math.round(1 * scale), scale) + pillGap
  }
  if (numberLabel) {
    drawFrameCapturePill(ctx, numberLabel, pillX, headerY + Math.round(1 * scale), scale)
  }

  ctx.font = `500 ${bodyFontSize}px ${fontFamily}`
  ctx.fillStyle = 'rgba(255, 255, 255, 0.92)'
  ctx.textBaseline = 'top'
  const bodyY = headerY + headerHeight + Math.round(8 * scale)
  lines.forEach((line, index) => {
    const nextY = bodyY + (index * lineHeight)
    if (nextY + lineHeight <= y + cardHeight - padding + Math.round(3 * scale)) {
      ctx.fillText(line, textX, nextY)
    }
  })

  ctx.restore()
}

export function renderVideoFrame({
  video,
  annotationCanvas,
  previewCanvas,
  includeAnnotations = false,
  comment = null,
  colorPreviewMode = 'source',
} = {}) {
  if (!video || video.readyState < 2) {
    throw new Error('No video frame is ready yet')
  }

  const width = Math.round(Number(video.videoWidth) || 0)
  const height = Math.round(Number(video.videoHeight) || 0)
  if (!width || !height) {
    throw new Error('No video frame is ready yet')
  }

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d', { alpha: false })
  if (!ctx) {
    throw new Error('Could not prepare current frame')
  }

  if (isVideoColorPreviewActive(colorPreviewMode)) {
    drawVideoColorPreviewFrame(ctx, video, colorPreviewMode, width, height)
  } else {
    ctx.drawImage(video, 0, 0, width, height)
  }
  if (includeAnnotations) {
    drawVisibleOverlayCanvas(ctx, annotationCanvas, width, height)
    drawVisibleOverlayCanvas(ctx, previewCanvas, width, height)
  }
  drawFrameCaptureComment(ctx, comment, width, height)

  return canvas
}
