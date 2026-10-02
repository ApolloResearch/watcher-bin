"""Import one explicitly selected Enterprise chat or session; see the example README."""

import asyncio
import os
from pathlib import Path
from typing import cast

import httpx
import structlog
from watcher_claude_compliance import ComplianceClient, import_conversation
from watcher_claude_compliance.integration import Family

from watcher_sdk import AsyncWatcherClient


async def main() -> None:
    """Use separate source/destination keys; emit counts without transcript content."""
    family = os.environ["CLAUDE_COMPLIANCE_FAMILY"]
    if family not in ("chats", "local", "remote"):
        raise ValueError("CLAUDE_COMPLIANCE_FAMILY must be chats, local or remote")
    async with (
        httpx.AsyncClient(
            base_url="https://api.anthropic.com",
            headers={
                "x-api-key": os.environ["ANTHROPIC_COMPLIANCE_ACCESS_KEY"],
                "anthropic-version": "2023-06-01",
            },
            timeout=30,
            trust_env=False,
        ) as source_http,
        AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as watcher,
    ):
        receipt = await import_conversation(
            ComplianceClient(source_http),
            watcher,
            family=cast(Family, family),
            conversation_id=os.environ["CLAUDE_COMPLIANCE_ID"],
            receipt_path=Path(os.environ.get("COMPLIANCE_RECEIPT", "import-receipt.json")),
        )
    # log_safety: Counts only; source transcript, identity and credentials are excluded.
    structlog.get_logger().info(
        "compliance_import_submitted", message_count=receipt.message_count, limitations=len(receipt.limitations)
    )


if __name__ == "__main__":
    asyncio.run(main())
