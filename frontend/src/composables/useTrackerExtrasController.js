import { computed, reactive } from 'vue'
import api, { buildShareCredentialQuery, getApiErrorMessage } from '../lib/api'
import { uploadWithLink } from '../lib/uploadLinks'
import { copyFilePath, loadNetworkPath } from '../utils/networkPath'
import { notify } from '../utils/toasts'

// Quick names for extras. Anything else can be typed. A reference starts as
// team only; everything else starts visible to clients.
export const EXTRA_TYPES = Object.freeze([
  { name: 'Alpha matte', clientVisible: true },
  { name: 'Holdout matte', clientVisible: true },
  { name: 'Clean plate', clientVisible: true },
  { name: 'Element', clientVisible: true },
  { name: 'Reference', clientVisible: false },
])

export function defaultClientVisibility(name) {
  const type = EXTRA_TYPES.find(item => item.name.toLowerCase() === String(name || '').trim().toLowerCase())
  return type ? type.clientVisible : true
}

// The download name the server will give an extra, shown before it exists.
export function previewExtraFileName(plateName, extraName, sourceName) {
  const extension = /\.[^./\\]+$/.exec(sourceName || '')?.[0] || ''
  const plateStem = String(plateName || '').replace(/\.[^./\\]+$/, '')
  // As the server does: characters file systems refuse become a dash.
  const safe = Array.from(String(extraName || ''), character => (character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127 || '<>:"/\\|?*'.includes(character) ? '-' : character)).join('')
  const name = safe.replace(/-+/g, '-').replace(/\s+/g, ' ').trim().replace(/^[ .-]+|[ .-]+$/g, '') || 'Extra'
  return plateStem ? `${plateStem}_${name}${extension}` : `${name}${extension}`
}

// The files of a drop from the computer. Folders are left out.
export function droppedExtraFiles(dataTransfer) {
  const items = Array.from(dataTransfer?.items || []).filter(item => item.kind === 'file')
  if (!items.length || typeof items[0].webkitGetAsEntry !== 'function') return Array.from(dataTransfer?.files || [])
  return items.filter(item => !item.webkitGetAsEntry()?.isDirectory).map(item => item.getAsFile()).filter(Boolean)
}

// The project path of a file dragged from the sidebar, as the file picker gives it.
function projectItemFilePath(item) {
  return item?.file_path || (item?.is_linked && item?.source_path ? item.source_path : item?.path) || ''
}

let uploadCounter = 0

// A first guess at what a file is, from words in its name.
const TYPE_HINTS = [
  [/holdout|hold[-_ ]?out/i, 'Holdout matte'],
  [/clean|(^|[^a-z])cp([^a-z]|$)/i, 'Clean plate'],
  [/alpha|matte|mask|roto/i, 'Alpha matte'],
  [/element|elem([^a-z]|$)|fx[-_ ]?pass/i, 'Element'],
  [/(^|[^a-z])ref(erence)?([^a-z]|$)/i, 'Reference'],
]

export function guessExtraType(fileName) {
  const stem = String(fileName || '').replace(/\.[^.]+$/, '')
  return TYPE_HINTS.find(([pattern]) => pattern.test(stem))?.[1] || ''
}

function newEntry({ file = null, item = null }) {
  const fileName = file?.name || item?.name || String(item?.file_path || '').split('/').pop() || ''
  const name = guessExtraType(fileName)
  return {
    key: `entry-${++uploadCounter}`,
    file,
    filePath: item?.file_path || null,
    fileName,
    size: file?.size ?? item?.size ?? null,
    name,
    note: '',
    clientVisible: defaultClientVisibility(name),
  }
}

export function useTrackerExtrasController(ctx) {
  // Uploads in progress, shown on the extra that gets the file.
  const extraUploads = reactive({})
  const extraBusy = reactive({})
  // The Add extras dialog. mode 'files' adds files; 'ask' asks for an extra without one.
  const extrasDialog = reactive({ open: false, mode: 'files', shot: null, version: null, entries: [], ask: { name: '', note: '', clientVisible: true } })

  function openAddExtras(shot, { files = [], items = [], mode = 'files' } = {}) {
    extrasDialog.shot = shot
    extrasDialog.version = latestVersion(shot)
    extrasDialog.mode = mode
    extrasDialog.entries = [...files.map(file => newEntry({ file })), ...items.map(item => newEntry({ item }))]
    extrasDialog.ask = { name: '', note: '', clientVisible: true }
    extrasDialog.open = true
  }

  function addDialogFiles(files = [], items = []) {
    extrasDialog.mode = 'files'
    extrasDialog.entries = [...extrasDialog.entries, ...files.map(file => newEntry({ file })), ...items.map(item => newEntry({ item }))]
  }

  function closeExtrasDialog() {
    extrasDialog.open = false
    extrasDialog.entries = []
  }

  const shareMode = () => Boolean(ctx.shareMode.value)
  const projectId = () => ctx.currentProject.value?.id || ''
  const shareId = () => (shareMode() ? ctx.pendingShareId.value : null)
  const canAddExtraFiles = computed(() => !ctx.shareMode.value && Boolean(ctx.canAddVersions.value))
  const canManageExtras = computed(() => canAddExtraFiles.value && !ctx.isRestrictedMember?.value)

  function latestVersion(shot) {
    return shot?.versions?.at(-1) || null
  }

  function versionExtraFiles(version) {
    return Array.isArray(version?.extras) ? version.extras : []
  }

  // Each extra of the shot with this version's file. The team also sees
  // the extras a version still needs; clients only see files.
  function getExtraSlots(shot, version = latestVersion(shot)) {
    const files = versionExtraFiles(version)
    if (shareMode() || !Array.isArray(shot?.extras)) {
      return files.map(file => ({ id: file.extra_id, name: file.name, note: file.note, client_visible: true, file, needed: false }))
    }
    const byExtra = new Map(files.map(file => [file.extra_id, file]))
    return shot.extras.map(extra => ({ ...extra, file: byExtra.get(extra.id) || null, needed: !byExtra.has(extra.id) }))
  }

  function getUploadsFor(shot, version = latestVersion(shot)) {
    return Object.values(extraUploads).filter(upload => upload.shotId === shot?.id && upload.versionId === version?.id)
  }

  // Files this extra has on earlier versions, newest first, one per file.
  function getEarlierExtraFiles(shot, extraId, version = latestVersion(shot)) {
    const versions = shot?.versions || []
    const index = versions.findIndex(item => item.id === version?.id)
    const seen = new Set()
    const result = []
    for (const earlier of versions.slice(0, index < 0 ? versions.length : index).reverse()) {
      const file = versionExtraFiles(earlier).find(item => item.extra_id === extraId)
      if (file && !seen.has(file.media_asset_id)) {
        seen.add(file.media_asset_id)
        result.push({ version: earlier, file })
      }
    }
    return result
  }

  function shotUrl(shot) {
    return `/api/horizons/projects/${encodeURIComponent(projectId())}/shots/${encodeURIComponent(shot.id)}/extras`
  }

  async function run(key, failure, action) {
    if (extraBusy[key]) return null
    extraBusy[key] = true
    try {
      const result = await action()
      await ctx.refreshTracker()
      return result
    } catch (error) {
      notify(`${failure}: ${getApiErrorMessage(error)}`, { tone: 'error' })
      return null
    } finally {
      delete extraBusy[key]
    }
  }

  async function uploadExtraFile(shot, version, { file, extraId = null, name, note = null, clientVisible = true }) {
    const key = `upload-${++uploadCounter}`
    extraUploads[key] = { key, shotId: shot.id, versionId: version.id, extraId, name, fileName: file.name, progress: 0 }
    try {
      const { data: link } = await api.post(
        `/api/horizons/projects/${encodeURIComponent(projectId())}/shots/${encodeURIComponent(shot.id)}/versions/${encodeURIComponent(version.id)}/extras/upload`,
        { filename: file.name, size: file.size, extra_id: extraId, name, note, client_visible: clientVisible },
      )
      await uploadWithLink(link, file, { onProgress: progress => { if (extraUploads[key]) extraUploads[key].progress = progress } })
      await ctx.refreshTracker()
      return true
    } catch (error) {
      notify(`Could not upload ${file.name}: ${getApiErrorMessage(error)}`, { tone: 'error' })
      return false
    } finally {
      delete extraUploads[key]
    }
  }

  // entries: [{ name, note, clientVisible, filePath } | { name, note, clientVisible, file }]
  async function addExtras(shot, entries, version = latestVersion(shot)) {
    if (!version || !entries?.length) return false
    const linked = entries.filter(entry => entry.filePath)
    const uploads = entries.filter(entry => entry.file)
    const done = await run(`add:${shot.id}`, 'Could not add the extra', async () => {
      for (const entry of linked) {
        await api.post(shotUrl(shot), {
          name: entry.name, note: entry.note || null, client_visible: entry.clientVisible !== false,
          version_id: version.id, file_path: entry.filePath,
        })
      }
      return true
    })
    if (linked.length && !done) return false
    const results = await Promise.all(uploads.map(entry => uploadExtraFile(shot, version, {
      file: entry.file, name: entry.name, note: entry.note || null, clientVisible: entry.clientVisible !== false,
    })))
    const added = linked.length + results.filter(Boolean).length
    if (added) notify(added === 1 ? `Added ${entries[0].name}` : `Added ${added} extras`)
    return results.every(Boolean)
  }

  function askForExtra(shot, { name, note = null, clientVisible = true }) {
    return run(`add:${shot.id}`, 'Could not ask for the extra', async () => {
      await api.post(shotUrl(shot), { name, note, client_visible: clientVisible })
      notify(`${shot.shot_id || 'The shot'} now needs ${name}`)
      return true
    })
  }

  // source: { filePath } | { fromVersionId } | { file }
  async function fillExtra(shot, extra, source, version = latestVersion(shot)) {
    if (!version) return false
    if (source.file) {
      return uploadExtraFile(shot, version, { file: source.file, extraId: extra.id, name: extra.name })
    }
    return run(`${shot.id}:${extra.id}`, `Could not add ${extra.name}`, async () => {
      await api.put(`${shotUrl(shot)}/${encodeURIComponent(extra.id)}/versions/${encodeURIComponent(version.id)}`,
        source.fromVersionId ? { from_version_id: source.fromVersionId } : { file_path: source.filePath })
      return true
    })
  }

  function clearExtraFile(shot, extra, version = latestVersion(shot)) {
    return run(`${shot.id}:${extra.id}`, `Could not remove the file of ${extra.name}`, () => (
      api.delete(`${shotUrl(shot)}/${encodeURIComponent(extra.id)}/versions/${encodeURIComponent(version.id)}`)
    ))
  }

  function updateExtra(shot, extra, changes) {
    return run(`${shot.id}:${extra.id}`, `Could not change ${extra.name}`, () => (
      api.patch(`${shotUrl(shot)}/${encodeURIComponent(extra.id)}`, changes)
    ))
  }

  function removeExtra(shot, extra) {
    return run(`${shot.id}:${extra.id}`, `Could not remove ${extra.name}`, async () => {
      await api.delete(`${shotUrl(shot)}/${encodeURIComponent(extra.id)}`)
      notify(`Removed ${extra.name} from ${shot.shot_id || 'the shot'}`)
    })
  }

  function reorderExtras(shot, extraIds) {
    return run(`order:${shot.id}`, 'Could not reorder the extras', () => (
      api.put(`${shotUrl(shot)}/order`, { extra_ids: extraIds })
    ))
  }

  function moveExtra(shot, extra, offset) {
    const ids = (shot?.extras || []).map(item => item.id)
    const from = ids.indexOf(extra.id)
    const to = from + offset
    if (from < 0 || to < 0 || to >= ids.length) return null
    ids.splice(to, 0, ids.splice(from, 1)[0])
    return reorderExtras(shot, ids)
  }

  function extraFileUrl(version, file, suffix) {
    const sharedId = shareId()
    if (sharedId) {
      const query = buildShareCredentialQuery({}, ctx.getShareCredential({ shareId: sharedId }))
      if (suffix === 'download') return `/api/projects/shared/${encodeURIComponent(sharedId)}/shot-versions/${encodeURIComponent(version.id)}/extras/${encodeURIComponent(file.extra_id)}/download${query}`
      return `/api/projects/shared/${encodeURIComponent(sharedId)}/media-assets/${encodeURIComponent(file.media_asset_id)}/${suffix}${query}`
    }
    if (suffix === 'download') return `/api/horizons/projects/${encodeURIComponent(projectId())}/shot-versions/${encodeURIComponent(version.id)}/extras/${encodeURIComponent(file.extra_id)}/download`
    return `/api/horizons/projects/${encodeURIComponent(projectId())}/media-assets/${encodeURIComponent(file.media_asset_id)}/${suffix}`
  }

  function getExtraThumbnailUrl(version, file) {
    return file?.media_asset_id && (file.is_video || file.is_image || file.is_pdf) ? extraFileUrl(version, file, 'thumbnail') : ''
  }

  function downloadExtra(version, file) {
    if (!version || !file || file.exists === false) return
    // The server names the file after the tracker, such as SH010_V2_Alpha matte.mov.
    ctx.triggerBrowserDownload(extraFileUrl(version, file, 'download'), '')
  }

  function prefetchExtraPath(version, file) {
    if (ctx.canCopyFilePaths?.value && file?.media_asset_id) loadNetworkPath(extraFileUrl(version, file, 'file-info')).catch(() => {})
  }

  function copyExtraPath(version, file) {
    return copyFilePath(file?.media_asset_id ? loadNetworkPath(extraFileUrl(version, file, 'file-info')) : '')
  }

  function chooseExtraProjectFiles({ multiple = true } = {}) {
    return new Promise(resolve => ctx.openExtraFilePicker({ multiple, onApply: resolve }))
  }

  // Files dropped on a card. On a needed extra, one file fills it. Anywhere
  // else they open the add dialog, so the person says what each file is.
  async function dropExtraFiles(shot, zone, { files = [], items = [] } = {}) {
    const version = latestVersion(shot)
    if (!canAddExtraFiles.value) return false
    if (!version) {
      notify('Add a version first. Extras go with a version.')
      return false
    }
    const projectItems = items.filter(item => item?.type !== 'folder').map(item => ({ name: item.name, file_path: projectItemFilePath(item) }))
    if (!files.length && !projectItems.length) {
      notify('Drop files, not folders.')
      return false
    }
    const extraId = String(zone || '').startsWith('needed:') ? zone.slice('needed:'.length) : ''
    const slot = extraId ? getExtraSlots(shot, version).find(entry => entry.id === extraId && !entry.file) : null
    if (!slot) {
      openAddExtras(shot, { files, items: projectItems })
      return true
    }
    if (files.length + projectItems.length !== 1) {
      notify(`Drop one file on ${slot.name}.`)
      return false
    }
    return fillExtra(shot, slot, files.length ? { file: files[0] } : { filePath: projectItems[0].file_path }, version)
  }

  function versionHasExtras(version) {
    return versionExtraFiles(version).length > 0
  }

  const trackerHasExtras = computed(() => (ctx.currentTracker.value?.shots || []).some(shot => versionHasExtras(latestVersion(shot))))

  return {
    EXTRA_TYPES,
    extrasDialog,
    openAddExtras,
    addDialogFiles,
    closeExtrasDialog,
    dropExtraFiles,
    extraUploads,
    extraBusy,
    canAddExtraFiles,
    canManageExtras,
    trackerHasExtras,
    getExtraSlots,
    getUploadsFor,
    getEarlierExtraFiles,
    getExtraThumbnailUrl,
    versionHasExtras,
    addExtras,
    askForExtra,
    fillExtra,
    clearExtraFile,
    updateExtra,
    removeExtra,
    moveExtra,
    reorderExtras,
    downloadExtra,
    prefetchExtraPath,
    copyExtraPath,
    chooseExtraProjectFiles,
  }
}
