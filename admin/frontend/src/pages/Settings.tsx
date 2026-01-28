/**
 * Страница настроек бота (только для админов)
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsApi, accessApi } from '@/api/client'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import type { AdminSettings, AccessListsResponse } from '@/types'

export default function Settings() {
  const queryClient = useQueryClient()
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  
  // Загружаем настройки
  const { data: settings, isLoading: settingsLoading } = useQuery<AdminSettings>({
    queryKey: ['settings', 'admin'],
    queryFn: settingsApi.getAdmin,
  })
  
  // Загружаем списки доступа
  const { data: accessLists, isLoading: accessLoading } = useQuery<AccessListsResponse>({
    queryKey: ['access'],
    queryFn: accessApi.get,
  })
  
  // Мутация для обновления настроек
  const updateSettingsMutation = useMutation({
    mutationFn: settingsApi.updateAdmin,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setSuccessMessage('Настройки сохранены')
      setTimeout(() => setSuccessMessage(null), 3000)
    },
  })
  
  // Мутация для обновления списков доступа
  const updateAccessMutation = useMutation({
    mutationFn: accessApi.update,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['access'] })
      setSuccessMessage('Списки доступа обновлены')
      setTimeout(() => setSuccessMessage(null), 3000)
    },
  })
  
  // Состояние формы
  const [formData, setFormData] = useState<Partial<AdminSettings>>({})
  
  // Инициализируем форму при загрузке данных
  if (settings && Object.keys(formData).length === 0) {
    setFormData(settings)
  }
  
  const handleChange = (field: keyof AdminSettings, value: string | boolean | number | null) => {
    setFormData((prev) => ({ ...prev, [field]: value }))
  }
  
  const handleSave = () => {
    updateSettingsMutation.mutate(formData)
  }
  
  if (settingsLoading || accessLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    )
  }
  
  return (
    <div className="space-y-6">
      {/* Заголовок */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Настройки бота</h1>
        <p className="mt-1 text-sm text-gray-500">
          Глобальные настройки Telegram-бота
        </p>
      </div>
      
      {/* Сообщение об успехе */}
      {successMessage && (
        <div className="p-4 bg-green-50 text-green-700 rounded-lg">
          {successMessage}
        </div>
      )}
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* LLM настройки */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-medium">Провайдеры LLM</h2>
          </div>
          <div className="card-body space-y-4">
            <div>
              <label className="form-label">Провайдер по умолчанию</label>
              <select
                value={formData.default_llm || 'yandex'}
                onChange={(e) => handleChange('default_llm', e.target.value)}
                className="form-input"
              >
                <option value="yandex">YandexGPT</option>
                <option value="openai">OpenAI</option>
                <option value="proxyapi">ProxyAPI</option>
              </select>
            </div>
            <div>
              <label className="form-label">Модель YandexGPT</label>
              <input
                type="text"
                value={formData.yandex_model || ''}
                onChange={(e) => handleChange('yandex_model', e.target.value)}
                className="form-input"
              />
            </div>
            <div>
              <label className="form-label">Модель OpenAI</label>
              <input
                type="text"
                value={formData.openai_model || ''}
                onChange={(e) => handleChange('openai_model', e.target.value)}
                className="form-input"
              />
            </div>
            <div>
              <label className="form-label">Провайдер для переводов</label>
              <select
                value={formData.translate_provider || 'yandex'}
                onChange={(e) => handleChange('translate_provider', e.target.value)}
                className="form-input"
              >
                <option value="yandex">YandexGPT</option>
                <option value="openai">OpenAI</option>
                <option value="proxyapi">ProxyAPI</option>
              </select>
            </div>
            <div>
              <label className="form-label">Модель для переводов</label>
              <input
                type="text"
                value={formData.translate_model || ''}
                onChange={(e) => handleChange('translate_model', e.target.value)}
                className="form-input"
              />
            </div>
            <div className="flex items-center">
              <input
                type="checkbox"
                id="translate_legacy"
                checked={formData.translate_legacy || false}
                onChange={(e) => handleChange('translate_legacy', e.target.checked)}
                className="h-4 w-4 text-primary-600 rounded"
              />
              <label htmlFor="translate_legacy" className="ml-2 text-sm text-gray-700">
                Использовать legacy Yandex Translate
              </label>
            </div>
          </div>
        </div>
        
        {/* Флаги */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-medium">Опции</h2>
          </div>
          <div className="card-body space-y-4">
            <div className="flex items-center">
              <input
                type="checkbox"
                id="convert_currency"
                checked={formData.convert_currency || false}
                onChange={(e) => handleChange('convert_currency', e.target.checked)}
                className="h-4 w-4 text-primary-600 rounded"
              />
              <label htmlFor="convert_currency" className="ml-2 text-sm text-gray-700">
                Конвертировать цены в рубли
              </label>
            </div>
            <div className="flex items-center">
              <input
                type="checkbox"
                id="tmapi_notify_439"
                checked={formData.tmapi_notify_439 || false}
                onChange={(e) => handleChange('tmapi_notify_439', e.target.checked)}
                className="h-4 w-4 text-primary-600 rounded"
              />
              <label htmlFor="tmapi_notify_439" className="ml-2 text-sm text-gray-700">
                Уведомлять об ошибке TMAPI 439
              </label>
            </div>
            <div className="flex items-center">
              <input
                type="checkbox"
                id="debug_mode"
                checked={formData.debug_mode || false}
                onChange={(e) => handleChange('debug_mode', e.target.checked)}
                className="h-4 w-4 text-primary-600 rounded"
              />
              <label htmlFor="debug_mode" className="ml-2 text-sm text-gray-700">
                Режим отладки
              </label>
            </div>
            <div className="flex items-center">
              <input
                type="checkbox"
                id="mock_mode"
                checked={formData.mock_mode || false}
                onChange={(e) => handleChange('mock_mode', e.target.checked)}
                className="h-4 w-4 text-primary-600 rounded"
              />
              <label htmlFor="mock_mode" className="ml-2 text-sm text-gray-700">
                Mock режим
              </label>
            </div>
            <div>
              <label className="form-label">Канал для дублирования</label>
              <input
                type="text"
                value={formData.forward_channel_id || ''}
                onChange={(e) => handleChange('forward_channel_id', e.target.value)}
                placeholder="-1001234567890 или @channel"
                className="form-input"
              />
            </div>
          </div>
        </div>
        
        {/* Лимиты */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-medium">Глобальные лимиты</h2>
          </div>
          <div className="card-body space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="form-label">Дневной на пользователя</label>
                <input
                  type="number"
                  min="0"
                  value={formData.per_user_daily_limit ?? ''}
                  onChange={(e) => handleChange('per_user_daily_limit', e.target.value ? parseInt(e.target.value) : null)}
                  placeholder="Без лимита"
                  className="form-input"
                />
              </div>
              <div>
                <label className="form-label">Месячный на пользователя</label>
                <input
                  type="number"
                  min="0"
                  value={formData.per_user_monthly_limit ?? ''}
                  onChange={(e) => handleChange('per_user_monthly_limit', e.target.value ? parseInt(e.target.value) : null)}
                  placeholder="Без лимита"
                  className="form-input"
                />
              </div>
              <div>
                <label className="form-label">Общий дневной</label>
                <input
                  type="number"
                  min="0"
                  value={formData.total_daily_limit ?? ''}
                  onChange={(e) => handleChange('total_daily_limit', e.target.value ? parseInt(e.target.value) : null)}
                  placeholder="Без лимита"
                  className="form-input"
                />
              </div>
              <div>
                <label className="form-label">Общий месячный</label>
                <input
                  type="number"
                  min="0"
                  value={formData.total_monthly_limit ?? ''}
                  onChange={(e) => handleChange('total_monthly_limit', e.target.value ? parseInt(e.target.value) : null)}
                  placeholder="Без лимита"
                  className="form-input"
                />
              </div>
            </div>
          </div>
        </div>
        
        {/* Контроль доступа */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-medium">Контроль доступа</h2>
          </div>
          <div className="card-body space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-700">Белый список</span>
              <button
                onClick={() => updateAccessMutation.mutate({ whitelist_enabled: !accessLists?.whitelist_enabled })}
                className={accessLists?.whitelist_enabled ? 'badge-green' : 'badge-gray'}
              >
                {accessLists?.whitelist_enabled ? 'Включён' : 'Выключен'}
              </button>
            </div>
            <p className="text-xs text-gray-500">
              Записей: {accessLists?.whitelist.length || 0}
            </p>
            
            <hr />
            
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-700">Чёрный список</span>
              <button
                onClick={() => updateAccessMutation.mutate({ blacklist_enabled: !accessLists?.blacklist_enabled })}
                className={accessLists?.blacklist_enabled ? 'badge-red' : 'badge-gray'}
              >
                {accessLists?.blacklist_enabled ? 'Включён' : 'Выключен'}
              </button>
            </div>
            <p className="text-xs text-gray-500">
              Записей: {accessLists?.blacklist.length || 0}
            </p>
          </div>
        </div>
      </div>
      
      {/* Кнопка сохранения */}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={updateSettingsMutation.isPending}
          className="btn-primary"
        >
          {updateSettingsMutation.isPending ? (
            <LoadingSpinner size="sm" className="mr-2" />
          ) : null}
          Сохранить настройки
        </button>
      </div>
    </div>
  )
}
