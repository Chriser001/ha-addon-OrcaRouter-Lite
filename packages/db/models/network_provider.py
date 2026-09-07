"""Network provider config — per-provider settings for the aggregated
web search / fetch surface (`/v1/network/*`).

One row per provider id from `app.network_providers.REGISTRY`, seeded at
startup. Keyless providers (Exa, Parallel, Firecrawl, Keenable) still get a
row — visibility, weight and the enable flag are operator-mutable state, and
keeping them in one place avoids a two-source merge between "registry
default" and "DB override" that would have to be re-implemented on every
read, every write and inside every strategy.

`encrypted_key` is NULL for keyless providers (and for keyed ones before the
operator supplies a key). It is deliberately NOT an empty bytes value: the
encryption layer raises on undecryptable input, and NULL is the honest
representation of "no credential".

`monthly_used` / `avg_latency_ms` are hot counters. They are updated with
single-statement expressions (never read-modify-write) because Lite runs on
SQLite by default, where two concurrent requests doing read-then-write
silently lose one of the two increments.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from packages.db.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class NetworkProvider(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "network_providers"
    __table_args__ = (UniqueConstraint("provider", name="uq_network_providers_provider"),)

    # Provider id — must exist in `app.network_providers.REGISTRY`. Rows for
    # unknown ids are ignored by the resolver (kept, not deleted: an operator
    # who downgrades to a build without that provider shouldn't lose config).
    provider: Mapped[str] = mapped_column(String(50), nullable=False)

    # NULL = no credential (keyless provider, or not configured yet).
    encrypted_key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    key_prefix: Mapped[str] = mapped_column(String(30), nullable=False, server_default="")

    # is_enabled: the only selection switch. A disabled provider is dropped
    # from the automatic pool AND refuses a pinned call, so the recovery path
    # is obvious — the row stays listed and the button reads "enable".
    # A separate visibility flag was tried and removed: hiding a row also hid
    # the only control that could un-hide it.
    is_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")

    # Relative pull for the `random` strategy. 0 never wins an automatic
    # selection but stays pin-able by name.
    weight: Mapped[int] = mapped_column(Integer, server_default="100")

    # `quota` strategy budget. NULL = unknown / unmetered (every keyless
    # vendor); those rank BEHIND metered providers so a monthly free-tier
    # allowance gets spent before it expires instead of expiring untouched.
    monthly_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_used: Mapped[int] = mapped_column(Integer, server_default="0")
    quota_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # EWMA of successful call latency in ms; NULL until the first sample.
    # Failures are excluded — a timed-out provider must not look "fast".
    avg_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success_count: Mapped[int] = mapped_column(Integer, server_default="0")
    failure_count: Mapped[int] = mapped_column(Integer, server_default="0")

    # Set when the last call hit a rate limit; filtered out of automatic
    # selection until it lapses. Skipping only the current request would
    # re-hit the same throttled endpoint on every subsequent call.
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
