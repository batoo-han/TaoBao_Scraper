/**
 * Zustand store для управления аутентификацией
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AdminUser } from '@/types'

interface AuthState {
  // Данные пользователя
  user: AdminUser | null
  
  // Токены
  accessToken: string | null
  refreshToken: string | null
  
  // Флаги
  isAuthenticated: boolean
  isLoading: boolean
  
  // Методы
  setUser: (user: AdminUser) => void
  setTokens: (accessToken: string, refreshToken: string) => void
  login: (user: AdminUser, accessToken: string, refreshToken: string) => void
  logout: () => void
  setLoading: (loading: boolean) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      // Начальное состояние
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: true,
      
      // Установить пользователя
      setUser: (user) => set({ user }),
      
      // Установить токены
      setTokens: (accessToken, refreshToken) => 
        set({ accessToken, refreshToken }),
      
      // Вход в систему
      login: (user, accessToken, refreshToken) => 
        set({
          user,
          accessToken,
          refreshToken,
          isAuthenticated: true,
          isLoading: false,
        }),
      
      // Выход из системы
      logout: () => 
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          isLoading: false,
        }),
      
      // Установить флаг загрузки
      setLoading: (isLoading) => set({ isLoading }),
    }),
    {
      // Настройки персистенции
      name: 'admin-auth-storage',
      // Сохраняем только токены
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
      }),
    }
  )
)

// Хелпер для проверки роли администратора
export const useIsAdmin = () => {
  const user = useAuthStore((state) => state.user)
  return user?.role === 'admin'
}
