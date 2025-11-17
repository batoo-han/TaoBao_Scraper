"""add_admin_username_to_admin_users

Revision ID: 001_add_admin_username
Revises: 
Create Date: 2025-11-12 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_add_admin_username'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем колонку admin_username
    op.add_column('admin_users', sa.Column('admin_username', sa.String(length=64), nullable=True))
    
    # Создаем уникальный индекс
    op.create_unique_constraint('uq_admin_username', 'admin_users', ['admin_username'])
    
    # Для существующих записей устанавливаем временное значение
    # Пользователь должен будет обновить через скрипт migrate_admin_username.py
    op.execute("""
        UPDATE admin_users 
        SET admin_username = 'admin_' || user_id::text 
        WHERE admin_username IS NULL
    """)


def downgrade() -> None:
    # Удаляем ограничение и колонку
    op.drop_constraint('uq_admin_username', 'admin_users', type_='unique')
    op.drop_column('admin_users', 'admin_username')

