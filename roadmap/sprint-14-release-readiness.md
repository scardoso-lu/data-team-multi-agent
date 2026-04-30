# Sprint 14 — Release Readiness Gates

## Goal
Introduce explicit release gates (test, policy, scorecard) before completion states.

## User Stories
1. Add release gate evaluator.
2. Block completion when gate thresholds fail.
3. Emit gate events and summaries.
4. Add end-to-end harness test for gated release.

## Implementation Status
- [x] Added release gate utility module.
- [x] Integrated release gates into terminal governance-stage transitions.
