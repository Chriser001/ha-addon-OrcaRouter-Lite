# Aider + OrcaRouter Lite

[Aider](https://aider.chat) speaks any OpenAI-compatible API. Two env vars and you're routing through Lite:

```bash
export OPENAI_API_BASE=http://localhost:8000/v1
export OPENAI_API_KEY=sk-orca-PASTE-YOUR-KEY-HERE

# Use any catalog model
aider --model openai/auto                       # ← cheapest capable per request
aider --model openai/gpt-4o
aider --model openai/claude-3-5-sonnet-latest
aider --model openai/gemini-2.5-flash
```

The `openai/` prefix is Aider's way of saying "use the OpenAI-compatible HTTP path." Lite serves that path; the model name after the slash is what gets routed.

## Two-model edit/whole pattern

```bash
# Cheap model proposes diffs, expensive model confirms them.
aider \
  --model openai/auto \
  --weak-model openai/claude-3-5-haiku-latest
```

## Persistent config

`~/.aider.conf.yml`:

```yaml
openai-api-base: http://localhost:8000/v1
openai-api-key: sk-orca-PASTE-YOUR-KEY-HERE
model: openai/auto
weak-model: openai/claude-3-5-haiku-latest
```

## What you get

- One env var, every model.
- The local dashboard shows exactly what each Aider session cost.
- `model="auto"` makes routine refactors hit Haiku/Flash automatically; complex sessions land on Sonnet/4o.
