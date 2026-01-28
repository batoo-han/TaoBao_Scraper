/**
 * Главный компонент приложения
 */

import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import { authApi } from '@/api/client'

// Layouts
import MainLayout from '@/components/layouts/MainLayout'

// Pages
import Login from '@/pages/Login'
import Dashboard from '@/pages/Dashboard'
import Users from '@/pages/Users'
import UserDetails from '@/pages/UserDetails'
import Statistics from '@/pages/Statistics'
import Settings from '@/pages/Settings'
import Profile from '@/pages/Profile'
import AdminUsers from '@/pages/AdminUsers'

// Components
import LoadingSpinner from '@/components/ui/LoadingSpinner'

/**
 * Компонент защищённого маршрута
 */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuthStore()
  
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  
  return <>{children}</>
}

/**
 * Компонент маршрута только для админов
 */
function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuthStore()
  
  if (user?.role !== 'admin') {
    return <Navigate to="/" replace />
  }
  
  return <>{children}</>
}

export default function App() {
  const { accessToken, refreshToken, login, logout, setLoading } = useAuthStore()
  
  // Проверяем авторизацию при загрузке
  useEffect(() => {
    const checkAuth = async () => {
      if (!accessToken || !refreshToken) {
        setLoading(false)
        return
      }
      
      try {
        // Пытаемся получить текущего пользователя
        const user = await authApi.me()
        login(user, accessToken, refreshToken)
      } catch (error) {
        // Токен невалидный, выходим
        logout()
      }
    }
    
    checkAuth()
  }, [])
  
  return (
    <Routes>
      {/* Публичные маршруты */}
      <Route path="/login" element={<Login />} />
      
      {/* Защищённые маршруты */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <MainLayout />
          </ProtectedRoute>
        }
      >
        {/* Dashboard */}
        <Route index element={<Dashboard />} />
        
        {/* Пользователи бота */}
        <Route path="users" element={<Users />} />
        <Route path="users/:userId" element={<UserDetails />} />
        
        {/* Статистика */}
        <Route path="statistics" element={<Statistics />} />
        
        {/* Настройки (только для админов) */}
        <Route
          path="settings"
          element={
            <AdminRoute>
              <Settings />
            </AdminRoute>
          }
        />
        
        {/* Управление админами (только для админов) */}
        <Route
          path="admin-users"
          element={
            <AdminRoute>
              <AdminUsers />
            </AdminRoute>
          }
        />
        
        {/* Профиль */}
        <Route path="profile" element={<Profile />} />
      </Route>
      
      {/* 404 */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
