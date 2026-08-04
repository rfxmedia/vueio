import { ref } from 'vue'

import api from '../lib/api'

export function usePageResourceController({
  currentProject,
  currentPage,
  clonePageDraft,
  savePage,
  openPicker,
  openProjectUpload,
  openSharedUpload,
}) {
  const pageResourcePickerBlockId = ref('')
  const sharedPageUploadTarget = ref('')

  function pageUploadTarget(page = currentPage.value) {
    const uploadBlock = (page?.blocks || []).find(block => (
      block.type === 'upload_inbox' && !block.hidden && block.enabled !== false
    ))
    return uploadBlock?.target_path || `client-uploads/${page?.slug || 'page'}`
  }

  async function appendPageResources(blockId, resources) {
    if (!currentPage.value || !resources?.length) return
    const draft = clonePageDraft()
    const block = (draft.blocks || []).find(item => item.id === blockId)
    if (!block || block.type !== 'resource_list') return
    block.resources = [...(block.resources || []), ...resources]
    await savePage(draft)
  }

  function openPageResourcePicker(blockId) {
    pageResourcePickerBlockId.value = blockId
    openPicker()
  }

  async function handlePageResourcePicked(item) {
    const blockId = pageResourcePickerBlockId.value
    if (!currentProject.value || !blockId || !item?.path) return
    const name = item.name || item.path.split('/').filter(Boolean).pop() || 'Resource'
    const targetFolder = pageUploadTarget()
    await api.post(`/api/projects/${currentProject.value.id}/link`, {
      source_path: item.path,
      target_folder: targetFolder,
    })
    await appendPageResources(blockId, [{
      id: `resource-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      kind: item.type === 'folder' ? 'folder' : 'file',
      label: name,
      path: [targetFolder, name].filter(Boolean).join('/'),
    }])
  }

  function openPageResourceUpload(blockId, targetPath = '') {
    pageResourcePickerBlockId.value = blockId
    openProjectUpload(targetPath || pageUploadTarget(), {
      title: 'Upload Vue Dashboard Resources',
      description: 'Upload files into this dashboard inbox. Completed files are added to the resource block.',
      onCompleted: items => appendPageResources(blockId, (items || []).map(item => ({
        id: `resource-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        kind: 'file',
        label: item.name || item.relPath || item.path,
        path: item.path,
      }))),
    })
  }

  function openSharedPageUpload(targetPath) {
    sharedPageUploadTarget.value = targetPath || ''
    openSharedUpload()
  }

  return {
    pageResourcePickerBlockId,
    sharedPageUploadTarget,
    pageUploadTarget,
    appendPageResources,
    openPageResourcePicker,
    handlePageResourcePicked,
    openPageResourceUpload,
    openSharedPageUpload,
  }
}
