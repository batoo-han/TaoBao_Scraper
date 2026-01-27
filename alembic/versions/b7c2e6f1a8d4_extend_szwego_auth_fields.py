"""extend szwego auth fields

Revision ID: b7c2e6f1a8d4
Revises: 9b1a2d3c4e5f
Create Date: 2026-01-27 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c2e6f1a8d4"
down_revision: Union[str, None] = "9b1a2d3c4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавляем зашифрованные cookies/UA и статус авторизации для SzwegoAuth."""
    with op.batch_alter_table("szwego_auth") as batch_op:
        batch_op.add_column(
            sa.Column(
                "cookies_encrypted",
                sa.Text(),
                nullable=True,
                comment="Зашифрованные cookies SZWEGO (JSON)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "user_agent_encrypted",
                sa.Text(),
                nullable=True,
                comment="Зашифрованный User-Agent",
            )
        )
        batch_op.add_column(
            sa.Column(
                "last_status",
                sa.String(length=50),
                nullable=True,
                comment="Последний статус авторизации (success/invalid_credentials/...)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "last_status_at",
                sa.DateTime(),
                nullable=True,
                comment="Время последнего обновления статуса",
            )
        )


def downgrade() -> None:
    """Удаляем добавленные поля SzwegoAuth (обратная миграция)."""
    with op.batch_alter_table("szwego_auth") as batch_op:
        batch_op.drop_column("last_status_at")
        batch_op.drop_column("last_status")
        batch_op.drop_column("user_agent_encrypted")
        batch_op.drop_column("cookies_encrypted")

