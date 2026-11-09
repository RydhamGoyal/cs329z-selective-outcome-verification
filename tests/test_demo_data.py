"""The public replay bundle must show observed runs without evaluator oracle data."""

import json

from scripts.build_demo_data import build, sanitize


def test_sanitizer_keeps_runtime_evidence_and_drops_oracle_fields():
    trace = {
        "task_id": "41",
        "reward": 1.0,
        "evaluation_details": {"golden_actions": ["secret"]},
        "user_objective": {"hidden_answer": "secret"},
        "messages": [
            {"role": "user", "content": "Please use 445 Maple Drive", "hidden_instruction": "secret"},
        ],
        "events": [
            {"tool": "modify_pending_order_address", "arguments": {"address1": "445 Maple Drive"},
             "verification": {"verdict": "PASS", "evidence": {"address": {"address1": "445 Maple Drive"}}},
             "gold_state": "secret"},
        ],
    }
    public = sanitize(trace)
    serialized = json.dumps(public)
    assert "secret" not in serialized
    assert "445 Maple Drive" in serialized
    assert public["reward"] == 1.0
    assert public["events"][0]["verification"]["verdict"] == "PASS"


def test_demo_bundle_counts_real_runs_and_keeps_faults_separate(tmp_path):
    result = build(tmp_path)
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert result == {"natural_runs": 70, "fault_runs": 2, "catalog_items": 5}
    assert len(catalog) == 5
    assert sum(item["collection"] == "controlled fault" for item in catalog) == 2
    assert all(item["title"] and item["customer_goal"] and item["what_happened"]
               and item["why_it_matters"] for item in catalog)
    by_id = {item["id"]: item for item in catalog}
    assert by_id["fault-risk"]["fault_final_street"] == "445 Maple Drive"
    assert by_id["fault-none"]["fault_final_street"] == "999 Wrong Road"
    assert not any(item["collection"] == "repeats" for item in catalog)
    assert {(row["policy"], row["successes"], row["readbacks"])
            for row in summary["heldout_seed42"]} == {
                ("none", 3, 0), ("final-only", 3, 9), ("exhaustive", 3, 22),
                ("random", 3, 14), ("risk", 2, 14),
            }
    paths = list((tmp_path / "traces").glob("*.json"))
    assert len(paths) == 5
    for path in paths:
        trace = json.loads(path.read_text())
        assert "evaluation_details" not in trace
        assert "user_objective" not in trace
        assert trace["messages"]


def test_guided_examples_match_observed_outcomes(tmp_path):
    build(tmp_path)
    directory = tmp_path / "traces"

    def read(identifier):
        return json.loads((directory / f"{identifier}.json").read_text())

    def verdicts(trace):
        return [(event.get("verification") or {}).get("verdict")
                for event in trace["events"] if event.get("verification")]

    confirmed = read("development-dev_task41_seed42_risk")
    assert confirmed["reward"] == 1.0
    assert verdicts(confirmed).count("PASS") == 2
    assert "INCONCLUSIVE" in verdicts(confirmed)

    caught = read("fault-risk")
    unchecked = read("fault-none")
    assert caught["fault_triggered"] and caught["fault_recovered"]
    assert "FAIL" in verdicts(caught)
    assert unchecked["fault_triggered"] and not unchecked["fault_recovered"]
    assert verdicts(unchecked) == []

    undecided = read("held-out-heldout_task17_seed42_risk")
    assert undecided["reward"] == 1.0
    assert verdicts(undecided) == ["INCONCLUSIVE"]

    local_pass = read("held-out-heldout_task42_seed42_risk")
    assert local_pass["reward"] == 0.0
    assert verdicts(local_pass).count("PASS") == 2
