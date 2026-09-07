"""Network request log — append-only log of every aggregated search / fetch.

Forked from `request_log.py` (which is LLM-specific: tokens, cost, model
resolution). The network surface has none of that, so it gets its own table
rather than a pile of nullable columns on the LLM one — a search request has
no `cost_microcents` and a chat completion has no `url_count`, and mixing
them would make both analytics queries filter on `kind` forever.

Nothing sensitive is stored: `query` is truncated, and fetch calls record
only the host plus a URL count — never the fetched body.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from packages.db.models.base import Base, SoftDeleteMixin, UUIDMixin

# "search" | "fetch"
KIND_SEARCH = "search"
KIND_FETCH = "fetch"


class NetworkRequestLog(Base, UUIDMixin, SoftDeleteMixin):
    __tablename__ = "network_requests_log"
    __table_args__ = (
        Index("ix_network_requests_log_created", "created_at"),
    )

    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    api_key_id: Mapped[str] = mapped_column(String(36), nullable=False)

    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    # The provider that actually served the request.
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    # The provider the caller pinned, if any (NULL for automatic selection).
    provider_requested: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # random | quota | latency | explicit
    strategy: Mapped[str] = mapped_column(String(20), nullable=False)

    # Search query, truncated. NULL for fetch.
    query: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Number of URLs submitted (fetch) — bodies are never persisted.
    url_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Comma-separated providers that failed before one succeeded — the
    # failover path, surfaced to callers so a silent vendor switch is visible.
    failover_from: Mapped[str | None] = mapped_column(String(300), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
