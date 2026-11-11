-- Run in LiteLLM's database before starting gateway replicas. Safe to repeat.
-- Stores account-scoped aliases, native IDs and prompt digests; no text or credentials.
CREATE TABLE IF NOT EXISTS watcher_copilot_tasks (
    root_id text NOT NULL,
    task_id uuid NOT NULL,
    parent_id uuid,
    external_id text NOT NULL,
    PRIMARY KEY (root_id, task_id),
    FOREIGN KEY (root_id, parent_id) REFERENCES watcher_copilot_tasks (root_id, task_id),
    CHECK (parent_id IS DISTINCT FROM task_id)
);

ALTER TABLE watcher_copilot_tasks ADD COLUMN IF NOT EXISTS prompt_digest bytea;
ALTER TABLE watcher_copilot_tasks ADD COLUMN IF NOT EXISTS spawning_tool_use_id text;

CREATE TABLE IF NOT EXISTS watcher_copilot_spawn_calls (
    root_id text NOT NULL,
    parent_id uuid NOT NULL,
    tool_use_id text NOT NULL,
    prompt_digest bytea NOT NULL,
    PRIMARY KEY (root_id, parent_id, tool_use_id),
    FOREIGN KEY (root_id, parent_id) REFERENCES watcher_copilot_tasks (root_id, task_id)
);
CREATE INDEX IF NOT EXISTS watcher_copilot_spawn_prompt
    ON watcher_copilot_spawn_calls (root_id, parent_id, prompt_digest);

ALTER TABLE watcher_copilot_tasks ADD COLUMN IF NOT EXISTS correlation_safe boolean NOT NULL DEFAULT false;

-- Registrations that update external_id do not record every spawning call.
-- Preserve their existing links, but stop assigning new ones.
CREATE OR REPLACE FUNCTION watcher_copilot_disable_correlation() RETURNS trigger AS $$
BEGIN
    NEW.correlation_safe := false;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS watcher_copilot_legacy_registration ON watcher_copilot_tasks;
CREATE TRIGGER watcher_copilot_legacy_registration
    BEFORE UPDATE OF external_id ON watcher_copilot_tasks
    FOR EACH ROW EXECUTE FUNCTION watcher_copilot_disable_correlation();
