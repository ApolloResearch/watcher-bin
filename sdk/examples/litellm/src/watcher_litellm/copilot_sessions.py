"""Durable mapping from Copilot task IDs to Watcher conversations.

The root task changes when Copilot resumes, so task IDs cannot identify the
root conversation. Register every task before inference using the shared
LiteLLM PostgreSQL database. Root tasks map to the session UUID; children map
to their own task UUID. Both are scoped to the authenticated account.
Synchronous children carry no spawning call ID, so matching uses a SHA-256
digest of the exact task prompt, scoped to its root and parent task. The map
retains digests, opaque IDs and matching state, never prompt text or credentials.
Duplicate prompts remain unlinked; no arrival-order inference is used. New
children of parent tasks handled by a replica that does not record spawning
calls also remain unlinked.
Apply the shipped SQL migration separately before starting gateway replicas.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

import asyncpg
from fastapi import HTTPException
from litellm.proxy._types import UserAPIKeyAuth
from pydantic import BaseModel, Field, JsonValue, ValidationError

from watcher_litellm.proxy_auth import account_session
from watcher_sdk import AsyncWatcherClient
from watcher_sdk._generated.models import AgentRelationshipRequest

if TYPE_CHECKING:
    from watcher_litellm.replan import ToolCall


class _TaskArguments(BaseModel):
    prompt: str = Field(strict=True)


class SpawningCall(BaseModel):
    """A parent's task call, retaining only its ID and exact prompt digest."""

    tool_use_id: str
    prompt_digest: bytes


def spawning_calls(calls: Sequence[ToolCall]) -> list[SpawningCall]:
    """Extract normalized task calls whose exact prompt can identify a child."""
    candidates: list[SpawningCall] = []
    for call in calls:
        if call.tool_name != "task":
            continue
        try:
            arguments = _TaskArguments.model_validate(call.tool_input)
        except ValidationError:
            continue
        candidates.append(
            SpawningCall(tool_use_id=call.tool_use_id, prompt_digest=hashlib.sha256(arguments.prompt.encode()).digest())
        )
    return candidates


def child_prompt_digest(body: dict[str, JsonValue]) -> bytes | None:
    """Match only the first user message with Copilot's exact timestamp wrapper.

    Unknown wrappers, multiple content blocks and missing messages remain
    unlinked. The timestamp is validated and removed; prompt whitespace stays
    significant. Later user messages cannot change a child's original identity.
    """
    items = body.get("input") if "input" in body else body.get("messages")
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, list) and len(content) == 1:
            block = content[0]
            content = (
                block.get("text") if isinstance(block, dict) and block.get("type") in {"input_text", "text"} else None
            )
        if not isinstance(content, str):
            return None
        match = re.fullmatch(r"<current_datetime>([^<>\r\n]+)</current_datetime>\n\n([\s\S]*)", content)
        if match is None:
            return None
        try:
            timestamp = datetime.fromisoformat(match[1])
        except ValueError:
            return None
        if timestamp.tzinfo is None:
            return None
        return hashlib.sha256(match[2].encode()).digest()
    return None


class Conversation(BaseModel):
    """One registered task's account-scoped alias and its parent's alias, if any."""

    external_id: str
    parent_external_id: str | None
    root_id: str | None = Field(default=None, repr=False, exclude=True)
    task_id: UUID | None = Field(default=None, repr=False, exclude=True)

    async def record_spawning_calls(self, calls: Sequence[ToolCall]) -> None:
        """Persist task candidates before releasing their calls to Copilot.

        All candidates in an exchange commit together, so duplicate prompts
        cannot acquire a link merely because one call was inserted first.
        Repeated call IDs must retain the same prompt digest.
        """
        candidates = spawning_calls(calls)
        if not candidates or self.root_id is None or self.task_id is None:
            return
        async with database() as connection, connection.transaction():
            for call in candidates:
                stored = await connection.fetchval(
                    """INSERT INTO watcher_copilot_spawn_calls (root_id, parent_id, tool_use_id, prompt_digest)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (root_id, parent_id, tool_use_id) DO UPDATE
                    SET tool_use_id=watcher_copilot_spawn_calls.tool_use_id
                    WHERE watcher_copilot_spawn_calls.prompt_digest=EXCLUDED.prompt_digest
                    RETURNING tool_use_id""",
                    self.root_id,
                    self.task_id,
                    call.tool_use_id,
                    call.prompt_digest,
                )
                if stored is None:
                    raise HTTPException(409, "Copilot spawning call changed")

    async def spawning_tool_use_id(self) -> str | None:
        """Assign a unique exact-prompt match once, shared across gateway replicas.

        The parent task scopes matching across resume. A missing or duplicate
        prompt leaves the current parent-only relationship intact. Once assigned,
        the call ID is immutable, including when a later task repeats its prompt.
        """
        if self.parent_external_id is None or self.root_id is None or self.task_id is None:
            return None
        async with database() as connection, connection.transaction():
            await connection.execute(
                """UPDATE watcher_copilot_tasks AS child SET spawning_tool_use_id=candidate.tool_use_id
                FROM (
                    SELECT min(spawn.tool_use_id) AS tool_use_id
                    FROM watcher_copilot_tasks AS task
                    JOIN watcher_copilot_tasks AS parent ON parent.root_id=task.root_id
                        AND parent.task_id=task.parent_id AND parent.correlation_safe
                    JOIN watcher_copilot_spawn_calls AS spawn ON spawn.root_id=task.root_id
                        AND spawn.parent_id=task.parent_id AND spawn.prompt_digest=task.prompt_digest
                    WHERE task.root_id=$1 AND task.task_id=$2 AND task.spawning_tool_use_id IS NULL
                    HAVING count(*)=1
                ) AS candidate
                WHERE child.root_id=$1 AND child.task_id=$2 AND child.spawning_tool_use_id IS NULL""",
                self.root_id,
                self.task_id,
            )
            return await connection.fetchval(
                "SELECT spawning_tool_use_id FROM watcher_copilot_tasks WHERE root_id=$1 AND task_id=$2",
                self.root_id,
                self.task_id,
            )

    async def link(self, client: AsyncWatcherClient) -> None:
        """Link a child and retry its spawning ID until Watcher records the call.

        Raw hooks record after replying. The existing 30-second bound covers
        both session discovery and spawning-message retries. Once the parent
        relationship exists, expiry leaves its known call ID for a later request
        to retry. Errors before that point still prevent releasing the child.
        """
        if self.parent_external_id is None:
            return
        is_linked = False
        try:
            async with asyncio.timeout(30):
                delay = 0.1
                spawning_id = await self.spawning_tool_use_id()
                while True:
                    children = await client.search_sessions(external_ids={"other": [self.external_id]}, limit=2)
                    parents = await client.search_sessions(external_ids={"other": [self.parent_external_id]}, limit=2)
                    if children.total > 1 or parents.total > 1:
                        raise HTTPException(409, "Copilot conversation mapping is ambiguous")
                    if children.sessions and parents.sessions:
                        relationship = await client.put_agent_relationship(
                            child_session_id=children.sessions[0].session_id,
                            relationship=AgentRelationshipRequest(
                                parent_session_id=UUID(parents.sessions[0].session_id),
                                spawning_tool_use_id=spawning_id,
                            ),
                        )
                        is_linked = True
                        if spawning_id is None or (
                            isinstance(relationship.spawning_message_trajectory_hash, str)
                            and relationship.spawning_message_trajectory_hash
                        ):
                            return
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 1)
        except TimeoutError:
            if not is_linked:
                raise


@asynccontextmanager
async def database() -> AsyncIterator[asyncpg.Connection]:
    """Use the gateway's PostgreSQL database; never the Watcher database."""
    connection = await asyncpg.connect(os.environ["DATABASE_URL"], timeout=10)
    try:
        yield connection
    finally:
        await connection.close()


async def register_task(
    user: UserAPIKeyAuth,
    session_id: UUID,
    task_id: UUID,
    parent_id: UUID | None,
    body: dict[str, JsonValue] | None = None,
) -> Conversation:
    """Register before generation, refusing conflicting or unknown ancestry.

    A parent must have begun its request before it can spawn a child. Resume
    registers new root task IDs against the same session alias. Repeated calls
    can only retain their original ancestry, including across replicas. Keep the
    conflict update on prompt_digest: the schema treats external_id updates as
    registrations from replicas that cannot record spawning calls.
    """
    root = account_session(user, json.dumps(["copilot", str(session_id)]))
    external_id = (
        root if parent_id is None else account_session(user, json.dumps(["copilot", str(session_id), str(task_id)]))
    )
    async with database() as connection, connection.transaction():
        parent_external_id = None
        if parent_id is not None:
            parent_external_id = await connection.fetchval(
                "SELECT external_id FROM watcher_copilot_tasks WHERE root_id=$1 AND task_id=$2",
                root,
                parent_id,
            )
            if parent_external_id is None:
                raise HTTPException(409, "Copilot parent task is unknown; start the parent through this gateway")
        stored = await connection.fetchval(
            """INSERT INTO watcher_copilot_tasks (root_id, task_id, parent_id, external_id, prompt_digest, correlation_safe)
            VALUES ($1, $2, $3, $4, $5, true)
            ON CONFLICT (root_id, task_id) DO UPDATE SET prompt_digest=watcher_copilot_tasks.prompt_digest
            WHERE watcher_copilot_tasks.parent_id IS NOT DISTINCT FROM EXCLUDED.parent_id
            RETURNING external_id""",
            root,
            task_id,
            parent_id,
            external_id,
            child_prompt_digest(body) if parent_id is not None and body is not None else None,
        )
        if stored is None:
            raise HTTPException(409, "Copilot task ancestry changed")
    return Conversation(external_id=stored, parent_external_id=parent_external_id, root_id=root, task_id=task_id)
