# Human-In-The-Loop Implementation Steps

## 1. Approval Data Model And Store
- [x] Add approval status constants and approval record helpers.
- [x] Add in-memory approval store for harness/tests.
- [x] Add JSON-file approval store for durable local approvals.
- [x] Add tests and mark complete. (`uv --cache-dir .uv-cache run pytest tests/test_approvals.py -v`: 2 passed)

## 2. Approval Decision Flow
- [ ] Replace work-item-only approval waits with approval record IDs.
- [ ] Support approved, rejected, and timeout decisions.
- [ ] Add reviewer comments and reviewer identity fields.
- [ ] Add tests and mark complete.

## 3. Agent Approval Integration
- [ ] Create approval records with artifact metadata before requesting approval.
- [ ] Move approved items to the next column.
- [ ] Move rejected items to configured rework column.
- [ ] Move timeout items to configured approval-timeout column.
- [ ] Add tests and mark complete.

## 4. Teams Approval Payloads
- [ ] Include approval ID, artifact summary, artifact links, approve action, reject action, and comment input.
- [ ] Add payload-shape tests without sending live Teams requests.
- [ ] Mark complete.

## 5. Approval Events And Audit Trail
- [ ] Add approval approved/rejected/timed-out event types.
- [ ] Emit reviewer identity and comments.
- [ ] Assert events in harness tests.
- [ ] Mark complete.

## 6. Harness Scenarios
- [ ] Add approved end-to-end scenario.
- [ ] Add rejected scenario.
- [ ] Add timeout scenario.
- [ ] Run full suite and mark complete.
