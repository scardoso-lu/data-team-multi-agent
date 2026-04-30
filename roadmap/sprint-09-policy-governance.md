# Sprint 9 — Policy Governance Layer

## Goal
Introduce a reusable policy engine for validating artifacts and actions before downstream transitions.

## User Stories
1. Add `PolicyRule` and `PolicyEngine` abstractions.
2. Evaluate artifact payloads against policy rules in `BoardAgent`.
3. Emit policy events for pass/fail.
4. Add unit tests for deterministic enforcement.

## Implementation Status
- [x] Added foundational `shared_skills/policy` module.
- [x] Added policy events and `BoardAgent` enforcement hook.
- [ ] Add role-specific policy packs.
