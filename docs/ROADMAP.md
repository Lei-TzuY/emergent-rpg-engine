# Roadmap

The project advances by coherent executable slices rather than placeholder subsystems.

1. **Deterministic core** — canonical state, typed events, validation, replay, memory tiers, persistent CLI demo. **Complete.**
2. **Real LLM provider** — replaceable OpenAI-compatible narration, constrained `ScenePlan` input, offline transport tests, and provider-failure atomicity. **Complete.**
3. **Structured LLM action parsing** — strict typed action JSON, visible-state-only prompt surface, deterministic fallback, and resolver-enforced legality. **Complete.**
4. **Mystery graph** — deterministic clue dependencies, replayable inference provenance, observer-scoped contradictions, and discovery gates. **Complete.**
5. **NPC autonomous planning** — goals, bounded plans, and knowledge-constrained action selection. **Next.**
6. **World simulation between player turns** — scheduled events and off-screen consequences.
7. **Vector/embedding retrieval** — optional semantic retrieval alongside deterministic ranking.
8. **Local-model support / Ollama** — explicit local-model presets/routing beyond the generic OpenAI-compatible endpoint.
9. **Web API** — stable service boundary over the core engine.
10. **Web UI** — presentation layer over persisted sessions.
11. **Model routing / cost controls** — per-stage provider selection, budgets, and caching.
12. **Evaluation harness for 1,000+ turn consistency** — repeatable long-run continuity metrics and adversarial scenarios.

## Milestone 3 invariant

The parser never receives mutation authority:

```text
freeform player text
→ visible interaction surface only
→ provider proposes strict PlayerAction JSON
→ Pydantic schema validation (extra fields forbidden)
→ deterministic resolver
→ ordinary event / validation / commit pipeline
```

Provider request/response failures fall back to the deterministic command parser. A syntactically valid but impossible model-proposed action is rejected by the resolver without changing canonical state or appending material events.

## Milestone 4 invariant

Mystery reasoning is canonical and replayable rather than prose-derived:

```text
known canonical facts
→ discovery prerequisite gate
→ deterministic inference rule
→ FactInferred(rule_id + premise_fact_ids)
→ ordinary event validation / reducer / persistence
```

Derived facts cannot be injected as ordinary `FactDiscovered` events. Inference events must match a registered rule exactly, the observer must already know every premise, and the conclusion must be marked `discoverability="inferred"`. Contradictions are computed from each observer's own knowledge set, so player/NPC epistemic boundaries remain intact.

## Promotion gate for Milestone 5

NPC planning must consume only that NPC's canonical knowledge, goals, local state, and permitted world observations. Plans must be bounded and propose ordinary typed actions/events through deterministic legality checks; an NPC planner must never mutate canonical state directly or gain player/other-NPC knowledge implicitly.
