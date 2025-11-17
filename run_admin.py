"""
Запуск административной панели.

Использование:
    python run_admin.py
"""

import uvicorn
from src.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "src.admin.main:app",
        host="0.0.0.0",
        port=settings.ADMIN_PANEL_PORT,
        reload=settings.DEBUG_MODE,
        log_level="info",
    )

