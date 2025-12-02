// Mimi App — главный модуль, обслуживающий взаимодействие с Telegram WebApp API.
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const basePath = window.location.pathname.replace(/\/$/, "");
const apiBase = `${window.location.origin}${basePath}/api`;

const state = {
  role: "user",
  user: null,
  admin: null,
};

const elements = {
  loader: document.getElementById("loader"),
  content: document.getElementById("content"),
  status: document.getElementById("status"),
  userForm: document.getElementById("user-form"),
  signatureInput: document.getElementById("signature"),
  currencySelect: document.getElementById("currency"),
  rateInput: document.getElementById("exchange-rate"),
  adminCard: document.getElementById("admin-card"),
  llmForm: document.getElementById("llm-form"),
  defaultProvider: document.getElementById("default-llm"),
  yandexModel: document.getElementById("yandex-model"),
  openaiModel: document.getElementById("openai-model"),
  translateProvider: document.getElementById("translate-provider"),
  translateModel: document.getElementById("translate-model"),
  translateLegacy: document.getElementById("translate-legacy"),
  flagsForm: document.getElementById("flags-form"),
  convertCurrency: document.getElementById("convert-currency"),
  notify439: document.getElementById("tmapi-notify"),
  debugMode: document.getElementById("debug-mode"),
  mockMode: document.getElementById("mock-mode"),
  accessCard: document.getElementById("access-card"),
  accessSummary: document.getElementById("access-summary"),
  accessDetails: document.getElementById("access-details"),
  accessForm: document.getElementById("access-form"),
  whitelistEnabled: document.getElementById("whitelist-enabled"),
  blacklistEnabled: document.getElementById("blacklist-enabled"),
  addWhitelist: document.getElementById("add-whitelist"),
  removeWhitelist: document.getElementById("remove-whitelist"),
  addBlacklist: document.getElementById("add-blacklist"),
  removeBlacklist: document.getElementById("remove-blacklist"),
};

function showStatus(type, message) {
  elements.status.textContent = message;
  elements.status.className = `status ${type}`;
}

async function apiRequest(path, options = {}) {
  const initData = tg.initData || window.Telegram.WebApp.initData;
  if (!initData) {
    throw new Error("initData отсутствует. Закройте и заново откройте Mimi App.");
  }

  const headers = {
    "Content-Type": "application/json",
    "X-Telegram-Init-Data": initData,
    ...(options.headers || {}),
  };

  const response = await fetch(`${apiBase}${path}`, {
    method: options.method || "GET",
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "Сервер вернул ошибку");
  }
  return data;
}

function renderUserSettings() {
  if (!state.user) {
    return;
  }
  const { signature, default_currency, exchange_rate } = state.user;
  elements.signatureInput.value = signature || "";
  elements.currencySelect.value = default_currency || "cny";
  elements.rateInput.value = exchange_rate ?? "";
}

function renderAdminSettings() {
  if (!state.admin) {
    return;
  }

  const {
    default_llm,
    yandex_model,
    openai_model,
    translate_provider,
    translate_model,
    translate_legacy,
    convert_currency,
    tmapi_notify_439,
    debug_mode,
    mock_mode,
  } = state.admin;

  elements.defaultProvider.value = default_llm || "yandex";
  elements.yandexModel.value = yandex_model || "";
  elements.openaiModel.value = openai_model || "";
  elements.translateProvider.value = translate_provider || "yandex";
  elements.translateModel.value = translate_model || "";
  elements.translateLegacy.checked = Boolean(translate_legacy);

  elements.convertCurrency.checked = Boolean(convert_currency);
  elements.notify439.checked = Boolean(tmapi_notify_439);
  elements.debugMode.checked = Boolean(debug_mode);
  elements.mockMode.checked = Boolean(mock_mode);
}

async function loadAccessRules() {
  if (!elements.accessCard) return;

  try {
    const data = await apiRequest("/admin/access");
    elements.accessCard.classList.remove("hidden");
    elements.accessSummary.textContent = data.summary || "";
    elements.accessDetails.innerHTML = data.details_html || "";

    const summary = data.summary || "";
    elements.whitelistEnabled.checked = summary.includes("Белый список: включён");
    elements.blacklistEnabled.checked = summary.includes("Чёрный список: включён");
  } catch (error) {
    console.error(error);
    elements.accessCard.classList.add("hidden");
  }
}

async function bootstrap() {
  try {
    const config = await apiRequest("/config");
    state.role = config.role;
    state.user = config.user.settings;
    state.admin = config.admin?.settings ?? null;

    renderUserSettings();

    if (state.role === "admin" && state.admin) {
      elements.adminCard.classList.remove("hidden");
      renderAdminSettings();
      await loadAccessRules();
    } else {
      elements.adminCard.classList.add("hidden");
      if (elements.accessCard) {
        elements.accessCard.classList.add("hidden");
      }
    }

    showStatus("success", "Готово к работе");
  } catch (error) {
    console.error(error);
    showStatus("error", error.message);
  } finally {
    elements.loader.classList.add("hidden");
    elements.content.classList.remove("hidden");
  }
}

elements.userForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const body = {
      signature: elements.signatureInput.value.trim(),
      currency: elements.currencySelect.value,
      exchange_rate: elements.rateInput.value
        ? Number(elements.rateInput.value)
        : null,
    };
    const result = await apiRequest("/user", { method: "POST", body });
    state.user = result.settings;
    renderUserSettings();
    showStatus("success", "Настройки пользователя сохранены");
  } catch (error) {
    console.error(error);
    showStatus("error", error.message);
  }
});

elements.llmForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.role !== "admin") {
    showStatus("error", "Нет прав администратора");
    return;
  }

  try {
    const body = {
      default_llm: elements.defaultProvider.value,
      yandex_model: elements.yandexModel.value.trim(),
      openai_model: elements.openaiModel.value.trim(),
      translate_provider: elements.translateProvider.value,
      translate_model: elements.translateModel.value.trim(),
      translate_legacy: elements.translateLegacy.checked,
    };
    const result = await apiRequest("/admin/llm", { method: "POST", body });
    state.admin = result.admin_settings;
    renderAdminSettings();
    showStatus("success", "LLM настройки обновлены");
  } catch (error) {
    console.error(error);
    showStatus("error", error.message);
  }
});

elements.flagsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.role !== "admin") {
    showStatus("error", "Нет прав администратора");
    return;
  }

  try {
    const body = {
      convert_currency: elements.convertCurrency.checked,
      tmapi_notify_439: elements.notify439.checked,
      debug_mode: elements.debugMode.checked,
      mock_mode: elements.mockMode.checked,
    };
    const result = await apiRequest("/admin/options", { method: "POST", body });
    state.admin = result.admin_settings;
    renderAdminSettings();
    showStatus("success", "Опции сохранены");
  } catch (error) {
    console.error(error);
    showStatus("error", error.message);
  }
});

if (elements.accessForm) {
  elements.accessForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.role !== "admin") {
      showStatus("error", "Нет прав администратора");
      return;
    }

    try {
      const body = {
        whitelist_enabled: elements.whitelistEnabled.checked,
        blacklist_enabled: elements.blacklistEnabled.checked,
        add_whitelist_usernames: elements.addWhitelist.value
          ? elements.addWhitelist.value
              .split(",")
              .map((v) => v.trim())
              .filter(Boolean)
          : [],
        remove_whitelist_usernames: elements.removeWhitelist.value
          ? elements.removeWhitelist.value
              .split(",")
              .map((v) => v.trim())
              .filter(Boolean)
          : [],
        add_blacklist_usernames: elements.addBlacklist.value
          ? elements.addBlacklist.value
              .split(",")
              .map((v) => v.trim())
              .filter(Boolean)
          : [],
        remove_blacklist_usernames: elements.removeBlacklist.value
          ? elements.removeBlacklist.value
              .split(",")
              .map((v) => v.trim())
              .filter(Boolean)
          : [],
      };

      const result = await apiRequest("/admin/access", {
        method: "POST",
        body,
      });
      elements.accessSummary.textContent = result.summary || "";
      elements.accessDetails.innerHTML = result.details_html || "";
      elements.addWhitelist.value = "";
      elements.removeWhitelist.value = "";
      elements.addBlacklist.value = "";
      elements.removeBlacklist.value = "";
      showStatus("success", "Правила доступа обновлены");
    } catch (error) {
      console.error(error);
      showStatus("error", error.message);
    }
  });
}

bootstrap();

