import { ref } from 'vue'
import { useModal } from './useModal'

export function useProjectShellChrome() {
  const {
    isOpen: showCreateProject,
    open: openCreateProjectModal,
    close: closeCreateProjectModal,
  } = useModal()
  const {
    isOpen: showCreatePage,
    open: openCreatePageModal,
    close: closeCreatePageModal,
  } = useModal()
  const {
    isOpen: showCreateSandbox,
    open: openCreateSandboxModal,
    close: closeCreateSandboxModal,
  } = useModal()
  const {
    isOpen: showCreateTracker,
    open: openCreateTrackerModal,
    close: closeCreateTrackerModal,
  } = useModal()
  const {
    isOpen: showCreateFolder,
    open: openCreateFolderModal,
    close: closeCreateFolderModal,
  } = useModal()
  const showNewMenu = ref(false)
  const showArtistNewMenu = ref(false)
  const newProjectTitle = ref('')
  const newProjectDesc = ref('')
  const newProjectDue = ref('')
  const newPageTitle = ref('')
  const newPageDesc = ref('')
  const newSandboxName = ref('')
  const newSandboxDesc = ref('')
  const newTrackerName = ref('')
  const newTrackerDescription = ref('')
  const newFolderName = ref('')

  function toggleProjectNewMenu() {
    showNewMenu.value = !showNewMenu.value
  }

  function toggleArtistNewMenu() {
    showArtistNewMenu.value = !showArtistNewMenu.value
  }

  function closeNewMenu() {
    showNewMenu.value = false
    showArtistNewMenu.value = false
  }

  function openProjectCreateTracker() {
    openCreateTrackerModal()
    showNewMenu.value = false
  }

  function openProjectCreatePage() {
    openCreatePageModal()
    showNewMenu.value = false
  }

  function openProjectCreateSandbox() {
    openCreateSandboxModal()
    showNewMenu.value = false
  }

  function openProjectCreateFolderFromMenu() {
    openCreateFolderModal()
    showNewMenu.value = false
    showArtistNewMenu.value = false
  }

  return {
    showCreateProject,
    showCreatePage,
    showCreateSandbox,
    showCreateTracker,
    showCreateFolder,
    showNewMenu,
    showArtistNewMenu,
    newProjectTitle,
    newProjectDesc,
    newProjectDue,
    newPageTitle,
    newPageDesc,
    newSandboxName,
    newSandboxDesc,
    newTrackerName,
    newTrackerDescription,
    newFolderName,
    openCreateProjectModal,
    closeCreateProjectModal,
    openCreatePageModal,
    closeCreatePageModal,
    openCreateSandboxModal,
    closeCreateSandboxModal,
    openCreateTrackerModal,
    closeCreateTrackerModal,
    openCreateFolderModal,
    closeCreateFolderModal,
    toggleProjectNewMenu,
    toggleArtistNewMenu,
    closeNewMenu,
    openProjectCreatePage,
    openProjectCreateSandbox,
    openProjectCreateTracker,
    openProjectCreateFolderFromMenu,
  }
}
