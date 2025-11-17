"""add runtime settings and pending restart config

Revision ID: 003_add_runtime_settings
Revises: 002_add_app_config_fields
Create Date: 2025-11-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "003_add_runtime_settings"
down_revision: Union[str, None] = "002_add_app_config_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем pending_restart_config к app_settings
    op.add_column(
        "app_settings",
        sa.Column(
            "pending_restart_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # Создаем таблицу runtime_settings
    op.create_table(
        "runtime_settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="env"),
        sa.Column("requires_restart", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("runtime_settings")
    op.drop_column("app_settings", "pending_restart_config")

