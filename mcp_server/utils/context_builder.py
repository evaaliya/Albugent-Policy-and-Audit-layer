"""
Structural port of Albugent's context_builder.py: collect_governance_context() there
loops over all datasets and assembles one payload for the report. Here it runs once
per purchase attempt and assembles one payload for the decision + audit log entry —
same idea, scoped to a single event instead of a scheduled full-registry sweep.
"""
from typing import Any, Dict

from mcp_server.utils.db_utils import get_agent_trust, get_session_actions, new_id, now_iso
from mcp_server.utils.session_profiler import profile_purchase_attempt
from mcp_server.utils.risk_evaluator import evaluate_purchase_risk
from mcp_server.utils.circuit_breaker import compute_action_status


def build_purchase_decision(
    agent_id: str, session_id: str, item: str, category: str, merchant: str, amount: float
) -> Dict[str, Any]:
    trust_score = get_agent_trust(agent_id)
    profile = profile_purchase_attempt(agent_id, session_id, item, category, merchant, amount)

    risk_result = evaluate_purchase_risk(
        category=category,
        amount=amount,
        anomaly_flags=profile["flags"],
        trust_score=trust_score,
    )

    prior_actions = get_session_actions(session_id)
    status, reason = compute_action_status(risk_result, prior_actions)

    return {
        "action_id": new_id("act"),
        "session_id": session_id,
        "agent_id": agent_id,
        "item": item,
        "category": category,
        "merchant": merchant,
        "amount": amount,
        "created_at": now_iso(),
        "risk_score": risk_result["risk_score"],
        "category_severity": risk_result["category_severity"],
        "anomaly_flags": profile["flags"],
        "anomaly_details": profile["details"],
        "status": status,
        "reason": reason,
        "resolution": None,
        "resolved_at": None,
        "resolved_by": None,
    }
