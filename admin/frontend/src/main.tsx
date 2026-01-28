import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'
import { useThemeStore } from './store/theme'

// Применяем сохранённую тему при загрузке (до рендеринга, чтобы избежать мерцания)
const savedTheme = localStorage.getItem('admin-theme-storage')
if (savedTheme) {
  try {
    const { state } = JSON.parse(savedTheme)
    const theme = state?.theme || 'dark'
    if (theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
      document.documentElement.classList.add('dark')
    }
  } catch {
    document.documentElement.classList.add('dark')
  }
} else {
  // По умолчанию — тёмная тема
  document.documentElement.classList.add('dark')
}

// Создаём QueryClient для React Query
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Время кэширования данных (30 секунд — данные актуальны недолго)
      staleTime: 30 * 1000,
      // Повторные попытки при ошибке
      retry: 1,
      // Перезапрос при фокусе на окне (актуализация при возврате в браузер)
      refetchOnWindowFocus: true,
      // Перезапрос при восстановлении сети
      refetchOnReconnect: true,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
