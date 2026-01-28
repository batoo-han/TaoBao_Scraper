/**
 * Типы данных для админ-панели
 */

// ==================== Аутентификация ====================

export type AdminRole = 'admin' | 'user'

export interface AdminUser {
  id: number
  username: string
  email: string | null
  display_name: string | null
  telegram_id: number | null
  role: AdminRole
  is_active: boolean
  created_at: string
  last_login: string | null
}

export interface LoginRequest {
  username: string
  password: string
}

export interface TelegramLoginData {
  id: number
  first_name?: string
  last_name?: string
  username?: string
  photo_url?: string
  auth_date: number
  hash: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: AdminUser
}

export interface RefreshTokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

// ==================== Пользователи бота ====================

export interface BotUserSettings {
  signature: string
  default_currency: string
  exchange_rate: number | null
  price_mode: string
  daily_limit: number | null
  monthly_limit: number | null
}

export interface BotUserLimits {
  day_start: string | null
  day_count: number
  month_start: string | null
  month_count: number
  day_cost: number
  month_cost: number
}

export interface BotUserAccessStatus {
  in_whitelist: boolean
  in_blacklist: boolean
  whitelist_type: string | null
  blacklist_type: string | null
}

export interface BotUser {
  user_id: number
  username: string | null
  created_at: string
  settings: BotUserSettings | null
  limits: BotUserLimits | null
  access: BotUserAccessStatus
  total_requests: number
  total_cost: number
  last_request_at: string | null
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

// ==================== Статистика ====================

export interface StatsOverview {
  total_users: number
  active_users_today: number
  active_users_month: number
  new_users_today: number
  new_users_month: number
  requests_today: number
  requests_month: number
  requests_total: number
  cost_today: number
  cost_month: number
  cost_total: number
  cache_hit_rate: number
  cache_saved_cost: number
  daily_limit: number | null
  daily_used: number
  monthly_limit: number | null
  monthly_used: number
}

export interface TimeSeriesPoint {
  date: string
  value: number
}

export interface PlatformStats {
  platform: string
  requests: number
  cost: number
  percentage: number
}

export interface TopUser {
  user_id: number
  username: string | null
  requests: number
  cost: number
}

export interface RequestLogEntry {
  id: number
  user_id: number | null
  username: string | null
  request_time: string
  platform: string | null
  product_url: string | null
  duration_ms: number | null
  total_tokens: number | null
  total_cost: number | null
  cache_hits: number | null
}

export interface StatsRequestsResponse extends PaginatedResponse<RequestLogEntry> {
  total_requests: number
  total_cost: number
  total_tokens: number
  avg_duration_ms: number
}

export interface StatsCostsResponse {
  period_start: string
  period_end: string
  total_cost: number
  daily_costs: TimeSeriesPoint[]
  by_platform: PlatformStats[]
  avg_cost_per_request: number
  avg_cost_per_user: number
}

export interface PeakHour {
  hour: number
  requests: number
  avg_requests: number
}

export interface StatsPeaksResponse {
  period_start: string
  period_end: string
  hourly_distribution: PeakHour[]
  peak_hour: number
  peak_requests: number
  daily_requests: TimeSeriesPoint[]
}

// ==================== Настройки ====================

export interface AdminSettings {
  default_llm: string
  yandex_model: string
  openai_model: string
  translate_provider: string
  translate_model: string
  translate_legacy: boolean
  convert_currency: boolean
  tmapi_notify_439: boolean
  debug_mode: boolean
  mock_mode: boolean
  forward_channel_id: string
  per_user_daily_limit: number | null
  per_user_monthly_limit: number | null
  total_daily_limit: number | null
  total_monthly_limit: number | null
}

export interface AccessListEntry {
  entry_type: string
  value: string
}

export interface AccessListsResponse {
  whitelist_enabled: boolean
  blacklist_enabled: boolean
  whitelist: AccessListEntry[]
  blacklist: AccessListEntry[]
}

export interface AccessListUpdate {
  whitelist_enabled?: boolean
  blacklist_enabled?: boolean
  add_whitelist_ids?: number[]
  add_whitelist_usernames?: string[]
  remove_whitelist_ids?: number[]
  remove_whitelist_usernames?: string[]
  add_blacklist_ids?: number[]
  add_blacklist_usernames?: string[]
  remove_blacklist_ids?: number[]
  remove_blacklist_usernames?: string[]
}
