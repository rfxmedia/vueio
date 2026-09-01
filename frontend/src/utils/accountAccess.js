export function isAdminUser(user) {
  return user?.role === 'admin'
}

export function isMemberUser(user) {
  return Boolean(user && !isAdminUser(user))
}

export function hasAppAccess(user, capability) {
  return isAdminUser(user) || user?.app_access?.[capability] === true
}

export function isRestrictedProjectMember(user) {
  return isMemberUser(user) && !hasAppAccess(user, 'manage_project_content')
}
