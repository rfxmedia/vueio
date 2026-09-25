import { copyFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'


// Keep decoder workers local and in sync with the locked Three.js release.
for (const [source, target] of [
  ['draco/gltf/draco_wasm_wrapper.js', 'draco/draco_wasm_wrapper.js'],
  ['draco/gltf/draco_decoder.wasm', 'draco/draco_decoder.wasm'],
  ['basis/basis_transcoder.js', 'basis/basis_transcoder.js'],
  ['basis/basis_transcoder.wasm', 'basis/basis_transcoder.wasm'],
]) {
  const destination = resolve(import.meta.dirname, 'public/model-decoders', target)
  mkdirSync(dirname(destination), { recursive: true })
  copyFileSync(resolve(import.meta.dirname, 'node_modules/three/examples/jsm/libs', source), destination)
}

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
