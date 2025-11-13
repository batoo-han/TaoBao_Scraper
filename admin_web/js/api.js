/**
 * API клиент для админ-панели.
 */

const API_BASE_URL = '/api/admin';

class API {
    constructor() {
        this.token = localStorage.getItem('admin_token');
    }

    /**
     * Выполняет запрос к API.
     */
    async request(endpoint, options = {}) {
        const url = `${API_BASE_URL}${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers,
        };

        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        try {
            const response = await fetch(url, {
                ...options,
                headers,
            });

            if (response.status === 401) {
                // Токен истек или невалиден
                localStorage.removeItem('admin_token');
                localStorage.removeItem('admin_user');
                window.location.href = '/login.html';
                return null;
            }

            if (!response.ok) {
                const error = await response.json().catch(() => ({ detail: 'Ошибка сервера' }));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    }

    // ========================================================================
    // Аутентификация
    // ========================================================================

    async login(username, password) {
        return this.request('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });
    }

    async getCurrentUser() {
        return this.request('/auth/me');
    }

    async logout() {
        return this.request('/auth/logout', { method: 'POST' });
    }

    // ========================================================================
    // Настройки
    // ========================================================================

    async getSettings() {
        return this.request('/settings');
    }

    async updateLLMProvider(vendor, config = null) {
        return this.request('/settings/llm-provider', {
            method: 'PUT',
            body: JSON.stringify({ vendor, config }),
        });
    }

    async updateConsentText(text) {
        return this.request('/settings/consent-text', {
            method: 'PUT',
            body: JSON.stringify({ text }),
        });
    }

    async updateAppConfig(config) {
        return this.request('/settings/app-config', {
            method: 'PUT',
            body: JSON.stringify({ config }),
        });
    }

    async getLLMPromptConfig() {
        return this.request('/settings/llm-prompt');
    }

    async updateLLMPromptConfig(promptTemplate, temperature, maxTokens) {
        return this.request('/settings/llm-prompt', {
            method: 'PUT',
            body: JSON.stringify({
                prompt_template: promptTemplate,
                temperature: temperature,
                max_tokens: maxTokens,
            }),
        });
    }

    async getPlatformsConfig() {
        return this.request('/settings/platforms');
    }

    async updatePlatformConfig(platform, enabled) {
        return this.request('/settings/platforms', {
            method: 'PUT',
            body: JSON.stringify({ platform, enabled }),
        });
    }

    async reloadConfig() {
        return this.request('/config/reload', {
            method: 'POST',
        });
    }

    // ========================================================================
    // Провайдеры
    // ========================================================================

    async getProviders() {
        return this.request('/providers');
    }

    async getProviderConfig(vendor) {
        return this.request(`/providers/${vendor}/config`);
    }

    async updateProviderConfig(vendor, payload) {
        return this.request(`/providers/${vendor}`, {
            method: 'PUT',
            body: JSON.stringify(payload),
        });
    }

    async restartSystem() {
        return this.request('/system/restart', {
            method: 'POST',
        });
    }

    // ========================================================================
    // Статистика
    // ========================================================================

    async getStatsOverview() {
        return this.request('/stats/overview');
    }

    async getUsersStats(limit = 100, offset = 0) {
        return this.request(`/stats/users?limit=${limit}&offset=${offset}`);
    }

    async getProvidersStats() {
        return this.request('/stats/providers');
    }

    // ========================================================================
    // Пользователи
    // ========================================================================

    async getUsers(page = 1, pageSize = 20, search = null) {
        let url = `/users?page=${page}&page_size=${pageSize}`;
        if (search) {
            url += `&search=${encodeURIComponent(search)}`;
        }
        return this.request(url);
    }

    async getUser(userId) {
        return this.request(`/users/${userId}`);
    }

    async updateUser(userId, data) {
        return this.request(`/users/${userId}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    }

    async makeAdmin(userId) {
        return this.request(`/users/${userId}/make-admin`, {
            method: 'POST',
        });
    }

    async revokeAdmin(userId) {
        return this.request(`/users/${userId}/revoke-admin`, {
            method: 'DELETE',
        });
    }

    // ========================================================================
    // Аудит
    // ========================================================================

    async getAuditLogs(page = 1, pageSize = 50, filters = {}) {
        let url = `/audit?page=${page}&page_size=${pageSize}`;
        if (filters.action) url += `&action=${encodeURIComponent(filters.action)}`;
        if (filters.user_id) url += `&user_id=${filters.user_id}`;
        if (filters.date_from) url += `&date_from=${filters.date_from}`;
        if (filters.date_to) url += `&date_to=${filters.date_to}`;
        return this.request(url);
    }

    async getAuditLog(logId) {
        return this.request(`/audit/${logId}`);
    }

    async exportAuditCSV(filters = {}) {
        let url = '/audit/export/csv';
        const params = new URLSearchParams();
        if (filters.date_from) params.append('date_from', filters.date_from);
        if (filters.date_to) params.append('date_to', filters.date_to);
        if (params.toString()) url += '?' + params.toString();

        const response = await fetch(`${API_BASE_URL}${url}`, {
            headers: {
                'Authorization': `Bearer ${this.token}`,
            },
        });

        if (response.ok) {
            const blob = await response.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = `audit_${new Date().toISOString().split('T')[0]}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(downloadUrl);
        } else {
            throw new Error('Ошибка экспорта');
        }
    }

    // ========================================================================
    // Логи
    // ========================================================================

    async getLogs(lines = 100, level = null, search = null) {
        let url = `/logs?lines=${lines}`;
        if (level) url += `&level=${encodeURIComponent(level)}`;
        if (search) url += `&search=${encodeURIComponent(search)}`;
        return this.request(url);
    }

    async downloadLogs(days = 1) {
        const response = await fetch(`${API_BASE_URL}/logs/download?days=${days}`, {
            headers: {
                'Authorization': `Bearer ${this.token}`,
            },
        });

        if (response.ok) {
            const blob = await response.blob();
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = `logs_${new Date().toISOString().split('T')[0]}.txt`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(downloadUrl);
        } else {
            throw new Error('Ошибка скачивания логов');
        }
    }

    // ========================================================================
    // Платформы
    // ========================================================================

    async getPlatformsStats() {
        return this.request('/stats/platforms');
    }
}

// Создаем глобальный экземпляр API
const api = new API();

