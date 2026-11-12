// 应用入口：注册全局 UI 组件和样式，然后挂载根组件。
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import 'leaflet/dist/leaflet.css'
import './style.css'
import App from './App.vue'

// use 注册 Element Plus；mount 将 App.vue 渲染到 index.html 中的 #app 节点。
createApp(App).use(ElementPlus).mount('#app')
