"""Workspace model.

Lite edition stores exactly one row, but the relational shape is preserved so
ORM queries from the SaaS edition continue to apply with `workspace_id="default"`.
"""

from sqlalchemy import JSON, String, text
from sqlalchemy.orm import Mapped, mapped_column

from packages.db.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Workspace(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    default_model: Mapped[str] = mapped_column(String(100), server_default="gpt-4o-mini")
    default_routing_strategy: Mapped[str] = mapped_column(String(20), server_default="balanced")
    settings_json: Mapped[dict] = mapped_column(JSON, server_default=text("'{}'"))
