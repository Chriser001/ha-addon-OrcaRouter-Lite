"""Provider keys — BYOK credentials for upstream LLM providers.

Renamed from PlatformProviderKey in the SaaS edition. Same shape, no admin
permissioning since the lite edition has a single user.
"""

from sqlalchemy import Boolean, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from packages.db.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class ProviderKey(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "provider_keys"

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(30), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False, server_default="default")
    is_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    rpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, server_default="0")

    # ── Custom endpoint (OpenAI-compatible or any litellm provider) ──────
    # When set, this provider is routed to `api_base` instead of the vendor's
    # public endpoint. That's what makes adding a third-party / self-hosted /
    # proxy endpoint a CONFIG operation rather than a code change: the model
    # list is discovered from `{api_base}/models` at router-build time.
    #
    # NULL keeps the legacy behavior (vendor's own endpoint, models sourced
    # from litellm's model_cost catalog).
    api_base: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Wire protocol litellm should speak to this endpoint — "openai" for the
    # overwhelming majority of third-party / OpenAI-compatible gateways.
    # NULL falls back to the provider's catalog-derived prefix (or "openai"
    # for providers unknown to the catalog).
    custom_llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
