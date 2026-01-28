/**
 * Zustand store для управления темой (светлая/тёмная)
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type Theme = 'light' | 'dark' | 'system'

interface ThemeState {
  // Выбранная тема
  theme: Theme
  
  // Методы
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

// Применяет тему к документу
const applyTheme = (theme: Theme) => {
  const root = document.documentElement
  
  if (theme === 'system') {
    // Определяем системную тему
    const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    root.classList.toggle('dark', systemDark)
  } else {
    root.classList.toggle('dark', theme === 'dark')
  }
}

// Слушаем изменения системной темы
if (typeof window !== 'undefined') {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    const state = useThemeStore.getState()
    if (state.theme === 'system') {
      document.documentElement.classList.toggle('dark', e.matches)
    }
  })
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      // Начальная тема — системная
      theme: 'dark',
      
      // Установить тему
      setTheme: (theme) => {
        set({ theme })
        applyTheme(theme)
      },
      
      // Переключить тему (light -> dark -> light)
      toggleTheme: () => {
        const current = get().theme
        const next = current === 'light' ? 'dark' : 'light'
        set({ theme: next })
        applyTheme(next)
      },
    }),
    {
      name: 'admin-theme-storage',
      onRehydrateStorage: () => (state) => {
        // Применяем тему после восстановления из localStorage
        if (state) {
          applyTheme(state.theme)
        }
      },
    }
  )
)

// Хук для получения текущей темы (resolved — учитывает system)
export const useResolvedTheme = () => {
  const theme = useThemeStore((state) => state.theme)
  
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  
  return theme
}
