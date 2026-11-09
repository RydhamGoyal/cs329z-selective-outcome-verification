"""Selective verification at tau2's synchronous tool boundary."""
from __future__ import annotations
import json
import random
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

WRITE_IMPACT = {"cancel_pending_order": .8, "return_delivered_order_items": .9,
                "exchange_delivered_order_items": .9,
                "modify_pending_order_payment": .9, "modify_pending_order_address": .7,
                "modify_pending_order_items": .8, "modify_user_address": .6}
IRREVERSIBLE = {"cancel_pending_order", "return_delivered_order_items", "exchange_delivered_order_items"}
READBACK = {"modify_pending_order_address": "get_order_details",
            "modify_pending_order_items": "get_order_details",
            "modify_pending_order_payment": "get_order_details",
            "cancel_pending_order": "get_order_details",
            "return_delivered_order_items": "get_order_details",
            "exchange_delivered_order_items": "get_order_details",
            "modify_user_address": "get_user_details"}

@dataclass
class Risk:
    impact: float
    downstream: float
    irreversibility: float
    uncertainty: float
    score: float

def risk(name: str, response_error: bool = False, weights=(.35, .25, .2, .2)) -> Risk:
    values = (WRITE_IMPACT.get(name, .5), .8 if name in {"modify_pending_order_address", "modify_pending_order_items", "modify_pending_order_payment"} else .4,
              1.0 if name in IRREVERSIBLE else .25, .8 if response_error else .5)
    assert len(weights) == 4 and all(x >= 0 for x in weights) and sum(weights) > 0
    return Risk(*values, sum(a*b for a,b in zip(values, weights))/sum(weights))

def selected(policy: str, score: float, rng: random.Random, threshold: float = .55, random_rate: float = .5) -> bool:
    if policy in ("none", "final-only"): return False
    if policy == "exhaustive": return True
    if policy == "risk": return score >= threshold
    if policy == "random": return rng.random() < random_rate
    raise ValueError(policy)

def visible_intent(messages: list[Any]) -> str:
    return "\n".join(str(m.content) for m in messages if getattr(m, "role", None) == "user" and getattr(m, "content", None))

def verdict(name: str, arguments: dict, evidence: dict | None, intent: str, error: bool = False) -> tuple[str,str]:
    if error or evidence is None: return "INCONCLUSIVE", "Readback unavailable or failed"
    if name == "modify_pending_order_address":
        import re
        address = evidence.get("address") or {}
        observed_street = str(address.get("address1", "")).strip()
        observed_zip = str(address.get("zip", "")).strip()
        # Require an independently visible target street. A matching zip alone
        # cannot prove the street is correct.
        street_pattern = (r"\b\d{1,6}\s+[A-Za-z][A-Za-z .'-]{0,50}?\s+"
                          r"(?:Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Lane|Ln|"
                          r"Boulevard|Blvd|Court|Ct|Way|Highway|Hwy)\b")
        matches = list(re.finditer(street_pattern, intent, flags=re.IGNORECASE))
        if not matches:
            return "INCONCLUSIVE", "No unambiguous target street independently stated by user"
        target_street = matches[-1].group(0).strip()
        if observed_street.casefold() != target_street.casefold():
            return "FAIL", "Readback street differs from user-stated street"
        if observed_zip and re.search(r"\b\d{5}(?:-\d{4})?\b", intent):
            if observed_zip not in intent:
                return "FAIL", "Readback postal code differs from user-stated postal code"
        return "PASS", "Readback street matches independently stated user intent"
    if name == "cancel_pending_order":
        if "cancel" not in intent.lower(): return "INCONCLUSIVE", "Cancellation intent not visible"
        return ("PASS", "Canceled state and cancellation intent observed") if evidence.get("status", "").lower() in ("cancelled", "canceled") else ("FAIL", "Order is not canceled")
    return "INCONCLUSIVE", "No intent-grounded deterministic rule for this operation"

def save_trace(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))

class VerificationOrchestratorMixin:
    """Override only the public half-duplex tool execution seam."""
    def configure_verification(self, policy: str, threshold: float = .55, seed: int = 42,
                               random_rate: float = .5, weights=(.35, .25, .2, .2)):
        self.check_policy = policy
        self.threshold = threshold
        if len(weights) != 4 or any(x < 0 for x in weights) or sum(weights) <= 0:
            raise ValueError('Risk weights must be four nonnegative numbers with positive sum')
        self.risk_weights = tuple(weights)
        # A fresh orchestrator is built for each task. Mixing the task ID into
        # the seed avoids replaying the same short prefix of Bernoulli draws
        # on every task (which made the initial random baseline exhaustive).
        task_id = getattr(getattr(self, "task", None), "id", "unknown")
        self.rng = random.Random(f"{seed}:{task_id}")
        self.random_rate = random_rate
        self.events = []
        self.corrections = 0

    def _execute_tool_calls(self, tool_calls):
        from tau2.data_model.message import ToolMessage
        results = []
        reject_remaining = False
        for call in tool_calls:
            if reject_remaining:
                reason = "Rejected because an earlier write in this batch failed outcome verification. Ask the agent to reassess before proceeding."
                results.append(ToolMessage(id=call.id, role="tool", requestor=call.requestor,
                                           content=reason, error=True, execution_status="rejected"))
                self.events.append({"tool": call.name, "arguments": call.arguments,
                                    "response": reason, "error": True,
                                    "mutating": self.environment.tools.tool_mutates_state(call.name),
                                    "executed": False, "checkpoint": False,
                                    "rejected_after_verification_fail": True,
                                    "elapsed_seconds": 0.0})
                continue
            t0 = time.perf_counter()
            mutating = self.environment.tools.tool_mutates_state(call.name)
            preliminary = risk(call.name, weights=self.risk_weights) if mutating else None
            check = selected(self.check_policy, preliminary.score, self.rng, self.threshold, self.random_rate) if mutating else False
            pre = self._readback(call) if check else None
            result = self.environment.get_response(call)
            if result.error: self.num_errors += 1
            event = {"tool":call.name, "arguments":call.arguments, "response":result.content,
                     "error":result.error, "mutating":mutating, "executed":True, "pre_state":pre,
                     "elapsed_seconds":time.perf_counter()-t0}
            if mutating:
                r = preliminary
                event["risk"] = asdict(r)
                event["checkpoint"] = check
                if check:
                    post = self._readback(call)
                    intent = visible_intent(self.get_trajectory())
                    status, reason = verdict(call.name, call.arguments, post, intent, result.error)
                    event["verification"] = {"verdict":status, "reason":reason,
                        "evidence":post, "read_calls":2 if READBACK.get(call.name) else 0}
                    if status == "FAIL":
                        reject_remaining = True
                        observed = (post.get('address', {}).get('address1')
                                    if isinstance(post, dict) else None)
                        feedback = (f"OUTCOME VERIFICATION FAILED for {call.name} "
                                    f"on {call.arguments.get('order_id', call.arguments.get('user_id', 'record'))}: {reason}. "
                                    + (f"Independent readback street: {observed}. " if observed else "")
                                    + "This write is not confirmed. Do not tell the user it succeeded. "
                                    "Later calls in this batch are rejected.")
                        event['feedback_to_agent'] = feedback
                        if call.name in IRREVERSIBLE or self.corrections >= 1:
                            from tau2.data_model.simulation import TerminationReason
                            self.done = True
                            self.termination_reason = TerminationReason.AGENT_ERROR
                            event['escalated'] = True
                        else:
                            self.corrections += 1
                            from tau2.data_model.message import SystemMessage
                            self.agent_state.system_messages.append(SystemMessage(
                                role="system", content=feedback + " You have one correction opportunity. "
                                "Reconfirm the user request and applicable policy, inspect state, then repair only if reversible."))
                            event["correction_opportunity"] = True
            event["elapsed_seconds"] = time.perf_counter()-t0
            self.events.append(event)
            results.append(result)
        return results

    def _readback(self, call):
        from tau2.data_model.message import ToolCall
        name = READBACK.get(call.name)
        key = "order_id" if "order_id" in call.arguments else "user_id" if "user_id" in call.arguments else None
        if not name or not key: return None
        try:
            response = self.environment.get_response(ToolCall(name=name, arguments={key:call.arguments[key]}))
        except (TimeoutError, OSError, RuntimeError):
            return None
        if response.error: return None
        try: return json.loads(response.content)
        except (ValueError, TypeError): return None
