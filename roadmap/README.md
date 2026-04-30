# Harness Improvement Roadmap

Seven sprints addressing the gaps identified against the LangChain agent harness
definition. Each sprint file contains the gap description, goal, and all user stories
with file-level implementation details and test guidance.

| Sprint | File | Gap addressed | Priority |
|--------|------|---------------|----------|
| 1 | `sprint-01-feedback-loop.md` | No self-correction — LLM never sees validation errors | Highest |
| 2 | `sprint-02-middleware-hooks.md` | No composable hook lifecycle (before/after model/agent) | High |
| 3 | `sprint-03-observability.md` | LLM calls invisible — can't distinguish real vs fallback | High |
| 4 | `sprint-04-checkpointing-typed-state.md` | No crash recovery; artifact contracts are untyped | Medium |
| 5 | `sprint-05-persistent-memory.md` | Every run starts cold — no cross-session memory | Medium |
| 6 | `sprint-06-context-management.md` | Payloads passed verbatim — no token budget management | Medium |
| 7 | `sprint-07-tao-loop-tools.md` | Single-shot LLM call; model cannot invoke tools | Large/Last |
| 8 | `sprint-08-agent-task-refinement.md` | Tasks too large/thin; new RequirementsAnalystAgent | Completed |

## Recommended execution order

Sprints 1–3 are independent of each other and can be parallelised across engineers.
Sprint 2 (middleware) is a prerequisite for Sprints 5 and 6 because `MemoryMiddleware`
and `SummarisationMiddleware` plug into the hook system. Sprint 7 is the largest
architectural change and should start only after Sprints 1–4 are stable.

```
Sprint 1 ──────────────────────────────────────────────► done
Sprint 2 ─────────────────────────────────────► done
Sprint 3 ──────────────────────────────────────────────► done
                   Sprint 4 ─────────────────► done
                                Sprint 5 ─────────────────► done (depends on Sprint 2)
                                Sprint 6 ─────────────────► done (depends on Sprint 2)
                                                   Sprint 7 ──────────────────────────► done
```

## Story count per sprint

| Sprint | Stories |
|--------|---------|
| 1 — Feedback loop | 4 |
| 2 — Middleware hooks | 4 |
| 3 — Observability | 5 |
| 4 — Checkpointing & typed state | 4 |
| 5 — Persistent memory | 4 |
| 6 — Context management | 4 |
| 7 — TAO loop & tools | 5 |
| 8 — Agent & task refinement | 7 |
| **Total** | **37** |
