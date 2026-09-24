"""
Direct analog of Albugent's patch_applier.py:apply_patch — "Not an MCP tool. It is
called directly by the backend endpoint when the Apply button is clicked in the UI.
The LLM/agent has no access to this function under any circumstances."

Same rule here, word for word: resolve_pending_action is called ONLY from
web_api/resolve_action.py's HTTP endpoint (the Alexa app's Tier 2, user-authenticated
channel). It is never imported by mcp_server/server.py, and it is not decorated as an
MCP tool anywhere. That separation is the entire point of this project.
"""
from typing import Any, Dict

from mcp_server.utils.db_utils import get_action, update_action_resolution, bump_agent_trust
from mcp_server.utils.receipts import send_purchase_receipt


def resolve_pending_action(action_id: str, approved: bool, resolved_by_user_id: str) -> Dict[str, Any]:
    action = get_action(action_id)
    if not action:
        return {"error": f"action_id '{action_id}' not found"}

    if action["status"] != "HALTED":
        return {"error": f"action '{action_id}' has status '{action['status']}', not HALTED — nothing to resolve"}

    if action.get("resolution"):
        return {"error": f"action '{action_id}' was already resolved: {action['resolution']}"}

    resolution = "APPROVED" if approved else "DENIED"
    update_action_resolution(action_id, resolution, resolved_by_user_id)
    bump_agent_trust(action["agent_id"], approved)

    # NOTE: actually executing the purchase after a Tier-2 approval is a separate,
    # merchant-specific integration (out of scope for this MVP) — it would be invoked
    # from here, still never from the agent's MCP channel.
    if approved:
        # Functional Requirements #8: a purchase that completes -- even one that
        # completes late, after Tier 2 approval -- still needs a receipt.
        send_purchase_receipt({**action, "status": "APPROVED_BY_USER"})

    return {
        "action_id": action_id,
        "resolution": resolution,
        "resolved_by": resolved_by_user_id,
    }
