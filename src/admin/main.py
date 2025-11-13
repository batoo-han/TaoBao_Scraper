"""
Главный файл FastAPI приложения для админ-панели.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.admin.api import audit, auth, config_reload, logs, providers, settings, stats, system, users
from src.core.config import settings as app_settings
from src.core.config_manager import config_manager
from src.core.logging_config import setup_logging

# Настройка логирования до инициализации приложения
setup_logging()

# Создаем FastAPI приложение
app = FastAPI(
    title="Taobao Scraper Bot - Admin Panel",
    description="Административная панель для управления ботом",
    version="1.0.0",
)

# Настройка CORS (для разработки разрешаем все, в продакшене нужно ограничить)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(auth.router, prefix="/api/admin")
app.include_router(settings.router, prefix="/api/admin")
app.include_router(config_reload.router, prefix="/api/admin")
app.include_router(providers.router, prefix="/api/admin")
app.include_router(stats.router, prefix="/api/admin")
app.include_router(users.router, prefix="/api/admin")
app.include_router(audit.router, prefix="/api/admin")
app.include_router(logs.router, prefix="/api/admin")
app.include_router(system.router, prefix="/api/admin")

# Подключение статических файлов (веб-интерфейс)
import os
from pathlib import Path

admin_web_path = Path(__file__).parent.parent.parent / "admin_web"
if admin_web_path.exists():
    # Статические файлы (CSS, JS, изображения)
    app.mount("/static", StaticFiles(directory=str(admin_web_path)), name="static")
    
    # Главная страница - index.html
    @app.get("/")
    async def root():
        from fastapi.responses import FileResponse
        index_path = admin_web_path / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"message": "Admin panel API", "docs": "/docs"}
    
    # Страница входа
    @app.get("/login.html")
    async def login_page():
        from fastapi.responses import FileResponse
        login_path = admin_web_path / "login.html"
        if login_path.exists():
            return FileResponse(str(login_path))
        return {"error": "Login page not found"}


@app.get("/api/admin/health")
async def health_check():
    """Проверка работоспособности API."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "database": "connected"  # TODO: Проверка подключения к БД
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.admin.main:app",
        host="0.0.0.0",
        port=app_settings.ADMIN_PANEL_PORT,
        reload=app_settings.DEBUG_MODE,
    )

