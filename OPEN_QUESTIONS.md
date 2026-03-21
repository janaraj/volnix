# Terrarium Open Questions

Unresolved design decisions that must be settled before or during their dependent implementation phase.

| # | Question | Phase Dependency | Status |
|---|----------|-----------------|--------|
| 1 | **Side effect recursion limit behavior** — When max depth is hit, should the pipeline silently drop the side effect, log a warning, or raise an error event? | Resolve before Phase 2 (pipeline module) | Open |
| 2 | **Semantic Kernel query interface** — How should engines query the kernel? Direct function calls or protocol? Lookup API signature? | Resolve before Phase 5 (kernel + responder) | Open |
| 3 | **Pack handler contract (Tier 1 handler interface)** — Exact interface a pack handler implements? How it receives state, returns ResponseProposal? | Resolve before Phase 5 (packs) | Open |
| 4 | **Natural language world compilation prompt architecture** — Single-shot or multi-step? How is world plan presented for review? | Resolve before Phase 6 (world compiler engine) | Open |
| 5 | **World Compiler output schema for NL input** — Exact intermediate representation? WorldPlan schema? | Resolve before Phase 6 (world compiler engine) | Open |
| 6 | **Animator scheduling semantics** — Time-triggered vs event-triggered? Tick model? | Resolve before Phase 6 (animator engine) | Open |
| 7 | **Policy condition language parser** — Hand-written or library (lark)? How to handle registered functions? | Resolve before Phase 4 (policy engine) | Open |
| 8 | **Visualization protocol** — SSE vs WebSocket for live streaming? Separate observation protocol? | Resolve before Phase 8 (dashboard) | Open |
