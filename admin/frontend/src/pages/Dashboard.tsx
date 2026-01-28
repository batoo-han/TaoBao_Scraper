/**
 * Главная страница - Dashboard со статистикой
 */

import { useQuery } from '@tanstack/react-query'
import {
  UsersIcon,
  DocumentTextIcon,
  CurrencyDollarIcon,
  ServerStackIcon,
} from '@heroicons/react/24/outline'
import { statsApi } from '@/api/client'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import type { StatsOverview } from '@/types'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts'

// Цвета для графика платформ
const PLATFORM_COLORS = {
  taobao: '#ff6b00',
  tmall: '#e4393c',
  '1688': '#ff7300',
  pinduoduo: '#e02e24',
  szwego: '#4f46e5',
  unknown: '#9ca3af',
}

// Карточка статистики
function StatCard({
  title,
  value,
  subValue,
  icon: Icon,
  trend,
  trendLabel,
}: {
  title: string
  value: string | number
  subValue?: string
  icon: React.ComponentType<{ className?: string }>
  trend?: 'up' | 'down' | 'neutral'
  trendLabel?: string
}) {
  return (
    <div className="stat-card">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">{title}</p>
          <p className="stat-value">{value}</p>
          {subValue && (
            <p className="text-sm text-gray-500 mt-1">{subValue}</p>
          )}
          {trendLabel && (
            <p
              className={
                trend === 'up'
                  ? 'stat-change-positive'
                  : trend === 'down'
                  ? 'stat-change-negative'
                  : 'stat-change text-gray-500'
              }
            >
              {trendLabel}
            </p>
          )}
        </div>
        <div className="p-3 bg-primary-50 rounded-lg">
          <Icon className="h-6 w-6 text-primary-600" />
        </div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  // Загружаем сводную статистику
  const { data: overview, isLoading: overviewLoading } = useQuery<StatsOverview>({
    queryKey: ['stats', 'overview'],
    queryFn: statsApi.overview,
  })
  
  // Загружаем расходы за 7 дней
  const { data: costs, isLoading: costsLoading } = useQuery({
    queryKey: ['stats', 'costs', '7d'],
    queryFn: () => {
      const to = new Date()
      const from = new Date()
      from.setDate(from.getDate() - 7)
      return statsApi.costs({
        date_from: from.toISOString().split('T')[0],
        date_to: to.toISOString().split('T')[0],
      })
    },
  })
  
  if (overviewLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    )
  }
  
  if (!overview) {
    return (
      <div className="text-center text-gray-500 py-12">
        Не удалось загрузить статистику
      </div>
    )
  }
  
  // Форматируем данные для графика расходов
  const dailyCostsData = costs?.daily_costs?.map((point: { date: string; value: number }) => ({
    date: new Date(point.date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }),
    value: point.value,
  })) || []
  
  // Форматируем данные для pie chart платформ
  const platformsData = costs?.by_platform?.map((p: { platform: string; cost: number; percentage: number }) => ({
    name: p.platform,
    value: p.cost,
    percentage: p.percentage,
  })) || []
  
  return (
    <div className="space-y-6">
      {/* Заголовок */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Панель управления</h1>
        <p className="mt-1 text-sm text-gray-500">
          Обзор статистики бота
        </p>
      </div>
      
      {/* Статистические карточки */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Пользователей"
          value={overview.total_users}
          subValue={`Активных сегодня: ${overview.active_users_today}`}
          icon={UsersIcon}
          trend="up"
          trendLabel={`+${overview.new_users_today} новых сегодня`}
        />
        <StatCard
          title="Запросов сегодня"
          value={overview.requests_today}
          subValue={`За месяц: ${overview.requests_month}`}
          icon={DocumentTextIcon}
          trend="neutral"
          trendLabel={`Всего: ${overview.requests_total}`}
        />
        <StatCard
          title="Расходы сегодня"
          value={`$${overview.cost_today.toFixed(2)}`}
          subValue={`За месяц: $${overview.cost_month.toFixed(2)}`}
          icon={CurrencyDollarIcon}
          trend="neutral"
          trendLabel={`Всего: $${overview.cost_total.toFixed(2)}`}
        />
        <StatCard
          title="Кэш hit rate"
          value={`${overview.cache_hit_rate}%`}
          subValue={`Сэкономлено: $${overview.cache_saved_cost.toFixed(4)}`}
          icon={ServerStackIcon}
        />
      </div>
      
      {/* Лимиты */}
      {(overview.daily_limit || overview.monthly_limit) && (
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-medium">Использование лимитов</h2>
          </div>
          <div className="card-body">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {overview.daily_limit && (
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span>Дневной лимит</span>
                    <span>{overview.daily_used} / {overview.daily_limit}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-primary-600 h-2 rounded-full transition-all"
                      style={{ width: `${Math.min(100, (overview.daily_used / overview.daily_limit) * 100)}%` }}
                    />
                  </div>
                </div>
              )}
              {overview.monthly_limit && (
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span>Месячный лимит</span>
                    <span>{overview.monthly_used} / {overview.monthly_limit}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-primary-600 h-2 rounded-full transition-all"
                      style={{ width: `${Math.min(100, (overview.monthly_used / overview.monthly_limit) * 100)}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      
      {/* Графики */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* График расходов */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-medium">Расходы за 7 дней</h2>
          </div>
          <div className="card-body">
            {costsLoading ? (
              <div className="h-64 flex items-center justify-center">
                <LoadingSpinner />
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={256}>
                <AreaChart data={dailyCostsData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip
                    formatter={(value: number) => [`$${value.toFixed(4)}`, 'Расходы']}
                  />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="#3b82f6"
                    fill="#93c5fd"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
        
        {/* Диаграмма платформ */}
        <div className="card">
          <div className="card-header">
            <h2 className="text-lg font-medium">Расходы по платформам</h2>
          </div>
          <div className="card-body">
            {costsLoading ? (
              <div className="h-64 flex items-center justify-center">
                <LoadingSpinner />
              </div>
            ) : platformsData.length > 0 ? (
              <div className="flex items-center">
                <ResponsiveContainer width="60%" height={256}>
                  <PieChart>
                    <Pie
                      data={platformsData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      label={({ name, percentage }) => `${name}: ${percentage}%`}
                    >
                      {platformsData.map((entry: { name: string }, index: number) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={PLATFORM_COLORS[entry.name as keyof typeof PLATFORM_COLORS] || PLATFORM_COLORS.unknown}
                        />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value: number) => [`$${value.toFixed(4)}`, 'Расходы']}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="w-40">
                  {platformsData.map((p: { name: string; value: number; percentage: number }) => (
                    <div key={p.name} className="flex items-center gap-2 mb-2">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: PLATFORM_COLORS[p.name as keyof typeof PLATFORM_COLORS] || PLATFORM_COLORS.unknown }}
                      />
                      <span className="text-sm">{p.name}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-gray-500">
                Нет данных за период
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
