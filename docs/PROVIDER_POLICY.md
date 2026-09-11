# Provider routing and runtime controls

Milestone 11 wraps the existing language-provider boundary with stage-aware routing, finite budgets, and bounded in-memory caching. It does not add a new state authority: action parsing still proposes a `PlayerAction`, narration still returns prose, and `GameEngine` remains the only transition path.

## Per-stage routing

The CLI/API already select the action-parser provider and narration provider independently. OpenAI-compatible and Ollama configuration can now also be overridden independently for each stage.

Generic OpenAI-compatible settings remain the fallback:

```text
EMERGENT_RPG_LLM_BASE_URL
EMERGENT_RPG_LLM_MODEL
EMERGENT_RPG_LLM_API_KEY
EMERGENT_RPG_LLM_TIMEOUT
EMERGENT_RPG_LLM_TEMPERATURE
EMERGENT_RPG_LLM_MAX_TOKENS
```

Stage overrides use:

```text
EMERGENT_RPG_ACTION_LLM_*
EMERGENT_RPG_NARRATION_LLM_*
```

For Ollama, generic `EMERGENT_RPG_OLLAMA_*` values remain the fallback and stage overrides use:

```text
EMERGENT_RPG_ACTION_OLLAMA_*
EMERGENT_RPG_NARRATION_OLLAMA_*
```

The same suffixes apply: `BASE_URL`, `MODEL`, `API_KEY`, `TIMEOUT`, `TEMPERATURE`, and `MAX_TOKENS`. Ollama routing still never inherits `EMERGENT_RPG_LLM_API_KEY`.

## Runtime budgets

External provider calls are bounded independently for action parsing and narration:

```text
EMERGENT_RPG_ACTION_BUDGET_REQUESTS
EMERGENT_RPG_ACTION_BUDGET_RESERVED_TOKENS
EMERGENT_RPG_NARRATION_BUDGET_REQUESTS
EMERGENT_RPG_NARRATION_BUDGET_RESERVED_TOKENS
```

Defaults are finite: 10,000 requests per stage, two million reserved output tokens for action parsing, and five million for narration.

A budget reservation occurs immediately before an external request. Failed attempted requests therefore remain charged against the request/reserved-token budget. Cache hits do not reserve budget because no provider request occurs.

`reserved tokens` means the configured output ceiling supplied to the provider request. It is intentionally **not** described as actual token usage, billing, or monetary cost. The current provider contract does not require trustworthy usage metadata, so the engine does not invent cost accounting from request limits.

A narration budget failure is a `ProviderBudgetExceeded` error before persistence and preserves the existing zero-partial-commit guarantee. An action-parser budget failure is also a `ProviderError`, so the existing `FallbackActionParser` can safely fall back to the deterministic parser; the deterministic resolver still decides whether that proposed action is legal.

## Completion cache

`EMERGENT_RPG_LLM_CACHE_ENTRIES` controls a bounded in-memory LRU cache (default 256 entries per external stage provider instance; `0` disables it).

Only successful language outputs are cached. The cache contains no canonical state objects and cannot write events. Keys are SHA-256 digests over:

- provider stage (`action-parser` or `narration`);
- provider base URL and model;
- a SHA-256 credential-scope fingerprint rather than the API key itself;
- system prompt;
- exact structured user payload;
- effective temperature;
- effective max-token ceiling.

This prevents reuse across stage/model/configuration/input boundaries. For action parsing, the user payload includes the already-restricted visible-state surface, so a cached proposal cannot silently cross into a different visible world context.

## Authority invariant

```text
stage routing policy
→ bounded cache lookup
→ finite request/token reservation on cache miss
→ existing provider transport
→ language result only
→ existing parser or narrative boundary
→ deterministic engine authority unchanged
```

Budget/cache metadata is process-local control state, not world truth. It is never written into `WorldState`, domain events, turns, episodes, or the append-only event log.

## Offline evidence

`tests/test_provider_controls.py` verifies stage-specific model routing, cache reuse without additional budget, key isolation across stage/model/credential scope, reserved-token exhaustion before transport, parser fallback on exhausted budget, narration zero-commit atomicity, and bounded LRU eviction. All tests use fake transports and require no API key or network service.
