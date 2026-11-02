import { BrowserRouter } from 'react-router-dom'
import { AppRouter } from './router/AppRouter'
import { AppStoreProvider } from './stores/AppStore'

export const App = () => (
  <BrowserRouter>
    <AppStoreProvider>
      <AppRouter />
    </AppStoreProvider>
  </BrowserRouter>
)
