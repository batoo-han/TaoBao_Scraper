/**
 * Основная логика админ-панели.
 */

// Текущая страница
let currentPage = 'dashboard';
let currentUsersPage = 1;
let currentAuditPage = 1;

// Проверка авторизации при загрузке
document.addEventListener('DOMContentLoaded', async () => {
    const token = localStorage.getItem('admin_token');
    if (!token) {
        window.location.href = '/login.html';
        return;
    }

    // Загружаем информацию о пользователе
    try {
        const user = await api.getCurrentUser();
        updateUserInfo(user);
    } catch (error) {
        console.error('Ошибка загрузки пользователя:', error);
        localStorage.removeItem('admin_token');
        window.location.href = '/login.html';
        return;
    }

    // Инициализация навигации
    initNavigation();
    
    // Загружаем данные для текущей страницы
    loadPage(currentPage);

    // Обработчик выхода
    document.getElementById('logoutBtn').addEventListener('click', () => {
        localStorage.removeItem('admin_token');
        localStorage.removeItem('admin_user');
        window.location.href = '/login.html';
    });
});

/**
 * Обновляет информацию о пользователе в интерфейсе.
 */
function updateUserInfo(user) {
    const userInfo = document.getElementById('userInfo');
    if (userInfo) {
        userInfo.innerHTML = `
            <div class="username">${user.username || user.first_name || 'Админ'}</div>
            <div style="font-size: 12px; color: rgba(255,255,255,0.6);">
                ${user.can_manage_keys ? '🔑' : ''} 
                ${user.can_view_stats ? '📊' : ''} 
                ${user.can_manage_users ? '👥' : ''}
            </div>
        `;
    }
}

/**
 * Инициализация навигации.
 */
function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.dataset.page;
            switchPage(page);
        });
    });
}

/**
 * Переключение страниц.
 */
function switchPage(page) {
    // Обновляем активный пункт меню
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.dataset.page === page) {
            item.classList.add('active');
        }
    });

    // Скрываем все страницы
    document.querySelectorAll('.page').forEach(p => {
        p.classList.add('hidden');
    });

    // Показываем нужную страницу
    const targetPage = document.getElementById(`page-${page}`);
    if (targetPage) {
        targetPage.classList.remove('hidden');
        currentPage = page;
        
        // Обновляем заголовок
        const titles = {
            dashboard: 'Дашборд',
            settings: 'Настройки',
            providers: 'LLM Провайдеры',
            users: 'Пользователи',
            stats: 'Статистика',
            audit: 'Аудит персональных данных',
            logs: 'Логи',
            platforms: 'Платформы',
            docs: 'Документация',
            billing: 'Биллинг',
        };
        document.getElementById('pageTitle').textContent = titles[page] || 'Админ-панель';

        // Загружаем данные для страницы
        loadPage(page);
    }
}

/**
 * Загрузка данных для страницы.
 */
async function loadPage(page) {
    try {
        switch (page) {
            case 'dashboard':
                await loadDashboard();
                break;
            case 'settings':
                await loadSettings();
                break;
            case 'providers':
                await loadProviders();
                break;
            case 'users':
                await loadUsers();
                break;
            case 'stats':
                await loadStats();
                break;
            case 'audit':
                await loadAudit();
                break;
            case 'logs':
                await loadLogs();
                break;
            case 'platforms':
                await loadPlatforms();
                break;
            case 'docs':
                await loadDocs();
                break;
            case 'billing':
                // Биллинг пока пустой
                break;
        }
    } catch (error) {
        console.error(`Ошибка загрузки страницы ${page}:`, error);
        showToast('Ошибка загрузки данных', 'error');
    }
}

/**
 * Загрузка дашборда.
 */
async function loadDashboard() {
    const stats = await api.getStatsOverview();
    
    document.getElementById('stat-total-users').textContent = stats.total_users || 0;
    document.getElementById('stat-active-users').textContent = stats.active_users_30d || 0;
    document.getElementById('stat-total-requests').textContent = formatNumber(stats.total_requests || 0);
    document.getElementById('stat-total-tokens').textContent = formatNumber(stats.total_tokens || 0);
    document.getElementById('stat-active-provider').textContent = stats.active_provider || '-';
    document.getElementById('stat-cache-rate').textContent = `${(stats.cache_hit_rate || 0).toFixed(1)}%`;
    
    document.getElementById('requests-today').textContent = stats.requests_today || 0;
    document.getElementById('requests-week').textContent = stats.requests_this_week || 0;
    document.getElementById('requests-month').textContent = stats.requests_this_month || 0;
}

/**
 * Загрузка настроек.
 */
let settingsHandlersAttached = false;
let currentAppSettings = null;
let logStreamController = null;
let logStreamActive = false;
let providerDataMap = new Map();

async function loadSettings() {
    const settingsData = await api.getSettings();

    if (!settingsHandlersAttached) {
        initSettingsTabs();
        setupSettingsHandlers();
        settingsHandlersAttached = true;
    }

    applySettingsData(settingsData);

    // Загружаем настройки промпта
    try {
        const promptConfig = await api.getLLMPromptConfig();
        const promptTemplateEl = document.getElementById('promptTemplate');
        const llmTemperatureEl = document.getElementById('llmTemperature');
        const llmTemperatureValueEl = document.getElementById('llmTemperatureValue');
        const llmMaxTokensEl = document.getElementById('llmMaxTokens');
        const llmMaxTokensValueEl = document.getElementById('llmMaxTokensValue');

        if (promptTemplateEl) {
            promptTemplateEl.value = promptConfig.prompt_template || '';
        }
        if (llmTemperatureEl) {
            const temperatureValue = promptConfig.temperature ?? 0.05;
            llmTemperatureEl.value = temperatureValue;
            attachRangeDisplay(llmTemperatureEl, llmTemperatureValueEl, (value) => Number(value).toFixed(2));
        }
        if (llmMaxTokensEl) {
            const tokensValue = promptConfig.max_tokens ?? 900;
            llmMaxTokensEl.value = tokensValue;
            attachRangeDisplay(llmMaxTokensEl, llmMaxTokensValueEl, (value) => Math.round(Number(value)));
        }
    } catch (error) {
        console.error('Ошибка загрузки настроек промпта:', error);
    } finally {
        const llmTemperatureEl = document.getElementById('llmTemperature');
        const llmTemperatureValueEl = document.getElementById('llmTemperatureValue');
        if (llmTemperatureEl) {
            if (!llmTemperatureEl.value) {
                llmTemperatureEl.value = 0.05;
            }
            attachRangeDisplay(llmTemperatureEl, llmTemperatureValueEl, (value) => Number(value).toFixed(2));
        }

        const llmMaxTokensEl = document.getElementById('llmMaxTokens');
        const llmMaxTokensValueEl = document.getElementById('llmMaxTokensValue');
        if (llmMaxTokensEl) {
            if (!llmMaxTokensEl.value) {
                llmMaxTokensEl.value = 900;
            }
            attachRangeDisplay(llmMaxTokensEl, llmMaxTokensValueEl, (value) => Math.round(Number(value)));
        }
    }
}

function applySettingsData(settingsData) {
    if (!settingsData) return;
    currentAppSettings = settingsData;
    const appConfig = settingsData.app_config || {};

    loadBasicSettings(appConfig);
    loadImageAnalysisSettings(appConfig);
    loadDatabaseSettings(appConfig);
    loadSystemSettings(appConfig);

    const llmProviderSelect = document.getElementById('llmProviderSelect');
    if (llmProviderSelect) {
        llmProviderSelect.value = settingsData.active_llm_vendor;
    }

    const consentTextEl = document.getElementById('consentText');
    const personalDataEnabledEl = document.getElementById('personalDataEnabled');
    if (consentTextEl) consentTextEl.value = settingsData.consent_text || '';
    if (personalDataEnabledEl) {
        personalDataEnabledEl.checked = appConfig.PERSONAL_DATA_ENABLED !== false;
    }

    updateRestartNotice(settingsData);
}

function updateRestartNotice(settingsData) {
    const notice = document.getElementById('restartNotice');
    const noticeText = document.getElementById('restartNoticeText');
    const restartBtn = document.getElementById('restartSystemBtn');
    if (!notice || !noticeText || !restartBtn) return;

    const pendingConfig = settingsData.pending_restart_config || {};
    const pendingKeys = Object.keys(pendingConfig);
    const safePendingKeys = pendingKeys.map(escapeHtml);

    // Показываем блок только если есть реальные pending ключи
    if (safePendingKeys.length > 0) {
        notice.classList.remove('hidden');
        noticeText.innerHTML = `Для применения настроек требуется перезапуск (изменены ключи: <strong>${safePendingKeys.join(', ')}</strong>).`;
        restartBtn.disabled = false;
        restartBtn.textContent = 'Перезапустить сервисы';
    } else {
        notice.classList.add('hidden');
        restartBtn.disabled = true;
        noticeText.textContent = '';
    }
}

function handleConfigUpdateResult(result) {
    if (!result) return;
    if (result.settings) {
        applySettingsData(result.settings);
    }
    const pending = result.pending_restart_keys || [];
    const toastType = pending.length ? 'warning' : 'success';
    const message = result.message || (pending.length ? 'Настройки сохранены. Необходим перезапуск.' : 'Настройки сохранены');
    showToast(message, toastType);
}

/**
 * Загрузка провайдеров.
 */
async function loadProviders() {
    const providers = await api.getProviders();
    const container = document.getElementById('providersList');
    if (!container) return;

    providerDataMap = new Map(providers.map(provider => [provider.vendor, provider]));
    container.innerHTML = providers.map(renderProviderCard).join('');

    providers.forEach(provider => {
        setupProviderCard(provider.vendor);
    });

    updateAllProviderCardStates();
}

function escapeHtml(value) {
    if (value === undefined || value === null) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function cssEscape(value) {
    if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') {
        return CSS.escape(value);
    }
    return String(value).replace(/[^a-zA-Z0-9_\-]/g, '\\$&');
}

function renderSettingField(field, value, scope) {
    const key = field.key;
    const inputId = `${scope}-${key}`;
    const hintHtml = field.hint ? `<small class="form-hint">${escapeHtml(field.hint)}</small>` : '';
    const placeholder = field.placeholder ? escapeHtml(field.placeholder) : 'Не задано';
    const disabledAttr = field.disabled ? 'disabled' : '';
    const requiredAttr = field.required ? 'required' : '';
    const minAttr = field.min !== undefined ? `min="${field.min}"` : '';
    const maxAttr = field.max !== undefined ? `max="${field.max}"` : '';
    const stepAttr = field.step !== undefined ? `step="${field.step}"` : '';
    const dataset = `data-setting-key="${escapeHtml(key)}" data-setting-scope="${escapeHtml(scope)}"`;

    if (field.type === 'checkbox') {
        const checked = value === true || value === 'true' || value === 'True' || value === 1;
        return `
            <div class="setting-item checkbox-item">
                <label class="checkbox-label">
                    <input type="checkbox" id="${escapeHtml(inputId)}" ${dataset} ${checked ? 'checked' : ''} ${disabledAttr}>
                    ${escapeHtml(field.label)}
                </label>
                ${hintHtml}
            </div>
        `;
    }

    if (field.type === 'select') {
        const options = (field.options || []).map(option => {
            const optValue = typeof option === 'string' ? option : option.value;
            const optLabel = typeof option === 'string' ? option : option.label;
            const selected = optValue === value ? 'selected' : '';
            return `<option value="${escapeHtml(optValue)}" ${selected}>${escapeHtml(optLabel)}</option>`;
        }).join('');
        return `
            <div class="setting-item">
                <label for="${escapeHtml(inputId)}">${escapeHtml(field.label)}</label>
                <select id="${escapeHtml(inputId)}" class="form-control" ${dataset} ${disabledAttr} ${requiredAttr}>
                    ${options}
                </select>
                ${hintHtml}
            </div>
        `;
    }

    if (field.type === 'textarea') {
        const textValue = value ?? '';
        return `
            <div class="setting-item">
                <label for="${escapeHtml(inputId)}">${escapeHtml(field.label)}</label>
                <textarea
                    id="${escapeHtml(inputId)}"
                    class="form-control"
                    rows="${field.rows || 5}"
                    ${dataset}
                    placeholder="${placeholder}"
                    ${disabledAttr}
                    ${requiredAttr}
                >${escapeHtml(textValue)}</textarea>
                ${hintHtml}
            </div>
        `;
    }

    const inputType = field.type === 'password' ? 'password' : field.type === 'number' ? 'number' : 'text';
    const displayValue = field.secret && value ? '' : (value ?? '');
    const secretHint = field.secret && value ? '<small class="form-hint">Оставьте поле пустым, чтобы сохранить текущее значение.</small>' : '';

    return `
        <div class="setting-item">
            <label for="${escapeHtml(inputId)}">${escapeHtml(field.label)}</label>
            <input
                type="${inputType}"
                id="${escapeHtml(inputId)}"
                class="form-control"
                ${dataset}
                value="${escapeHtml(displayValue)}"
                placeholder="${field.secret && value ? 'Секрет уже задан' : placeholder}"
                ${disabledAttr}
                ${requiredAttr}
                ${minAttr}
                ${maxAttr}
                ${stepAttr}
            >
            ${hintHtml}
            ${secretHint}
        </div>
    `;
}

function renderSettingsGrid(containerId, fields, appConfig, scope) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = fields.map(field => renderSettingField(field, appConfig[field.key], scope)).join('');
}

function collectSettingsPayload(scope) {
    const payload = {};
    const elements = document.querySelectorAll(`[data-setting-scope="${scope}"]`);
    elements.forEach(element => {
        const key = element.dataset.settingKey;
        if (!key) return;

        if (element.type === 'checkbox') {
            payload[key] = element.checked;
            return;
        }

        if (element.tagName === 'SELECT') {
            if (element.value !== '') {
                payload[key] = element.value;
            }
            return;
        }

        if (element.type === 'number') {
            if (element.value !== '') {
                const numericValue = Number(element.value);
                if (!Number.isNaN(numericValue)) {
                    payload[key] = numericValue;
                }
            }
            return;
        }

        if (element.type === 'range') {
            if (element.value !== '') {
                const numericValue = Number(element.value);
                payload[key] = Number.isNaN(numericValue) ? element.value : numericValue;
            }
            return;
        }

        const value = element.value ?? '';
        if (value.trim() !== '') {
            payload[key] = value.trim();
        }
    });
    return payload;
}

function attachRangeDisplay(inputElement, valueElement, formatter) {
    if (!inputElement || !valueElement) return;
    const updateValue = (raw) => {
        if (raw === undefined || raw === null || raw === '') {
            valueElement.textContent = '';
            return;
        }
        if (formatter) {
            valueElement.textContent = formatter(raw);
        } else {
            valueElement.textContent = raw;
        }
    };

    if (!inputElement.dataset.rangeDisplayBound) {
        inputElement.addEventListener('input', (event) => updateValue(event.target.value));
        inputElement.dataset.rangeDisplayBound = 'true';
    }

    updateValue(inputElement.value ?? inputElement.getAttribute('value'));
}

function renderProviderCard(provider) {
    const fieldsHtml = provider.config_fields.map(field => renderProviderField(provider, field)).join('');
    const disabledRadio = !provider.config_ready && !provider.is_active ? 'disabled' : '';
    const radioLabelClass = `radio-label ${disabledRadio ? 'disabled' : ''}`;
    return `
        <div class="provider-card ${provider.is_active ? 'active' : ''}" data-vendor="${escapeHtml(provider.vendor)}">
            <div class="provider-card-header">
                <div>
                    <h3>${escapeHtml(provider.name)}</h3>
                    <span class="status-badge ${provider.is_active ? 'active' : 'inactive'}">
                        ${provider.is_active ? 'Активен' : 'Неактивен'}
                    </span>
                </div>
                <label class="${radioLabelClass}">
                    <input type="radio" name="activeProvider" value="${escapeHtml(provider.vendor)}" ${provider.is_active ? 'checked' : ''} ${disabledRadio}>
                    <span>Активировать</span>
                </label>
            </div>
            <div class="provider-config-form">
                ${fieldsHtml}
            </div>
            <div class="provider-warning hidden"></div>
            <div class="provider-actions">
                <button class="btn-primary provider-save" data-vendor="${escapeHtml(provider.vendor)}" disabled>Сохранить</button>
            </div>
        </div>
    `;
}

function renderProviderField(provider, field) {
    const value = provider.config[field.key];
    const isSecret = field.secret === true;
    const placeholder = isSecret && value ? 'Секрет уже задан' : (field.placeholder || '');
    const displayValue = isSecret ? '' : (value ?? '');
    const safePlaceholder = escapeHtml(placeholder);

    if (field.type === 'select' && Array.isArray(field.choices)) {
        const options = field.choices.map(choice => `
            <option value="${escapeHtml(choice)}" ${choice === value ? 'selected' : ''}>${escapeHtml(choice)}</option>
        `).join('');
        return `
            <div class="provider-field">
                <label for="provider-${escapeHtml(provider.vendor)}-${escapeHtml(field.key)}">${escapeHtml(field.label)}${field.required ? ' *' : ''}</label>
                <select id="provider-${escapeHtml(provider.vendor)}-${escapeHtml(field.key)}" class="form-control" data-provider-field="${escapeHtml(field.key)}" data-secret="${isSecret}">
                    ${options}
                </select>
                ${field.help ? `<small class="form-hint">${escapeHtml(field.help)}</small>` : ''}
            </div>
        `;
    }

    const inputType = field.type === 'password' ? 'password' : field.type === 'number' ? 'number' : 'text';
    return `
        <div class="provider-field">
            <label for="provider-${escapeHtml(provider.vendor)}-${escapeHtml(field.key)}">${escapeHtml(field.label)}${field.required ? ' *' : ''}</label>
            <input
                type="${inputType}"
                id="provider-${escapeHtml(provider.vendor)}-${escapeHtml(field.key)}"
                class="form-control"
                data-provider-field="${escapeHtml(field.key)}"
                data-secret="${isSecret}"
                value="${escapeHtml(displayValue)}"
                placeholder="${safePlaceholder}"
            >
            ${field.help ? `<small class="form-hint">${escapeHtml(field.help)}</small>` : ''}
            ${isSecret && value ? '<small class="form-hint">Оставьте поле пустым, чтобы сохранить текущий ключ.</small>' : ''}
        </div>
    `;
}

function setupProviderCard(vendor) {
    const container = document.getElementById('providersList');
    if (!container) return;
    const card = container.querySelector(`.provider-card[data-vendor="${cssEscape(vendor)}"]`);
    const provider = providerDataMap.get(vendor);
    if (!card || !provider) return;

    const saveButton = card.querySelector('.provider-save');
    if (saveButton) {
        saveButton.disabled = true;
        saveButton.addEventListener('click', async () => {
            await handleProviderSave(vendor, card, saveButton);
        });
    }

    const inputs = card.querySelectorAll('[data-provider-field]');
    inputs.forEach(input => {
        const fieldKey = input.dataset.providerField;
        if (!fieldKey) return;
        const fieldDef = provider.config_fields.find(f => f.key === fieldKey);
        if (!fieldDef) return;
        if (fieldDef.secret) {
            input.value = '';
        } else if (input.tagName !== 'SELECT') {
            input.value = provider.config[fieldKey] ?? '';
        }
        const handler = () => handleProviderInputChange(vendor);
        input.addEventListener('input', handler);
        if (input.tagName === 'SELECT') {
            input.addEventListener('change', handler);
        }
    });

    const radio = card.querySelector('input[name="activeProvider"]');
    if (radio) {
        radio.addEventListener('change', handleProviderRadioChange);
    }
}

function handleProviderInputChange(vendor) {
    updateProviderCardState(vendor);
}

function handleProviderRadioChange() {
    updateAllProviderCardStates();
}

function updateAllProviderCardStates() {
    providerDataMap.forEach((_, vendor) => updateProviderCardState(vendor));
}

function updateProviderCardState(vendor) {
    const container = document.getElementById('providersList');
    const provider = providerDataMap.get(vendor);
    if (!container || !provider) return;

    const card = container.querySelector(`.provider-card[data-vendor="${cssEscape(vendor)}"]`);
    if (!card) return;

    const { isValid, missing } = validateProviderInputs(card, provider);
    const hasChanges = detectProviderChanges(card, provider);

    const warning = card.querySelector('.provider-warning');
    if (warning) {
        if (!isValid) {
            warning.classList.remove('hidden');
            warning.textContent = `Заполните обязательные поля: ${missing.map(escapeHtml).join(', ')}`;
        } else {
            warning.classList.add('hidden');
            warning.textContent = '';
        }
    }

    const saveButton = card.querySelector('.provider-save');
    if (saveButton) {
        saveButton.disabled = !hasChanges;
    }

    const radio = card.querySelector('input[name="activeProvider"]');
    if (radio && !provider.is_active) {
        radio.disabled = !isValid;
        if (radio.disabled) {
            radio.checked = false;
        }
        radio.parentElement.classList.toggle('disabled', radio.disabled);
    }
}

function validateProviderInputs(card, provider) {
    const missing = [];
    provider.config_fields.forEach(field => {
        if (!field.required) {
            return;
        }
        const input = card.querySelector(`[data-provider-field="${cssEscape(field.key)}"]`);
        if (!input) return;
        const value = input.tagName === 'SELECT' ? input.value : input.value.trim();
        const hasPersistentValue = provider.filled_fields?.[field.key] === true;
        const isValid = value !== '' || hasPersistentValue;
        if (!isValid) {
            missing.push(field.label || field.key);
        }
    });

    return { isValid: missing.length === 0, missing };
}

function detectProviderChanges(card, provider) {
    let changed = false;
    const inputs = card.querySelectorAll('[data-provider-field]');
    inputs.forEach(input => {
        const fieldKey = input.dataset.providerField;
        if (!fieldKey) return;
        const fieldDef = provider.config_fields.find(f => f.key === fieldKey);
        if (!fieldDef) return;
        if (fieldDef.secret) {
            if (input.value.trim()) {
                changed = true;
            }
        } else if (input.tagName === 'SELECT') {
            if ((provider.config[fieldKey] ?? '') !== input.value) {
                changed = true;
            }
        } else if ((provider.config[fieldKey] ?? '') !== input.value.trim()) {
            changed = true;
        }
    });

    const activeVendor = getActiveProviderVendor();
    if (!provider.is_active && activeVendor === provider.vendor) {
        changed = true;
    }

    return changed;
}

function getActiveProviderVendor() {
    const selected = document.querySelector('input[name="activeProvider"]:checked');
    return selected ? selected.value : null;
}

async function handleProviderSave(vendor, card, button) {
    const provider = providerDataMap.get(vendor);
    if (!provider) return;

    const config = {};
    card.querySelectorAll('[data-provider-field]').forEach(input => {
        const fieldKey = input.dataset.providerField;
        if (!fieldKey) return;
        const fieldDef = provider.config_fields.find(f => f.key === fieldKey);
        if (!fieldDef) return;
        if (fieldDef.secret) {
            const value = input.value.trim();
            if (value) {
                config[fieldKey] = value;
            }
            return;
        }

        if (input.tagName === 'SELECT') {
            const currentValue = provider.config[fieldKey] ?? '';
            if (input.value !== currentValue) {
                config[fieldKey] = input.value;
            }
        } else {
            const newValue = input.value.trim();
            const currentValue = (provider.config[fieldKey] ?? '').trim();
            if (newValue !== currentValue) {
                config[fieldKey] = newValue;
            }
        }
    });

    const activeVendor = getActiveProviderVendor();
    const activate = activeVendor === vendor;

    button.disabled = true;
    button.textContent = 'Сохранение...';

    try {
        const result = await api.updateProviderConfig(vendor, { activate, config });
        handleConfigUpdateResult(result);
        await loadProviders();
    } catch (error) {
        console.error('Ошибка обновления провайдера:', error);
        let message = 'Ошибка обновления настроек провайдера';
        if (error?.detail) {
            message = error.detail;
        } else if (error instanceof Error && error.message) {
            message = error.message;
        }
        showToast(message, 'error');
        button.disabled = false;
        button.textContent = 'Сохранить';
    }
}

/**
 * Загрузка пользователей.
 */
async function loadUsers(page = 1) {
    const search = document.getElementById('userSearch')?.value || null;
    const data = await api.getUsers(page, 20, search);
    
    const tbody = document.getElementById('usersTableBody');
    if (data.users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center">Пользователи не найдены</td></tr>';
        return;
    }

    tbody.innerHTML = data.users.map(user => `
        <tr>
            <td>${user.id}</td>
            <td>${user.telegram_id}</td>
            <td>${user.username || '-'}</td>
            <td>${user.first_name || '-'}</td>
            <td>${user.is_admin ? '✅' : '❌'}</td>
            <td>${formatDate(user.created_at)}</td>
            <td>
                <button class="btn-secondary" onclick="viewUser(${user.id})" style="padding: 6px 12px; font-size: 12px;">
                    Детали
                </button>
            </td>
        </tr>
    `).join('');

    // Пагинация
    updatePagination('usersPagination', data.page, data.total_pages, (newPage) => {
        currentUsersPage = newPage;
        loadUsers(newPage);
    });

    // Поиск
    const searchInput = document.getElementById('userSearch');
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                currentUsersPage = 1;
                loadUsers(1);
            }, 500);
        });
    }
}

/**
 * Загрузка статистики.
 */
async function loadStats() {
    // Статистика по пользователям
    const usersStats = await api.getUsersStats(100);
    const usersTbody = document.getElementById('statsTableBody');
    usersTbody.innerHTML = usersStats.map(stat => `
        <tr>
            <td>${stat.username || stat.first_name || stat.telegram_id}</td>
            <td>${formatNumber(stat.total_requests)}</td>
            <td>${formatNumber(stat.total_tokens)}</td>
            <td>${stat.last_request_at ? formatDate(stat.last_request_at) : '-'}</td>
        </tr>
    `).join('');

    // Статистика по провайдерам
    const providersStats = await api.getProvidersStats();
    const providersTbody = document.getElementById('providersStatsTableBody');
    providersTbody.innerHTML = providersStats.map(stat => `
        <tr>
            <td><strong>${stat.vendor}</strong></td>
            <td>${formatNumber(stat.total_requests)}</td>
            <td>${formatNumber(stat.total_tokens)}</td>
            <td>${stat.unique_users}</td>
            <td>${formatNumber(stat.cache_hits)}</td>
            <td>${formatNumber(stat.cache_misses)}</td>
        </tr>
    `).join('');
}

/**
 * Загрузка аудита.
 */
async function loadAudit(page = 1) {
    const filters = {
        action: null,
        user_id: null,
        date_from: document.getElementById('auditDateFrom')?.value || null,
        date_to: document.getElementById('auditDateTo')?.value || null,
    };

    const data = await api.getAuditLogs(page, 50, filters);
    
    const tbody = document.getElementById('auditTableBody');
    if (data.logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center">Записи не найдены</td></tr>';
        return;
    }

    tbody.innerHTML = data.logs.map(log => `
        <tr>
            <td>${log.id}</td>
            <td>${log.actor_username || log.actor_id || '-'}</td>
            <td>${log.target_username || log.target_user_id || '-'}</td>
            <td><code>${log.action}</code></td>
            <td><pre style="max-width: 200px; overflow: auto; font-size: 12px;">${JSON.stringify(log.details, null, 2)}</pre></td>
            <td>${formatDate(log.created_at)}</td>
        </tr>
    `).join('');

    // Пагинация
    updatePagination('auditPagination', data.page, data.total_pages, (newPage) => {
        currentAuditPage = newPage;
        loadAudit(newPage);
    });

    // Фильтры
    document.getElementById('auditFilterBtn')?.addEventListener('click', () => {
        currentAuditPage = 1;
        loadAudit(1);
    });

    // Экспорт
    document.getElementById('auditExportBtn')?.addEventListener('click', async () => {
        try {
            await api.exportAuditCSV(filters);
            showToast('Экспорт завершен', 'success');
        } catch (error) {
            showToast('Ошибка экспорта', 'error');
        }
    });
}

/**
 * Просмотр деталей пользователя.
 */
async function viewUser(userId) {
    const user = await api.getUser(userId);
    const modal = document.getElementById('userModal');
    const content = document.getElementById('userModalContent');
    
    content.innerHTML = `
        <div style="margin-bottom: 20px;">
            <strong>ID:</strong> ${user.id}<br>
            <strong>Telegram ID:</strong> ${user.telegram_id}<br>
            <strong>Username:</strong> ${user.username || '-'}<br>
            <strong>Имя:</strong> ${user.first_name || '-'} ${user.last_name || ''}<br>
            <strong>Язык:</strong> ${user.language_code || '-'}<br>
            <strong>Админ:</strong> ${user.is_admin ? 'Да' : 'Нет'}<br>
            <strong>Создан:</strong> ${formatDate(user.created_at)}
        </div>
        ${user.settings ? `
            <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--border-color);">
                <h3>Настройки:</h3>
                <strong>Подпись:</strong> ${user.settings.signature}<br>
                <strong>Валюта:</strong> ${user.settings.default_currency.toUpperCase()}<br>
                ${user.settings.exchange_rate ? `<strong>Курс:</strong> ${user.settings.exchange_rate} ₽ за 1 ¥<br>` : ''}
            </div>
        ` : ''}
        <div style="margin-top: 20px;">
            <button class="btn-primary" onclick="makeUserAdmin(${user.id})" ${user.is_admin ? 'disabled' : ''}>
                Назначить админом
            </button>
            <button class="btn-secondary" onclick="revokeUserAdmin(${user.id})" ${!user.is_admin ? 'disabled' : ''} style="margin-left: 10px;">
                Отозвать права админа
            </button>
        </div>
    `;
    
    modal.classList.add('show');
    
    document.getElementById('userModalClose').onclick = () => {
        modal.classList.remove('show');
    };
    
    modal.onclick = (e) => {
        if (e.target === modal) {
            modal.classList.remove('show');
        }
    };
}

/**
 * Назначить пользователя админом.
 */
async function makeUserAdmin(userId) {
    if (!confirm('Назначить этого пользователя администратором?')) return;
    try {
        await api.makeAdmin(userId);
        showToast('Пользователь назначен администратором', 'success');
        document.getElementById('userModal').classList.remove('show');
        loadUsers(currentUsersPage);
    } catch (error) {
        showToast('Ошибка назначения админа', 'error');
    }
}

/**
 * Отозвать права админа.
 */
async function revokeUserAdmin(userId) {
    if (!confirm('Отозвать права администратора у этого пользователя?')) return;
    try {
        await api.revokeAdmin(userId);
        showToast('Права администратора отозваны', 'success');
        document.getElementById('userModal').classList.remove('show');
        loadUsers(currentUsersPage);
    } catch (error) {
        showToast('Ошибка отзыва прав', 'error');
    }
}

/**
 * Обновление пагинации.
 */
function updatePagination(containerId, currentPage, totalPages, onPageChange) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }
    
    let html = '';
    
    // Кнопка "Назад"
    html += `<button ${currentPage === 1 ? 'disabled' : ''} onclick="onPageChange(${currentPage - 1})">‹</button>`;
    
    // Номера страниц
    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages || (i >= currentPage - 2 && i <= currentPage + 2)) {
            html += `<button ${i === currentPage ? 'style="background-color: var(--primary-color); color: white;"' : ''} onclick="onPageChange(${i})">${i}</button>`;
        } else if (i === currentPage - 3 || i === currentPage + 3) {
            html += `<span class="page-info">...</span>`;
        }
    }
    
    // Кнопка "Вперед"
    html += `<button ${currentPage === totalPages ? 'disabled' : ''} onclick="onPageChange(${currentPage + 1})">›</button>`;
    
    // Информация о странице
    html += `<span class="page-info">Страница ${currentPage} из ${totalPages}</span>`;
    
    container.innerHTML = html;
    
    // Обновляем обработчики
    container.querySelectorAll('button').forEach(btn => {
        const onclick = btn.getAttribute('onclick');
        if (onclick) {
            btn.onclick = () => {
                const match = onclick.match(/onPageChange\((\d+)\)/);
                if (match) {
                    onPageChange(parseInt(match[1]));
                }
            };
        }
    });
}

/**
 * Показ уведомления (toast).
 * @param {string} message - Текст сообщения
 * @param {string} type - Тип уведомления ('success', 'error', 'warning', 'info')
 * @param {number} duration - Длительность показа в миллисекундах (0 = бесконечно)
 * @returns {HTMLElement} - Элемент toast для возможности удаления
 */
function showToast(message, type = 'success', duration = 3000) {
    const container = document.getElementById('toastContainer');
    if (!container) {
        console.warn('Toast container not found');
        return null;
    }
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    // Анимация появления
    setTimeout(() => {
        toast.style.animation = 'slideInRight 0.3s';
    }, 10);
    
    // Автоматическое скрытие (если duration > 0)
    if (duration > 0) {
        setTimeout(() => {
            toast.style.animation = 'slideInRight 0.3s reverse';
            setTimeout(() => {
                if (toast.parentNode === container) {
                    container.removeChild(toast);
                }
            }, 300);
        }, duration);
    }
    
    // Возвращаем элемент для возможности ручного удаления
    toast.remove = function() {
        if (toast.parentNode === container) {
            toast.style.animation = 'slideInRight 0.3s reverse';
            setTimeout(() => {
                if (toast.parentNode === container) {
                    container.removeChild(toast);
                }
            }, 300);
        }
    };
    
    return toast;
}

/**
 * Форматирование числа.
 */
function formatNumber(num) {
    return new Intl.NumberFormat('ru-RU').format(num);
}

/**
 * Форматирование даты.
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('ru-RU', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    }).format(date);
}

/**
 * Загрузка логов.
 */
let logsHandlersAttached = false;

async function loadLogs() {
    if (logStreamActive) {
        stopLogStream();
    }

    const linesEl = document.getElementById('logLines');
    const levelEl = document.getElementById('logLevel');
    const searchEl = document.getElementById('logSearch');
    
    const lines = linesEl ? parseInt(linesEl.value) || 100 : 100;
    const level = levelEl ? (levelEl.value || null) : null;
    const search = searchEl ? (searchEl.value || null) : null;
    
    const content = document.getElementById('logsContent');
    if (!content) return;
    
    content.textContent = 'Загрузка логов...';
    
    try {
        const data = await api.getLogs(lines, level, search);
        
        if (data && data.logs && Array.isArray(data.logs) && data.logs.length > 0) {
            content.textContent = data.logs.join('\n');
        } else if (data && data.message) {
            content.textContent = data.message;
        } else {
            content.textContent = 'Логи не найдены или файл логов пуст';
        }
    } catch (error) {
        console.error('Ошибка загрузки логов:', error);
        content.textContent = `Ошибка загрузки логов: ${error.message || 'Неизвестная ошибка'}`;
        showToast('Ошибка загрузки логов', 'error');
    }
    
    // Обработчики - добавляем только один раз
    if (!logsHandlersAttached) {
        const refreshBtn = document.getElementById('refreshLogsBtn');
        const downloadBtn = document.getElementById('downloadLogsBtn');
        const streamBtn = document.getElementById('streamLogsBtn');
        
        if (refreshBtn) {
            const newBtn = refreshBtn.cloneNode(true);
            refreshBtn.parentNode.replaceChild(newBtn, refreshBtn);
            newBtn.addEventListener('click', loadLogs);
        }
        
        if (downloadBtn) {
            const newBtn = downloadBtn.cloneNode(true);
            downloadBtn.parentNode.replaceChild(newBtn, downloadBtn);
            newBtn.addEventListener('click', async () => {
                try {
                    await api.downloadLogs(1);
                    showToast('Логи скачаны', 'success');
                } catch (error) {
                    console.error('Ошибка скачивания логов:', error);
                    showToast('Ошибка скачивания логов', 'error');
                }
            });
        }

        if (streamBtn) {
            const newBtn = streamBtn.cloneNode(true);
            streamBtn.parentNode.replaceChild(newBtn, streamBtn);
            newBtn.addEventListener('click', toggleLogStream);
        }
        
        logsHandlersAttached = true;
    }
}

async function toggleLogStream() {
    const button = document.getElementById('streamLogsBtn');
    const content = document.getElementById('logsContent');
    if (!button || !content) return;

    if (logStreamActive) {
        stopLogStream();
        return;
    }

    if (!api.token) {
        showToast('Необходимо выполнить вход', 'error');
        return;
    }

    logStreamController = new AbortController();
    logStreamActive = true;
    button.textContent = 'Остановить поток';
    button.classList.add('active');

    try {
        const response = await fetch('/api/admin/logs/stream', {
            headers: {
                'Authorization': `Bearer ${api.token}`,
            },
            signal: logStreamController.signal,
        });

        if (!response.ok || !response.body) {
            throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (logStreamActive) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const events = buffer.split('\n\n');
            buffer = events.pop() || '';

            events.forEach(eventChunk => {
                eventChunk.split('\n').forEach(line => {
                    if (line.startsWith('data:')) {
                        const payload = line.replace(/^data:\s*/, '');
                        appendLogLine(payload);
                    }
                });
            });
        }
    } catch (error) {
        if (logStreamActive) {
            console.error('Ошибка потоковой загрузки логов:', error);
            showToast('Ошибка потоковой загрузки логов', 'error');
        }
    } finally {
        stopLogStream();
    }
}

function stopLogStream() {
    const button = document.getElementById('streamLogsBtn');
    if (logStreamController) {
        logStreamController.abort();
        logStreamController = null;
    }
    logStreamActive = false;
    if (button) {
        button.textContent = 'Поток (SSE)';
        button.classList.remove('active');
    }
}

function appendLogLine(line) {
    const content = document.getElementById('logsContent');
    if (!content) return;

    const text = line.trimEnd();
    if (!text) return;

    const isAtBottom = Math.abs(content.scrollHeight - content.clientHeight - content.scrollTop) < 10;
    if (content.textContent.length > 0) {
        content.textContent += '\n';
    }
    content.textContent += text;

    const maxLines = 2000;
    const lines = content.textContent.split('\n');
    if (lines.length > maxLines) {
        content.textContent = lines.slice(lines.length - maxLines).join('\n');
    }

    if (isAtBottom) {
        content.scrollTop = content.scrollHeight;
    }
}

/**
 * Загрузка платформ.
 */
let platformHandlersAttached = false;

async function loadPlatforms() {
    try {
        const config = await api.getPlatformsConfig();
        const stats = await api.getPlatformsStats();
        
        // Управление платформами
        const container = document.getElementById('platformsList');
        const platforms = [
            { key: 'taobao', name: 'Taobao', icon: '🛍️' },
            { key: 'pinduoduo', name: 'Pinduoduo', icon: '📦' },
            { key: 'szwego', name: 'Szwego', icon: '🛒' },
            { key: '1688', name: '1688', icon: '🏪' },
        ];
        
        container.innerHTML = platforms.map(p => {
            const enabled = config[p.key]?.enabled !== false;
            return `
                <div class="platform-card ${enabled ? 'enabled' : 'disabled'}">
                    <div class="platform-icon">${p.icon}</div>
                    <div class="platform-info">
                        <h3>${p.name}</h3>
                        <span class="platform-status ${enabled ? 'active' : 'inactive'}">
                            ${enabled ? '✅ Включена' : '❌ Выключена'}
                        </span>
                    </div>
                    <label class="switch">
                        <input type="checkbox" data-platform="${p.key}" ${enabled ? 'checked' : ''}>
                        <span class="slider"></span>
                    </label>
                </div>
            `;
        }).join('');
        
        // Используем делегирование событий для обработки переключений
        // Это предотвращает дублирование обработчиков
        if (!platformHandlersAttached) {
            container.addEventListener('change', async (e) => {
                if (e.target.type === 'checkbox' && e.target.dataset.platform) {
                    const platform = e.target.dataset.platform;
                    const enabled = e.target.checked;
                    // Блокируем чекбокс во время запроса
                    e.target.disabled = true;
                    try {
                        await api.updatePlatformConfig(platform, enabled);
                        showToast(`Платформа ${platform} ${enabled ? 'включена' : 'выключена'}`, 'success');
                        // Обновляем только статистику, не перезагружая всю страницу
                        await updatePlatformsStats();
                        // Обновляем визуальное состояние карточки
                        const card = e.target.closest('.platform-card');
                        if (card) {
                            if (enabled) {
                                card.classList.remove('disabled');
                                card.classList.add('enabled');
                                const statusSpan = card.querySelector('.platform-status');
                                if (statusSpan) {
                                    statusSpan.className = 'platform-status active';
                                    statusSpan.textContent = '✅ Включена';
                                }
                            } else {
                                card.classList.remove('enabled');
                                card.classList.add('disabled');
                                const statusSpan = card.querySelector('.platform-status');
                                if (statusSpan) {
                                    statusSpan.className = 'platform-status inactive';
                                    statusSpan.textContent = '❌ Выключена';
                                }
                            }
                        }
                    } catch (error) {
                        console.error('Ошибка обновления платформы:', error);
                        showToast('Ошибка обновления платформы', 'error');
                        e.target.checked = !enabled; // Откатываем изменение
                    } finally {
                        e.target.disabled = false;
                    }
                }
            });
            platformHandlersAttached = true;
        }
        
        // Статистика по платформам
        await updatePlatformsStats();
        
    } catch (error) {
        console.error('Ошибка загрузки платформ:', error);
        showToast('Ошибка загрузки платформ', 'error');
    }
}

/**
 * Обновление статистики платформ.
 */
async function updatePlatformsStats() {
    try {
        const stats = await api.getPlatformsStats();
        const statsTbody = document.getElementById('platformsStatsTableBody');
        if (statsTbody) {
            statsTbody.innerHTML = stats.map(s => `
                <tr>
                    <td><strong>${s.platform}</strong></td>
                    <td><span class="status-badge ${s.enabled ? 'active' : 'inactive'}">${s.enabled ? 'Включена' : 'Выключена'}</span></td>
                    <td>${formatNumber(s.total_requests || 0)}</td>
                    <td>${s.last_request_at ? formatDate(s.last_request_at) : '-'}</td>
                </tr>
            `).join('');
        }
    } catch (error) {
        console.error('Ошибка обновления статистики платформ:', error);
    }
}

/**
 * Загрузка документации.
 */
async function loadDocs() {
    const content = document.getElementById('docContent');
    
    // Инициализация вкладок документации
    const docTabs = document.querySelectorAll('#page-docs .tab-btn');
    docTabs.forEach(btn => {
        btn.addEventListener('click', () => {
            docTabs.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const tab = btn.dataset.docTab;
            showDocTab(tab);
        });
    });
    
    // Показываем первую вкладку
    showDocTab('admin');
}

/**
 * Показать вкладку документации.
 */
function showDocTab(tab) {
    const content = document.getElementById('docContent');
    
    if (tab === 'admin') {
        content.innerHTML = `
            <div class="doc-section">
                <h3>📖 Руководство для администраторов</h3>
                <p>Этот раздел описывает ежедневные задачи и процедуры сопровождения сервиса.</p>
                <h4>Настройки и конфигурация</h4>
                <ul>
                    <li><strong>Изменение параметров</strong>: в разделе «Настройки» редактируйте значения и нажимайте «Сохранить» для соответствующей вкладки.</li>
                    <li><strong>Динамическое применение</strong>: большинство изменений (API ключи, токены, лимиты) применяются сразу без перезапуска.</li>
                    <li><strong>Перезапуск требуется</strong>: если изменены критичные параметры (например, подключение к БД или порт панели), появится блок «Необходим перезапуск». Нажмите кнопку «Перезапустить сервисы», чтобы автоматически перезапустить бота и админку.</li>
                    <li><strong>Мониторинг Pending-настроек</strong>: список ключей, ожидающих перезапуска, отображается прямо в уведомлении.</li>
                </ul>
                <h4>Работа с провайдерами LLM</h4>
                <ul>
                    <li>В разделе «LLM провайдеры» можно отредактировать конфигурацию каждого провайдера: API ключи, идентификаторы моделей и др.</li>
                    <li>Чтобы активировать провайдера, выберите пункт «Активировать» и сохраните изменения.</li>
                    <li>Секреты хранятся в безопасном виде — оставьте поле пустым, если нужно сохранить существующий ключ.</li>
                </ul>
                <h4>Логи и диагностика</h4>
                <ul>
                    <li>Раздел «Логи» предоставляет быстрый просмотр последних записей с фильтром по уровню и поиском.</li>
                    <li>Для долгосрочного хранения используйте кнопку «Скачать» — логи агрегируются и хранятся не более 30 дней или 100 МБ.</li>
                </ul>
                <h4>Операционные процедуры</h4>
                <ul>
                    <li><strong>Перезапуск сервисов</strong>: инициируйте из панели или выполните <code>python scripts/restart_services.py</code> на сервере.</li>
                    <li><strong>Поиск висящих процессов</strong>: используйте <code>python scripts/find_bot_processes.py --kill</code>.</li>
                    <li><strong>Миграции БД</strong>: запускать через <code>alembic upgrade head</code> при обновлении версии.</li>
                </ul>
            </div>
        `;
    } else if (tab === 'dev') {
        content.innerHTML = `
            <div class="doc-section">
                <h3>👨‍💻 Документация для разработчиков</h3>
                <p>Краткое описание архитектуры и точек расширения проекта.</p>
                <h4>Архитектура</h4>
                <pre><code>src/
├── bot/          # Telegram бот (Handlers, Middleware, Error Handling)
├── core/         # Базовая логика (config, logging_config, config_manager, restart_manager)
├── services/     # Сервисы доменной логики (app_settings, runtime_settings, llm, ...)
├── admin/        # Админ-панель (FastAPI + фронтенд)
├── api/          # Внешние API-клиенты (YandexGPT, OpenAI, ProxiAPI)
├── db/           # SQLAlchemy модели, сессии, миграции
└── scripts/      # Утилиты сопровождения (перезапуск, поиск процессов)</code></pre>
                <h4>Система конфигурации</h4>
                <ul>
                    <li><strong>Runtime settings</strong>: таблица <code>runtime_settings</code> хранит актуальные значения. При старте данные загружаются из <code>app_settings.app_config</code> или .env.</li>
                    <li><strong>ConfigManager</strong> управляет обновлением настроек, синхронизируя runtime-таблицу и глобальный объект <code>settings</code>.</li>
                    <li><strong>Pending restart</strong>: значения, требующие рестарта, сохраняются в <code>app_settings.pending_restart_config</code> и отображаются в UI.</li>
                </ul>
                <h4>Логирование</h4>
                <ul>
                    <li>Единый конфиг задаётся в <code>src/core/logging_config.py</code>.</li>
                    <li>Логи пишутся в <code>logs/app.log</code> с ротацией (5 МБ × 20 файлов, максимум 100 МБ и 30 дней хранения).</li>
                    <li>Для дополнительной отладки используйте уровни <code>DEBUG</code>/<code>INFO</code> на соответствующих логгерах.</li>
                </ul>
                <h4>Миграции и база данных</h4>
                <ul>
                    <li>Все структурные изменения оформляйте миграциями Alembic (см. папку <code>alembic/versions</code>).</li>
                    <li>При добавлении новых JSON-полей используйте <code>MutableDict</code>, чтобы SQLAlchemy отслеживал изменения.</li>
                    <li>Асинхронные операции выполняйте через <code>get_db_session</code>, который обеспечивает автокоммит/rollback.</li>
                </ul>
                <h4>CI/CD и эксплуатация</h4>
                <ul>
                    <li>Перед развёртыванием: <code>pip install -r requirements.txt</code>, <code>alembic upgrade head</code>, заполнение <code>.env</code>.</li>
                    <li>Для запуска используйте <code>python run_all.py</code> — скрипт поднимет бота и админку в отдельных процессах.</li>
                    <li>Docker-образы собирайте, копируя корневой проект и выполняя миграции внутри контейнера.</li>
                </ul>
            </div>
        `;
    }
}

// Обработчик кликабельных карточек на дашборде
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        document.querySelectorAll('.stat-card.clickable').forEach(card => {
            card.style.cursor = 'pointer';
            card.addEventListener('click', () => {
                const page = card.dataset.page;
                if (page) {
                    switchPage(page);
                }
            });
        });
    }, 100);
});

/**
 * Инициализация вкладок настроек.
 */
function initSettingsTabs() {
    const tabButtons = document.querySelectorAll('#page-settings .tab-btn');
    const tabContents = document.querySelectorAll('#page-settings .tab-content');
    
    tabButtons.forEach(btn => {
        // Удаляем старые обработчики
        const newBtn = btn.cloneNode(true);
        btn.parentNode.replaceChild(newBtn, btn);
        
        newBtn.addEventListener('click', () => {
            const tab = newBtn.dataset.tab;
            
            // Убираем активный класс со всех кнопок и контента
            document.querySelectorAll('#page-settings .tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('#page-settings .tab-content').forEach(c => c.classList.add('hidden'));
            
            // Активируем выбранную вкладку
            newBtn.classList.add('active');
            const targetTab = document.getElementById(`tab-${tab}`);
            if (targetTab) {
                targetTab.classList.remove('hidden');
            }
        });
    });
}

/**
 * Загрузка основных настроек.
 */
function loadBasicSettings(appConfig) {
    const botFields = [
        { key: 'BOT_TOKEN', label: 'BOT_TOKEN', type: 'password', hint: 'Токен Telegram бота от @BotFather.', secret: true },
        { key: 'ADMIN_CHAT_ID', label: 'ADMIN_CHAT_ID', type: 'text', hint: 'Telegram Chat ID для получения уведомлений от бота.' },
    ];

    const integrationsFields = [
        { key: 'TMAPI_TOKEN', label: 'TMAPI_TOKEN', type: 'password', hint: 'API токен для TMAPI (tmapi.top).', secret: true },
        { key: 'EXCHANGE_RATE_API_KEY', label: 'EXCHANGE_RATE_API_KEY', type: 'password', hint: 'API ключ сервиса конвертации валют.', secret: true },
        { key: 'TMAPI_RATE_LIMIT', label: 'TMAPI_RATE_LIMIT', type: 'number', hint: 'Максимальное количество запросов к TMAPI в секунду.', min: 1, max: 20, step: 1 },
    ];

    const defaultsFields = [
        { key: 'DEFAULT_SIGNATURE', label: 'DEFAULT_SIGNATURE', type: 'text', hint: 'Подпись, добавляемая в конец сообщения по умолчанию.' },
        { key: 'DEFAULT_CURRENCY', label: 'DEFAULT_CURRENCY', type: 'select', hint: 'Базовая валюта для расчётов.', options: [
            { value: 'cny', label: 'CNY (юань)' },
            { value: 'rub', label: 'RUB (рубль)' },
        ] },
        { key: 'DEFAULT_LLM_VENDOR', label: 'DEFAULT_LLM_VENDOR', type: 'select', hint: 'Провайдер LLM по умолчанию.', options: [
            { value: 'yandex', label: 'YandexGPT' },
            { value: 'openai', label: 'OpenAI' },
            { value: 'proxiapi', label: 'ProxiAPI' },
        ] },
        { key: 'LLM_CACHE_TTL_MINUTES', label: 'LLM_CACHE_TTL_MINUTES', type: 'number', hint: 'Время жизни кэша ответов LLM (в минутах).', min: 0, step: 30 },
    ];

    renderSettingsGrid('basicSettings-bot', botFields, appConfig, 'basic');
    renderSettingsGrid('basicSettings-integrations', integrationsFields, appConfig, 'basic');
    renderSettingsGrid('basicSettings-defaults', defaultsFields, appConfig, 'basic');
}

/**
 * Загрузка настроек OCR/LLM для изображений.
 */
function loadImageAnalysisSettings(appConfig) {
    const fields = [
        { key: 'ENABLE_IMAGE_TEXT_ANALYSIS', label: 'Включить анализ изображений', type: 'checkbox', hint: 'Запускает распознавание текста и таблиц на всех фотографиях товара.' },
        { key: 'IMAGE_TEXT_OCR_PROVIDER', label: 'OCR провайдер', type: 'select', hint: 'Сервис, выполняющий распознавание текста.', options: [
            { value: 'yandex', label: 'Yandex Vision (OCR)' },
        ] },
        { key: 'YANDEX_VISION_API_KEY', label: 'YANDEX_VISION_API_KEY', type: 'password', hint: 'API ключ Yandex Vision.', secret: true },
        { key: 'YANDEX_VISION_FOLDER_ID', label: 'YANDEX_VISION_FOLDER_ID', type: 'text', hint: 'ID каталога Yandex Cloud для Vision (если отличается от YANDEX_FOLDER_ID).' },
        { key: 'YANDEX_VISION_MODEL', label: 'YANDEX_VISION_MODEL', type: 'select', hint: 'Модель распознавания Yandex Vision. page - по умолчанию (одноколоночный текст), table - для таблиц, handwritten - рукописный текст.', options: [
            { value: 'page', label: 'page (одноколоночный текст, по умолчанию)' },
            { value: 'page-column-sort', label: 'page-column-sort (многоколоночный текст)' },
            { value: 'handwritten', label: 'handwritten (рукописный текст)' },
            { value: 'table', label: 'table (таблицы)' },
            { value: 'markdown', label: 'markdown (результат в формате Markdown)' },
            { value: 'math-markdown', label: 'math-markdown (математические формулы)' },
        ] },
        { key: 'IMAGE_TEXT_TRANSLATE_LANGUAGE', label: 'IMAGE_TEXT_TRANSLATE_LANGUAGE', type: 'select', hint: 'Язык перевода распознанного текста.', options: [
            { value: 'ru', label: 'ru (русский)' },
            { value: 'en', label: 'en (английский)' },
        ] },
        { key: 'IMAGE_TEXT_OUTPUT_DIR', label: 'IMAGE_TEXT_OUTPUT_DIR', type: 'text', hint: 'Каталог для сохранения визуализированных таблиц и вспомогательных изображений.' },
    ];

    renderSettingsGrid('imageSettingsGrid', fields, appConfig, 'image');

    const promptEl = document.getElementById('imageSummaryPrompt');
    if (promptEl) {
        promptEl.value = appConfig.IMAGE_TEXT_SUMMARY_PROMPT || '';
    }
}

/**
 * Загрузка настроек базы данных.
 */
function loadDatabaseSettings(appConfig) {
    const fields = [
        { key: 'POSTGRES_HOST', label: 'POSTGRES_HOST', type: 'text', hint: 'Хост сервера PostgreSQL (обычно localhost или адрес контейнера).' },
        { key: 'POSTGRES_PORT', label: 'POSTGRES_PORT', type: 'number', hint: 'Порт PostgreSQL.', min: 1, max: 65535 },
        { key: 'POSTGRES_DB', label: 'POSTGRES_DB', type: 'text', hint: 'Имя базы данных.' },
        { key: 'POSTGRES_USER', label: 'POSTGRES_USER', type: 'text', hint: 'Имя пользователя PostgreSQL.' },
        { key: 'POSTGRES_PASSWORD', label: 'POSTGRES_PASSWORD', type: 'password', hint: 'Пароль пользователя PostgreSQL.', secret: true },
        { key: 'POSTGRES_SSLMODE', label: 'POSTGRES_SSLMODE', type: 'select', hint: 'Режим подключения через SSL.', options: [
            { value: 'prefer', label: 'prefer' },
            { value: 'require', label: 'require' },
            { value: 'disable', label: 'disable' },
        ] },
    ];

    renderSettingsGrid('databaseSettings', fields, appConfig, 'database');
}

/**
 * Загрузка системных настроек.
 */
function loadSystemSettings(appConfig) {
    const fields = [
        { key: 'DEBUG_MODE', label: 'DEBUG_MODE', type: 'checkbox', hint: 'Включает детализированные логи и отладочные сообщения.' },
        { key: 'MOCK_MODE', label: 'MOCK_MODE', type: 'checkbox', hint: 'Использовать mock-данные вместо реальных API-запросов.' },
        { key: 'DISABLE_SSL_VERIFY', label: 'DISABLE_SSL_VERIFY', type: 'checkbox', hint: 'Отключить проверку SSL-сертификатов (не рекомендуется).' },
        { key: 'ADMIN_JWT_SECRET', label: 'ADMIN_JWT_SECRET', type: 'password', hint: 'Секретный ключ для подписи JWT токенов админ-панели.', secret: true },
        { key: 'ADMIN_PANEL_PORT', label: 'ADMIN_PANEL_PORT', type: 'number', hint: 'HTTP-порт, на котором доступна админ-панель.', min: 1, max: 65535 },
    ];

    renderSettingsGrid('systemSettings', fields, appConfig, 'system');
}

/**
 * Настройка обработчиков сохранения.
 */
function setupSettingsHandlers() {
    // Основные настройки
    const saveBasicBtn = document.getElementById('saveBasicSettingsBtn');
    if (saveBasicBtn) {
        // Удаляем старые обработчики
        const newBtn = saveBasicBtn.cloneNode(true);
        saveBasicBtn.parentNode.replaceChild(newBtn, saveBasicBtn);
        
        newBtn.addEventListener('click', async () => {
            const config = collectSettingsPayload('basic');
            if (Object.keys(config).length === 0) {
                showToast('Изменений не обнаружено', 'info');
                return;
            }
            try {
                const result = await api.updateAppConfig(config);
                handleConfigUpdateResult(result);
            } catch (error) {
                console.error('Ошибка сохранения основных настроек:', error);
                showToast('Ошибка сохранения настроек', 'error');
            }
        });
    }

    // Настройки базы данных
    const saveDbBtn = document.getElementById('saveDatabaseSettingsBtn');
    if (saveDbBtn) {
        const newBtn = saveDbBtn.cloneNode(true);
        saveDbBtn.parentNode.replaceChild(newBtn, saveDbBtn);
        
        newBtn.addEventListener('click', async () => {
            const config = collectSettingsPayload('database');
            if (Object.keys(config).length === 0) {
                showToast('Изменений не обнаружено', 'info');
                return;
            }
            try {
                const result = await api.updateAppConfig(config);
                handleConfigUpdateResult(result);
            } catch (error) {
                console.error('Ошибка сохранения настроек БД:', error);
                showToast('Ошибка сохранения настроек БД', 'error');
            }
        });
    }

    // Настройки анализа изображений
    const saveImageBtn = document.getElementById('saveImageSettingsBtn');
    if (saveImageBtn) {
        const newBtn = saveImageBtn.cloneNode(true);
        saveImageBtn.parentNode.replaceChild(newBtn, saveImageBtn);

        newBtn.addEventListener('click', async () => {
            const config = collectSettingsPayload('image');
            const promptEl = document.getElementById('imageSummaryPrompt');
            if (promptEl) {
                config.IMAGE_TEXT_SUMMARY_PROMPT = promptEl.value || '';
            }

            if (Object.keys(config).length === 0) {
                showToast('Изменений не обнаружено', 'info');
                return;
            }

            try {
                const result = await api.updateAppConfig(config);
                handleConfigUpdateResult(result);
            } catch (error) {
                console.error('Ошибка сохранения настроек распознавания изображений:', error);
                showToast('Ошибка сохранения настроек', 'error');
            }
        });
    }

    // Системные настройки
    const saveSysBtn = document.getElementById('saveSystemSettingsBtn');
    if (saveSysBtn) {
        const newBtn = saveSysBtn.cloneNode(true);
        saveSysBtn.parentNode.replaceChild(newBtn, saveSysBtn);
        
        newBtn.addEventListener('click', async () => {
            const config = collectSettingsPayload('system');
            if (Object.keys(config).length === 0) {
                showToast('Изменений не обнаружено', 'info');
                return;
            }
            try {
                const result = await api.updateAppConfig(config);
                handleConfigUpdateResult(result);
            } catch (error) {
                console.error('Ошибка сохранения системных настроек:', error);
                showToast('Ошибка сохранения системных настроек', 'error');
            }
        });
    }

    // LLM провайдер
    const saveProviderBtn = document.getElementById('saveProviderBtn');
    if (saveProviderBtn) {
        const newBtn = saveProviderBtn.cloneNode(true);
        saveProviderBtn.parentNode.replaceChild(newBtn, saveProviderBtn);
        
        newBtn.addEventListener('click', async () => {
            const vendor = document.getElementById('llmProviderSelect')?.value;
            if (!vendor) return;
            try {
                const response = await api.updateLLMProvider(vendor);
                applySettingsData(response);
                showToast('Провайдер успешно изменен', 'success');
                await loadProviders();
            } catch (error) {
                console.error('Ошибка сохранения провайдера:', error);
                showToast('Ошибка сохранения провайдера', 'error');
            }
        });
    }

    // Настройки промпта
    const savePromptBtn = document.getElementById('savePromptConfigBtn');
    if (savePromptBtn) {
        const newBtn = savePromptBtn.cloneNode(true);
        savePromptBtn.parentNode.replaceChild(newBtn, savePromptBtn);
        
        newBtn.addEventListener('click', async () => {
            const promptTemplate = document.getElementById('promptTemplate')?.value || '';
            const temperature = parseFloat(document.getElementById('llmTemperature')?.value || 0.05);
            const maxTokens = parseInt(document.getElementById('llmMaxTokens')?.value || 900, 10);
            try {
                const response = await api.updateLLMPromptConfig(promptTemplate, temperature, maxTokens);
                applySettingsData(response);
                showToast('Настройки промпта сохранены', 'success');
            } catch (error) {
                console.error('Ошибка сохранения настроек промпта:', error);
                showToast('Ошибка сохранения настроек промпта', 'error');
            }
        });
    }

    // Персональные данные
    const saveConsentBtn = document.getElementById('saveConsentBtn');
    if (saveConsentBtn) {
        const newBtn = saveConsentBtn.cloneNode(true);
        saveConsentBtn.parentNode.replaceChild(newBtn, saveConsentBtn);
        
        newBtn.addEventListener('click', async () => {
            const text = document.getElementById('consentText')?.value || '';
            const enabled = document.getElementById('personalDataEnabled')?.checked || false;
            if (text.length < 10) {
                showToast('Текст согласия должен быть не менее 10 символов', 'error');
                return;
            }
            try {
                const consentResponse = await api.updateConsentText(text);
                applySettingsData(consentResponse);
                const result = await api.updateAppConfig({ PERSONAL_DATA_ENABLED: enabled });
                handleConfigUpdateResult(result);
            } catch (error) {
                console.error('Ошибка сохранения настроек ПД:', error);
                showToast('Ошибка сохранения настроек ПД', 'error');
            }
        });
    }

    // Перезапуск сервисов
    const restartBtn = document.getElementById('restartSystemBtn');
    if (restartBtn) {
        const newBtn = restartBtn.cloneNode(true);
        restartBtn.parentNode.replaceChild(newBtn, restartBtn);

        newBtn.addEventListener('click', async () => {
            if (!confirm('Вы уверены, что хотите перезапустить сервисы? Это займет 10-15 секунд.')) {
                return;
            }

            newBtn.disabled = true;
            const originalText = newBtn.textContent;
            newBtn.textContent = 'Перезапуск...';
            
            try {
                const response = await api.restartSystem();
                
                if (response.success) {
                    showToast(response.message || 'Перезапуск инициирован', 'info');
                    
                    // Показываем индикатор загрузки
                    const loadingToast = showToast('Ожидание перезапуска сервисов...', 'info', 0);
                    
                    // Ждем 12 секунд для перезапуска
                    await new Promise(resolve => setTimeout(resolve, 12000));
                    
                    // Пытаемся переподключиться к API
                    let reconnected = false;
                    for (let attempt = 0; attempt < 5; attempt++) {
                        try {
                            await api.getStatsOverview();
                            reconnected = true;
                            break;
                        } catch (error) {
                            console.log(`Попытка переподключения ${attempt + 1}/5...`);
                            await new Promise(resolve => setTimeout(resolve, 2000));
                        }
                    }
                    
                    // Закрываем индикатор загрузки
                    if (loadingToast && loadingToast.remove) {
                        loadingToast.remove();
                    }
                    
                    if (reconnected) {
                        showToast('✅ Сервисы успешно перезапущены!', 'success');
                        // Обновляем страницу через 1 секунду
                        setTimeout(() => {
                            window.location.reload();
                        }, 1000);
                    } else {
                        showToast('⚠️ Перезапуск выполнен, но не удалось проверить статус. Обновляю страницу...', 'warning');
                        setTimeout(() => {
                            window.location.reload();
                        }, 2000);
                    }
                } else {
                    showToast(response.message || 'Ошибка при перезапуске', 'error');
                    newBtn.disabled = false;
                    newBtn.textContent = originalText;
                }
            } catch (error) {
                console.error('Ошибка перезапуска сервисов:', error);
                showToast('Не удалось инициировать перезапуск: ' + (error.message || 'неизвестная ошибка'), 'error');
                newBtn.disabled = false;
                newBtn.textContent = originalText;
            }
        });
    }
}

// Экспортируем функции для использования в HTML
window.viewUser = viewUser;
window.makeUserAdmin = makeUserAdmin;
window.revokeUserAdmin = revokeUserAdmin;

