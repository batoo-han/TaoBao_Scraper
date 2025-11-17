"""add_app_config_fields

Revision ID: 002_add_app_config_fields
Revises: 001_add_admin_username
Create Date: 2025-11-12 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '002_add_app_config_fields'
down_revision: Union[str, None] = '001_add_admin_username'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем колонки для расширенных настроек
    op.add_column('app_settings', sa.Column('app_config', JSONB, nullable=True, server_default='{}'))
    op.add_column('app_settings', sa.Column('platforms_config', JSONB, nullable=True, server_default='{}'))
    
    # Обновляем существующие записи
    op.execute("""
        UPDATE app_settings 
        SET app_config = '{}'::jsonb 
        WHERE app_config IS NULL
    """)
    op.execute("""
        UPDATE app_settings 
        SET platforms_config = '{"taobao": {"enabled": true}, "pinduoduo": {"enabled": true}, "szwego": {"enabled": false}, "1688": {"enabled": false}}'::jsonb 
        WHERE platforms_config IS NULL
    """)
    
    # Делаем колонки NOT NULL
    op.alter_column('app_settings', 'app_config', nullable=False, server_default='{}')
    op.alter_column('app_settings', 'platforms_config', nullable=False, server_default='{}')


def downgrade() -> None:
    op.drop_column('app_settings', 'platforms_config')
    op.drop_column('app_settings', 'app_config')

