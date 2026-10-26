// A change made with an agent key names the key, for example "Daniel via Claude Code".
export function activityActorName(item) {
  const name = item?.actor_name || 'Someone'
  const agent = item?.source === 'agent' ? item.payload?.agent?.name : ''
  return agent ? `${name} via ${agent}` : name
}
