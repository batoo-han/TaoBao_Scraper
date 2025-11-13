"""SQLAlchemy ORM models for bot persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.mutable import MutableDict

from .base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255))
    first_name: Mapped[Optional[str]] = mapped_column(String(255))
    last_name: Mapped[Optional[str]] = mapped_column(String(255))
    language_code: Mapped[Optional[str]] = mapped_column(String(8))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    settings: Mapped["UserSettings | None"] = relationship(
        "UserSettings",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    admin_profile: Mapped["AdminUser | None"] = relationship(
        "AdminUser",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    usage_stats: Mapped[list["UsageStats"]] = relationship(
        "UsageStats",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserSettings(TimestampMixin, Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    default_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="cny")
    exchange_rate: Mapped[Optional[float]] = mapped_column(Numeric(14, 4))
    exchange_rate_at: Mapped[Optional[datetime]] = mapped_column()
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="settings")


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    active_llm_vendor: Mapped[str] = mapped_column(String(32), nullable=False)
    llm_config: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSONB), default=dict, nullable=False)
    consent_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Расширенные настройки приложения (все настройки из .env и другие)
    app_config: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSONB), default=dict, nullable=False)
    # Настройки магазинов (включение/выключение и статистика)
    platforms_config: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSONB), default=dict, nullable=False)
    # Настройки, требующие перезапуска для применения
    pending_restart_config: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSONB), default=dict, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSONB), nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="env")
    requires_restart: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class LLMCache(Base):
    __tablename__ = "llm_cache"
    __table_args__ = (
        UniqueConstraint("vendor", "cache_key", name="uq_llm_cache_vendor_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor: Mapped[str] = mapped_column(String(32), nullable=False)
    cache_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    response_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column()


class UsageStats(Base):
    __tablename__ = "usage_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    vendor: Mapped[Optional[str]] = mapped_column(String(32))
    total_requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_request_at: Mapped[Optional[datetime]] = mapped_column()

    user: Mapped[Optional["User"]] = relationship("User", back_populates="usage_stats")


class PDAuditLog(Base):
    __tablename__ = "pd_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    target_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    actor: Mapped[Optional["User"]] = relationship("User", foreign_keys=[actor_id])
    target_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[target_user_id])


class AdminUser(TimestampMixin, Base):
    __tablename__ = "admin_users"
    __table_args__ = (
        UniqueConstraint("admin_username", name="uq_admin_username"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    admin_username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # Имя пользователя для входа
    can_manage_keys: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_view_stats: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_manage_users: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)  # Хранит хеш пароля (временное решение)

    user: Mapped["User"] = relationship("User", back_populates="admin_profile")


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    plan: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column()
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    subscription_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    user: Mapped["User"] = relationship("User")


