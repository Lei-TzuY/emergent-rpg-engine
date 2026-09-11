# Roadmap

The first milestone intentionally stops at a deterministic, persistent core.

1. **Deterministic core** — canonical state, typed events, validation, replay, memory tiers, persistent CLI demo. **Current.**
2. **Real LLM provider** — provider implementation without leaking provider specifics into domain code.
3. **Structured LLM action parsing** — constrained parsing with deterministic validation/fallback.
4. **Mystery graph** — richer clue dependencies, inference, contradiction tracking, and reveal gates.
5. **NPC autonomous planning** — goals, bounded plans, and knowledge-constrained action selection.
6. **World simulation between player turns** — scheduled events and off-screen consequences.
7. **Vector/embedding retrieval** — optional semantic retrieval alongside deterministic ranking.
8. **Local-model support / Ollama** — offline provider adapter and routing.
9. **Web API** — stable service boundary over the core engine.
10. **Web UI** — presentation layer over persisted sessions.
11. **Model routing / cost controls** — per-stage provider selection, budgets, and caching.
12. **Evaluation harness for 1,000+ turn consistency** — repeatable long-run continuity metrics and adversarial scenarios.
