"""Routing config — single row for the lite edition's only workspace."""

from sqlalchemy import JSON, Boolean, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from packages.db.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class RoutingConfig(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "routing_config"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), unique=True, nullable=False
    )
    strategy: Mapped[str] = mapped_column(String(20), nullable=False, server_default="balanced")
    cost_weight: Mapped[float] = mapped_column(Numeric(3, 2), server_default="0.40")
    latency_weight: Mapped[float] = mapped_column(Numeric(3, 2), server_default="0.35")
    reliability_weight: Mapped[float] = mapped_column(Numeric(3, 2), server_default="0.25")
    fallback_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    preferred_models: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
