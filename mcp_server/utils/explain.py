"""
Mirrors the one hard rule from Albugent's agent.py: an LLM (if used at all) only turns
already-computed facts into a sentence. It never sees raw tool access and never produces
the risk_score/status itself. For this MVP the explanation is fully deterministic template
text — swapping in a real LLM call later (like generate_executive_summary in agent.py)
is a drop-in change that must keep this same constraint.
"""
from typing import Any, Dict


def explain_decision(decision: Dict[str, Any]) -> str:
    status = decision["status"]
    item = decision.get("item", "an item")
    amount = decision.get("amount")
    merchant = decision.get("merchant")
    category = decision.get("category")

    base = f"Alexa+ attempted to purchase '{item}' (${amount}, category: {category}, merchant: {merchant})."

    if status == "OK":
        return base + " No risk signals were found; the purchase was completed automatically."

    if status == "MONITOR":
        flags = ", ".join(decision.get("anomaly_flags", [])) or "elevated category risk"
        return (
            base + f" It was completed, but flagged for review because: {flags}. "
            f"reason: {decision.get('reason')}"
        )

    # HALTED
    return (
        base + " It was NOT completed and requires your explicit approval because: "
        f"{decision.get('reason')}. Approve or deny this from your Alexa app, not through the assistant."
    )
