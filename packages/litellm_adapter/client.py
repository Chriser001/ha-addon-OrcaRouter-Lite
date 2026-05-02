"""LiteLLM Router wrapper — the only module that imports litellm.

Lite edition: a thin wrapper. The full SaaS adapter handles streaming,
generation IDs, retry-cost accumulation, and structured error translation.
Lite covers the happy path and basic error mapping; that's enough for a
solo dev to ship a working router.
"""

from __future__ import annotations

import time

import structlog

from packages.litellm_adapter.types import ProviderDeployment, UpstreamProviderError

logger = structlog.get_logger(__name__)


def _translate_error(exc: Exception) -> UpstreamProviderError:
    import litellm

    msg = str(exc)
    if isinstance(exc, litellm.ContextWindowExceededError):
        return UpstreamProviderError(msg, http_status=422, error_type="context_length_exceeded")
    if isinstance(exc, litellm.NotFoundError):
        return UpstreamProviderError(msg, http_status=422, error_type="model_not_found")
    if isinstance(exc, litellm.RateLimitError):
        return UpstreamProviderError(msg, http_status=429, error_type="rate_limit_error")
    if isinstance(exc, litellm.AuthenticationError):
        return UpstreamProviderError(msg, http_status=503, error_type="upstream_auth_error")
    if isinstance(exc, litellm.Timeout):
        return UpstreamProviderError(msg, http_status=503, error_type="upstream_timeout")
    return UpstreamProviderError(msg, http_status=503, error_type="upstream_error")


class OrcaLiteLLMClient:
    """Wraps a litellm.Router, routes by `model` alias, returns a dict."""

    def __init__(self, deployments: list[ProviderDeployment]):
        # litellm-suppress-debug
        import litellm
        from litellm import Router
        litellm.suppress_debug_info = True
        litellm.vertex_project = None
        litellm.vertex_location = None

        model_list = []
        for d in deployments:
            params: dict = {
                "model": d.litellm_model,
                "api_key": d.api_key,
            }
            if d.api_base:
                params["api_base"] = d.api_base
            if d.custom_llm_provider:
                params["custom_llm_provider"] = d.custom_llm_provider
            if d.rpm:
                params["rpm"] = d.rpm
            if d.tpm:
                params["tpm"] = d.tpm
            entry: dict = {"model_name": d.model_name, "litellm_params": params}
            model_list.append(entry)

        if not model_list:
            self._router = None
            self._deployments = []
            return

        self._router = Router(
            model_list=model_list,
            num_retries=2,
            timeout=30.0,
        )
        self._deployments = deployments

    async def acompletion(self, **kwargs) -> dict:
        if self._router is None:
            raise UpstreamProviderError(
                "No provider keys configured. Set OPENAI_API_KEY (or another) "
                "in your env, or add a key via PUT /v1/providers/{provider}.",
                http_status=503,
                error_type="no_providers_configured",
            )
        started = time.perf_counter()
        try:
            resp = await self._router.acompletion(**kwargs)
        except Exception as exc:
            raise _translate_error(exc) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        # Convert litellm's ModelResponse to a plain dict + attach orca metadata.
        out = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
        # Look up which deployment served the request via the resolved model name.
        provider = "unknown"
        for d in self._deployments:
            if d.litellm_model == out.get("model") or d.model_name == out.get("model"):
                provider = d.provider
                break
        out["_orca_meta"] = {
            "provider": provider,
            "latency_ms": latency_ms,
        }
        return out
