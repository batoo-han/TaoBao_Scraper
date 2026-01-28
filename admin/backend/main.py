# -*- coding: utf-8 -*-
"""
Точка входа FastAPI приложения админ-панели.

Запуск:
    uvicorn admin.backend.main:app --host 0.0.0.0 --port 8082 --reload
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from logging.handlers import RotatingFileHandler

from pathlib import Path as FilePath

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from admin.backend.config import admin_settings
from admin.backend.database import init_db, close_db

# Настройка логирования
def setup_logging() -> None:
    """Настраивает логирование для админ-панели."""
    
    # Создаём директорию для логов
    log_dir = Path(admin_settings.ADMIN_LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Формат логов
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    formatter = logging.Formatter(log_format)
    
    # Уровень логирования
    log_level = getattr(logging, admin_settings.ADMIN_LOG_LEVEL.upper(), logging.INFO)
    
    # Корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Консольный хэндлер
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)
    
    # Файловый хэндлер с ротацией
    file_handler = RotatingFileHandler(
        admin_settings.ADMIN_LOG_FILE,
        maxBytes=admin_settings.ADMIN_LOG_MAX_SIZE_MB * 1024 * 1024,
        backupCount=admin_settings.ADMIN_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    root_logger.addHandler(file_handler)
    
    # Логгер для админ-панели
    admin_logger = logging.getLogger("admin")
    admin_logger.setLevel(log_level)


# Инициализируем логирование
setup_logging()
logger = logging.getLogger("admin.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Контекстный менеджер жизненного цикла приложения.
    
    Выполняет инициализацию при старте и очистку при остановке.
    """
    # Startup
    logger.info("Запуск админ-панели...")
    logger.info(f"Версия: {admin_settings.APP_VERSION}")
    logger.info(f"Debug режим: {admin_settings.DEBUG}")
    
    try:
        await init_db()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")
        raise
    
    logger.info(f"Админ-панель запущена на http://{admin_settings.ADMIN_HOST}:{admin_settings.ADMIN_PORT}")
    
    yield
    
    # Shutdown
    logger.info("Остановка админ-панели...")
    await close_db()
    logger.info("Админ-панель остановлена")


# Создаём приложение FastAPI
app = FastAPI(
    title=admin_settings.APP_NAME,
    version=admin_settings.APP_VERSION,
    description="REST API для управления Telegram-ботом Taobao Scraper",
    docs_url="/api/docs" if admin_settings.DEBUG else None,
    redoc_url="/api/redoc" if admin_settings.DEBUG else None,
    openapi_url="/api/openapi.json" if admin_settings.DEBUG else None,
    lifespan=lifespan,
)


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=admin_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Глобальный обработчик исключений
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Глобальный обработчик необработанных исключений."""
    logger.error(f"Необработанное исключение: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера"},
    )


# Health check endpoint
@app.get("/health", tags=["System"])
async def health_check():
    """Проверка работоспособности сервиса."""
    return {"status": "ok", "version": admin_settings.APP_VERSION}


# API info endpoint
@app.get("/api", tags=["System"])
async def api_info():
    """Информация об API."""
    return {
        "name": admin_settings.APP_NAME,
        "version": admin_settings.APP_VERSION,
        "docs": "/api/docs" if admin_settings.DEBUG else None,
    }


# Импорт и регистрация роутеров
def register_routers():
    """Регистрирует все API роутеры."""
    from admin.backend.routers import auth, users, stats, settings, admin_users, access
    
    app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
    app.include_router(users.router, prefix="/api/users", tags=["Bot Users"])
    app.include_router(stats.router, prefix="/api/stats", tags=["Statistics"])
    app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
    app.include_router(admin_users.router, prefix="/api/admin-users", tags=["Admin Users"])
    app.include_router(access.router, prefix="/api/access", tags=["Access Control"])


# Регистрируем роутеры
register_routers()


# =============================================================================
# Раздача статических файлов фронтенда (для Docker / production)
# =============================================================================

# Путь к собранному фронтенду (относительно корня проекта)
FRONTEND_DIST = FilePath(__file__).parent.parent / "frontend" / "dist"

# Проверяем, существует ли папка dist (есть только после npm run build)
if FRONTEND_DIST.exists() and FRONTEND_DIST.is_dir():
    logger.info(f"Раздача статических файлов из: {FRONTEND_DIST}")
    
    # Раздача assets (JS, CSS, images)
    assets_path = FRONTEND_DIST / "assets"
    if assets_path.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")
    
    # SPA fallback: все остальные маршруты → index.html
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """
        Отдаёт index.html для всех маршрутов, кроме /api и /health.
        
        Это необходимо для работы React Router в режиме HTML5 History.
        """
        # Пропускаем API и системные эндпоинты
        if full_path.startswith(("api", "health")):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        
        # Пробуем отдать статический файл, если существует
        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        
        # Иначе отдаём index.html (SPA fallback)
        index_path = FRONTEND_DIST / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        
        return JSONResponse(status_code=404, content={"detail": "Not found"})


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "admin.backend.main:app",
        host=admin_settings.ADMIN_HOST,
        port=admin_settings.ADMIN_PORT,
        reload=admin_settings.DEBUG,
        log_level=admin_settings.ADMIN_LOG_LEVEL.lower(),
    )
