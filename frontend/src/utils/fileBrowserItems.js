import { fileTimestampValue } from './formatters'

const FILE_BROWSER_FILE_TYPES = new Set(['file', 'video', 'image'])

const THREE_D_FILE_TYPES = {
  '3ds': '3D Studio scene',
  abc: 'Alembic 3D cache',
  dae: 'COLLADA 3D scene',
  fbx: 'FBX 3D scene',
  glb: 'glTF binary scene',
  gltf: 'glTF 3D scene',
  obj: 'Wavefront 3D object',
  ply: 'Polygon 3D model',
  stl: 'STL 3D model',
  usd: 'Universal Scene Description',
  usda: 'Universal Scene Description ASCII',
  usdc: 'Universal Scene Description crate',
  usdz: 'Universal Scene Description package',
  vdb: 'OpenVDB volume',
}

const FILE_TYPE_VISUALS = {
  aep: { mark: 'Ae', label: 'After Effects', color: '#9999ff' },
  aet: { mark: 'Ae', label: 'After Effects template', color: '#9999ff' },
  aetx: { mark: 'Ae', label: 'After Effects template', color: '#9999ff' },
  prproj: { mark: 'Pr', label: 'Premiere Pro', color: '#b6a5ff' },
  psd: { mark: 'Ps', label: 'Photoshop', color: '#52a8ff' },
  psb: { mark: 'Ps', label: 'Photoshop large document', color: '#52a8ff' },
  ai: { mark: 'Ai', label: 'Illustrator', color: '#ff9a38' },
  blend: { mark: 'Bl', label: 'Blender', color: '#f28c28' },
  blend1: { mark: 'Bl', label: 'Blender backup', color: '#f28c28' },
  blend2: { mark: 'Bl', label: 'Blender backup', color: '#f28c28' },
  drp: { mark: 'Da', label: 'DaVinci Resolve project', color: '#58aee8' },
  dra: { mark: 'Da', label: 'DaVinci Resolve archive', color: '#58aee8' },
  fcpxml: { mark: 'Fc', label: 'Final Cut Pro XML', color: '#e26bc7' },
  fcpbundle: { mark: 'Fc', label: 'Final Cut Pro library', color: '#e26bc7' },
  nk: { mark: 'Nk', label: 'Nuke script', color: '#c7db45' },
  nknc: { mark: 'Nk', label: 'Nuke Non-commercial script', color: '#c7db45' },
  c4d: { mark: 'C4', label: 'Cinema 4D', color: '#5596e6' },
  ma: { mark: 'Ma', label: 'Maya ASCII scene', color: '#63c5c8' },
  mb: { mark: 'Ma', label: 'Maya binary scene', color: '#63c5c8' },
  hip: { mark: 'H', label: 'Houdini scene', color: '#f47c35' },
  hiplc: { mark: 'H', label: 'Houdini Indie scene', color: '#f47c35' },
  hipnc: { mark: 'H', label: 'Houdini Apprentice scene', color: '#f47c35' },
  ptx: { mark: 'Pt', label: 'Pro Tools session', color: '#8f7df0' },
  ptf: { mark: 'Pt', label: 'Pro Tools session', color: '#8f7df0' },
  sesx: { mark: 'Au', label: 'Audition session', color: '#56c6a9' },
  logicx: { mark: 'L', label: 'Logic Pro project', color: '#74a9d8' },
  rpp: { mark: 'Re', label: 'REAPER project', color: '#aebdc4' },
}

function fileExtension(item) {
  const explicit = String(item?.extension || '').trim().toLowerCase().replace(/^\./, '')
  if (explicit) return explicit

  const name = String(item?.name || '')
  const separator = name.lastIndexOf('.')
  return separator >= 0 ? name.slice(separator + 1).toLowerCase() : ''
}

export const FILE_SORT_OPTIONS = [
  { value: 'name', label: 'Name' },
  { value: 'date', label: 'Date added' },
  { value: 'size', label: 'Size' },
  { value: 'type', label: 'Type' },
  { value: 'uploader', label: 'Uploaded by' },
]

export function isFileBrowserFolder(item) {
  return item?.type === 'folder'
}

export function isFileBrowserFile(item) {
  return FILE_BROWSER_FILE_TYPES.has(item?.type)
}

export function isFileBrowserEntry(item) {
  return isFileBrowserFolder(item) || isFileBrowserFile(item)
}

export function fileTypeVisual(item) {
  if (isFileBrowserFolder(item)) return null
  const extension = fileExtension(item)
  if (FILE_TYPE_VISUALS[extension]) return FILE_TYPE_VISUALS[extension]
  if (THREE_D_FILE_TYPES[extension]) {
    return {
      kind: 'three-d',
      mark: extension.toUpperCase(),
      label: THREE_D_FILE_TYPES[extension],
      color: 'var(--v-text-secondary)',
    }
  }
  return null
}

export function fileTypeLabel(item) {
  if (item?.type === 'folder') return 'Folder'

  const extension = String(item?.extension || '').trim().toUpperCase()
  const isPdf = item?.is_pdf || extension === 'PDF'
  const isImage = item?.is_image || item?.type === 'image'
  const isVideo = item?.is_video || item?.type === 'video'

  if (isPdf) return 'PDF document'
  if (isImage) return extension ? `${extension} image` : 'Image'
  if (isVideo) return extension ? `${extension} video` : 'Video'
  return extension ? `${extension} file` : 'File'
}

export function fileUploaderLabel(item) {
  return String(item?.uploaded_by || item?.uploader_name || '').trim()
}

function compareStrings(left, right) {
  return String(left || '').localeCompare(String(right || ''), undefined, {
    numeric: true,
    sensitivity: 'base',
  })
}

function compareValues(left, right, key) {
  if (key === 'size') return Number(left?.size || 0) - Number(right?.size || 0)
  if (key === 'date') return fileTimestampValue(left) - fileTimestampValue(right)
  if (key === 'type') return compareStrings(fileTypeLabel(left), fileTypeLabel(right))
  if (key === 'uploader') return compareStrings(fileUploaderLabel(left), fileUploaderLabel(right))
  return compareStrings(left?.name, right?.name)
}

export function sortFileBrowserItems(items, key = 'name', direction = 'asc') {
  const multiplier = direction === 'desc' ? -1 : 1
  return [...(items || [])].sort((left, right) => {
    const leftFolder = left?.type === 'folder'
    const rightFolder = right?.type === 'folder'
    if (leftFolder !== rightFolder) return leftFolder ? -1 : 1

    const primary = compareValues(left, right, key)
    if (primary !== 0) return primary * multiplier
    return compareStrings(left?.name, right?.name)
  })
}
