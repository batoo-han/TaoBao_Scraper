"""
API endpoints для аудита персональных данных (ФЗ-152).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.dependencies import get_current_admin_user
from src.admin.models.schemas import AuditLogInfo, AuditLogListResponse
from src.db.models import AdminUser, PDAuditLog, User
from src.db.session import get_db_session

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    admin_user: Annotated[AdminUser, Depends(get_current_admin_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
):
    """
    Получить список записей аудита с фильтрацией.
    
    Фильтры:
    - action: тип действия
    - user_id: ID пользователя
    - date_from: начало периода
    - date_to: конец периода
    """
    offset = (page - 1) * page_size
    
    # Базовый запрос
    query = select(
        PDAuditLog,
        User.username.label("actor_username"),
        User.telegram_id.label("actor_telegram_id"),
    ).outerjoin(
        User, PDAuditLog.actor_id == User.id
    )
    
    # Применяем фильтры
    if action:
        query = query.where(PDAuditLog.action == action)
    if user_id:
        query = query.where(PDAuditLog.target_user_id == user_id)
    if date_from:
        query = query.where(PDAuditLog.created_at >= date_from)
    if date_to:
        query = query.where(PDAuditLog.created_at <= date_to)
    
    # Общее количество
    count_query = select(func.count()).select_from(
        query.subquery()
    )
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    
    # Список записей
    result = await session.execute(
        query.order_by(PDAuditLog.created_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    
    # Получаем информацию о целевых пользователях
    logs = []
    for row in result.all():
        audit_log = row.PDAuditLog
        actor_username = row.actor_username
        
        # Получаем username целевого пользователя
        target_username = None
        if audit_log.target_user_id:
            target_result = await session.execute(
                select(User.username).where(User.id == audit_log.target_user_id)
            )
            target_username = target_result.scalar_one_or_none()
        
        logs.append(
            AuditLogInfo(
                id=audit_log.id,
                actor_id=audit_log.actor_id,
                actor_username=actor_username,
                target_user_id=audit_log.target_user_id,
                target_username=target_username,
                action=audit_log.action,
                details=audit_log.details,
                created_at=audit_log.created_at,
            )
        )
    
    total_pages = (total + page_size - 1) // page_size
    
    return AuditLogListResponse(
        logs=logs,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{log_id}", response_model=AuditLogInfo)
async def get_audit_log(
    log_id: int,
    admin_user: Annotated[AdminUser, Depends(get_current_admin_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """Получить детальную информацию о записи аудита."""
    result = await session.execute(
        select(PDAuditLog).where(PDAuditLog.id == log_id)
    )
    audit_log = result.scalar_one_or_none()
    
    if audit_log is None:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Запись аудита с ID {log_id} не найдена",
        )
    
    # Получаем username актора
    actor_username = None
    if audit_log.actor_id:
        actor_result = await session.execute(
            select(User.username).where(User.id == audit_log.actor_id)
        )
        actor_username = actor_result.scalar_one_or_none()
    
    # Получаем username целевого пользователя
    target_username = None
    if audit_log.target_user_id:
        target_result = await session.execute(
            select(User.username).where(User.id == audit_log.target_user_id)
        )
        target_username = target_result.scalar_one_or_none()
    
    return AuditLogInfo(
        id=audit_log.id,
        actor_id=audit_log.actor_id,
        actor_username=actor_username,
        target_user_id=audit_log.target_user_id,
        target_username=target_username,
        action=audit_log.action,
        details=audit_log.details,
        created_at=audit_log.created_at,
    )


@router.get("/export/csv")
async def export_audit_csv(
    admin_user: Annotated[AdminUser, Depends(get_current_admin_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
):
    """
    Экспортировать записи аудита в CSV.
    
    TODO: Реализовать экспорт в CSV формат
    """
    from fastapi.responses import Response
    
    # Пока возвращаем JSON (CSV экспорт будет реализован позже)
    query = select(PDAuditLog)
    if date_from:
        query = query.where(PDAuditLog.created_at >= date_from)
    if date_to:
        query = query.where(PDAuditLog.created_at <= date_to)
    
    result = await session.execute(query.order_by(PDAuditLog.created_at.desc()))
    logs = result.scalars().all()
    
    # Простой CSV (можно улучшить)
    csv_lines = ["id,actor_id,target_user_id,action,created_at,details"]
    for log in logs:
        details_str = str(log.details).replace(",", ";").replace("\n", " ")
        csv_lines.append(
            f"{log.id},{log.actor_id or ''},{log.target_user_id or ''},"
            f"{log.action},{log.created_at.isoformat()},{details_str}"
        )
    
    csv_content = "\n".join(csv_lines)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=audit_log_{datetime.utcnow().strftime('%Y%m%d')}.csv"
        }
    )

