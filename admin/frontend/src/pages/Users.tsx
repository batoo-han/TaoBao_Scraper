/**
 * Страница управления пользователями бота
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { 
  MagnifyingGlassIcon, 
  ChevronLeftIcon, 
  ChevronRightIcon,
  PlusIcon,
  TrashIcon,
  ShieldCheckIcon,
  NoSymbolIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { usersApi } from '@/api/client'
import { useIsAdmin } from '@/store/auth'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import type { BotUser, PaginatedResponse } from '@/types'

export default function Users() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)
  const [newUserId, setNewUserId] = useState('')
  const [newUsername, setNewUsername] = useState('')
  const isAdmin = useIsAdmin()
  const queryClient = useQueryClient()
  
  // Загружаем пользователей
  // refetchOnMount: 'always' — перезапрос при каждом возврате на страницу
  // staleTime: 0 — данные сразу считаются устаревшими
  const { data, isLoading, error } = useQuery<PaginatedResponse<BotUser>>({
    queryKey: ['users', page, search],
    queryFn: () => usersApi.list({ page, per_page: 20, search: search || undefined }),
    refetchOnMount: 'always',
    staleTime: 0,
  })
  
  // Мутации
  const createMutation = useMutation({
    mutationFn: (data: { user_id: number; username?: string }) => usersApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setShowAddModal(false)
      setNewUserId('')
      setNewUsername('')
    },
  })
  
  const deleteMutation = useMutation({
    mutationFn: (userId: number) => usersApi.delete(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
  
  const whitelistMutation = useMutation({
    mutationFn: ({ userId, add }: { userId: number; add: boolean }) =>
      add ? usersApi.addToWhitelist(userId) : usersApi.removeFromWhitelist(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
  
  const blacklistMutation = useMutation({
    mutationFn: ({ userId, add }: { userId: number; add: boolean }) =>
      add ? usersApi.addToBlacklist(userId) : usersApi.removeFromBlacklist(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
  
  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSearch(searchInput)
    setPage(1)
  }
  
  const handleAddUser = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newUserId) return
    createMutation.mutate({
      user_id: parseInt(newUserId),
      username: newUsername || undefined,
    })
  }
  
  const handleDelete = (userId: number, username?: string) => {
    if (confirm(`Удалить пользователя ${username ? '@' + username : userId}? Все данные будут потеряны.`)) {
      deleteMutation.mutate(userId)
    }
  }
  
  return (
    <div className="space-y-6">
      {/* Заголовок */}
      <div className="sm:flex sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Пользователи бота</h1>
          <p className="mt-1 text-sm text-gray-500">
            Управление пользователями Telegram-бота
          </p>
        </div>
        {isAdmin && (
          <button
            onClick={() => setShowAddModal(true)}
            className="btn-primary mt-4 sm:mt-0"
          >
            <PlusIcon className="h-5 w-5 mr-2" />
            Добавить
          </button>
        )}
      </div>
      
      {/* Поиск */}
      <div className="card">
        <div className="card-body">
          <form onSubmit={handleSearch} className="flex gap-4">
            <div className="flex-1 relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" />
              </div>
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Поиск по ID или username..."
                className="form-input pl-10"
              />
            </div>
            <button type="submit" className="btn-primary">
              Найти
            </button>
          </form>
        </div>
      </div>
      
      {/* Таблица */}
      <div className="card overflow-hidden">
        {isLoading ? (
          <div className="p-8 flex justify-center">
            <LoadingSpinner size="lg" />
          </div>
        ) : error ? (
          <div className="p-8 text-center text-red-600">
            Ошибка загрузки данных
          </div>
        ) : !data?.items.length ? (
          <div className="p-8 text-center text-gray-500">
            Пользователи не найдены
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Username</th>
                    <th>Дата регистрации</th>
                    <th>Запросов</th>
                    <th>Расходы</th>
                    <th>Статус</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {data.items.map((user) => (
                    <tr key={user.user_id}>
                      <td className="font-medium">{user.user_id}</td>
                      <td>{user.username ? `@${user.username}` : '-'}</td>
                      <td>
                        {new Date(user.created_at).toLocaleDateString('ru-RU')}
                      </td>
                      <td>{user.total_requests}</td>
                      <td>${user.total_cost.toFixed(4)}</td>
                      <td>
                        <div className="flex gap-1">
                          {user.access.in_whitelist && (
                            <span className="badge-green">В белом</span>
                          )}
                          {user.access.in_blacklist && (
                            <span className="badge-red">В чёрном</span>
                          )}
                          {!user.access.in_whitelist && !user.access.in_blacklist && (
                            <span className="badge-gray">Обычный</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <div className="flex items-center gap-2">
                          <Link
                            to={`/users/${user.user_id}`}
                            className="text-primary-600 hover:text-primary-800 text-sm"
                          >
                            Подробнее
                          </Link>
                          {isAdmin && (
                            <>
                              {/* Кнопка белого списка */}
                              <button
                                onClick={() => whitelistMutation.mutate({ 
                                  userId: user.user_id, 
                                  add: !user.access.in_whitelist 
                                })}
                                className={`p-1 rounded ${
                                  user.access.in_whitelist 
                                    ? 'text-green-600 hover:bg-green-50' 
                                    : 'text-gray-400 hover:bg-gray-50'
                                }`}
                                title={user.access.in_whitelist ? 'Убрать из белого списка' : 'Добавить в белый список'}
                              >
                                <ShieldCheckIcon className="h-5 w-5" />
                              </button>
                              {/* Кнопка блокировки */}
                              <button
                                onClick={() => blacklistMutation.mutate({ 
                                  userId: user.user_id, 
                                  add: !user.access.in_blacklist 
                                })}
                                className={`p-1 rounded ${
                                  user.access.in_blacklist 
                                    ? 'text-red-600 hover:bg-red-50' 
                                    : 'text-gray-400 hover:bg-gray-50'
                                }`}
                                title={user.access.in_blacklist ? 'Разблокировать' : 'Заблокировать'}
                              >
                                <NoSymbolIcon className="h-5 w-5" />
                              </button>
                              {/* Кнопка удаления */}
                              <button
                                onClick={() => handleDelete(user.user_id, user.username || undefined)}
                                className="p-1 rounded text-gray-400 hover:text-red-600 hover:bg-red-50"
                                title="Удалить пользователя"
                              >
                                <TrashIcon className="h-5 w-5" />
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            
            {/* Пагинация */}
            <div className="px-6 py-4 border-t border-gray-200 flex items-center justify-between">
              <div className="text-sm text-gray-500">
                Показано {(page - 1) * 20 + 1} - {Math.min(page * 20, data.total)} из {data.total}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="btn-secondary"
                >
                  <ChevronLeftIcon className="h-5 w-5" />
                </button>
                <span className="px-4 py-2 text-sm">
                  {page} / {data.pages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                  disabled={page === data.pages}
                  className="btn-secondary"
                >
                  <ChevronRightIcon className="h-5 w-5" />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
      
      {/* Модальное окно добавления пользователя */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex items-center justify-center min-h-screen px-4">
            {/* Затемнение */}
            <div 
              className="fixed inset-0 bg-black/30 dark:bg-black/50" 
              onClick={() => setShowAddModal(false)}
            />
            
            {/* Модальное окно */}
            <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">Добавить пользователя</h3>
                <button 
                  onClick={() => setShowAddModal(false)}
                  className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                >
                  <XMarkIcon className="h-6 w-6" />
                </button>
              </div>
              
              <form onSubmit={handleAddUser} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Telegram ID *
                  </label>
                  <input
                    type="number"
                    value={newUserId}
                    onChange={(e) => setNewUserId(e.target.value)}
                    className="form-input"
                    placeholder="123456789"
                    required
                  />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Username (без @)
                  </label>
                  <input
                    type="text"
                    value={newUsername}
                    onChange={(e) => setNewUsername(e.target.value)}
                    className="form-input"
                    placeholder="username"
                  />
                </div>
                
                {createMutation.isError && (
                  <div className="text-sm text-red-600 dark:text-red-400">
                    Ошибка: пользователь с таким ID уже существует
                  </div>
                )}
                
                <div className="flex gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowAddModal(false)}
                    className="btn-secondary flex-1"
                  >
                    Отмена
                  </button>
                  <button
                    type="submit"
                    disabled={createMutation.isPending}
                    className="btn-primary flex-1"
                  >
                    {createMutation.isPending ? 'Добавление...' : 'Добавить'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
