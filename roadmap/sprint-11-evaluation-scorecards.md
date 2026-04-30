# Sprint 11 — Evaluation Scorecards

## Goal
Standardize quality scoring for artifacts and runs.

## User Stories
1. Add typed scorecard schema.
2. Compute run-level metrics from events.
3. Persist scorecards as JSON artifacts.
4. Add tests for score aggregation.

## Implementation Status
- [x] Added foundational `shared_skills/evaluation` scorecard utilities.
- [x] Integrated scorecard generation and optional persistence into `harness.run`.
