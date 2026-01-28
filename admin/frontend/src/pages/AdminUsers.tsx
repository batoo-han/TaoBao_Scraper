/**
 * Страница управления пользователями админки
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Dialog } from '@headlessui/react'
import { PlusIcon, PencilIcon, TrashIcon } from '@heroicons/react/24/outline'
import { useForm } from 'react-hook-form'
import { adminUsersApi } from '@/api/client'
import { useAuthStore } from '@/store/auth'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import type { AdminUser, PaginatedResponse } from '@/types'

interface UserForm {
  username: string
  password?: string
  email?: string
  display_name?: string
  telegram_id?: number
  role: 'admin' | 'user'
}

export default function AdminUsers() {
  const { user: currentUser } = useAuthStore()
  const queryClient = useQueryClient()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null)
  
  const { register, handleSubmit, reset, formState: { errors } } = useForm<UserForm>()
  
  // Загружаем пользователей
  const { data, isLoading } = useQuery<PaginatedResponse<AdminUser>>({
    queryKey: ['admin-users'],
    queryFn: () => adminUsersApi.list({ per_page: 100 }),
  })
  
  // Создание пользователя
  const createMutation = useMutation({
    mutationFn: adminUsersApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      closeModal()
    },
  })
  
  // Обновление пользователя
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) =>
      adminUsersApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      closeModal()
    },
  })
  
  // Удаление пользователя
  const deleteMutation = useMutation({
    mutationFn: adminUsersApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
    },
  })
  
  const openCreateModal = () => {
    setEditingUser(null)
    reset({ username: '', password: '', email: '', display_name: '', role: 'user' })
    setIsModalOpen(true)
  }
  
  const openEditModal = (user: AdminUser) => {
    setEditingUser(user)
    reset({
      username: user.username,
      email: user.email || '',
      display_name: user.display_name || '',
      telegram_id: user.telegram_id || undefined,
      role: user.role,
    })
    setIsModalOpen(true)
  }
  
  const closeModal = () => {
    setIsModalOpen(false)
    setEditingUser(null)
    reset()
  }
  
  const onSubmit = (data: UserForm) => {
    if (editingUser) {
      updateMutation.mutate({
        id: editingUser.id,
        data: {
          email: data.email || null,
          display_name: data.display_name || null,
          telegram_id: data.telegram_id || null,
          role: data.role,
          password: data.password || undefined,
        },
      })
    } else {
      createMutation.mutate(data)
    }
  }
  
  const handleDelete = (user: AdminUser) => {
    if (confirm(`Удалить пользователя ${user.username}?`)) {
      deleteMutation.mutate(user.id)
    }
  }
  
  return (
    <div className="space-y-6">
      {/* Заголовок */}
      <div className="sm:flex sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Администраторы</h1>
          <p className="mt-1 text-sm text-gray-500">
            Управление пользователями админ-панели
          </p>
        </div>
        <button onClick={openCreateModal} className="btn-primary mt-4 sm:mt-0">
          <PlusIcon className="h-5 w-5 mr-2" />
          Добавить
        </button>
      </div>
      
      {/* Таблица */}
      <div className="card overflow-hidden">
        {isLoading ? (
          <div className="p-8 flex justify-center">
            <LoadingSpinner size="lg" />
          </div>
        ) : !data?.items.length ? (
          <div className="p-8 text-center text-gray-500">
            Нет пользователей
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Логин</th>
                  <th>Email</th>
                  <th>Имя</th>
                  <th>Telegram</th>
                  <th>Роль</th>
                  <th>Статус</th>
                  <th></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {data.items.map((user) => (
                  <tr key={user.id}>
                    <td className="font-medium">{user.username}</td>
                    <td>{user.email || '-'}</td>
                    <td>{user.display_name || '-'}</td>
                    <td>{user.telegram_id || '-'}</td>
                    <td>
                      <span className={user.role === 'admin' ? 'badge-blue' : 'badge-gray'}>
                        {user.role === 'admin' ? 'Админ' : 'Пользователь'}
                      </span>
                    </td>
                    <td>
                      <span className={user.is_active ? 'badge-green' : 'badge-red'}>
                        {user.is_active ? 'Активен' : 'Заблокирован'}
                      </span>
                    </td>
                    <td>
                      <div className="flex gap-2">
                        <button
                          onClick={() => openEditModal(user)}
                          className="text-gray-400 hover:text-primary-600"
                        >
                          <PencilIcon className="h-5 w-5" />
                        </button>
                        {user.id !== currentUser?.id && (
                          <button
                            onClick={() => handleDelete(user)}
                            className="text-gray-400 hover:text-red-600"
                          >
                            <TrashIcon className="h-5 w-5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      
      {/* Модальное окно */}
      <Dialog open={isModalOpen} onClose={closeModal} className="relative z-50">
        <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
        
        <div className="fixed inset-0 flex items-center justify-center p-4">
          <Dialog.Panel className="mx-auto max-w-md w-full bg-white rounded-xl shadow-lg">
            <div className="p-6">
              <Dialog.Title className="text-lg font-medium mb-4">
                {editingUser ? 'Редактировать пользователя' : 'Новый пользователь'}
              </Dialog.Title>
              
              <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                <div>
                  <label className="form-label">Логин</label>
                  <input
                    type="text"
                    {...register('username', { required: 'Введите логин' })}
                    disabled={!!editingUser}
                    className="form-input"
                  />
                  {errors.username && <p className="form-error">{errors.username.message}</p>}
                </div>
                
                <div>
                  <label className="form-label">
                    Пароль {editingUser && '(оставьте пустым, чтобы не менять)'}
                  </label>
                  <input
                    type="password"
                    {...register('password', {
                      required: !editingUser ? 'Введите пароль' : false,
                      minLength: { value: 6, message: 'Минимум 6 символов' },
                    })}
                    className="form-input"
                  />
                  {errors.password && <p className="form-error">{errors.password.message}</p>}
                </div>
                
                <div>
                  <label className="form-label">Email</label>
                  <input type="email" {...register('email')} className="form-input" />
                </div>
                
                <div>
                  <label className="form-label">Имя</label>
                  <input type="text" {...register('display_name')} className="form-input" />
                </div>
                
                <div>
                  <label className="form-label">Telegram ID</label>
                  <input
                    type="number"
                    {...register('telegram_id', { valueAsNumber: true })}
                    className="form-input"
                  />
                </div>
                
                <div>
                  <label className="form-label">Роль</label>
                  <select {...register('role')} className="form-input">
                    <option value="user">Пользователь</option>
                    <option value="admin">Администратор</option>
                  </select>
                </div>
                
                <div className="flex gap-3 pt-4">
                  <button type="button" onClick={closeModal} className="btn-secondary flex-1">
                    Отмена
                  </button>
                  <button
                    type="submit"
                    disabled={createMutation.isPending || updateMutation.isPending}
                    className="btn-primary flex-1"
                  >
                    {(createMutation.isPending || updateMutation.isPending) && (
                      <LoadingSpinner size="sm" className="mr-2" />
                    )}
                    {editingUser ? 'Сохранить' : 'Создать'}
                  </button>
                </div>
              </form>
            </div>
          </Dialog.Panel>
        </div>
      </Dialog>
    </div>
  )
}
