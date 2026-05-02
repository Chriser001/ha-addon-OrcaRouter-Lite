# Cursor + OrcaRouter Lite

Cursor lets you bring your own OpenAI-compatible model. Lite slots right in.

## Setup

1. **Settings → Models → Override OpenAI Base URL**: `http://localhost:8000/v1`
2. **Settings → Models → OpenAI API Key**: paste your `sk-orca-...`
3. **Settings → Models → Custom Model Names**: add the models you care about, e.g.
   - `auto`
   - `gpt-4o`
   - `claude-3-5-sonnet-latest`
   - `claude-3-5-haiku-latest`
   - `gemini-2.5-flash`

Cursor will route Cmd-K, Cmd-L, and tab-completion through Lite, which handles
the actual provider routing.

## Caveat

Cursor's "Composer" mode pins specific models internally and may bypass your
custom config for some flows. Cmd-K and Cmd-L are reliable.
