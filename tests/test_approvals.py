from approvals import APPROVED, REJECTED, InMemoryApprovalStore, JsonFileApprovalStore, new_approval_record


def test_in_memory_approval_store_creates_and_decides():
    store = InMemoryApprovalStore()
    record = new_approval_record("1", "data_architect", "Architecture")

    created = store.create(record)
    decided = store.decide(
        created["approval_id"],
        APPROVED,
        decided_by="reviewer@example.com",
        comments="Looks good",
    )

    assert decided["status"] == APPROVED
    assert decided["decided_by"] == "reviewer@example.com"
    assert decided["comments"] == "Looks good"


def test_json_file_approval_store_persists_records(tmp_path):
    path = tmp_path / "approvals.json"
    store = JsonFileApprovalStore(path)
    record = store.create(new_approval_record("1", "data_architect", "Architecture"))
    store.decide(record["approval_id"], REJECTED, decided_by="reviewer", comments="Needs work")

    reloaded = JsonFileApprovalStore(path)

    assert reloaded.get(record["approval_id"])["status"] == REJECTED
    assert reloaded.get(record["approval_id"])["comments"] == "Needs work"
