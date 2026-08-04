import { computed, ref } from 'vue'

const NATIVE_LOOP_MAX_SECONDS = 2
const NATIVE_LOOP_MAX_FRAMES = 60

function playSilently(video) {
  const promise = video?.play?.()
  if (promise && typeof promise.catch === 'function') promise.catch(() => {})
}

export function useViewerTransport({
  videoEl,
  videoInfo,
  suppressViewerAutoplay,
  viewerAutoplayPending,
  isVideoActive = () => true,
  isSeekBlocked = () => false,
  onPlayingTimeUpdate,
  onLoadedMedia,
  onPlaybackStarted,
  getFullscreenTarget = () => document.querySelector('.player-main'),
}) {
  const currentTime = ref(0)
  const duration = ref(0)
  const isPlaying = ref(false)
  const loopEnabled = ref(true)
  const lastPausedTime = ref(null)
  const playerMuted = ref(true)
  const playerVolume = ref(0.8)
  const lastNonZeroVolume = ref(0.8)
  const activeTimelinePointerId = ref(null)

  const progress = computed(() => (
    duration.value ? (currentTime.value / duration.value) * 100 : 0
  ))
  const isActuallyMuted = computed(() => playerMuted.value || playerVolume.value <= 0.001)
  const volumeIconHref = computed(() => (isActuallyMuted.value ? '#icon-volume-mute' : '#icon-volume'))
  const nativeVideoLoopEnabled = computed(() => {
    if (!loopEnabled.value || !isVideoActive()) return false
    const durationSeconds = Number(duration.value || videoInfo.value?.duration || videoEl.value?.duration || 0)
    const frameCount = Number(videoInfo.value?.frames || 0)
    if (frameCount > 0 && frameCount <= NATIVE_LOOP_MAX_FRAMES) return true
    return durationSeconds > 0 && durationSeconds <= NATIVE_LOOP_MAX_SECONDS
  })

  let progressAnimationId = null
  let controlledSeekRequestId = 0
  let timelinePointerRect = null
  let timelinePendingSeekTime = null
  let timelineShouldResume = false

  function resetForMediaOpen() {
    playerMuted.value = true
    loopEnabled.value = true
    lastPausedTime.value = null
  }

  function resetPlaybackState() {
    stopSmoothProgress()
    currentTime.value = 0
    duration.value = 0
    isPlaying.value = false
    lastPausedTime.value = null
    clearTimelinePointerState()
  }

  function applyPlayerAudioState() {
    const video = videoEl.value
    if (!video) return
    try {
      video.muted = !!playerMuted.value || playerVolume.value <= 0.001
      video.volume = Math.max(0, Math.min(1, Number(playerVolume.value) || 0))
    } catch {
      // iOS Safari can restrict programmatic volume changes; muted still applies when supported.
    }
  }

  function toggleMute() {
    if (isActuallyMuted.value) {
      playerMuted.value = false
      if (playerVolume.value <= 0.001) {
        playerVolume.value = Math.max(0.05, Math.min(1, lastNonZeroVolume.value || 0.8))
      }
    } else {
      playerMuted.value = true
    }
    applyPlayerAudioState()
  }

  function onVolumeSliderInput(event) {
    const parsedVolume = Number.parseFloat(event?.target?.value)
    playerVolume.value = Number.isFinite(parsedVolume)
      ? Math.max(0, Math.min(1, parsedVolume))
      : 0
    if (playerVolume.value <= 0.001) {
      playerMuted.value = true
    } else {
      lastNonZeroVolume.value = playerVolume.value
      playerMuted.value = false
    }
    applyPlayerAudioState()
  }

  function togglePlay() {
    const video = videoEl.value
    if (!video) return
    const shouldPlay = video.paused || video.ended || !isPlaying.value
    if (shouldPlay) {
      restorePausedTimeIfNeeded()
      playSilently(video)
    } else {
      video.pause()
    }
  }

  function updateProgressSmooth() {
    if (videoEl.value && isPlaying.value) {
      currentTime.value = videoEl.value.currentTime
      progressAnimationId = requestAnimationFrame(updateProgressSmooth)
    }
  }

  function startSmoothProgress() {
    if (progressAnimationId) cancelAnimationFrame(progressAnimationId)
    progressAnimationId = requestAnimationFrame(updateProgressSmooth)
  }

  function stopSmoothProgress() {
    if (!progressAnimationId) return
    cancelAnimationFrame(progressAnimationId)
    progressAnimationId = null
  }

  function rememberPausedTime(time) {
    if (!Number.isFinite(time)) return
    lastPausedTime.value = time
  }

  function restorePausedTimeIfNeeded() {
    const video = videoEl.value
    if (!video || lastPausedTime.value === null) return
    const target = clampSeekTime(Number(lastPausedTime.value))
    if (Math.abs((video.currentTime || 0) - target) <= 0.1) return
    try { video.currentTime = target } catch { /* Seek failed */ }
  }

  function onTimeUpdate() {
    if (!videoEl.value) return
    currentTime.value = videoEl.value.currentTime
    if (isPlaying.value) onPlayingTimeUpdate?.(currentTime.value)
  }

  function onLoaded() {
    if (!videoEl.value) return
    duration.value = videoEl.value.duration
    applyPlayerAudioState()
    onLoadedMedia?.()
  }

  function onVideoCanPlay() {
    const video = videoEl.value
    if (!video) return
    applyPlayerAudioState()
    if (viewerAutoplayPending.value && !suppressViewerAutoplay.value && video.paused) {
      playSilently(video)
    }
    viewerAutoplayPending.value = false
    suppressViewerAutoplay.value = false
  }

  function onVideoEnded() {
    if (loopEnabled.value && videoEl.value) {
      if (nativeVideoLoopEnabled.value) {
        currentTime.value = 0
        playCurrentVideo()
        return
      }
      seekVideo(0, { resume: true, disableLoop: false })
      return
    }
    isPlaying.value = false
    stopSmoothProgress()
  }

  function onVideoPlay() {
    isPlaying.value = true
    onPlaybackStarted?.()
    startSmoothProgress()
  }

  function onVideoPause() {
    isPlaying.value = false
    stopSmoothProgress()
    const video = videoEl.value
    if (video) {
      const durationValue = Number(video.duration || 0)
      const nearEnd = Number.isFinite(durationValue) && durationValue > 0
        ? video.currentTime >= Math.max(0, durationValue - 0.05)
        : false
      if (loopEnabled.value && (video.ended || nearEnd)) {
        lastPausedTime.value = null
      } else {
        const pausedAt = Number.isFinite(video.currentTime) && video.currentTime > 0
          ? video.currentTime
          : currentTime.value
        rememberPausedTime(pausedAt)
      }
    }
    requestAnimationFrame(() => applyPlayerAudioState())
  }

  function onVideoSeeked() {
    if (videoEl.value && !isPlaying.value) rememberPausedTime(videoEl.value.currentTime)
  }

  function toggleLoop() {
    loopEnabled.value = !loopEnabled.value
  }

  function disableLoopForUserSeek() {
    if (loopEnabled.value) loopEnabled.value = false
  }

  function clampSeekTime(time) {
    const video = videoEl.value
    if (!video || !Number.isFinite(time)) return 0

    let maximum = Number(video.duration)
    if (!Number.isFinite(maximum) || maximum <= 0) maximum = Number(duration.value)
    if (!Number.isFinite(maximum) || maximum <= 0) maximum = Number(videoInfo.value?.duration)
    if (!Number.isFinite(maximum) || maximum <= 0) {
      try {
        if (video.seekable?.length) maximum = Number(video.seekable.end(video.seekable.length - 1))
      } catch { /* Seekable range unavailable */ }
    }
    if (!Number.isFinite(maximum) || maximum <= 0) return 0

    const baseEpsilon = Math.min(0.05, Math.max(0.001, (1 / (videoInfo.value?.fps || 24)) / 2))
    const epsilon = Math.min(baseEpsilon, maximum / 10)
    const safeMaximum = maximum > epsilon ? maximum - epsilon : maximum
    return Math.max(0, Math.min(safeMaximum, time))
  }

  function playCurrentVideo() {
    if (!videoEl.value) return
    playSilently(videoEl.value)
    isPlaying.value = true
    startSmoothProgress()
  }

  function seekVideo(time, options = {}) {
    const video = videoEl.value
    if (!video) return
    if (options.disableLoop !== false) disableLoopForUserSeek()

    const target = clampSeekTime(time)
    const shouldResume = options.resume ?? (!video.paused && !video.ended)
    currentTime.value = target

    const requestId = ++controlledSeekRequestId
    const cleanup = () => {
      video.removeEventListener('canplay', finalize)
      video.removeEventListener('seeked', finalize)
    }
    const finalize = () => {
      cleanup()
      if (requestId !== controlledSeekRequestId) return
      playCurrentVideo()
    }

    if (shouldResume) {
      video.addEventListener('seeked', finalize, { once: true })
      video.addEventListener('canplay', finalize, { once: true })
    }
    try {
      video.currentTime = target
      if (shouldResume) {
        playSilently(video)
        if (video.readyState >= 3) window.setTimeout(finalize, 0)
      }
    } catch {
      cleanup()
      if (shouldResume) playCurrentVideo()
    }
  }

  function seekTo(time) {
    if (videoEl.value) seekVideo(time)
  }

  function clampTimelinePercent(clientX, rect) {
    if (!rect?.width) return 0
    return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
  }

  function updateTimelineFromPointer(event, timelineEl) {
    if (!timelineEl || activeTimelinePointerId.value === null) return
    if (event.pointerId !== activeTimelinePointerId.value) return
    const time = clampSeekTime(clampTimelinePercent(event.clientX, timelinePointerRect) * duration.value)
    disableLoopForUserSeek()
    currentTime.value = time
    timelinePendingSeekTime = time
  }

  function startTimelinePointer(event, timelineEl) {
    if (!timelineEl || !videoEl.value || isSeekBlocked()) return
    if (event.isPrimary === false || activeTimelinePointerId.value !== null) return
    activeTimelinePointerId.value = event.pointerId
    timelineShouldResume = !videoEl.value.paused && !videoEl.value.ended
    timelinePointerRect = timelineEl.getBoundingClientRect()
    try { timelineEl.setPointerCapture?.(event.pointerId) } catch { /* Pointer capture unavailable */ }
    updateTimelineFromPointer(event, timelineEl)
  }

  function moveTimelinePointer(event, timelineEl) {
    if (!videoEl.value) return
    updateTimelineFromPointer(event, timelineEl)
  }

  function finishTimelinePointer(event, timelineEl) {
    if (activeTimelinePointerId.value === null || event.pointerId !== activeTimelinePointerId.value) return
    if (timelinePendingSeekTime !== null) {
      seekVideo(timelinePendingSeekTime, { resume: timelineShouldResume })
    }
    try {
      if (timelineEl?.hasPointerCapture?.(event.pointerId)) timelineEl.releasePointerCapture(event.pointerId)
    } catch { /* Pointer capture already released */ }
    clearTimelinePointerState()
  }

  function clearTimelinePointerState() {
    activeTimelinePointerId.value = null
    timelinePointerRect = null
    timelinePendingSeekTime = null
    timelineShouldResume = false
  }

  function toggleFullscreen() {
    const target = getFullscreenTarget()
    if (document.fullscreenElement) {
      document.exitFullscreen()
    } else if (target?.requestFullscreen) {
      target.requestFullscreen()
    } else if (target?.webkitRequestFullscreen) {
      target.webkitRequestFullscreen()
    } else if (videoEl.value?.webkitEnterFullscreen) {
      videoEl.value.webkitEnterFullscreen()
    }
  }

  return {
    currentTime,
    duration,
    isPlaying,
    loopEnabled,
    lastPausedTime,
    progress,
    playerMuted,
    playerVolume,
    isActuallyMuted,
    volumeIconHref,
    nativeVideoLoopEnabled,
    activeTimelinePointerId,
    resetForMediaOpen,
    resetPlaybackState,
    applyPlayerAudioState,
    toggleMute,
    onVolumeSliderInput,
    togglePlay,
    startSmoothProgress,
    stopSmoothProgress,
    rememberPausedTime,
    restorePausedTimeIfNeeded,
    onTimeUpdate,
    onLoaded,
    onVideoCanPlay,
    onVideoEnded,
    onVideoPlay,
    onVideoPause,
    onVideoSeeked,
    toggleLoop,
    disableLoopForUserSeek,
    clampSeekTime,
    seekVideo,
    seekTo,
    startTimelinePointer,
    moveTimelinePointer,
    finishTimelinePointer,
    cancelTimelinePointer: finishTimelinePointer,
    toggleFullscreen,
  }
}
