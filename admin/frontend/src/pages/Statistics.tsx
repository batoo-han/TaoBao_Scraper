/**
 * Страница детальной статистики
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format, subDays } from 'date-fns'
import { statsApi } from '@/api/client'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import type { StatsRequestsResponse, StatsPeaksResponse, TopUser } from '@/types'
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

export default function Statistics() {
  const [dateFrom, setDateFrom] = useState(() => format(subDays(new Date(), 30), 'yyyy-MM-dd'))
  const [dateTo, setDateTo] = useState(() => format(new Date(), 'yyyy-MM-dd'))
  
  // Запросы с пагинацией
  const { data: requestsData, isLoading: requestsLoading } = useQuery<StatsRequestsResponse>({
    queryKey: ['stats', 'requests', dateFrom, dateTo],
    queryFn: () => statsApi.requests({ date_from: dateFrom, date_to: dateTo, per_page: 10 }),
  })
  
  // Пики активности
  const { data: peaksData, isLoading: peaksLoading } = useQuery<StatsPeaksResponse>({
    queryKey: ['stats', 'peaks', dateFrom, dateTo],
    queryFn: () => statsApi.peaks({ date_from: dateFrom, date_to: dateTo }),
  })
  
  // Топ пользователей
  const { data: topUsersData, isLoading: topUsersLoading } = useQuery<{ top_users: TopUser[] }>({
    queryKey: ['stats', 'topUsers', dateFrom, dateTo],
    queryFn: () => statsApi.topUsers({ date_from: dateFrom, date_to: dateTo, limit: 10 }),
  })
  
  return (
    <div className="space-y-6">
      {/* Заголовок и фильтры */}
      <div className="sm:flex sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Статистика</h1>
          <p className="mt-1 text-sm text-gray-500">
            Детальный анализ использования бота
          </p>
        </div>
        
        {/* Фильтр по датам */}
        <div className="mt-4 sm:mt-0 flex gap-3">
          <div>
            <label className="sr-only">От</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="form-input"
            />
          </div>
          <div>
            <label className="sr-only">До</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="form-input"
            />
          </div>
        </div>
      </div>
      
      {/* Сводка */}
      {requestsData && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="stat-card">
            <p className="text-sm text-gray-500">Всего запросов</p>
            <p className="stat-value">{requestsData.total_requests}</p>
          </div>
          <div className="stat-card">
            <p className="text-sm text-gray-500">Общие расходы</p>
            <p className="stat-value">${requestsData.total_cost.toFixed(2)}</p>
          </div>
          <div className="stat-card">
            <p className="text-sm text-gray-500">Токенов</p>
            <p className="stat-value">{requestsData.total_tokens.toLocaleString()}</p>
          </div>
          <div className="stat-card">
            <p className="text-sm text-gray-500">Ср. время (мс)</p>
            <p className="stat-value">{Math.round(requestsData.avg_duration_ms)}</p>
          </div>
        </div>
      )}
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* График запросов по дням */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-medium">Запросы по дням</h2>
          </div>
          <div className="card-body">
            {peaksLoading ? (
              <div className="h-64 flex items-center justify-center">
                <LoadingSpinner />
              </div>
            ) : peaksData?.daily_requests?.length ? (
              <ResponsiveContainer width="100%" height={256}>
                <AreaChart
                  data={peaksData.daily_requests.map((p) => ({
                    date: format(new Date(p.date), 'dd.MM'),
                    value: p.value,
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip />
                  <Area type="monotone" dataKey="value" stroke="#3b82f6" fill="#93c5fd" name="Запросов" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-64 flex items-center justify-center text-gray-500">
                Нет данных
              </div>
            )}
          </div>
        </div>
        
        {/* Распределение по часам */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-medium">Активность по часам</h2>
            {peaksData && (
              <p className="text-sm text-gray-500">
                Пик: {peaksData.peak_hour}:00 ({peaksData.peak_requests} запросов)
              </p>
            )}
          </div>
          <div className="card-body">
            {peaksLoading ? (
              <div className="h-64 flex items-center justify-center">
                <LoadingSpinner />
              </div>
            ) : peaksData?.hourly_distribution?.length ? (
              <ResponsiveContainer width="100%" height={256}>
                <BarChart
                  data={peaksData.hourly_distribution.map((h) => ({
                    hour: `${h.hour}:00`,
                    requests: h.requests,
                    avg: h.avg_requests,
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="hour" interval={2} />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="requests" fill="#3b82f6" name="Запросов" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-64 flex items-center justify-center text-gray-500">
                Нет данных
              </div>
            )}
          </div>
        </div>
      </div>
      
      {/* Топ пользователей */}
      <div className="card">
        <div className="card-header">
          <h2 className="text-lg font-medium">Топ-10 активных пользователей</h2>
        </div>
        <div className="overflow-x-auto">
          {topUsersLoading ? (
            <div className="p-8 flex justify-center">
              <LoadingSpinner />
            </div>
          ) : topUsersData?.top_users?.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>ID</th>
                  <th>Username</th>
                  <th>Запросов</th>
                  <th>Расходы</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {topUsersData.top_users.map((user, index) => (
                  <tr key={user.user_id}>
                    <td className="font-medium">{index + 1}</td>
                    <td>{user.user_id}</td>
                    <td>{user.username ? `@${user.username}` : '-'}</td>
                    <td>{user.requests}</td>
                    <td>${user.cost.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="p-8 text-center text-gray-500">
              Нет данных за выбранный период
            </div>
          )}
        </div>
      </div>
      
      {/* Последние запросы */}
      <div className="card">
        <div className="card-header">
          <h2 className="text-lg font-medium">Последние запросы</h2>
        </div>
        <div className="overflow-x-auto">
          {requestsLoading ? (
            <div className="p-8 flex justify-center">
              <LoadingSpinner />
            </div>
          ) : requestsData?.items?.length ? (
            <table className="table">
              <thead>
                <tr>
                  <th>Время</th>
                  <th>Пользователь</th>
                  <th>Платформа</th>
                  <th>Время (мс)</th>
                  <th>Токены</th>
                  <th>Стоимость</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {requestsData.items.map((req) => (
                  <tr key={req.id}>
                    <td>{new Date(req.request_time).toLocaleString('ru-RU')}</td>
                    <td>{req.username ? `@${req.username}` : req.user_id || '-'}</td>
                    <td>
                      <span className="badge-blue">{req.platform || 'unknown'}</span>
                    </td>
                    <td>{req.duration_ms || '-'}</td>
                    <td>{req.total_tokens || '-'}</td>
                    <td>${(req.total_cost || 0).toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="p-8 text-center text-gray-500">
              Нет запросов за выбранный период
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
