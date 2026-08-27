import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './assets/main.css'
import './assets/admin.css'
import { loadAndApplyStoredTheme } from './utils/themeManager'
import api from './lib/api'
import { installConnectionRecovery } from './lib/connectionRecovery'

const STARTUP_ERROR_PREFIX = '[vue.io startup crash]'
const RUNTIME_ERROR_PREFIX = '[vue.io runtime error]'
let appMounted = false

installConnectionRecovery(api)

function renderStartupCrash(title) {
  const target = document.querySelector('#app')
  console.error(STARTUP_ERROR_PREFIX, title)

  if (!target) {
    return
  }

  target.innerHTML = `
    <div style="min-height:100vh;padding:24px;background:#0f1115;color:#f3f4f6;font-family:'SF Pro Display',sans-serif;box-sizing:border-box;">
      <h1 style="margin:0 0 12px;font-size:20px;">Startup error</h1>
      <p style="margin:0;color:#f59e0b;">Vueio could not start. Refresh the page or ask the installation administrator to check the server logs.</p>
    </div>
  `
}

window.addEventListener('error', () => {
  if (appMounted) {
    console.error(RUNTIME_ERROR_PREFIX, 'window.error')
    return
  }
  renderStartupCrash('window.error')
})

window.addEventListener('unhandledrejection', () => {
  if (appMounted) {
    console.error(RUNTIME_ERROR_PREFIX, 'window.unhandledrejection')
    return
  }
  renderStartupCrash('window.unhandledrejection')
})

async function bootstrap() {
  try {
    await loadAndApplyStoredTheme()
  } catch {
    console.warn('[vue.io theme load] Failed to apply the stored theme')
  }

  const app = createApp(App)

  app.config.errorHandler = () => {
    if (appMounted) {
      console.error(RUNTIME_ERROR_PREFIX, 'vue.errorHandler')
      return
    }
    renderStartupCrash('vue.errorHandler')
  }

  app.use(router)
  app.mount('#app')
  appMounted = true
}

bootstrap().catch(() => {
  renderStartupCrash('bootstrap')
})
