"""add szwego auth table

Revision ID: 9b1a2d3c4e5f
Revises: 423c8f1fa3ae
Create Date: 2026-01-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b1a2d3c4e5f'
down_revision: Union[str, None] = '423c8f1fa3ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'szwego_auth',
        sa.Column('user_id', sa.BigInteger(), nullable=False, comment='Telegram user ID'),
        sa.Column('login_enc', sa.Text(), nullable=True, comment='Зашифрованный логин'),
        sa.Column('password_enc', sa.Text(), nullable=True, comment='Зашифрованный пароль'),
        sa.Column('cookies_file', sa.Text(), nullable=True, comment='Путь к cookies файлу пользователя'),
        sa.Column('user_agent', sa.Text(), nullable=True, comment='User-Agent, использованный при авторизации'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False, comment='Время создания'),
        sa.Column('updated_at', sa.Integer(), nullable=True, comment='Unix timestamp последнего обновления'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade() -> None:
    op.drop_table('szwego_auth')
