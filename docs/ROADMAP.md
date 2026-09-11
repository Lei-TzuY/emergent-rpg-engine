# Roadmap

The project advances by coherent executable slices rather than placeholder subsystems.

1. **Deterministic core** — canonical state, typed events, validation, replay, memory tiers, persistent CLI demo. **Complete.**
2. **Real LLM provider** — provider implementation without leaking provider specifics into domain code; constrained `ScenePlan` input; offline transport tests; provider-failure atomicity. **Complete.**
3. **Structured LLM action parsing** — constrained schema parsing with deterministic validation, retry/fallback behavior, and no direct state mutation. **Next.**
4. **Mystery graph** — richer clue dependencies, inference, contradiction tracking, and reveal gates.
5. **NPC autonomous planning** — goals, bounded plans, and knowledge-constrained action selection.
6. **World simulation between player turns** — scheduled events and off-screen consequences.
7. **Vector/embedding retrieval** — optional semantic retrieval alongside deterministic ranking.
8. **Local-model support / Ollama** — explicit local-model presets/routing beyond the generic OpenAI-compatible endpoint.
9. **Web API** — stable service boundary over the core engine.
10. **Web UI** — presentation layer over persisted sessions.
11. **Model routing / cost controls** — per-stage provider selection, budgets, and caching.
12. **Evaluation harness for 1,000+ turn consistency** — repeatable long-run continuity metrics and adversarial scenarios.

## Promotion gate for Milestone 3

Structured LLM parsing should not begin by giving a model mutation authority. The acceptance boundary is:

```text
freeform text
→ provider proposes typed PlayerAction JSON
→ schema validation
→ deterministic resolver
→ ordinary event/validator pipeline
```

Malformed, unknown, or semantically impossible model output must fall back or fail structurally without corrupting canonical state.
