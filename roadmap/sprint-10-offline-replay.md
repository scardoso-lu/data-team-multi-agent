# Sprint 10 — Offline Replay & Regression Harness

## Goal
Allow replay of recorded event streams to reproduce failures and compare behavior across versions.

## User Stories
1. Add replay record format and loader.
2. Build a replay runner for event streams.
3. Provide deterministic comparison utilities.
4. Add regression tests with golden traces.

## Implementation Status
- [x] Added foundational `shared_skills/replay` module with trace loader.
- [x] Integrated replay summaries and optional trace persistence into `harness.run`.
- [x] Added regression tests for trace saving and replay summaries.
