/**
 * Страница входа в админ-панель
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { useAuthStore } from '@/store/auth'
import { authApi } from '@/api/client'
import LoadingSpinner from '@/components/ui/LoadingSpinner'

interface LoginForm {
  username: string
  password: string
}

export default function Login() {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { isAuthenticated, login } = useAuthStore()
  const navigate = useNavigate()
  
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>()
  
  // Редирект если уже авторизован
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/')
    }
  }, [isAuthenticated, navigate])
  
  // Обработка входа по логину/паролю
  const onSubmit = async (data: LoginForm) => {
    setIsLoading(true)
    setError(null)
    
    try {
      const response = await authApi.login(data.username, data.password)
      login(response.user, response.access_token, response.refresh_token)
      navigate('/')
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      setError(error.response?.data?.detail || 'Ошибка входа. Проверьте логин и пароль.')
    } finally {
      setIsLoading(false)
    }
  }
  
  // Обработка входа через Telegram
  const handleTelegramAuth = async (telegramUser: Record<string, unknown>) => {
    setIsLoading(true)
    setError(null)
    
    try {
      const response = await authApi.telegramLogin(telegramUser)
      login(response.user, response.access_token, response.refresh_token)
      navigate('/')
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      setError(error.response?.data?.detail || 'Ошибка входа через Telegram')
    } finally {
      setIsLoading(false)
    }
  }
  
  // Инициализация Telegram Login Widget
  useEffect(() => {
    // Добавляем callback в глобальный scope
    (window as unknown as Record<string, unknown>).onTelegramAuth = handleTelegramAuth
    
    return () => {
      delete (window as unknown as Record<string, unknown>).onTelegramAuth
    }
  }, [])
  
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 py-12 px-4 sm:px-6 lg:px-8 transition-colors duration-200">
      <div className="max-w-md w-full space-y-8">
        {/* Заголовок */}
        <div>
          <h1 className="text-center text-3xl font-bold text-gray-900 dark:text-gray-100">
            Taobao Bot Admin
          </h1>
          <p className="mt-2 text-center text-sm text-gray-600 dark:text-gray-400">
            Войдите в панель управления
          </p>
        </div>
        
        {/* Форма входа */}
        <div className="card">
          <div className="card-body">
            {/* Ошибка */}
            {error && (
              <div className="mb-4 p-3 rounded-lg bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 text-sm">
                {error}
              </div>
            )}
            
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
              {/* Логин */}
              <div>
                <label htmlFor="username" className="form-label">
                  Логин
                </label>
                <input
                  id="username"
                  type="text"
                  autoComplete="username"
                  {...register('username', {
                    required: 'Введите логин',
                    minLength: { value: 3, message: 'Минимум 3 символа' },
                  })}
                  className="form-input"
                  disabled={isLoading}
                />
                {errors.username && (
                  <p className="form-error">{errors.username.message}</p>
                )}
              </div>
              
              {/* Пароль */}
              <div>
                <label htmlFor="password" className="form-label">
                  Пароль
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  {...register('password', {
                    required: 'Введите пароль',
                    minLength: { value: 6, message: 'Минимум 6 символов' },
                  })}
                  className="form-input"
                  disabled={isLoading}
                />
                {errors.password && (
                  <p className="form-error">{errors.password.message}</p>
                )}
              </div>
              
              {/* Кнопка входа */}
              <button
                type="submit"
                disabled={isLoading}
                className="btn-primary w-full"
              >
                {isLoading ? (
                  <LoadingSpinner size="sm" className="mr-2" />
                ) : null}
                Войти
              </button>
            </form>
            
            {/* Разделитель */}
            <div className="mt-6">
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-300 dark:border-gray-600" />
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-2 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400">или</span>
                </div>
              </div>
            </div>
            
            {/* Telegram Login Widget */}
            <div className="mt-6 flex justify-center">
              <div id="telegram-login-container">
                {/* 
                  Telegram Login Widget будет инициализирован через JavaScript.
                  В продакшене замените BOT_USERNAME на реальное имя бота.
                */}
                <script
                  async
                  src="https://telegram.org/js/telegram-widget.js?22"
                  data-telegram-login="YOUR_BOT_USERNAME"
                  data-size="large"
                  data-radius="8"
                  data-onauth="onTelegramAuth(user)"
                  data-request-access="write"
                />
                <noscript>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Для входа через Telegram включите JavaScript
                  </p>
                </noscript>
              </div>
            </div>
            
            <p className="mt-4 text-center text-xs text-gray-500 dark:text-gray-400">
              Если у вас нет аккаунта, обратитесь к администратору
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
