"""Declarative base and mixins for SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime
import re

from sqlalchemy.orm import DeclarativeBase, declared_attr
from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


_CAMEL_PATTERN = re.compile(r"(?<!^)(?=[A-Z])")


class Base(DeclarativeBase):
    """Root declarative base."""

    @declared_attr.directive
    def __tablename__(cls) -> str:  # type: ignore[override]
        return _CAMEL_PATTERN.sub("_", cls.__name__).lower()


class TimestampMixin:
    """Adds created/updated timestamp columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )


