"""Install the native Copilot task mapping in the gateway's PostgreSQL database.

Run ``watcher-litellm-copilot-migrate`` once before the gateway replicas start.
``DATABASE_URL`` must name the LiteLLM database, never Watcher's. The migration
stores conversation IDs, native task UUIDs and exact-prompt digests, and is safe
to rerun. Prompt text and credentials are never stored.
LiteLLM's own schema migration is a separate prerequisite.
"""

import asyncio
from importlib.resources import files

from watcher_litellm.copilot_sessions import database


async def migrate() -> None:
    """Create the mapping tables transactionally; propagate connection/schema errors."""
    async with database() as connection, connection.transaction():
        await connection.execute(files("watcher_litellm").joinpath("copilot-schema.sql").read_text())


def main() -> None:
    """Console entry point for the deployment's separate migration job."""
    asyncio.run(migrate())
