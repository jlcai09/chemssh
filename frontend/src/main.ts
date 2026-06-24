import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { ElLoading } from 'element-plus'
import 'element-plus/dist/index.css'
import './styles-liquid-glass.css'
import './styles.css'
import App from './App.vue'

const app = createApp(App)
app.use(createPinia())
app.directive('loading', ElLoading.directive)
app.mount('#app')
