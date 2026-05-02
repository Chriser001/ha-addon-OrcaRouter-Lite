# Integrations

Drop-in configs that plug existing AI dev tools into a local OrcaRouter Lite
instance. All of these route via the standard OpenAI-compatible base URL —
nothing custom, nothing magic.

| Tool | File | What it gives you |
|---|---|---|
| **Continue.dev** | [`continue.json`](./continue.json) | Sidebar code chat / autocomplete / edit, routed through Lite |
| **Aider** | [`aider.md`](./aider.md) | CLI pair programmer with Lite as the LLM backend |
| **LangChain (Python)** | [`langchain_orcarouter.py`](./langchain_orcarouter.py) | Drop-in `OrcaRouter()` LLM class |
| **LlamaIndex (Python)** | [`llamaindex_orcarouter.py`](./llamaindex_orcarouter.py) | Drop-in `OrcaRouter()` LLM class |
| **Vercel AI SDK** | [`vercel_ai.ts`](./vercel_ai.ts) | OpenAI-provider config pointing at Lite |
| **OpenAI Python SDK** | (any) | Just set `base_url=http://localhost:8000/v1` |
| **Cursor** | [`cursor.md`](./cursor.md) | Custom OpenAI-compatible model config |

The pattern is the same everywhere: **point the OpenAI base URL at `http://localhost:8000/v1` and use your seeded `sk-orca-*` key as the API key.** You get `model="auto"` routing, hosted-as-upstream fallback, and the local cost dashboard for free.

## Why Lite for these tools?

- **One key for everything** — your tool ships an "OpenAI key" config; you drop in a `sk-orca-*` and unlock 100+ models from every major provider.
- **Cost guardrails** — see exactly what your editor / agent is spending in the local dashboard.
- **Auto-routing** — `model="auto"` picks the cheapest capable model per request. Aider does a quick refactor → routed to Haiku; Continue runs a long agentic chain → routed to Sonnet. No manual config.
- **Failover** — Anthropic rate-limited? Lite transparently retries via Google or Groq.
