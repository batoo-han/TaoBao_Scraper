/**
 * HTTP клиент для работы с API админ-панели
 */

import axios, { AxiosError, AxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/store/auth'

// Базовый URL API
const API_BASE_URL = '/api'

// Создаём экземпляр axios
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000, // 30 секунд
})

// Интерсептор для добавления токена авторизации
apiClient.interceptors.request.use(
  (config) => {
    const token = useAuthStore.getState().accessToken
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Интерсептор для обработки ответов и обновления токенов
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean }
    
    // Если получили 401 и это не повторный запрос
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      
      const refreshToken = useAuthStore.getState().refreshToken
      
      // Если есть refresh token, пытаемся обновить
      if (refreshToken) {
        try {
          const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
            refresh_token: refreshToken,
          })
          
          const { access_token, refresh_token: newRefreshToken } = response.data
          
          // Обновляем токены в store
          useAuthStore.getState().setTokens(access_token, newRefreshToken)
          
          // Повторяем оригинальный запрос с новым токеном
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${access_token}`
          }
          
          return apiClient(originalRequest)
        } catch (refreshError) {
          // Если обновление не удалось, выходим
          useAuthStore.getState().logout()
          window.location.href = '/login'
          return Promise.reject(refreshError)
        }
      } else {
        // Нет refresh token, выходим
        useAuthStore.getState().logout()
        window.location.href = '/login'
      }
    }
    
    return Promise.reject(error)
  }
)

// API методы

// === Аутентификация ===

export const authApi = {
  login: async (username: string, password: string) => {
    const response = await apiClient.post('/auth/login', { username, password })
    return response.data
  },
  
  telegramLogin: async (data: Record<string, unknown>) => {
    const response = await apiClient.post('/auth/telegram', data)
    return response.data
  },
  
  refresh: async (refreshToken: string) => {
    const response = await apiClient.post('/auth/refresh', { refresh_token: refreshToken })
    return response.data
  },
  
  logout: async () => {
    const response = await apiClient.post('/auth/logout')
    return response.data
  },
  
  changePassword: async (currentPassword: string, newPassword: string) => {
    const response = await apiClient.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
    return response.data
  },
  
  me: async () => {
    const response = await apiClient.get('/auth/me')
    return response.data
  },
}

// === Пользователи бота ===

export const usersApi = {
  list: async (params?: { page?: number; per_page?: number; search?: string }) => {
    const response = await apiClient.get('/users/', { params })
    return response.data
  },
  
  get: async (userId: number) => {
    const response = await apiClient.get(`/users/${userId}`)
    return response.data
  },
  
  create: async (data: { user_id: number; username?: string }) => {
    const response = await apiClient.post('/users/', data)
    return response.data
  },
  
  delete: async (userId: number) => {
    const response = await apiClient.delete(`/users/${userId}`)
    return response.data
  },
  
  updateSettings: async (userId: number, data: Record<string, unknown>) => {
    const response = await apiClient.put(`/users/${userId}/settings`, data)
    return response.data
  },
  
  updateLimits: async (userId: number, data: { daily_limit?: number; monthly_limit?: number }) => {
    const response = await apiClient.put(`/users/${userId}/limits`, data)
    return response.data
  },
  
  // Управление списками доступа
  addToWhitelist: async (userId: number) => {
    const response = await apiClient.post(`/users/${userId}/whitelist`)
    return response.data
  },
  
  removeFromWhitelist: async (userId: number) => {
    const response = await apiClient.delete(`/users/${userId}/whitelist`)
    return response.data
  },
  
  addToBlacklist: async (userId: number) => {
    const response = await apiClient.post(`/users/${userId}/blacklist`)
    return response.data
  },
  
  removeFromBlacklist: async (userId: number) => {
    const response = await apiClient.delete(`/users/${userId}/blacklist`)
    return response.data
  },
}

// === Статистика ===

export const statsApi = {
  overview: async () => {
    const response = await apiClient.get('/stats/overview')
    return response.data
  },
  
  requests: async (params?: {
    page?: number
    per_page?: number
    date_from?: string
    date_to?: string
    platform?: string
    user_id?: number
  }) => {
    const response = await apiClient.get('/stats/requests', { params })
    return response.data
  },
  
  costs: async (params?: { date_from?: string; date_to?: string }) => {
    const response = await apiClient.get('/stats/costs', { params })
    return response.data
  },
  
  platforms: async (params?: { date_from?: string; date_to?: string }) => {
    const response = await apiClient.get('/stats/platforms', { params })
    return response.data
  },
  
  topUsers: async (params?: { date_from?: string; date_to?: string; limit?: number }) => {
    const response = await apiClient.get('/stats/users/top', { params })
    return response.data
  },
  
  peaks: async (params?: { date_from?: string; date_to?: string }) => {
    const response = await apiClient.get('/stats/peaks', { params })
    return response.data
  },
}

// === Настройки ===

export const settingsApi = {
  getAdmin: async () => {
    const response = await apiClient.get('/settings/admin')
    return response.data
  },
  
  updateAdmin: async (data: Record<string, unknown>) => {
    const response = await apiClient.put('/settings/admin', data)
    return response.data
  },
  
  getLLM: async () => {
    const response = await apiClient.get('/settings/llm')
    return response.data
  },
  
  updateLLM: async (data: Record<string, unknown>) => {
    const response = await apiClient.put('/settings/llm', data)
    return response.data
  },
  
  getLimits: async () => {
    const response = await apiClient.get('/settings/limits')
    return response.data
  },
  
  updateLimits: async (data: Record<string, unknown>) => {
    const response = await apiClient.put('/settings/limits', data)
    return response.data
  },
  
  getFlags: async () => {
    const response = await apiClient.get('/settings/flags')
    return response.data
  },
  
  updateFlags: async (data: Record<string, unknown>) => {
    const response = await apiClient.put('/settings/flags', data)
    return response.data
  },
}

// === Контроль доступа ===

export const accessApi = {
  get: async () => {
    const response = await apiClient.get('/access/')
    return response.data
  },
  
  update: async (data: Record<string, unknown>) => {
    const response = await apiClient.put('/access/', data)
    return response.data
  },
}

// === Пользователи админки ===

export const adminUsersApi = {
  list: async (params?: { page?: number; per_page?: number; search?: string; role?: string }) => {
    const response = await apiClient.get('/admin-users/', { params })
    return response.data
  },
  
  get: async (id: number) => {
    const response = await apiClient.get(`/admin-users/${id}`)
    return response.data
  },
  
  create: async (data: Record<string, unknown>) => {
    const response = await apiClient.post('/admin-users/', data)
    return response.data
  },
  
  update: async (id: number, data: Record<string, unknown>) => {
    const response = await apiClient.put(`/admin-users/${id}`, data)
    return response.data
  },
  
  delete: async (id: number) => {
    const response = await apiClient.delete(`/admin-users/${id}`)
    return response.data
  },
}

export default apiClient
