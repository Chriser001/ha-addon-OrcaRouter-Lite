"""POST /v1/chat/completions — the proxy endpoint, slimmed for lite.

Supports both blocking and streaming. The streaming path returns an SSE
response in OpenAI's `text/event-stream` format with a terminal
`data: [DONE]` sentinel, exactly matching what the OpenAI SDK expects.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterable

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import prompt_cache, router_cache
from app.auto_routing import choose_auto_model, required_capabilities
from app.deps import get_db, get_key_context
from app.schemas import ChatCompletionRequest
from packages.auth.types import KeyContext
from packages.db.models.request_log import RequestLog
from packages.litellm_adapter.catalog import CATALOG

logger = structlog.get_logger()
router = APIRouter(prefix="/v1", tags=["Chat Completions"])


def _chunk_to_dict(chunk) -> dict:
    """Normalize a litellm chunk (Pydantic model or dict) into a plain dict."""
    if isinstance(chunk, dict):
        return chunk
    if hasattr(chunk, "model_dump"):
        return chunk.model_dump(exclude_none=True)
    return dict(chunk)


async def _build_log_row(
    *,
    body: ChatCompletionRequest,
    kc: KeyContext,
    response: dict,
    status_code: int,
    error_type: str | None,
    started_perf: float,
) -> RequestLog:
    latency_ms = int((time.perf_counter() - started_perf) * 1000)
    meta = response.get("_orca_meta", {})
    usage = response.get("usage", {}) or {}
    return RequestLog(
        workspace_id=str(kc.workspace_id),
        api_key_id=str(kc.key_id),
        trace_id=str(uuid.uuid4()),
        model_requested=body.model,
        model_resolved=response.get("model", body.model),
        provider=meta.get("provider", "unknown"),
        routing_strategy="balanced",
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
        cost_microcents=0,
        latency_ms=meta.get("latency_ms", latency_ms),
        status_code=status_code,
        error_type=error_type,
        is_streaming=body.stream,
    )


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    kc: KeyContext = Depends(get_key_context),
    db: AsyncSession = Depends(get_db),
):
    if kc.model_allowlist and body.model not in kc.model_allowlist:
        raise HTTPException(
            status_code=403,
            detail=f"Model '{body.model}' is not allowed for this API key",
        )

    client = await router_cache.get_router(db)

    # Resolve `model="auto"` BEFORE building the request kwargs so the router
    # sees a real model. Capability requirements come from the request body
    # (tools / response_format / image content); deployable set comes from the
    # current router's deployment list.
    requested_model = body.model
    resolved_model = body.model
    if body.model == "auto":
        body_dict = body.model_dump(exclude_none=True)
        needs = required_capabilities(body_dict)
        deployable = {
            d.model_name for d in getattr(client, "_deployments", []) or []
        }
        if not deployable:
            raise HTTPException(
                status_code=422,
                detail=(
                    "model='auto' requires at least one provider with a "
                    "configured key. No deployable provider found."
                ),
            )
        chosen = choose_auto_model(
            needs=needs, deployable=deployable, candidates=CATALOG,
        )
        if chosen is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "No deployable model satisfies the requested capabilities "
                    f"({sorted(needs) or 'none'}). Configure a provider that "
                    "supports them or pin a specific model."
                ),
            )
        resolved_model = chosen
        body.model = chosen  # mutate for downstream

    started_perf = time.perf_counter()
    completion_kwargs = body.model_dump(exclude_none=True)

    # ── Prompt cache (blocking deterministic requests only) ────────────
    cache_status = "BYPASS"
    cache_hit_response: dict | None = None
    cache_lookup_key: str | None = None
    if not body.stream and prompt_cache.is_cacheable(completion_kwargs):
        cache_lookup_key = prompt_cache.cache_key(
            model=body.model,
            messages=completion_kwargs["messages"],
            temperature=completion_kwargs.get("temperature"),
            tools=completion_kwargs.get("tools"),
            response_format=completion_kwargs.get("response_format"),
            seed=completion_kwargs.get("seed"),
        )
        cached = await prompt_cache.get_backend().get(cache_lookup_key)
        if cached is not None:
            cache_status = "HIT"
            cache_hit_response = cached
        else:
            cache_status = "MISS"

    if cache_hit_response is not None:
        # Log the hit so dashboards reflect real traffic, but mark provider="cache"
        # and cost=0 so spend math stays right.
        log = await _build_log_row(
            body=body, kc=kc,
            response={
                "model": cache_hit_response.get("model", body.model),
                "usage": cache_hit_response.get("usage", {}),
                "_orca_meta": {"provider": "cache", "latency_ms": 0},
            },
            status_code=200, error_type=None, started_perf=started_perf,
        )
        log.cost_microcents = 0
        db.add(log)
        try:
            await db.commit()
        except Exception as commit_err:
            logger.warning("request_log_commit_failed", error=str(commit_err))
        return JSONResponse(
            content=cache_hit_response,
            headers={
                "x-orca-cache": "HIT",
                "x-orca-resolved-model": resolved_model,
                "x-orca-requested-model": requested_model,
            },
        )

    # ── Streaming path ─────────────────────────────────────────────────
    if body.stream:
        try:
            stream_obj = await client.acompletion(**completion_kwargs)
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("chat_completion_upstream_error", error=str(exc))
            raise HTTPException(status_code=503, detail=f"Upstream provider error: {exc}") from exc

        async def sse() -> AsyncGenerator[str, None]:
            """Drain the chunk stream → emit SSE → write RequestLog when done."""
            agg_usage: dict = {}
            agg_provider = "unknown"
            agg_latency = 0
            agg_model = body.model
            status_code = 200
            error_type: str | None = None
            try:
                async for chunk in _aiter(stream_obj):
                    d = _chunk_to_dict(chunk)
                    # Hoist orca-internal metadata onto the request log without
                    # leaking it into the SSE stream.
                    if "_orca_meta" in d:
                        meta = d.pop("_orca_meta") or {}
                        agg_provider = meta.get("provider", agg_provider)
                        agg_latency = meta.get("latency_ms", agg_latency)
                    if "usage" in d and d["usage"]:
                        agg_usage = d["usage"]
                    if d.get("model"):
                        agg_model = d["model"]
                    yield f"data: {json.dumps(d, separators=(',', ':'))}\n\n"
            except Exception as exc:
                status_code = 503
                error_type = type(exc).__name__
                logger.warning("chat_completion_stream_error", error=str(exc))
                err_body = {
                    "error": {
                        "message": f"Upstream provider error: {exc}",
                        "type": "upstream_error",
                    }
                }
                yield f"data: {json.dumps(err_body)}\n\n"
            finally:
                yield "data: [DONE]\n\n"
                # Synthesize a response-shaped dict for the log helper.
                synthetic = {
                    "model": agg_model,
                    "usage": agg_usage,
                    "_orca_meta": {"provider": agg_provider, "latency_ms": agg_latency},
                }
                log = await _build_log_row(
                    body=body, kc=kc, response=synthetic,
                    status_code=status_code, error_type=error_type,
                    started_perf=started_perf,
                )
                db.add(log)
                try:
                    await db.commit()
                except Exception as commit_err:
                    logger.warning("request_log_commit_failed", error=str(commit_err))

        return StreamingResponse(
            sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "x-orca-resolved-model": resolved_model,
                "x-orca-requested-model": requested_model,
            },
        )

    # ── Blocking path ──────────────────────────────────────────────────
    status_code = 200
    error_type: str | None = None
    response: dict = {}
    try:
        response = await client.acompletion(**completion_kwargs)
    except HTTPException:
        raise
    except Exception as exc:
        status_code = 503
        error_type = type(exc).__name__
        logger.warning("chat_completion_upstream_error", error=str(exc))
        raise HTTPException(status_code=503, detail=f"Upstream provider error: {exc}") from exc
    finally:
        log = await _build_log_row(
            body=body, kc=kc, response=response if isinstance(response, dict) else {},
            status_code=status_code, error_type=error_type,
            started_perf=started_perf,
        )
        db.add(log)
        try:
            await db.commit()
        except Exception as commit_err:
            logger.warning("request_log_commit_failed", error=str(commit_err))

    if isinstance(response, dict) and "_orca_meta" in response:
        response = {k: v for k, v in response.items() if k != "_orca_meta"}

    # Write to cache on MISS (don't write on BYPASS — that's by design).
    if cache_status == "MISS" and cache_lookup_key is not None and isinstance(response, dict):
        try:
            await prompt_cache.get_backend().set(cache_lookup_key, response, ttl=3600)
        except Exception as exc:
            logger.warning("prompt_cache_set_failed", error=str(exc))

    return JSONResponse(
        content=response,
        headers={
            "x-orca-cache": cache_status,
            "x-orca-resolved-model": resolved_model,
            "x-orca-requested-model": requested_model,
        },
    )


def _aiter(obj):
    """Coerce a thing into an async iterator.

    LiteLLM's `acompletion(stream=True)` returns a `CustomStreamWrapper`
    that's already async-iterable. Test mocks may return a plain async
    generator. Accept both.
    """
    if hasattr(obj, "__aiter__"):
        return obj.__aiter__()
    if isinstance(obj, AsyncIterable):
        return obj.__aiter__()
    raise TypeError(f"Streaming router returned non-iterable: {type(obj).__name__}")
