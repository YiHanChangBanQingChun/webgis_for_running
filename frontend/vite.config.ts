import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Keep FastAPI as the default for the original development script. The
// Spring Boot launcher overrides this value with http://127.0.0.1:8080.
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': apiProxyTarget,
    },
  },
})
