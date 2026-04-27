# Implementation Steps

## 1. Extract Common Agent Base Logic
- [x] Add shared base helpers for polling, approval URLs, approval waits, and result logging.
- [x] Refactor agents to use the shared helpers without changing behavior.
- [x] Run tests and mark complete. (`uv --cache-dir .uv-cache run pytest tests/ -v`: 16 passed)

## 2. Start Real ADO Implementation
- [x] Replace placeholder ADO query/move/claim/wiki behavior with SDK-shaped implementations.
- [x] Keep simulated fallback behavior for local harness and tests.
- [x] Run tests and mark complete. (`uv --cache-dir .uv-cache run pytest tests/ -v`: 21 passed)

## 3. Add Mocked ADO SDK Tests
- [x] Test WIQL construction.
- [x] Test claim and move JSON Patch payloads.
- [x] Test wiki update call shape.
- [x] Run tests and mark complete. (`uv --cache-dir .uv-cache run pytest tests/ -v`: 21 passed)

## 4. Improve Artifact Contracts
- [x] Add explicit artifact validation helpers.
- [x] Validate architecture, Fabric implementation, QA result, semantic model, and governance audit artifacts in the harness path.
- [x] Run tests and mark complete. (`uv --cache-dir .uv-cache run pytest tests/ -v`: 23 passed)

## 5. Add Event Sink Abstraction
- [x] Add stdout JSONL and file JSONL event sinks.
- [x] Keep in-memory and no-op sinks for tests/defaults.
- [x] Run tests and mark complete. (`uv --cache-dir .uv-cache run pytest tests/ -v`: 26 passed)

## 6. Container Smoke Testing Hooks
- [x] Add `Makefile` targets for test, harness, compose config, docker build, and docker smoke.
- [x] Document Docker availability limitation in this environment.
- [x] Run available tests and mark complete. (`make test`: 26 passed; `make harness`: passed; `make syntax`: passed; `make compose-config`: Docker unavailable in this WSL distro)
