"""Export flagged session summaries, with full transcript content only when explicitly enabled."""

import asyncio
import os
from datetime import datetime

import httpx
import structlog
from watcher_google_security_operations import GoogleSecOpsSink, export_sessions

from watcher_sdk import AsyncWatcherClient


async def main() -> None:
    """Read explicit credentials only; emit aggregate acknowledgment counts."""
    content_setting = os.environ.get("WATCHER_EXPORT_INCLUDE_TRANSCRIPTS", "false").lower()
    if content_setting not in {"true", "false"}:
        raise ValueError("WATCHER_EXPORT_INCLUDE_TRANSCRIPTS must be true or false")
    include_transcripts = content_setting == "true"
    async with (
        AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as watcher,
        httpx.AsyncClient(timeout=30, trust_env=False) as destination,
    ):
        receipt = await export_sessions(
            watcher,
            GoogleSecOpsSink(
                destination,
                endpoint=os.environ["GOOGLE_SECOPS_ENDPOINT"],
                parent=os.environ["GOOGLE_SECOPS_PARENT"],
                access_token=os.environ["GOOGLE_SECOPS_ACCESS_TOKEN"],
            ),
            start=datetime.fromisoformat(os.environ["WATCHER_EXPORT_START"]),
            end=datetime.fromisoformat(os.environ["WATCHER_EXPORT_END"]),
            include_transcripts=include_transcripts,
        )
    structlog.get_logger().info(
        "watcher_decision_imports_acknowledged", records=receipt.records, batches=receipt.batches
    )


if __name__ == "__main__":
    asyncio.run(main())
