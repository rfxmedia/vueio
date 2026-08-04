import { computed, onBeforeUnmount, ref, watch } from 'vue'
import Hls from 'hls.js'

const MENU_QUALITY_MIN_HEIGHT = 360
const PREFERRED_START_QUALITY_HEIGHT = 1080

export function useViewerStreamEngine(ctx) {
  let hls = null
  let attachedManifestUrl = ''
  let nativeManifestRequestId = 0
  let nativeQualitySwitchRequestId = 0

  const nativeManifestCache = new Map()
  const availableQualityOptions = ref([])
  const selectedQuality = ref('')

  const qualityOptions = computed(() => (
    availableQualityOptions.value
      .filter((option) => Number(option?.height || 0) >= MENU_QUALITY_MIN_HEIGHT)
      .sort((a, b) => b.height - a.height)
  ))
  const selectedQualityLabel = computed(() => (
    qualityOptions.value.find((option) => option.value === selectedQuality.value)?.label
    || qualityOptions.value[0]?.label
    || ''
  ))
  const scrubPreviewSourceUrl = computed(() => {
    const candidates = availableQualityOptions.value
      .filter((option) => option?.sourceUrl)
      .sort((a, b) => a.height - b.height)
    const lowRung = candidates.find((option) => option.height <= 240) || candidates[0]
    return lowRung?.sourceUrl || ''
  })
  function clearVideoElement(video) {
    if (!video) return
    try { video.pause() } catch {}
    try {
      video.removeAttribute('src')
      video.load()
    } catch {}
  }

  function resolveSourceUrl(rawUrl, manifestUrl) {
    if (!rawUrl) return ''
    try {
      return new URL(rawUrl, manifestUrl || attachedManifestUrl || window.location.href).toString()
    } catch {
      return String(rawUrl)
    }
  }

  function normalizeQualityOptions(entries = []) {
    const dedupedByHeight = new Map()
    entries.forEach((entry) => {
      const height = Number(entry?.height || 0)
      if (!height || dedupedByHeight.has(height)) return
      dedupedByHeight.set(height, {
        value: String(height),
        label: `${height}p`,
        width: Number(entry?.width || 0),
        height,
        index: Number.isInteger(entry?.index) ? entry.index : null,
        sourceUrl: entry?.sourceUrl || '',
      })
    })
    return [...dedupedByHeight.values()].sort((a, b) => b.height - a.height)
  }

  function getDefaultQualityOption(options = availableQualityOptions.value) {
    const highestMenuOption = [...options]
      .filter((option) => Number(option?.height || 0) >= MENU_QUALITY_MIN_HEIGHT)
      .sort((a, b) => b.height - a.height)[0]
    const preferredOption = [...options]
      .filter((option) => (
        Number(option?.height || 0) >= MENU_QUALITY_MIN_HEIGHT
        && Number(option?.height || 0) <= PREFERRED_START_QUALITY_HEIGHT
      ))
      .sort((a, b) => b.height - a.height)[0]
    return preferredOption
      || highestMenuOption
      || [...options].sort((a, b) => b.height - a.height)[0]
      || null
  }

  function setAvailableQualityOptions(options = []) {
    availableQualityOptions.value = normalizeQualityOptions(options)
    if (!getSelectedQualityOption(selectedQuality.value)) {
      selectedQuality.value = getDefaultQualityOption()?.value || ''
    }
  }

  function resetQualityState() {
    availableQualityOptions.value = []
    selectedQuality.value = ''
  }

  function cacheNativeManifestOptions(manifestUrl, options = []) {
    if (!manifestUrl || !options.length) return
    nativeManifestCache.set(manifestUrl, options.map((option) => ({ ...option })))
  }

  function applyCachedNativeManifestOptions(manifestUrl) {
    const cachedOptions = nativeManifestCache.get(manifestUrl)
    if (!cachedOptions?.length) return false
    setAvailableQualityOptions(cachedOptions)
    return true
  }

  function parseNativeManifestOptions(manifestText, manifestUrl) {
    const entries = []
    const lines = String(manifestText || '')
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index]
      if (!line.startsWith('#EXT-X-STREAM-INF:')) continue
      const nextLine = lines[index + 1]
      if (!nextLine || nextLine.startsWith('#')) continue

      const resolutionMatch = line.match(/RESOLUTION=(\d+)x(\d+)/i)
      const width = Number(resolutionMatch?.[1] || 0)
      const height = Number(resolutionMatch?.[2] || 0)
      if (!height) continue

      entries.push({
        width,
        height,
        sourceUrl: resolveSourceUrl(nextLine, manifestUrl),
      })
    }

    return normalizeQualityOptions(entries)
  }

  function getSelectedQualityOption(value) {
    return availableQualityOptions.value.find((option) => option.value === value) || null
  }

  async function loadNativeManifestQualityOptions(manifestUrl) {
    const requestId = ++nativeManifestRequestId
    try {
      const response = await fetch(manifestUrl, { credentials: 'same-origin' })
      if (!response.ok || requestId !== nativeManifestRequestId) return

      const manifestText = await response.text()
      if (requestId !== nativeManifestRequestId) return

      const options = parseNativeManifestOptions(manifestText, manifestUrl)
      if (!options.length) {
        applyCachedNativeManifestOptions(manifestUrl)
        return
      }

      cacheNativeManifestOptions(manifestUrl, options)
      setAvailableQualityOptions(options)
      if (requestId === nativeManifestRequestId && attachedManifestUrl === manifestUrl && ctx.videoEl.value) {
        switchNativeQuality(selectedQuality.value)
      }
    } catch {
      if (requestId !== nativeManifestRequestId) return
      applyCachedNativeManifestOptions(manifestUrl)
    }
  }

  function destroyEngine({ resetElement = true } = {}) {
    const video = ctx.videoEl.value
    if (hls) {
      try { hls.destroy() } catch {}
      hls = null
    }
    attachedManifestUrl = ''
    nativeManifestRequestId += 1
    nativeQualitySwitchRequestId += 1
    resetQualityState()
    if (resetElement) clearVideoElement(video)
  }

  function shouldAttachStream() {
    return !!ctx.videoEl.value
      && !!ctx.videoManifestUrl.value
      && !!ctx.isViewingVideo.value
      && !ctx.mediaUnavailable?.value
      && !ctx.streamPreparing.value
  }

  function switchNativeQuality(value) {
    const video = ctx.videoEl.value
    if (!video || !attachedManifestUrl) return

    const targetOption = getSelectedQualityOption(value) || getDefaultQualityOption()
    const targetUrl = targetOption?.sourceUrl || attachedManifestUrl
    if (!targetUrl || video.getAttribute('src') === targetUrl) return
    selectedQuality.value = targetOption?.value || value || ''

    const resumeTime = Number(video.currentTime || 0)
    const shouldResume = !video.paused && !video.ended
    const requestId = ++nativeQualitySwitchRequestId
    ctx.suppressViewerAutoplay.value = true

    const cleanupNativeSwitchListeners = () => {
      video.removeEventListener('seeked', finalizeQualitySwitch)
      video.removeEventListener('canplay', handleCanPlayFallback)
    }
    const finalizeQualitySwitch = () => {
      cleanupNativeSwitchListeners()
      if (requestId !== nativeQualitySwitchRequestId) return
      if (shouldResume) video.play().catch(() => {})
      else video.pause()
    }
    const handleCanPlayFallback = () => {
      if (resumeTime > 0.05) return
      finalizeQualitySwitch()
    }
    const restorePlaybackPosition = () => {
      if (requestId !== nativeQualitySwitchRequestId) return
      try {
        if (resumeTime > 0.05) {
          video.currentTime = resumeTime
          return
        }
      } catch {
        finalizeQualitySwitch()
        return
      }
      finalizeQualitySwitch()
    }

    video.addEventListener('loadedmetadata', restorePlaybackPosition, { once: true })
    video.addEventListener('seeked', finalizeQualitySwitch, { once: true })
    video.addEventListener('canplay', handleCanPlayFallback, { once: true })
    try { video.pause() } catch {}
    video.src = targetUrl
    video.load()
  }

  function switchHlsQuality(value) {
    if (!hls) return
    const targetOption = getSelectedQualityOption(value) || getDefaultQualityOption()
    if (!targetOption || targetOption.index == null) return
    selectedQuality.value = targetOption.value
    try { hls.startLevel = targetOption.index } catch {}
    try { hls.currentLevel = targetOption.index } catch {}
    hls.nextLevel = targetOption.index
    hls.loadLevel = targetOption.index
  }

  function setInitialHlsQuality(options = availableQualityOptions.value) {
    if (!hls) return
    const targetOption = getDefaultQualityOption(options)
    if (!targetOption || targetOption.index == null) return
    selectedQuality.value = targetOption.value
    try { hls.startLevel = targetOption.index } catch {}
  }

  function applyQualitySelection(value) {
    if (hls) {
      switchHlsQuality(value)
      return
    }
    switchNativeQuality(value)
  }

  function attachNativeHls(video, manifestUrl) {
    if (attachedManifestUrl === manifestUrl && video.getAttribute('src')) return
    destroyEngine({ resetElement: true })
    attachedManifestUrl = manifestUrl
    if (applyCachedNativeManifestOptions(manifestUrl)) {
      switchNativeQuality(selectedQuality.value)
      return
    }
    video.src = manifestUrl
    video.load()
    void loadNativeManifestQualityOptions(manifestUrl)
  }

  function attachHlsJs(video, manifestUrl) {
    if (attachedManifestUrl === manifestUrl && hls) return
    destroyEngine({ resetElement: true })
    attachedManifestUrl = manifestUrl

    hls = new Hls({
      enableWorker: true,
      lowLatencyMode: false,
      preferManagedMediaSource: false,
      backBufferLength: 90,
      autoStartLoad: false,
      startFragPrefetch: true,
    })
    hls.on(Hls.Events.MANIFEST_PARSED, (_event, data) => {
      const levelEntries = (data?.levels || hls?.levels || []).map((level, index) => ({
        width: Number(level?.width || 0),
        height: Number(level?.height || 0),
        index,
        sourceUrl: resolveSourceUrl(Array.isArray(level?.url) ? level.url[0] : level?.url, manifestUrl),
      }))
      setAvailableQualityOptions(levelEntries)
      setInitialHlsQuality(levelEntries)
      try { hls?.startLoad(0) } catch {}
    })
    hls.on(Hls.Events.ERROR, (_event, data) => {
      if (!data?.fatal) return
      ctx.handleStreamError?.(data)
      destroyEngine()
    })
    hls.attachMedia(video)
    hls.on(Hls.Events.MEDIA_ATTACHED, () => { hls?.loadSource(manifestUrl) })
  }

  function syncStreamAttachment() {
    const video = ctx.videoEl.value
    const manifestUrl = ctx.videoManifestUrl.value
    if (!shouldAttachStream() || !video || !manifestUrl) {
      destroyEngine()
      return
    }
    if (Hls.isSupported()) {
      attachHlsJs(video, manifestUrl)
      return
    }
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      attachNativeHls(video, manifestUrl)
      return
    }
    ctx.handleStreamError?.(new Error('HLS playback is not supported in this browser'))
    destroyEngine()
  }

  watch(
    [
      () => ctx.videoEl.value,
      () => ctx.videoManifestUrl.value,
      () => ctx.streamPreparing.value,
      () => ctx.isViewingVideo.value,
      () => ctx.mediaUnavailable?.value,
    ],
    syncStreamAttachment,
    { immediate: true },
  )

  onBeforeUnmount(() => { destroyEngine() })

  return {
    destroyStreamEngine: destroyEngine,
    qualityOptions,
    selectedQuality,
    selectedQualityLabel,
    scrubPreviewSourceUrl,
    setStreamQuality: applyQualitySelection,
  }
}
