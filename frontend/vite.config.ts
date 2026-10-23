import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { viteStaticCopy } from 'vite-plugin-static-copy'

// 保持现有后端代理配置。
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000'

// Cesium 在浏览器中加载 Worker、图片、控件 CSS 等静态文件的根路径。
const cesiumSource = 'node_modules/cesium/Build/Cesium'
const cesiumBaseUrl = 'cesium'

const cesiumStaticFolders = ['Workers', 'ThirdParty', 'Assets', 'Widgets'] as const

export default defineConfig({
  define: {
    CESIUM_BASE_URL: JSON.stringify(`/${cesiumBaseUrl}/`),
  },

  plugins: [
    vue(),

    viteStaticCopy({
      targets: cesiumStaticFolders.map((folder) => ({
        src: `${cesiumSource}/${folder}/**/*`,
        dest: cesiumBaseUrl,

        // 去除 node_modules/cesium/Build/Cesium 四层前缀，
        // 保留 Assets、Workers 等目录及其内部子目录。
        rename: { stripBase: 4 },
      })),
    }),
  ],

  server: {
    proxy: {
      '/api': apiProxyTarget,
    },
  },
})
