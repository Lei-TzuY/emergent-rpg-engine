# Roadmap

The project advances by coherent executable slices rather than placeholder subsystems.

1. **Deterministic core** — canonical state, typed events, validation, replay, memory tiers, persistent CLI demo. **Complete.**
2. **Real LLM provider** — replaceable OpenAI-compatible narration, constrained `ScenePlan` input, offline transport tests, and provider-failure atomicity. **Complete.**
3. **Structured LLM action parsing** — strict typed action JSON, visible-state-only prompt surface, deterministic fallback, and resolver-enforced legality. **Complete.**
4. **Mystery graph** — richer clue dependencies, inference, contradiction tracking, and reveal gates. **Next.**
5. **NPC autonomous planning** — goals, bounded plans, and knowledge-constrained action selection.
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

## Promotion gate for Milestone 4

The mystery layer should model clue dependencies and inference explicitly without turning narration into truth. New derived knowledge must have a reproducible provenance path from canonical facts/events, and NPC inference must remain epistemically isolated from player knowledge and other NPCs.
