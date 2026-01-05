"""initial migration

Revision ID: 001_initial
Revises: 
Create Date: 2024-12-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Создание таблицы users
    op.create_table(
        'users',
        sa.Column('user_id', sa.BigInteger(), nullable=False, comment='Telegram user ID'),
        sa.Column('username', sa.String(length=255), nullable=True, comment='Telegram username (без @)'),
        sa.Column('created_at', sa.Date(), nullable=False, comment='Дата первой регистрации'),
        sa.PrimaryKeyConstraint('user_id')
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=False)

    # Создание таблицы user_settings
    op.create_table(
        'user_settings',
        sa.Column('user_id', sa.BigInteger(), nullable=False, comment='Telegram user ID'),
        sa.Column('signature', sa.Text(), nullable=False, server_default='', comment='Подпись пользователя для постов'),
        sa.Column('default_currency', sa.String(length=10), nullable=False, server_default='cny', comment='Валюта по умолчанию (cny/rub)'),
        sa.Column('exchange_rate', sa.Float(), nullable=True, comment='Курс обмена для рубля'),
        sa.Column('price_mode', sa.String(length=20), nullable=False, server_default='', comment='Режим цен (simple/advanced/пусто)'),
        sa.Column('daily_limit', sa.Integer(), nullable=True, comment='Индивидуальный дневной лимит'),
        sa.Column('monthly_limit', sa.Integer(), nullable=True, comment='Индивидуальный месячный лимит'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id')
    )

    # Создание таблицы access_control
    op.create_table(
        'access_control',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('whitelist_enabled', sa.Boolean(), nullable=False, server_default='false', comment='Включен ли белый список'),
        sa.Column('blacklist_enabled', sa.Boolean(), nullable=False, server_default='false', comment='Включен ли черный список'),
        sa.PrimaryKeyConstraint('id')
    )

    # Создание таблицы access_list_entries
    op.create_table(
        'access_list_entries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('access_control_id', sa.Integer(), nullable=False),
        sa.Column('list_type', sa.Enum('WHITELIST', 'BLACKLIST', name='listtype'), nullable=False, comment='Тип списка (whitelist/blacklist)'),
        sa.Column('entry_type', sa.Enum('ID', 'USERNAME', name='entrytype'), nullable=False, comment='Тип записи (id/username)'),
        sa.Column('value', sa.String(length=255), nullable=False, comment='Значение (ID или username)'),
        sa.ForeignKeyConstraint(['access_control_id'], ['access_control.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('access_control_id', 'list_type', 'entry_type', 'value', name='uq_access_entry')
    )

    # Создание таблицы admin_settings
    op.create_table(
        'admin_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('default_llm', sa.String(length=50), nullable=False, server_default='yandex', comment='Провайдер LLM по умолчанию'),
        sa.Column('yandex_model', sa.String(length=100), nullable=False, server_default='yandexgpt-lite', comment='Модель YandexGPT'),
        sa.Column('openai_model', sa.String(length=100), nullable=False, server_default='gpt-4o-mini', comment='Модель OpenAI'),
        sa.Column('translate_provider', sa.String(length=50), nullable=False, server_default='yandex', comment='Провайдер для переводов'),
        sa.Column('translate_model', sa.String(length=100), nullable=False, server_default='yandexgpt-lite', comment='Модель для переводов'),
        sa.Column('translate_legacy', sa.Boolean(), nullable=False, server_default='false', comment='Использовать старый Yandex Translate'),
        sa.Column('convert_currency', sa.Boolean(), nullable=False, server_default='false', comment='Конвертировать валюту'),
        sa.Column('tmapi_notify_439', sa.Boolean(), nullable=False, server_default='false', comment='Уведомлять об ошибке 439 TMAPI'),
        sa.Column('debug_mode', sa.Boolean(), nullable=False, server_default='false', comment='Режим отладки'),
        sa.Column('mock_mode', sa.Boolean(), nullable=False, server_default='false', comment='Mock режим'),
        sa.Column('forward_channel_id', sa.String(length=255), nullable=False, server_default='', comment='ID канала для дублирования постов'),
        sa.Column('per_user_daily_limit', sa.Integer(), nullable=True, comment='Глобальный дневной лимит на пользователя'),
        sa.Column('per_user_monthly_limit', sa.Integer(), nullable=True, comment='Глобальный месячный лимит на пользователя'),
        sa.Column('total_daily_limit', sa.Integer(), nullable=True, comment='Общий дневной лимит'),
        sa.Column('total_monthly_limit', sa.Integer(), nullable=True, comment='Общий месячный лимит'),
        sa.PrimaryKeyConstraint('id')
    )

    # Создание таблицы rate_limits_global
    op.create_table(
        'rate_limits_global',
        sa.Column('id', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('day_start', sa.Date(), nullable=False, comment='Начало текущего дня (МСК)'),
        sa.Column('day_count', sa.Integer(), nullable=False, server_default='0', comment='Количество запросов за день'),
        sa.Column('month_start', sa.Date(), nullable=False, comment='Начало текущего месяца (МСК)'),
        sa.Column('month_count', sa.Integer(), nullable=False, server_default='0', comment='Количество запросов за месяц'),
        sa.Column('day_cost', sa.Float(), nullable=False, server_default='0.0', comment='Стоимость запросов за день (USD)'),
        sa.Column('month_cost', sa.Float(), nullable=False, server_default='0.0', comment='Стоимость запросов за месяц (USD)'),
        sa.PrimaryKeyConstraint('id')
    )

    # Создание таблицы rate_limits_users
    op.create_table(
        'rate_limits_users',
        sa.Column('user_id', sa.BigInteger(), nullable=False, comment='Telegram user ID'),
        sa.Column('day_start', sa.Date(), nullable=False, comment='Начало текущего дня (МСК)'),
        sa.Column('day_count', sa.Integer(), nullable=False, server_default='0', comment='Количество запросов за день'),
        sa.Column('month_start', sa.Date(), nullable=False, comment='Начало текущего месяца (МСК)'),
        sa.Column('month_count', sa.Integer(), nullable=False, server_default='0', comment='Количество запросов за месяц'),
        sa.Column('day_cost', sa.Float(), nullable=False, server_default='0.0', comment='Стоимость запросов за день (USD)'),
        sa.Column('month_cost', sa.Float(), nullable=False, server_default='0.0', comment='Стоимость запросов за месяц (USD)'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id')
    )


def downgrade() -> None:
    op.drop_table('rate_limits_users')
    op.drop_table('rate_limits_global')
    op.drop_table('admin_settings')
    op.drop_table('access_list_entries')
    op.drop_table('access_control')
    op.drop_table('user_settings')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_table('users')
    op.execute('DROP TYPE IF EXISTS entrytype')
    op.execute('DROP TYPE IF EXISTS listtype')
