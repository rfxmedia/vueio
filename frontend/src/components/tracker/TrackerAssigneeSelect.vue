<template>
  <TrackerInlineSelect
    v-bind="$attrs"
    class="tracker-assignee-select"
    tone="assignee"
    :label="getShotAssigneeLabel(shot)"
    :interactive="canAssignShots && !shareMode"
    :open="canAssignShots && showAssigneePicker === shot.shot_id"
    :flip-up="flipUp"
    :highlighted="hasAssignee"
    @trigger="toggleShotAssigneePicker($event, shot.shot_id)"
    @close="showAssigneePicker = null"
  >
    <template #leading>
      <svg class="icon tracker-assignee-icon"><use href="#icon-user" /></svg>
    </template>
    <template #menu>
      <div class="tracker-select-list">
        <button
          class="assignee-option tracker-select-option v-dropdown-item"
          :class="{ active: !hasAssignee }"
          @click="selectShotAssignee(shot, null)"
        >
          <span class="tracker-select-option-label">Unassigned</span>
          <svg v-if="!hasAssignee" class="icon tracker-select-check"><use href="#icon-check" /></svg>
        </button>
        <button
          v-for="candidate in assignmentCandidates"
          :key="candidate.id"
          class="assignee-option tracker-select-option v-dropdown-item"
          :class="{ active: isShotAssignedTo(shot, candidate.id) }"
          @click="selectShotAssignee(shot, candidate.id)"
        >
          <span
            class="assignee-option-check"
            :class="{ active: isShotAssignedTo(shot, candidate.id) }"
          >
            <svg v-if="isShotAssignedTo(shot, candidate.id)" class="icon"><use href="#icon-check" /></svg>
          </span>
          <span class="tracker-select-option-label">{{ candidate.display_name || candidate.username }}</span>
          <span class="assignee-option-meta">{{ candidate.role }}</span>
        </button>
      </div>
    </template>
  </TrackerInlineSelect>
</template>

<script setup>
import { computed } from 'vue'
import { useShareAccessContext } from '../../ownership/shareAccessContext'
import { useTrackerStore } from '../../ownership/tracker'
import TrackerInlineSelect from './TrackerInlineSelect.vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  shot: { type: Object, required: true },
  flipUp: { type: Boolean, default: false },
})

const {
  assignmentCandidates,
  canAssignShots,
  getShotAssigneeLabel,
  isShotAssignedTo,
  selectShotAssignee,
  showAssigneePicker,
  toggleShotAssigneePicker,
} = useTrackerStore()
const { shareMode } = useShareAccessContext()

const hasAssignee = computed(() => Boolean(
  props.shot?.assignee_user_ids?.length
  || props.shot?.assignee_user_id
  || props.shot?.assignees?.length
  || props.shot?.assignee,
))
</script>
