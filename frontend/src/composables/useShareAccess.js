export function useShareAccess({ shareAccessToken, pendingShareId = null, pendingShareType = null, shareAccessTokenScope = null }) {
  function activeShareId() {
    return pendingShareId?.value || ''
  }

  function rememberShareAccessToken(payload, scope = {}) {
    if (payload?.access_granted) {
      shareAccessToken.value = 'cookie'
      if (shareAccessTokenScope) {
        shareAccessTokenScope.value = {
          shareId: scope.shareId || payload.share_id || activeShareId(),
          shareType: scope.shareType || pendingShareType?.value || '',
        }
      }
    }
  }

  function scopedShareAccessToken(shareId = activeShareId()) {
    if (!shareAccessToken.value) return ''
    if (!shareAccessTokenScope) return shareAccessToken.value
    const scope = shareAccessTokenScope.value
    if (!scope?.shareId || !shareId || scope.shareId !== shareId) return ''
    return shareAccessToken.value
  }

  function clearShareAccessToken() {
    shareAccessToken.value = ''
    if (shareAccessTokenScope) shareAccessTokenScope.value = null
  }

  function getShareCredential({ shareId = activeShareId() } = {}) {
    scopedShareAccessToken(shareId)
    return {}
  }

  return {
    rememberShareAccessToken,
    scopedShareAccessToken,
    clearShareAccessToken,
    getShareCredential,
  }
}
