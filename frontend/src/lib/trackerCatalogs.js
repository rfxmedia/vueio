export const TRACKER_STATUS_ORDER = ['not_started', 'in_progress', 'waiting_review', 'edits_requested', 'done']

export const TRACKER_STATUS_LABELS = {
  not_started: 'Not Started',
  in_progress: 'In Progress',
  waiting_review: 'Review',
  edits_requested: 'Edits Requested',
  done: 'Done',
}

export const TRACKER_STATUS_COLORS = {
  not_started: 'var(--v-status-draft)',
  in_progress: 'var(--v-status-active)',
  waiting_review: 'var(--v-status-review)',
  edits_requested: 'var(--v-status-hold)',
  done: 'var(--v-status-done)',
}

export const TRACKER_STATUS_TEXT_COLORS = {
  not_started: 'var(--v-text-secondary)',
  in_progress: 'var(--v-status-active-text)',
  waiting_review: 'var(--v-status-review-text)',
  edits_requested: 'var(--v-status-hold-text)',
  done: 'var(--v-status-done-text)',
}

export const TRACKER_ACTIVITY_FILTERS = [
  { value: 'all', label: 'All', mobileLabel: 'All', icon: '#icon-activity' },
  { value: 'versions', label: 'Versions', mobileLabel: 'Versions', icon: '#icon-video' },
  { value: 'comments', label: 'Comments', mobileLabel: 'Comments', icon: '#icon-comment' },
  { value: 'assignments', label: 'Assignments', mobileLabel: 'Assign', icon: '#icon-user' },
  { value: 'status', label: 'Status', mobileLabel: 'Status', icon: '#icon-circle' },
  { value: 'tags', label: 'Tags', mobileLabel: 'Tags', icon: '#icon-bar-chart' },
  { value: 'downloads', label: 'Downloads', mobileLabel: 'Downloads', icon: '#icon-download' },
]

const TRACKER_EVENT_ICONS = {
  shot_created: '#icon-plus',
  shot_deleted: '#icon-trash',
  shot_archived: '#icon-inbox',
  shot_restored: '#icon-undo',
  shot_reordered: '#icon-sort',
  shot_renamed: '#icon-edit-3',
  brief_changed: '#icon-image',
  brief_file_uploaded: '#icon-upload',
  shots_imported: '#icon-inbox',
  status_changed: '#icon-circle',
  category_changed: '#icon-bar-chart',
  assignee_changed: '#icon-user',
  download_started: '#icon-download',
  version_added: '#icon-video',
  versions_bulk_updated: '#icon-video',
  version_published: '#icon-eye',
  version_kept_internal: '#icon-eye-off',
  version_removed_from_shares: '#icon-eye-off',
  status_changed_bulk: '#icon-circle',
  shots_bulk_updated: '#icon-edit-3',
  shots_deleted_bulk: '#icon-trash',
  comment_added: '#icon-comment',
  comment_resolved: '#icon-check',
  comment_deleted: '#icon-trash',
}

export function getTrackerStatusLabel(status) {
  return TRACKER_STATUS_LABELS[status] || status
}

export function getTrackerStatusColor(status) {
  return TRACKER_STATUS_COLORS[status] || 'var(--v-text-muted)'
}

export function getTrackerStatusTextColor(status) {
  return TRACKER_STATUS_TEXT_COLORS[status] || 'var(--v-text-secondary)'
}

export function getTrackerEventIcon(type) {
  return TRACKER_EVENT_ICONS[type] || '#icon-activity'
}
