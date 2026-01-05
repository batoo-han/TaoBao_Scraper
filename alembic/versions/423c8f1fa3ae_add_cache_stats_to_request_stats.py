"""add cache stats to request_stats

Revision ID: 423c8f1fa3ae
Revises: af9c1ed9fb60
Create Date: 2026-01-05 23:21:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '423c8f1fa3ae'
down_revision: Union[str, None] = 'af9c1ed9fb60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поля статистики Redis кэша в таблицу request_stats
    op.add_column('request_stats', sa.Column('cache_hits', sa.Integer(), nullable=True, server_default='0', comment='Количество попаданий в кэш (cache hits)'))
    op.add_column('request_stats', sa.Column('cache_misses', sa.Integer(), nullable=True, server_default='0', comment='Количество промахов кэша (cache misses)'))
    op.add_column('request_stats', sa.Column('cache_saved_tokens', sa.Integer(), nullable=True, comment='Сэкономлено токенов благодаря кэшу'))
    op.add_column('request_stats', sa.Column('cache_saved_cost', sa.Float(), nullable=True, comment='Сэкономлено денег благодаря кэшу (USD)'))
    op.add_column('request_stats', sa.Column('cache_saved_time_ms', sa.Integer(), nullable=True, comment='Сэкономлено времени благодаря кэшу (мс)'))


def downgrade() -> None:
    # Удаляем поля статистики кэша
    op.drop_column('request_stats', 'cache_saved_time_ms')
    op.drop_column('request_stats', 'cache_saved_cost')
    op.drop_column('request_stats', 'cache_saved_tokens')
    op.drop_column('request_stats', 'cache_misses')
    op.drop_column('request_stats', 'cache_hits')
