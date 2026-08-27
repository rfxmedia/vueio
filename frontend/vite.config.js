import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const apiProxy = {
  target: process.env.VUEIO_API_PROXY || 'http://localhost:8000',
  changeOrigin: true
}

if (process.env.VUEIO_PROXY_INSECURE_COOKIES === '1') {
  apiProxy.configure = (proxy) => {
    proxy.on('proxyRes', (response) => {
      const cookies = response.headers['set-cookie']
      if (!cookies) return
      response.headers['set-cookie'] = (Array.isArray(cookies) ? cookies : [cookies])
        .map((cookie) => cookie.replace(/;\s*Secure(?=;|$)/gi, ''))
    })
  }
}

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      '/api': apiProxy
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (
            id.includes('/node_modules/vue/') ||
            id.includes('/node_modules/@vue/') ||
            id.includes('/node_modules/vue-router/')
          ) return 'vue-vendor'
        }
      }
    }
  }
})
