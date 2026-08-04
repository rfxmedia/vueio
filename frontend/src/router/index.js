/**
 * ═══════════════════════════════════════════════════════════════════════════════
 * VUE.IO - ROUTER CONFIGURATION
 * ═══════════════════════════════════════════════════════════════════════════════
 *
 * URL Structure:
 *
 * PUBLIC ROUTES (No Auth Required):
 *   /s/:shareId                    - Shared NAS file/folder (root)
 *   /s/:shareId/*path              - Deep link into shared folder
 *   /p/:shareId                    - Shared project
 *   /p/:shareId/t/:tracker         - Shared tracker
 *   /p/:shareId/f                  - Shared project file/folder root (opaque URL)
 *   /p/:shareId/f/*path            - Legacy/deep shared project file/folder path
 *   /login                         - Login page
 *
 * PROTECTED ROUTES (Auth Required):
 *   /                              - Redirect to /files or /projects
 *   /files                         - File browser root
 *   /files/*path                   - File browser with path
 *   /projects                      - Project list
 *   /projects/:id                  - Project folder view
 *   /projects/:id/f/*path          - Project folder deep link
 *   /projects/:id/t/:tracker       - Tracker view
 *   /projects/:id/page/:page       - Page view
 *   /settings                      - User settings and admin controls
 *   /admin                         - Legacy redirect to Settings
 *
 * ═══════════════════════════════════════════════════════════════════════════════
 */

import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  // ═══════════════════════════════════════════════════════════════════════════
  // PUBLIC SHARE ROUTES (No authentication required)
  // ═══════════════════════════════════════════════════════════════════════════

  {
    path: '/s/:shareId/:path*',
    name: 'shared-nas',
    meta: { public: true, shareType: 'nas' }
  },
  {
    path: '/p/:shareId',
    name: 'shared-project',
    meta: { public: true, shareType: 'project' }
  },
  {
    path: '/p/:shareId/t/:tracker',
    name: 'shared-tracker',
    meta: { public: true, shareType: 'tracker' }
  },
  {
    path: '/p/:shareId/f',
    name: 'shared-project-file-root',
    meta: { public: true, shareType: 'project-file' }
  },
  {
    path: '/p/:shareId/f/:path*',
    name: 'shared-project-file',
    meta: { public: true, shareType: 'project-file' }
  },
  {
    path: '/login',
    name: 'login',
    meta: { public: true }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // PROTECTED APP ROUTES (Authentication required)
  // ═══════════════════════════════════════════════════════════════════════════

  {
    path: '/',
    name: 'home',
    meta: { requiresAuth: true }
  },
  {
    path: '/files/:path*',
    name: 'files',
    meta: { requiresAuth: true, module: 'files' }
  },
  {
    path: '/projects',
    name: 'projects',
    meta: { requiresAuth: true, module: 'projects' }
  },
  {
    path: '/projects/:projectId',
    name: 'project-folder',
    meta: { requiresAuth: true, module: 'projects' }
  },
  {
    path: '/projects/:projectId/f/:path*',
    name: 'project-folder-path',
    meta: { requiresAuth: true, module: 'projects' }
  },
  {
    path: '/projects/:projectId/t/:tracker',
    name: 'project-tracker',
    meta: { requiresAuth: true, module: 'projects' }
  },
  {
    path: '/projects/:projectId/page/:page',
    name: 'project-page',
    meta: { requiresAuth: true, module: 'projects' }
  },
  {
    path: '/settings',
    name: 'settings',
    meta: { requiresAuth: true, module: 'settings' }
  },
  {
    path: '/admin',
    redirect: '/settings',
    meta: { requiresAuth: true }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // CATCH-ALL (404) - Redirect to home
  // ═══════════════════════════════════════════════════════════════════════════

  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Global navigation guard to prevent escaping share bounds
router.beforeEach((to, from, next) => {
  // Check if we're in share mode (coming from a share route)
  const wasInShare = from.meta?.public && from.meta?.shareType
  const goingToShare = to.meta?.public && to.meta?.shareType
  const goingToProtected = to.meta?.requiresAuth

  // SECURITY: If in share mode and trying to navigate to protected route, block it
  if (wasInShare && goingToProtected) {
    // User tried to navigate away from share (e.g., via browser back to a protected route)
    // Stay on current share route
    console.warn('Navigation blocked: Cannot escape share mode')
    next(false) // Cancel navigation
    return
  }

  // Allow navigation within shares or to other public routes
  next()
})

export default router
