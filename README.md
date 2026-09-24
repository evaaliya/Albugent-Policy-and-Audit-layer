# Albugent -> Alexa+ Purchase Guard

An Alexa+ agent-trust layer for autonomous purchases, ported from the Albugent data
governance engine, built strictly on Amazon's own MCP Toolkit for Alexa+
(developer.amazon.com/docs/alexaplus/add-ons/). Same architecture, same hard rule,
new domain:

> **The system that requests a risky action is never the system that approves it.**

In Albugent this was: the LLM/agent can call `apply_patch` only through a UI button,
never as a tool call. Here it becomes: **the Alexa+ agent has an MCP tool to *attempt*
a purchase, but no tool to *approve* one it halted.**

## Built on Amazon's own tooling, not a generic MCP stack

This project follows the Alexa+ MCP QuickStart Guide and MCP Design Guide for Alexa+
end to end, not just "an MCP server that happens to work":

- **Transport & spec**: Streamable HTTP, MCP spec 2025-11-25+ (Alexa+ MCP Toolkit's
  hard technical requirement -- the legacy SSE transport is not accepted).
- **Onboarding**: `addon-package/addon.json` (this repo includes one, schema per the
  QuickStart Guide) + the **Alexa AI CLI** -- `alexa-ai configure`, then either the
  Add-on Agent Skill or `alexa-ai new mcp` / `alexa-ai deploy` manually. This is how
  the MCP server actually gets registered with Alexa+; it is not something you can
  fake with your own web server.
- **Tool design**: every tool below follows the Design Guide's "Tools, Schema, and
  Data Design" rules -- one tool per customer intent, a description stating when/why
  to call it and what it returns, and "declare only what you honor" (see the
  `agent_id` note below).
- **Testing**: the guide-prescribed path is "Test in the Web Simulator" after
  `alexa-ai deploy`. `demo/simulate_session.py` is a stand-in generic MCP client for
  local development before you have simulator access; `demo/test_logic_offline.py`
  exercises the decision pipeline with no MCP transport at all.

### A correction the Design Guide forced

The guide is explicit: *"Declare only what you honor... A parameter the model can
send but your server silently ignores produces confidently wrong answers, since the
model trusts the schema and fills arguments based on it."* An earlier version of this
project had `attempt_purchase(agent_id, ...)` -- but `agent_id` isn't something Alexa+
can honestly know; it would have to invent it, and a bad-faith caller could pass any
agent_id it wants, quietly defeating the trust-score check in `risk_evaluator.py`.
Caller identity now comes from `mcp_server/utils/auth_context.py`, which reads it off
the authenticated request context (via FastMCP's `Context`), not from an
LLM-suppliable tool argument. Real identity verification needs Account Linking (OAuth
2.1 + PKCE S256) configured in the Amazon developer console -- see "Not yet done"
below.

### Corrections the Functional Requirements forced

Certification review (developer.amazon.com/docs/alexaplus/add-ons/functional-requirements.html)
surfaces a checklist, not just guidance. A few of its rules changed actual code here:

- **#13, MCP Tool Validation** -- *"Include common synonyms, abbreviations, and
  alternate spellings in your tool parameter descriptions and enums so variants
  resolve correctly."* `category` used to be free text matched by substring
  (`"gift_card" in category.lower()`), which would silently miss `"gift card"` (a
  space instead of an underscore) and quietly downgrade a High-severity purchase to
  Low. Fixed by making `category` a closed `Literal[...]` enum in the tool schema
  (`CATEGORY_VALUES` in `category_risk.py`) -- there's no longer a spelling for the
  model to get wrong, and severity lookup is now an exact match, not a guess.
- **#13** -- *"use the MCP error contract (isError: true or JSON-RPC errors) for
  failures rather than returning malformed payloads"* and *"gracefully handle
  unexpected or invalid parameters."* `get_audit_trail` used to return
  `{"error": "not found"}` as an ordinary successful result; it now raises, so FastMCP
  produces a proper MCP error response. `attempt_purchase` now validates `amount`,
  `item`, and `merchant` before doing anything, raising instead of silently scoring
  garbage input.
- **#8, Transaction Flow** -- *"Detect and prevent duplicate transactions"* and
  *"Deliver a receipt via at least one channel... after payment."* Neither existed
  before. `session_profiler.py` now flags a `duplicate_attempt` (same item/merchant/
  amount attempted twice in one session), which forces at least MONITOR through the
  existing anomaly-flag path. `mcp_server/utils/receipts.py` is a stub call site for
  the required post-purchase receipt -- it logs instead of actually sending one; wire
  in a real channel (transactional email, SMS, Alexa notifications) before
  certification.
- **#8** -- *"Require explicit confirmation with key details before any
  high-consequence action (payment, cancellation, deletion)"* is, almost word for
  word, the reason this whole project's HALT/Tier-2 design exists. Worth knowing this
  isn't just our own risk-management preference -- it's a certification requirement
  independent of this project.

## Two trust tiers

- **Tier 1 -- `mcp_server/`**: the MCP server Alexa+ actually talks to (Streamable
  HTTP). Exposes `attempt_purchase`, `get_session_status`, `get_audit_trail`. Nothing
  else.
- **Tier 2 -- `web_api/`**: a separate FastAPI service reachable only through an
  authenticated end-user channel (the Alexa companion app, in a real deployment). The
  only place a HALTED action can be approved or denied. Not an MCP tool, not listed in
  `addon.json`'s `integrations`, not reachable from the agent.

This maps onto something Amazon already ships: the Payments for Alexa+ guide
describes an Amazon Wallet consent flow where the customer "sees a message to scan a
QR code or check notifications in the Alexa app" before a charge completes -- the same
shape as our HALTED -> Tier 2 approval step. Wiring `resolve_pending_action` to an
actual charge (via `ChargePermissionId` / a partner-wallet checkout API) is future
work, described in "Implement Checkout Endpoints" -- out of scope for this MVP.

## File-by-file mapping from Albugent

| Albugent | Here |
|---|---|
| `pii_detector.py` | `mcp_server/utils/category_risk.py` -- keyword+severity pattern, now for purchase categories |
| `anomaly_profiler.py` | `mcp_server/utils/session_profiler.py` -- new-merchant / amount z-score / same-session frequency spike |
| `risk_evaluator.py` | `mcp_server/utils/risk_evaluator.py` -- `category_severity + anomalies + (1 - trust) * weight`, 0.65 threshold |
| `circuit_breaker.py` | `mcp_server/utils/circuit_breaker.py` -- HALT propagates through a session's chronological steps |
| `context_builder.py` | `mcp_server/utils/context_builder.py` -- one decision payload per purchase attempt |
| `agent.py`'s "LLM only writes prose from precomputed facts" | `mcp_server/utils/explain.py` -- deterministic for this MVP |
| `patch_applier.py` (`apply_patch`, UI-only) | `web_api/apply_resolution.py` (`resolve_pending_action`, Tier-2-only) |
| `mcp_server.py` (tool surface) | `mcp_server/server.py` |
| `db_utils.py` | `mcp_server/utils/db_utils.py` -- same sqlite helpers, over `data/actions_log.db` |
| `github_utils.py` | not ported -- approval must happen before the action, not async in a PR |
| `graph_engine.py` / `lineage_discoverer.py` | dropped -- "merchant centrality" wasn't a clear risk signal |

## Running it

### Local development / logic check (no Amazon account needed)

```bash
pip install -r requirements.txt
python demo/test_logic_offline.py        # decision pipeline, no transport involved
```

### Real MCP transport, generic client (before you have simulator access)

```bash
# terminal 1
python -m mcp_server.server        # Tier 1, Streamable HTTP, port 8000
# terminal 2
python -m web_api.resolve_action   # Tier 2, port 8010
# terminal 3
python demo/simulate_session.py
```

### The actual Alexa+ onboarding path

```bash
alexa-ai configure                 # LWA OAuth login, once
# expose mcp_server (port 8000) via a tunnel, e.g.:
cloudflared tunnel --url http://localhost:8000

# fill addon-package/addon.json: privacyPolicyUrl, termsOfUseUrl, mediaAssets,
# and integrations[0].config.endpoints.default.uri = your tunnel/deployed URL

alexa-ai deploy                    # registers the add-on, dev stage
# then: Test in the Web Simulator (developer.amazon.com/alexa/console/ask/addons)
```

### Pre-certification check: Local Inspector

Before relying on the web simulator, `@alexa-ai/addon-local-inspector` can hit this
server directly and produce a pass/fail `certification-verdict.json` against the
Functional Requirements checklist:

```bash
addon-local-inspector https://your-tunnel-or-deployed-url.example.com/mcp
```

This server returns data only (no `_meta.ui.resourceUri`), so only **data-layer
analysis** applies here -- no Playwright/visual-rendering setup needed. It checks tool
schemas, request/response payloads, and errors, which is exactly where the fixes in
"Corrections the Functional Requirements forced" above came from.

## What's intentionally NOT built yet

- **Account Linking / OAuth 2.1 + PKCE(S256)**: the MCP Toolkit Authentication
  checklist requires 401-without-`WWW-Authenticate` on unauthenticated requests, a
  Protected Resource Metadata document at the RFC 9728 well-known URI, and an
  `/.well-known/oauth-authorization-server` document. None of that is stubbed here --
  it's real infrastructure that belongs in your Amazon developer console setup, not
  something to fake in `mcp_server/server.py`. Until it exists,
  `resolve_agent_identity()` logs a loud warning and returns a placeholder.
- Real merchant execution after a Tier 2 approval, and the actual Alexa+ Checkout API
  integration (`ChargePermissionId` / partner wallet, per "Implement Checkout
  Endpoints") -- stubbed with a comment in `apply_resolution.py`.
- The compliance-digest PR flow from `github_utils.py`.

