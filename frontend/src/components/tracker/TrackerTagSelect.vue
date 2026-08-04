<template>
  <TrackerInlineSelect
    v-bind="$attrs"
    class="tracker-tag-select"
    tone="category"
    :label="tagLabel"
    :interactive="canCategorizeShots && !shareMode"
    :open="canCategorizeShots && showCategoryPicker === shot.shot_id"
    :flip-up="flipUp"
    @trigger="toggleShotCategoryPicker($event, shot.shot_id)"
    @close="close"
  >
    <template #leading>
      <span
        class="category-color-indicator"
        :style="{ backgroundColor: getCategoryColor(tagValue) }"
      ></span>
    </template>
    <template #menu>
      <div class="tracker-select-search">
        <input
          class="tracker-select-search-input v-input"
          type="text"
          :value="categorySearchFilter"
          placeholder="Search or create tag..."
          @input="setCategorySearchFilter($event.target.value)"
          @keydown.enter="assignOrCreateCategory(shot, categorySearchFilter)"
        />
      </div>
      <div class="tracker-select-list">
        <button
          v-for="category in filteredCategories"
          :key="category"
          class="category-option tracker-select-option v-dropdown-item"
          :class="{ active: tagLabel === category }"
          @click="assignCategory(shot, category)"
        >
          <span
            class="category-color-indicator"
            :style="{ backgroundColor: getCategoryColor(category) }"
          ></span>
          <span class="tracker-select-option-label">{{ category }}</span>
          <svg v-if="tagLabel === category" class="icon tracker-select-check"><use href="#icon-check" /></svg>
        </button>
        <button
          v-if="tagValue"
          class="category-option tracker-select-option v-dropdown-item"
          @click="assignCategory(shot, null)"
        >
          <svg class="icon"><use href="#icon-x" /></svg>
          <span class="tracker-select-option-label">Remove tag</span>
        </button>
        <button
          v-if="isAdmin && deletableTag"
          class="category-option tracker-select-option tracker-select-option-danger v-dropdown-item"
          @click="deleteCategoryFromTable(deletableTag)"
        >
          <svg class="icon"><use href="#icon-trash" /></svg>
          <span class="tracker-select-option-label">Delete "{{ deletableTag }}"</span>
        </button>
      </div>
      <button
        v-if="categorySearchFilter && !trackerCategories.includes(categorySearchFilter)"
        class="tracker-select-option tracker-select-option-create v-dropdown-item"
        @click="assignOrCreateCategory(shot, categorySearchFilter)"
      >
        <svg class="icon"><use href="#icon-plus" /></svg>
        <span class="tracker-select-option-label">Create "{{ categorySearchFilter }}"</span>
      </button>
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
  assignCategory,
  assignOrCreateCategory,
  canCategorizeShots,
  categorySearchFilter,
  deleteCategoryFromTable,
  filteredCategories,
  getCategoryColor,
  isAdmin,
  setCategorySearchFilter,
  showCategoryPicker,
  toggleShotCategoryPicker,
  trackerCategories,
} = useTrackerStore()
const { shareMode } = useShareAccessContext()

const tagValue = computed(() => {
  const raw = String(props.shot?.tag ?? props.shot?.category ?? '').trim()
  return (!raw || raw === 'Uncategorized' || raw === 'Untagged') ? '' : raw
})
const tagLabel = computed(() => tagValue.value || 'Untagged')
const deletableTag = computed(() => {
  if (tagValue.value) return tagValue.value
  const customTags = (trackerCategories.value || []).filter(category => (
    category && !['Untagged', 'Uncategorized'].includes(category)
  ))
  return customTags.length === 1 ? customTags[0] : ''
})

function close() {
  showCategoryPicker.value = null
  setCategorySearchFilter('')
}
</script>
