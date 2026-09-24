-- actions_log.db schema
-- Analog of the "dataset" in Albugent is now a single append-only actions log,
-- scoped per (agent_id, session_id) instead of per SQLite table.

CREATE TABLE IF NOT EXISTS agent_trust (
    agent_id        TEXT PRIMARY KEY,
    trust_score     REAL NOT NULL DEFAULT 0.5,   -- 0.0 (untrusted) .. 1.0 (fully trusted)
    approved_count  INTEGER NOT NULL DEFAULT 0,
    denied_count    INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS actions (
    action_id       TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    agent_id        TEXT NOT NULL,
    item            TEXT,
    category        TEXT,
    merchant        TEXT,
    amount          REAL,
    created_at      TEXT NOT NULL,
    -- risk evaluation output
    risk_score      REAL,
    category_severity TEXT,
    anomaly_flags   TEXT,     -- JSON list, e.g. ["new_merchant", "amount_spike"]
    status          TEXT NOT NULL,   -- OK | MONITOR | HALTED
    reason          TEXT,
    -- Tier 2 resolution (NULL until a human resolves a HALTED action)
    resolution      TEXT,     -- APPROVED | DENIED | NULL
    resolved_at     TEXT,
    resolved_by     TEXT      -- user id, never an agent id
);

CREATE INDEX IF NOT EXISTS idx_actions_session ON actions(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_actions_agent   ON actions(agent_id, merchant);
