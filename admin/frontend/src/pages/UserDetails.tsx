/**
 * Страница детальной информации о пользователе бота
 */

import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { 
  ArrowLeftIcon, 
  TrashIcon, 
  ShieldCheckIcon, 
  NoSymbolIcon 
} from '@heroicons/react/24/outline'
import { usersApi } from '@/api/client'
import { useIsAdmin } from '@/store/auth'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import type { BotUser } from '@/types'

export default function UserDetails() {
  const { userId } = useParams<{ userId: string }>()
  const isAdmin = useIsAdmin()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  
  // Загружаем пользователя
  // refetchOnMount: 'always' — всегда свежие данные при открытии страницы
  const { data: user, isLoading, error } = useQuery<BotUser>({
    queryKey: ['user', userId],
    queryFn: () => usersApi.get(Number(userId)),
    enabled: !!userId,
    refetchOnMount: 'always',
    staleTime: 0,
  })
  
  // Мутация для обновления лимитов
  const updateLimitsMutation = useMutation({
    mutationFn: (data: { daily_limit?: number; monthly_limit?: number }) =>
      usersApi.updateLimits(Number(userId), data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user', userId] })
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
  
  // Мутация для удаления
  const deleteMutation = useMutation({
    mutationFn: () => usersApi.delete(Number(userId)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      navigate('/users')
    },
  })
  
  // Мутации для списков доступа
  const whitelistMutation = useMutation({
    mutationFn: (add: boolean) =>
      add ? usersApi.addToWhitelist(Number(userId)) : usersApi.removeFromWhitelist(Number(userId)),
    onSuccess: () => {
      // Инвалидируем и пользователя, и список пользователей
      queryClient.invalidateQueries({ queryKey: ['user', userId] })
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
  
  const blacklistMutation = useMutation({
    mutationFn: (add: boolean) =>
      add ? usersApi.addToBlacklist(Number(userId)) : usersApi.removeFromBlacklist(Number(userId)),
    onSuccess: () => {
      // Инвалидируем и пользователя, и список пользователей
      queryClient.invalidateQueries({ queryKey: ['user', userId] })
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
  
  const handleDelete = () => {
    if (confirm(`Удалить пользователя ${user?.username ? '@' + user.username : userId}? Все данные будут потеряны.`)) {
      deleteMutation.mutate()
    }
  }
  
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    )
  }
  
  if (error || !user) {
    return (
      <div className="text-center py-12">
        <p className="text-red-600 mb-4">Пользователь не найден</p>
        <Link to="/users" className="btn-secondary">
          Вернуться к списку
        </Link>
      </div>
    )
  }
  
  return (
    <div className="space-y-6">
      {/* Навигация */}
      <div>
        <Link
          to="/users"
          className="inline-flex items-center text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
        >
          <ArrowLeftIcon className="h-4 w-4 mr-1" />
          К списку пользователей
        </Link>
      </div>
      
      {/* Заголовок */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {user.username ? `@${user.username}` : `ID: ${user.user_id}`}
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Зарегистрирован: {new Date(user.created_at).toLocaleDateString('ru-RU')}
          </p>
        </div>
        <div className="flex gap-2">
          {user.access.in_whitelist && (
            <span className="badge-green">В белом списке</span>
          )}
          {user.access.in_blacklist && (
            <span className="badge-red">В чёрном списке</span>
          )}
        </div>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Основная информация */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-medium">Основная информация</h2>
          </div>
          <div className="card-body space-y-4">
            <div className="flex justify-between">
              <span className="text-gray-500">Telegram ID</span>
              <span className="font-medium">{user.user_id}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Username</span>
              <span className="font-medium">{user.username || '-'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Всего запросов</span>
              <span className="font-medium">{user.total_requests}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Общие расходы</span>
              <span className="font-medium">${user.total_cost.toFixed(4)}</span>
            </div>
            {user.last_request_at && (
              <div className="flex justify-between">
                <span className="text-gray-500">Последний запрос</span>
                <span className="font-medium">
                  {new Date(user.last_request_at).toLocaleString('ru-RU')}
                </span>
              </div>
            )}
          </div>
        </div>
        
        {/* Настройки пользователя */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-medium">Настройки</h2>
          </div>
          <div className="card-body space-y-4">
            <div className="flex justify-between">
              <span className="text-gray-500">Подпись</span>
              <span className="font-medium text-right max-w-xs truncate">
                {user.settings?.signature || '-'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Валюта</span>
              <span className="font-medium">
                {user.settings?.default_currency?.toUpperCase() || 'CNY'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Курс</span>
              <span className="font-medium">
                {user.settings?.exchange_rate || '-'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Режим цен</span>
              <span className="font-medium">
                {user.settings?.price_mode || 'По умолчанию'}
              </span>
            </div>
          </div>
        </div>
        
        {/* Лимиты */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-medium">Лимиты</h2>
          </div>
          <div className="card-body space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-gray-500">Дневной лимит</span>
              <span className="font-medium">
                {user.settings?.daily_limit || 'Глобальный'}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-500">Месячный лимит</span>
              <span className="font-medium">
                {user.settings?.monthly_limit || 'Глобальный'}
              </span>
            </div>
            
            {user.limits && (
              <>
                <hr />
                <div className="flex justify-between">
                  <span className="text-gray-500">Запросов сегодня</span>
                  <span className="font-medium">{user.limits.day_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Запросов за месяц</span>
                  <span className="font-medium">{user.limits.month_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Расходы за день</span>
                  <span className="font-medium">${user.limits.day_cost.toFixed(4)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Расходы за месяц</span>
                  <span className="font-medium">${user.limits.month_cost.toFixed(4)}</span>
                </div>
              </>
            )}
            
            {/* Изменение лимитов (только для админов) */}
            {isAdmin && (
              <div className="pt-4 border-t space-y-3">
                <p className="text-sm font-medium text-gray-700">Установить лимиты</p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-gray-500">Дневной (0 = глоб.)</label>
                    <input
                      type="number"
                      min="0"
                      className="form-input"
                      defaultValue={user.settings?.daily_limit || 0}
                      onBlur={(e) => {
                        const value = parseInt(e.target.value) || 0
                        updateLimitsMutation.mutate({ daily_limit: value })
                      }}
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-500">Месячный (0 = глоб.)</label>
                    <input
                      type="number"
                      min="0"
                      className="form-input"
                      defaultValue={user.settings?.monthly_limit || 0}
                      onBlur={(e) => {
                        const value = parseInt(e.target.value) || 0
                        updateLimitsMutation.mutate({ monthly_limit: value })
                      }}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
        
        {/* Статус доступа */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-medium">Статус доступа</h2>
          </div>
          <div className="card-body space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-gray-500">В белом списке</span>
              <span className={user.access.in_whitelist ? 'badge-green' : 'badge-gray'}>
                {user.access.in_whitelist ? 'Да' : 'Нет'}
              </span>
            </div>
            {user.access.whitelist_type && (
              <div className="flex justify-between">
                <span className="text-gray-500">Тип записи</span>
                <span className="font-medium">{user.access.whitelist_type}</span>
              </div>
            )}
            <div className="flex justify-between items-center">
              <span className="text-gray-500">В чёрном списке</span>
              <span className={user.access.in_blacklist ? 'badge-red' : 'badge-gray'}>
                {user.access.in_blacklist ? 'Да' : 'Нет'}
              </span>
            </div>
            {user.access.blacklist_type && (
              <div className="flex justify-between">
                <span className="text-gray-500">Тип записи</span>
                <span className="font-medium">{user.access.blacklist_type}</span>
              </div>
            )}
            
            {/* Кнопки управления доступом (только для админов) */}
            {isAdmin && (
              <div className="pt-4 border-t space-y-3">
                <p className="text-sm font-medium text-gray-700">Управление доступом</p>
                <div className="flex flex-wrap gap-2">
                  {/* Белый список */}
                  <button
                    onClick={() => whitelistMutation.mutate(!user.access.in_whitelist)}
                    disabled={whitelistMutation.isPending}
                    className={`btn-sm ${
                      user.access.in_whitelist 
                        ? 'bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300 hover:bg-green-200 dark:hover:bg-green-900/70' 
                        : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }`}
                  >
                    <ShieldCheckIcon className="h-4 w-4 mr-1" />
                    {user.access.in_whitelist ? 'Убрать из белого' : 'В белый список'}
                  </button>
                  
                  {/* Блокировка */}
                  <button
                    onClick={() => blacklistMutation.mutate(!user.access.in_blacklist)}
                    disabled={blacklistMutation.isPending}
                    className={`btn-sm ${
                      user.access.in_blacklist 
                        ? 'bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/70' 
                        : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }`}
                  >
                    <NoSymbolIcon className="h-4 w-4 mr-1" />
                    {user.access.in_blacklist ? 'Разблокировать' : 'Заблокировать'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
        
        {/* Опасная зона (только для админов) */}
        {isAdmin && (
          <div className="card border-red-200 dark:border-red-900/50 lg:col-span-2">
            <div className="card-header bg-red-50 dark:bg-red-900/30">
              <h2 className="text-lg font-medium text-red-700 dark:text-red-400">Опасная зона</h2>
            </div>
            <div className="card-body">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-gray-900 dark:text-gray-100">Удалить пользователя</p>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Удаление пользователя приведёт к потере всех его данных, настроек и статистики.
                  </p>
                </div>
                <button
                  onClick={handleDelete}
                  disabled={deleteMutation.isPending}
                  className="btn-danger"
                >
                  <TrashIcon className="h-5 w-5 mr-2" />
                  {deleteMutation.isPending ? 'Удаление...' : 'Удалить'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
