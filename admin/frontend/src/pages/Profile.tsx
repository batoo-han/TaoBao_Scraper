/**
 * Страница профиля пользователя
 */

import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useMutation } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth'
import { authApi } from '@/api/client'
import LoadingSpinner from '@/components/ui/LoadingSpinner'

interface ChangePasswordForm {
  currentPassword: string
  newPassword: string
  confirmPassword: string
}

export default function Profile() {
  const { user } = useAuthStore()
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<ChangePasswordForm>()
  
  const newPassword = watch('newPassword')
  
  const changePasswordMutation = useMutation({
    mutationFn: (data: { currentPassword: string; newPassword: string }) =>
      authApi.changePassword(data.currentPassword, data.newPassword),
    onSuccess: () => {
      setSuccessMessage('Пароль успешно изменён')
      setErrorMessage(null)
      reset()
      setTimeout(() => setSuccessMessage(null), 5000)
    },
    onError: (err: unknown) => {
      const error = err as { response?: { data?: { detail?: string } } }
      setErrorMessage(error.response?.data?.detail || 'Ошибка смены пароля')
      setSuccessMessage(null)
    },
  })
  
  const onSubmit = (data: ChangePasswordForm) => {
    changePasswordMutation.mutate({
      currentPassword: data.currentPassword,
      newPassword: data.newPassword,
    })
  }
  
  return (
    <div className="space-y-6">
      {/* Заголовок */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Профиль</h1>
        <p className="mt-1 text-sm text-gray-500">
          Информация о вашем аккаунте
        </p>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Информация о пользователе */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-medium">Данные аккаунта</h2>
          </div>
          <div className="card-body space-y-4">
            <div className="flex justify-between">
              <span className="text-gray-500">Логин</span>
              <span className="font-medium">{user?.username}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Email</span>
              <span className="font-medium">{user?.email || '-'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Имя</span>
              <span className="font-medium">{user?.display_name || '-'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Telegram ID</span>
              <span className="font-medium">{user?.telegram_id || 'Не привязан'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Роль</span>
              <span className={user?.role === 'admin' ? 'badge-blue' : 'badge-gray'}>
                {user?.role === 'admin' ? 'Администратор' : 'Пользователь'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Дата регистрации</span>
              <span className="font-medium">
                {user?.created_at ? new Date(user.created_at).toLocaleDateString('ru-RU') : '-'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Последний вход</span>
              <span className="font-medium">
                {user?.last_login ? new Date(user.last_login).toLocaleString('ru-RU') : '-'}
              </span>
            </div>
          </div>
        </div>
        
        {/* Смена пароля */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-medium">Смена пароля</h2>
          </div>
          <div className="card-body">
            {/* Сообщения */}
            {successMessage && (
              <div className="mb-4 p-3 bg-green-50 text-green-700 rounded-lg text-sm">
                {successMessage}
              </div>
            )}
            {errorMessage && (
              <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">
                {errorMessage}
              </div>
            )}
            
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <div>
                <label className="form-label">Текущий пароль</label>
                <input
                  type="password"
                  {...register('currentPassword', {
                    required: 'Введите текущий пароль',
                  })}
                  className="form-input"
                />
                {errors.currentPassword && (
                  <p className="form-error">{errors.currentPassword.message}</p>
                )}
              </div>
              
              <div>
                <label className="form-label">Новый пароль</label>
                <input
                  type="password"
                  {...register('newPassword', {
                    required: 'Введите новый пароль',
                    minLength: { value: 6, message: 'Минимум 6 символов' },
                  })}
                  className="form-input"
                />
                {errors.newPassword && (
                  <p className="form-error">{errors.newPassword.message}</p>
                )}
              </div>
              
              <div>
                <label className="form-label">Подтвердите пароль</label>
                <input
                  type="password"
                  {...register('confirmPassword', {
                    required: 'Подтвердите пароль',
                    validate: (value) =>
                      value === newPassword || 'Пароли не совпадают',
                  })}
                  className="form-input"
                />
                {errors.confirmPassword && (
                  <p className="form-error">{errors.confirmPassword.message}</p>
                )}
              </div>
              
              <button
                type="submit"
                disabled={changePasswordMutation.isPending}
                className="btn-primary w-full"
              >
                {changePasswordMutation.isPending ? (
                  <LoadingSpinner size="sm" className="mr-2" />
                ) : null}
                Сменить пароль
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
