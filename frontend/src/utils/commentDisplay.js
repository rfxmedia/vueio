export function getCommentInitials(name) {
  if (!name) return '?'
  const parts = String(name).trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export function getCommentAvatarFill(name) {
  const seed = String(name || '?')
  let hash = 7
  for (let i = 0; i < seed.length; i++) hash = ((hash * 31) + seed.charCodeAt(i)) >>> 0
  return `hsl(${hash % 360} 58% 46%)`
}

export function getCommentAvatarStyle(name) {
  return {
    background: getCommentAvatarFill(name),
    color: '#fff',
  }
}
