import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles-liquid-glass.css'
import './styles.css'
import App from './App.vue'
import { initializeClientSession } from './api/clientSession'

async function bootstrap() {
  await initializeClientSession()
  createApp(App).use(ElementPlus).mount('#app')
}

bootstrap().catch(error => {
  console.error('Failed to initialize application:', error)
  createApp(App).use(ElementPlus).mount('#app')
})
