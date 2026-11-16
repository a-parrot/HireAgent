import { watchEffect } from 'vue'
import { can } from '@/stores/auth'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import './styles/main.css'

const app = createApp(App)
const permissionEffects = new WeakMap<HTMLElement, () => void>()
app.directive('permission', {
  mounted(el: HTMLElement, binding) { permissionEffects.set(el, watchEffect(() => { el.hidden = !can(binding.value); el.style.display = can(binding.value) ? '' : 'none' })) },
  updated(el: HTMLElement, binding) { el.hidden = !can(binding.value); el.style.display = can(binding.value) ? '' : 'none' },
  unmounted(el: HTMLElement) { permissionEffects.get(el)?.(); permissionEffects.delete(el) },
})
app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })
app.mount('#app')
