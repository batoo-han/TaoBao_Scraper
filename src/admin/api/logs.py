"""
API endpoints для просмотра и выгрузки логов приложения.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.dependencies import get_current_admin_user, get_current_admin_user_optional_token
from src.db.models import AdminUser
from src.db.session import get_db_session

router = APIRouter(prefix="/logs", tags=["logs"])

# Путь к директории с логами
LOGS_DIR = Path("logs")
if not LOGS_DIR.exists():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


@router.get("")
async def get_logs(
    admin_user: Annotated[AdminUser, Depends(get_current_admin_user)],
    lines: int = Query(100, ge=1, le=10000, description="Количество последних строк"),
    level: Optional[str] = Query(None, description="Уровень логирования (DEBUG, INFO, WARNING, ERROR)"),
    search: Optional[str] = Query(None, description="Поиск по тексту"),
):
    """
    Получить последние строки логов.
    
    Args:
        lines: Количество строк для возврата
        level: Фильтр по уровню логирования
        search: Поиск по тексту в логах
    """
    log_file = LOGS_DIR / "app.log"
    
    if not log_file.exists():
        return {
            "logs": [],
            "total_lines": 0,
            "message": "Файл логов не найден"
        }
    
    try:
        # Читаем последние N строк из файла
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        
        # Фильтруем по уровню и поиску
        filtered_lines = []
        for line in all_lines:
            if level and level.upper() not in line:
                continue
            if search and search.lower() not in line.lower():
                continue
            filtered_lines.append(line)
        
        # Берем последние N строк
        result_lines = filtered_lines[-lines:] if len(filtered_lines) > lines else filtered_lines
        
        return {
            "logs": [line.strip() for line in result_lines],
            "total_lines": len(filtered_lines),
            "returned_lines": len(result_lines),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка чтения логов: {str(e)}"
        )


@router.get("/stream")
async def stream_logs(
    admin_user: Annotated[AdminUser, Depends(get_current_admin_user_optional_token)],
):
    """
    Потоковая передача логов в реальном времени (SSE).
    """
    log_file = LOGS_DIR / "app.log"
    
    if not log_file.exists():
        return PlainTextResponse("Файл логов не найден", status_code=404)
    
    async def generate():
        file_handle = None
        try:
            file_handle = open(log_file, "r", encoding="utf-8")
            file_handle.seek(0, os.SEEK_END)

            while True:
                line = file_handle.readline()
                if line:
                    payload = line.rstrip("\n")
                    yield f"data: {payload}\n\n"
                    continue

                await asyncio.sleep(0.25)

                try:
                    current_size = os.path.getsize(log_file)
                except FileNotFoundError:
                    await asyncio.sleep(0.5)
                    continue

                if current_size < file_handle.tell():
                    file_handle.close()
                    file_handle = open(log_file, "r", encoding="utf-8")
                    file_handle.seek(0, os.SEEK_END)
        finally:
            if file_handle is not None and not file_handle.closed:
                file_handle.close()
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.get("/download")
async def download_logs(
    admin_user: Annotated[AdminUser, Depends(get_current_admin_user)],
    days: int = Query(1, ge=1, le=30, description="Количество дней для выгрузки"),
):
    """
    Выгрузить логи в виде файла.
    """
    log_file = LOGS_DIR / "app.log"
    
    if not log_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл логов не найден"
        )
    
    try:
        cutoff_date = datetime.utcnow().timestamp() - (days * 24 * 60 * 60)
        
        def generate():
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    # Простая проверка по дате (если в логе есть timestamp)
                    # В реальности нужно парсить timestamp из строки лога
                    yield line
        
        filename = f"logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
        
        return StreamingResponse(
            generate(),
            media_type="text/plain",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка выгрузки логов: {str(e)}"
        )

