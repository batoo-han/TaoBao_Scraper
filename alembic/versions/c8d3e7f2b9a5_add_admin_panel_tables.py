"""add admin panel tables

Revision ID: c8d3e7f2b9a5
Revises: b7c2e6f1a8d4
Create Date: 2026-01-28 12:00:00.000000

Добавляем таблицы для админ-панели:
- admin_users: пользователи админки с ролями
- admin_sessions: сессии для JWT аутентификации
- admin_action_logs: журнал действий для аудита
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8d3e7f2b9a5"
down_revision: Union[str, None] = "b7c2e6f1a8d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Создание таблиц админ-панели."""
    
    # Таблица пользователей админки
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="ID пользователя админки"),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True, comment="Telegram ID (опционально, для входа через Telegram)"),
        sa.Column("username", sa.String(length=255), nullable=False, comment="Логин пользователя"),
        sa.Column("password_hash", sa.String(length=255), nullable=True, comment="Хэш пароля (bcrypt)"),
        sa.Column("email", sa.String(length=255), nullable=True, comment="Email пользователя"),
        sa.Column("display_name", sa.String(length=255), nullable=True, comment="Отображаемое имя"),
        sa.Column(
            "role",
            sa.Enum("admin", "user", name="adminrole"),
            nullable=False,
            server_default="user",
            comment="Роль пользователя"
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true", comment="Активен ли аккаунт"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="Время создания"),
        sa.Column("updated_at", sa.DateTime(), nullable=True, comment="Время последнего обновления"),
        sa.Column("last_login", sa.DateTime(), nullable=True, comment="Время последнего входа"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
        sa.UniqueConstraint("username"),
    )
    
    # Индекс для быстрого поиска по telegram_id
    op.create_index("ix_admin_users_telegram_id", "admin_users", ["telegram_id"], unique=False)
    op.create_index("ix_admin_users_username", "admin_users", ["username"], unique=False)
    
    # Таблица сессий
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="ID сессии"),
        sa.Column("user_id", sa.Integer(), nullable=False, comment="ID пользователя"),
        sa.Column("token_hash", sa.String(length=255), nullable=False, comment="Хэш refresh token (SHA-256)"),
        sa.Column("ip_address", sa.String(length=45), nullable=True, comment="IP адрес клиента (IPv4/IPv6)"),
        sa.Column("user_agent", sa.Text(), nullable=True, comment="User-Agent браузера"),
        sa.Column("expires_at", sa.DateTime(), nullable=False, comment="Время истечения токена"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="Время создания сессии"),
        sa.Column("last_used_at", sa.DateTime(), nullable=True, comment="Время последнего использования"),
        sa.ForeignKeyConstraint(["user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    
    # Индекс для быстрого поиска по user_id и token_hash
    op.create_index("ix_admin_sessions_user_id", "admin_sessions", ["user_id"], unique=False)
    op.create_index("ix_admin_sessions_token_hash", "admin_sessions", ["token_hash"], unique=False)
    op.create_index("ix_admin_sessions_expires_at", "admin_sessions", ["expires_at"], unique=False)
    
    # Таблица журнала действий
    op.create_table(
        "admin_action_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="ID записи лога"),
        sa.Column("user_id", sa.Integer(), nullable=True, comment="ID пользователя админки"),
        sa.Column("action", sa.String(length=100), nullable=False, comment="Тип действия (login, logout, update_settings, etc.)"),
        sa.Column("target_type", sa.String(length=50), nullable=True, comment="Тип объекта (user, settings, access_list, etc.)"),
        sa.Column("target_id", sa.String(length=255), nullable=True, comment="ID объекта (user_id, setting_name, etc.)"),
        sa.Column("details", sa.Text(), nullable=True, comment="Детали действия (JSON)"),
        sa.Column("ip_address", sa.String(length=45), nullable=True, comment="IP адрес"),
        sa.Column("user_agent", sa.Text(), nullable=True, comment="User-Agent"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="Время действия"),
        sa.ForeignKeyConstraint(["user_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    
    # Индексы для журнала действий
    op.create_index("ix_admin_action_logs_user_id", "admin_action_logs", ["user_id"], unique=False)
    op.create_index("ix_admin_action_logs_action", "admin_action_logs", ["action"], unique=False)
    op.create_index("ix_admin_action_logs_created_at", "admin_action_logs", ["created_at"], unique=False)


def downgrade() -> None:
    """Удаление таблиц админ-панели."""
    
    # Удаляем индексы журнала действий
    op.drop_index("ix_admin_action_logs_created_at", table_name="admin_action_logs")
    op.drop_index("ix_admin_action_logs_action", table_name="admin_action_logs")
    op.drop_index("ix_admin_action_logs_user_id", table_name="admin_action_logs")
    
    # Удаляем таблицу журнала действий
    op.drop_table("admin_action_logs")
    
    # Удаляем индексы сессий
    op.drop_index("ix_admin_sessions_expires_at", table_name="admin_sessions")
    op.drop_index("ix_admin_sessions_token_hash", table_name="admin_sessions")
    op.drop_index("ix_admin_sessions_user_id", table_name="admin_sessions")
    
    # Удаляем таблицу сессий
    op.drop_table("admin_sessions")
    
    # Удаляем индексы пользователей
    op.drop_index("ix_admin_users_username", table_name="admin_users")
    op.drop_index("ix_admin_users_telegram_id", table_name="admin_users")
    
    # Удаляем таблицу пользователей
    op.drop_table("admin_users")
    
    # Удаляем enum тип
    op.execute("DROP TYPE IF EXISTS adminrole")
