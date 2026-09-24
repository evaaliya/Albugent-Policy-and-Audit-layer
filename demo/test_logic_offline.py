"""
Offline smoke test of the decision pipeline (no MCP transport involved — just proves
risk_evaluator + session_profiler + circuit_breaker + db_utils behave as designed).
The real "it works over Streamable HTTP" proof is demo/simulate_session.py, which needs
the `mcp` package installed and the server actually running.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_server.utils.db_utils import ensure_schema, insert_action, DB_PATH
from mcp_server.utils.context_builder import build_purchase_decision
from mcp_server.utils.explain import explain_decision

if DB_PATH.exists():
    DB_PATH.unlink()  # fresh db for a repeatable demo run
ensure_schema()


def run_attempt(agent_id, session_id, item, category, merchant, amount):
    decision = build_purchase_decision(agent_id, session_id, item, category, merchant, amount)
    record = dict(decision)
    record["anomaly_flags"] = json.dumps(decision["anomaly_flags"])
    record.pop("anomaly_details", None)
    insert_action(record)
    print(f"\n[{decision['status']}] {item} (${amount}, {category} @ {merchant})")
    print(f"  risk_score={decision['risk_score']}  reason={decision['reason']}")
    print(f"  -> {explain_decision(decision)}")
    return decision


if __name__ == "__main__":
    session = "sess_demo_1"
    agent = "alexa_agent_1"

    # 1. Normal, low-risk purchase -> should be OK
    run_attempt(agent, session, "USB-C cable", "electronics", "amazon_basics", 12.99)

    # 2. High-risk category + brand-new merchant -> should be HALTED
    d2 = run_attempt(agent, session, "Gift card bundle", "gift_card", "random-giftcard-site", 500.0)
    assert d2["status"] == "HALTED", "expected HALTED for gift_card category"

    # 3. A perfectly ordinary follow-up purchase in the SAME session -> should still
    #    inherit at least MONITOR because of the prior HALT (circuit-breaker propagation)
    d3 = run_attempt(agent, session, "Coffee", "subscription", "amazon_basics", 6.50)
    assert d3["status"] in ("MONITOR", "HALTED"), "expected inherited MONITOR from prior HALT in session"

    print("\nAll assertions passed — session-level circuit breaker propagation works.")
