"""Prepare a safe, local replay bundle from completed tau2 traces."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
DESTINATION = ROOT / "demo" / "data"
COLLECTIONS = {
    "development": OUTPUTS / "benchmark_final_dev",
    "held-out": OUTPUTS / "benchmark_heldout",
    "repeats": OUTPUTS / "benchmark_repeats",
}
FAULTS = {
    "fault-risk": OUTPUTS / "controlled_task41_risk_replay_safe.json",
    "fault-none": OUTPUTS / "controlled_task41_none_fault.json",
}
CURATED = {
    "development-dev_task41_seed42_risk": {
        "title": "The agent confirms an address change",
        "intro": "A completed task with two confirmed order addresses.",
        "customer_goal": "The customer wants an easier puzzle and the correct address on two orders and their profile.",
        "what_happened": "The agent changed the puzzle and addresses. Readbacks confirmed 445 Maple Drive on both orders. The puzzle check was inconclusive, and the full task passed.",
        "why_it_matters": "This run shows a working address checkpoint and the verifier's narrower coverage for item changes.",
    },
    "fault-risk": {
        "title": "A hidden address error is caught",
        "intro": "The tool reports the requested address, but the saved order contains another street.",
        "customer_goal": "The customer wants to change a puzzle and correct order and profile addresses.",
        "what_happened": "A controlled fault saved 999 Wrong Road while the tool reported 445 Maple Drive. A readback found the mismatch. The agent repaired that order address, although the full task remained incomplete.",
        "why_it_matters": "This demonstrates detection and local repair of a hidden state error. The fault was injected for testing and does not measure natural error rates.",
    },
    "fault-none": {
        "title": "The same error goes unchecked",
        "intro": "A control run shows the injected fault without an outcome check.",
        "customer_goal": "The customer wants to change a puzzle and correct order and profile addresses.",
        "what_happened": "With checking disabled, a controlled fault saved the wrong street after a successful-looking response. The agent told the customer the address was updated, but the wrong street remained.",
        "why_it_matters": "This shows the error that an independent readback can catch. It does not estimate how often the error occurs in ordinary runs.",
    },
    "held-out-heldout_task17_seed42_risk": {
        "title": "A check cannot decide",
        "intro": "The task succeeds, but the verifier cannot reach a confident verdict.",
        "customer_goal": "The customer wants to change the suite number on an order.",
        "what_happened": "The agent changed the suite to 641, and the full task passed. The verifier read the saved order but returned INCONCLUSIVE because the customer had not independently stated the street.",
        "why_it_matters": "Independent readback does not always settle whether a change fulfilled the request. The controller needs an honest inconclusive outcome.",
    },
    "held-out-heldout_task42_seed42_risk": {
        "title": "A passed check is not a completed task",
        "intro": "Two address writes pass local checks, while the full task fails.",
        "customer_goal": "The customer wants to correct addresses on their account and orders.",
        "what_happened": "Readbacks confirmed two order-address changes. An item-change check was inconclusive, and the official end-to-end task score was zero.",
        "why_it_matters": "A PASS describes one checked write. It does not certify every action in a multi-step request.",
    },
}
MESSAGE_FIELDS = ("role", "content", "turn_idx", "timestamp", "id")
EVENT_FIELDS = (
    "tool", "arguments", "response", "error", "mutating", "executed",
    "checkpoint", "risk", "pre_state", "verification", "correction_opportunity",
    "rejected_after_verification_fail", "escalated", "elapsed_seconds",
)
TRACE_FIELDS = (
    "task_id", "seed", "policy", "model", "threshold", "reward",
    "elapsed_seconds", "total_model_tokens", "estimated_model_cost_usd",
    "controlled_fault_injection", "fault_triggered", "fault_intended_street",
    "fault_injected_street", "fault_final_street", "fault_recovered",
    "termination_reason",
)


def sanitize(trace: dict) -> dict:
    """Copy runtime observations and the final reward, never evaluator-only state."""
    public = {key: trace.get(key) for key in TRACE_FIELDS if key in trace}
    public["messages"] = []
    for message in trace.get("messages", []):
        entry = {key: message.get(key) for key in MESSAGE_FIELDS if key in message}
        if message.get("tool_calls"):
            entry["tool_calls"] = [
                {key: call.get(key) for key in ("id", "name", "arguments") if key in call}
                for call in message["tool_calls"]
            ]
        public["messages"].append(entry)
    public["events"] = [
        {key: event.get(key) for key in EVENT_FIELDS if key in event}
        for event in trace.get("events", [])
    ]
    return public


def metadata(identifier: str, collection: str, trace: dict) -> dict:
    events = trace.get("events", [])
    verdicts = [(event.get("verification") or {}).get("verdict") for event in events]
    return {
        "id": identifier,
        "collection": collection,
        "task_id": str(trace.get("task_id", "")),
        "seed": trace.get("seed"),
        "policy": trace.get("policy"),
        "reward": trace.get("reward"),
        "message_count": len(trace.get("messages", [])),
        "tool_count": len(events),
        "write_count": sum(bool(event.get("mutating") and event.get("executed", True)) for event in events),
        "check_count": sum(verdict is not None for verdict in verdicts),
        "readback_calls": sum((event.get("verification") or {}).get("read_calls", 0) for event in events),
        "has_fail": "FAIL" in verdicts,
        "has_inconclusive": "INCONCLUSIVE" in verdicts,
        "fault_recovered": trace.get("fault_recovered"),
        "fault_final_street": trace.get("fault_final_street"),
    }


def build(destination: Path = DESTINATION) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    trace_dir = destination / "traces"
    trace_dir.mkdir(exist_ok=True)
    catalog = []
    natural = []

    for collection, directory in COLLECTIONS.items():
        for path in sorted(directory.glob("*_task*_seed*_*.json")):
            original = json.loads(path.read_text())
            if original.get("error") or original.get("reward") is None:
                continue
            identifier = f"{collection}-{path.stem}"
            public = sanitize(original)
            natural.append(public)
            if identifier in CURATED:
                (trace_dir / f"{identifier}.json").write_text(json.dumps(public, ensure_ascii=False))
                catalog.append({**metadata(identifier, collection, public), **CURATED[identifier]})

    fault_count = 0
    for identifier, path in FAULTS.items():
        if not path.exists():
            continue
        public = sanitize(json.loads(path.read_text()))
        fault_count += 1
        if identifier in CURATED:
            (trace_dir / f"{identifier}.json").write_text(json.dumps(public, ensure_ascii=False))
            catalog.append({**metadata(identifier, "controlled fault", public), **CURATED[identifier]})

    missing = set(CURATED) - {item["id"] for item in catalog}
    if missing:
        raise FileNotFoundError(f"Missing curated traces: {', '.join(sorted(missing))}")
    for path in trace_dir.glob("*.json"):
        if path.stem not in CURATED:
            path.unlink()

    heldout = [trace for trace in natural if trace["task_id"] in {"17", "42", "71", "97", "102"}
               and trace["seed"] == 42 and trace["policy"] in
               {"none", "final-only", "exhaustive", "random", "risk"}]
    # Development task IDs do not overlap the five held-out task IDs.
    policy_rows = []
    for policy in ("none", "final-only", "exhaustive", "random", "risk"):
        items = [trace for trace in heldout if trace["policy"] == policy]
        policy_rows.append({
            "policy": policy,
            "trials": len(items),
            "successes": sum(trace["reward"] == 1 for trace in items),
            "readbacks": sum(metadata("", "", trace)["readback_calls"] for trace in items),
            "checks": sum(metadata("", "", trace)["check_count"] for trace in items),
            "inconclusive": sum(
                (event.get("verification") or {}).get("verdict") == "INCONCLUSIVE"
                for trace in items for event in trace["events"]
            ),
        })

    paired = {}
    for trace in natural:
        if trace["task_id"] not in {"17", "42", "71", "97", "102"}:
            continue
        if trace["policy"] not in {"risk", "none"}:
            continue
        if trace["seed"] not in {42, 43, 44}:
            continue
        # Development tasks do not overlap these five test IDs.
        paired[(trace["task_id"], trace["seed"], trace["policy"])] = trace
    repeated = {}
    for policy in ("risk", "none"):
        items = [trace for (task, seed, name), trace in paired.items() if name == policy]
        repeated[policy] = {
            "trials": len(items),
            "successes": sum(trace["reward"] == 1 for trace in items),
            "readbacks": sum(metadata("", "", trace)["readback_calls"] for trace in items),
        }
    wins = {"risk": 0, "none": 0, "ties": 0}
    for task in ("17", "42", "71", "97", "102"):
        for seed in (42, 43, 44):
            risk = paired[(task, seed, "risk")]["reward"]
            none = paired[(task, seed, "none")]["reward"]
            wins["risk" if risk > none else "none" if none > risk else "ties"] += 1

    summary = {"heldout_seed42": policy_rows, "repeated_heldout": repeated,
               "paired_outcomes": wins, "natural_runs": len(natural)}
    (destination / "catalog.json").write_text(json.dumps(catalog, indent=2))
    (destination / "summary.json").write_text(json.dumps(summary, indent=2))
    return {"natural_runs": len(natural), "fault_runs": fault_count,
            "catalog_items": len(catalog)}


if __name__ == "__main__":
    print(build())
