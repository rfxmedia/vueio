// Geometry and artwork are shared by the live preview and the export request.
export function exportGeometry(info, options) {
  const split = options.mode === 'side-by-side'
  const [sw, sh] = info.source_sizes[Number(options.swapped)]
  const ratios = { '3:4': [3, 4], '1:1': [1, 1], '16:9': [16, 9] }
  const ratio = ratios[options.aspect]
  if (!ratio) {
    const panes = split ? 2 : 1, portrait = sw * panes < sh
    const scale = Math.min(1, (portrait ? 1080 : 1920) / (sw * panes), (portrait ? 1920 : 1080) / sh)
    return { width: Math.max(2, Math.floor(sw * scale / 2) * 2) * panes, height: Math.max(2, Math.floor(sh * scale / 2) * 2), stacked: false }
  }
  const [rw, rh] = ratio, r = rw / rh
  // Compare actual visible image area, not just the output's orientation.
  const area = (w, h) => info.source_sizes.reduce((sum, [w0, h0]) => sum + Math.min(w / w0, h / h0) ** 2 * w0 * h0, 0)
  const stacked = split && area(r, .5) > area(r / 2, 1) * 1.01
  let unit = 2
  if (split && (stacked ? rh : rw) * unit % 4) unit = 4
  const size = Math.min((r < 1 ? 1080 : 1920) / rw, (r < 1 ? 1920 : 1080) / rh)
  const pw = rw * size / (split && !stacked ? 2 : 1), ph = rh * size / (stacked ? 2 : 1)
  const fit = Math.max(...info.source_sizes.map(([w, h]) => Math.min(pw / w, ph / h)))
  const k = Math.max(unit, Math.floor(size * Math.min(1, 1 / fit) / unit) * unit)
  return { width: rw * k, height: rh * k, stacked }
}

export function exportFrameCount(options) {
  return options.freeze_frame != null ? options.freeze_frames : options.end_frame - options.start_frame
}

export function exportTiming(options) {
  const frames = exportFrameCount(options)
  const duration = Math.max(2, Math.min(frames, Math.round(options.wipe_duration * frames)))
  return { start: Math.max(0, Math.min(frames - duration, Math.round(options.wipe_start * frames))), duration }
}

export function paintExport(target, source, info, options, frame, artwork) {
  const { width, height, stacked } = exportGeometry(info, options)
  if (target.width !== width) target.width = width
  if (target.height !== height) target.height = height
  const ctx = target.getContext('2d', { alpha: false })
  if (!ctx) return
  const half = source.videoWidth / 2, sourceHeight = source.videoHeight
  const sideBySide = options.mode === 'side-by-side', paneWidth = width / (sideBySide && !stacked ? 2 : 1), paneHeight = height / (stacked ? 2 : 1)
  const draw = (index, x, y = 0) => {
    const [sw, sh] = info.source_sizes[index]
    // Remove the packed preview's padding before fitting the original aspect ratio.
    const inputScale = Math.min(half / sw, sourceHeight / sh)
    // Wipes fill the height; the canvas clips any excess width symmetrically.
    const outputScale = sideBySide ? Math.min(paneWidth / sw, paneHeight / sh) : paneHeight / sh
    const sx = (index === 0) === info.primary_is_left ? 0 : half
    ctx.fillStyle = '#000'
    ctx.fillRect(x, y, paneWidth, paneHeight)
    ctx.drawImage(source, sx + (half - sw * inputScale) / 2, (sourceHeight - sh * inputScale) / 2,
      sw * inputScale, sh * inputScale, x + (paneWidth - sw * outputScale) / 2,
      y + (paneHeight - sh * outputScale) / 2, sw * outputScale, sh * outputScale)
  }
  const before = Number(options.swapped)
  const timing = exportTiming(options)
  const p = Math.max(0, Math.min(1, (frame - timing.start) / (timing.duration - 1)))
  draw(before, 0)
  if (sideBySide) draw(1 - before, stacked ? 0 : paneWidth, stacked ? paneHeight : 0)
  else {
    ctx.save(); ctx.beginPath(); ctx.rect(0, 0, width * p * p * (3 - 2 * p), height); ctx.clip()
    draw(1 - before, 0); ctx.restore()
  }
  if (artwork) ctx.drawImage(artwork, 0, p >= .5 ? height : 0, width, height, 0, 0, width, height)
}

export function createExportArtwork(info, options, branding, logo, previous = null) {
  if (!branding.labels && !logo) return null
  const { width, height, stacked } = exportGeometry(info, options)
  const canvas = previous || document.createElement('canvas')
  if (canvas.width !== width) canvas.width = width
  if (canvas.height !== height * 2) canvas.height = height * 2
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, width, height * 2)
  const margin = Math.max(4, Math.round(Math.min(width, height) * .04))
  const fontSize = Math.max(10, Math.round(Math.min(width, height) * .036))
  const fontFamily = getComputedStyle(document.documentElement).getPropertyValue('--v-font').trim() || 'sans-serif'
  for (let state = 0; state < 2; state++) {
    ctx.save(); ctx.translate(0, state * height)
    if (logo) {
      const scale = Math.min(width * branding.size / 100 / logo.width, height * .25 / logo.height)
      const w = logo.width * scale, h = logo.height * scale
      ctx.drawImage(logo, branding.corner.endsWith('right') ? width - margin - w : margin,
        branding.corner.startsWith('bottom') ? height - margin - h : margin, w, h)
    }
    if (branding.labels) {
      const labels = options.mode === 'side-by-side' ? [branding.before, branding.after] : [state ? branding.after : branding.before]
      labels.forEach((text, i) => {
        if (!text.trim()) return
        const paneWidth = width / (stacked ? 1 : labels.length), paneHeight = height / (stacked ? labels.length : 1), padding = fontSize * .6
        ctx.font = `600 ${fontSize}px ${fontFamily}`
        const limit = paneWidth - margin * 2 - padding * 2
        while (text.length > 1 && ctx.measureText(text).width > limit) text = text.slice(0, -1)
        const w = Math.min(limit, ctx.measureText(text).width) + padding * 2, h = fontSize * 1.8
        const y = (stacked ? i * paneHeight : 0) + (logo && branding.corner.startsWith('bottom') ? margin : paneHeight - margin - h)
        const x = (stacked ? 0 : i * paneWidth) + margin
        // Neutral video-overlay colors stay readable independently of the app theme.
        ctx.fillStyle = 'rgba(0,0,0,.7)'; ctx.beginPath(); ctx.roundRect(x, y, w, h, fontSize * .3); ctx.fill()
        ctx.fillStyle = '#fff'; ctx.textBaseline = 'middle'; ctx.fillText(text, x + padding, y + h / 2, limit)
      })
    }
    ctx.restore()
  }
  return canvas
}

export function loadLogo(data) {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('This image could not be read. Choose a PNG, JPEG, or WebP file.'))
    image.src = data
  })
}
