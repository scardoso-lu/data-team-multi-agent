# Harness Improvement Roadmap

Fourteen sprints addressing the gaps identified against the LangChain agent harness
definition. Each sprint file contains the gap description, goal, and all user stories
with file-level implementation details and test guidance.

## Sprints 1–8 (original wave)

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
| 9 | `sprint-09-policy-governance.md` | Missing centralized policy enforcement | High |
| 10 | `sprint-10-offline-replay.md` | No replay/regression framework | Medium |
| 11 | `sprint-11-evaluation-scorecards.md` | No standardized run scoring | Medium |
| 12 | `sprint-12-human-feedback-dataset.md` | Reviewer feedback not captured as dataset | Medium |
| 13 | `sprint-13-planning-optimizer.md` | No step ranking/optimization heuristics | Medium |
| 14 | `sprint-14-release-readiness.md` | No explicit release readiness gates | High |

## Sprints 9–14 (harness primitives wave)

Identified from a second-pass review against the LangChain anatomy: the execution
loop (Sprint 7), memory (Sprint 5), and context management (Sprint 6) were addressed
in wave 1, but four foundational harness primitives remain unimplemented.

| Sprint | File | Gap addressed | Priority |
|--------|------|---------------|----------|
| 9  | `sprint-09-filesystem-workspace.md` | No agent workspace — artifacts are entirely in-memory | High |
| 10 | `sprint-10-code-execution.md` | No code/command execution — QA checks are never run | High |
| 11 | `sprint-11-agent-delegation.md` | No subagent delegation — pipeline is strictly linear | Medium |
| 12 | `sprint-12-inagent-task-planning.md` | No in-agent task planning (write_todos / TodoTracker) | Medium |
| 13 | `sprint-13-mcp-integration.md` | No MCP support — external tool servers can't plug in | Medium |
| 14 | `sprint-14-provider-registry.md` | Hard-coded CLI list — no provider registry or model swapping | Low |

## Recommended execution order

### Wave 1 (sprints 1–8)
Sprints 1–3 are independent of each other and can be parallelised across engineers.
Sprint 2 (middleware) is a prerequisite for Sprints 5 and 6 because `MemoryMiddleware`
and `SummarisationMiddleware` plug into the hook system. Sprint 7 is the largest
architectural change and should start only after Sprints 1–4 are stable.
Sprint 8 is already implemented.

### Wave 2 (sprints 9–14)
Sprint 9 (filesystem workspace) is a prerequisite for Sprint 10 (code execution)
because the executor sandbox is anchored to the workspace directory.
Sprint 7 (TAO loop + ToolRegistry) is a prerequisite for Sprints 10–13 because
those sprints register new tools into the registry.
Sprints 11–14 are independent of each other once Sprint 9 and 7 are stable.

```
Sprint 1 ────────────────────────────────────────────────────────► planned
Sprint 2 ───────────────────────────────────────────────────────► planned
Sprint 3 ────────────────────────────────────────────────────────► planned
                   Sprint 4 ──────────────────────────────────► planned
                                Sprint 5 ──────────────────────► planned (depends on 2)
                                Sprint 6 ──────────────────────► planned (depends on 2)
                                                   Sprint 7 ───────────────────────────► planned
Sprint 8 ────────────────────────────────────────────────────────► done

Sprint 9 ──────────────────────────────────────────────────────────────────────────────► planned
                   Sprint 10 ─────────────────────────────────────────────────────────► planned (depends on 9)
                   Sprint 11 ─────────────────────────────────────────────────────────► planned (depends on 7)
                   Sprint 12 ─────────────────────────────────────────────────────────► planned (depends on 7)
                   Sprint 13 ─────────────────────────────────────────────────────────► planned (depends on 7)
                   Sprint 14 ─────────────────────────────────────────────────────────► planned
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
| 9 — Policy governance | 4 |
| 10 — Offline replay | 4 |
| 11 — Evaluation scorecards | 4 |
| 12 — Human feedback dataset | 4 |
| 13 — Planning optimizer | 4 |
| 14 — Release readiness | 4 |
| **Total** | **61** |
