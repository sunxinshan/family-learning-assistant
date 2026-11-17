import { BrowserRouter } from 'react-router-dom'
import { AppRouter } from './router/AppRouter'
import { AppStoreProvider } from './stores/AppStore'

// 子路径部署（base=/zijixue/）时，路由 basename 必须是 /zijixue，
// 否则刷新 /zijixue/xxx 会匹配不到任何路由。BASE_URL 结尾带 /，这里去掉。
const routerBasename = import.meta.env.BASE_URL.replace(/\/+$/, '') || '/'

export const App = () => (
  <BrowserRouter basename={routerBasename}>
    <AppStoreProvider>
      <AppRouter />
    </AppStoreProvider>
  </BrowserRouter>
)
