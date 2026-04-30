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
loop (Sprint 7), memory (Sprint 5), context management (Sprint 6), and the
foundational harness primitives are now represented by offline-safe local modules.

| Sprint | File | Gap addressed | Priority |
|--------|------|---------------|----------|
| 9  | `sprint-09-filesystem-workspace.md` | Agent workspace and file tools | Completed |
| 10 | `sprint-10-code-execution.md` | Sandboxed code/command execution tools | Completed |
| 11 | `sprint-11-agent-delegation.md` | In-process subagent delegation | Completed |
| 12 | `sprint-12-inagent-task-planning.md` | In-agent todo tracking and tools | Completed |
| 13 | `sprint-13-mcp-integration.md` | MCP client/tool adapter primitives | Completed |
| 14 | `sprint-14-provider-registry.md` | Provider registry and built-in providers | Completed |

## Recommended execution order

### Wave 1 (sprints 1–8)
Sprints 1–3 are independent of each other and can be parallelised across engineers.
Sprint 2 (middleware) is a prerequisite for Sprints 5 and 6 because `MemoryMiddleware`
and `SummarisationMiddleware` plug into the hook system. Sprint 7 is the largest
architectural change and should start only after Sprints 1–4 are stable.
Sprint 8 is implemented. The Requirements Analyst agent, config entry, registry
entry, harness wiring, requirements artifact validator, Data Architect handoff,
and expanded task prompts are present.

### Wave 2 (sprints 9–14)
Sprint 9 (filesystem workspace) is a prerequisite for Sprint 10 (code execution)
because the executor sandbox is anchored to a configured local directory.
Sprint 7 (TAO loop + ToolRegistry) remains the integration point for Sprints 10-13
because those sprints register new tools into the registry.

```
Sprint 1 ────────────────────────────────────────────────────────► done
Sprint 2 ───────────────────────────────────────────────────────► done
Sprint 3 ────────────────────────────────────────────────────────► done
                   Sprint 4 ──────────────────────────────────► done
                                Sprint 5 ──────────────────────► done
                                Sprint 6 ──────────────────────► done
                                                   Sprint 7 ───────────────────────────► done
Sprint 8 ────────────────────────────────────────────────────────► done

Sprint 9 ──────────────────────────────────────────────────────────────────────────────► done
                   Sprint 10 ─────────────────────────────────────────────────────────► done
                   Sprint 11 ─────────────────────────────────────────────────────────► done
                   Sprint 12 ─────────────────────────────────────────────────────────► done
                   Sprint 13 ─────────────────────────────────────────────────────────► done
                   Sprint 14 ─────────────────────────────────────────────────────────► done
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
