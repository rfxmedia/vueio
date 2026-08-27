const PROJECT_CONTENT_TYPES = new Set(['folder', 'file', 'tracker', 'page'])

export function normalizeProjectContentItems(items = []) {
  return (Array.isArray(items) ? items : [])
    .filter(item => PROJECT_CONTENT_TYPES.has(item?.type))
    .map(item => {
      if (item.type !== 'file') return { ...item, _pickerSource: 'project' }
      return {
        ...item,
        type: item.is_video ? 'video' : item.is_image ? 'image' : 'file',
        project_item_type: 'file',
        _pickerSource: 'project',
        _projectFile: !item.is_linked,
      }
    })
}

export function projectContentItemTarget(item) {
  if (!item) return null
  if (item.type === 'folder') {
    const targetId = String(item.path || '').replace(/^\/+|\/+$/g, '')
    return {
      ...item,
      target_type: 'folder',
      target_id: targetId,
      label: item.name || targetId.split('/').filter(Boolean).at(-1) || 'Project folder',
      sublabel: item.is_workspace ? 'Workspace' : 'Folder',
      kind: item.is_workspace ? 'workspace' : 'folder',
      disabled: !targetId,
      disabled_hint: targetId ? '' : 'The project root cannot be mentioned',
    }
  }
  if (item.type === 'tracker') {
    const targetId = item.id || item.tracker_id
    return targetId ? {
      ...item,
      target_type: 'tracker',
      target_id: targetId,
      tracker_id: targetId,
      label: item.name || item.title || 'Tracker',
      sublabel: 'Tracker',
      kind: 'tracker',
    } : null
  }
  if (item.type === 'page') {
    const targetId = item.id || item.page_id
    return targetId ? {
      ...item,
      target_type: 'page',
      target_id: targetId,
      label: item.title || item.name || 'Page',
      sublabel: 'Page',
      kind: 'page',
    } : null
  }
  const targetId = item.media_asset_id || item.horizons_media_asset_id
  return {
    ...item,
    target_type: 'media_asset',
    target_id: targetId || '',
    media_asset_id: targetId || '',
    label: item.name || 'Project file',
    sublabel: item.path || 'Project file',
    kind: item.is_video || item.type === 'video'
      ? 'video'
      : item.is_image || item.type === 'image'
        ? 'image'
        : item.extension === 'pdf' || String(item.name || '').toLowerCase().endsWith('.pdf')
          ? 'pdf'
          : 'file',
    disabled: !targetId,
    disabled_hint: targetId ? '' : 'This file is not registered yet',
  }
}
