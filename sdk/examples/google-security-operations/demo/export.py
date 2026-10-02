"""Export an explicit Watcher time window with an operator-provided OAuth access token."""

import asyncio
import os
from datetime import datetime

import httpx
import structlog
from watcher_google_security_operations import GoogleSecOpsSink, export_window

from watcher_sdk import AsyncWatcherClient


async def main() -> None:
    """Read explicit credentials only; emit aggregate acknowledgment counts."""
    async with (
        AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as watcher,
        httpx.AsyncClient(timeout=30, trust_env=False) as destination,
    ):
        receipt = await export_window(
            watcher,
            GoogleSecOpsSink(
                destination,
                endpoint=os.environ["GOOGLE_SECOPS_ENDPOINT"],
                parent=os.environ["GOOGLE_SECOPS_PARENT"],
                access_token=os.environ["GOOGLE_SECOPS_ACCESS_TOKEN"],
            ),
            start=datetime.fromisoformat(os.environ["WATCHER_EXPORT_START"]),
            end=datetime.fromisoformat(os.environ["WATCHER_EXPORT_END"]),
        )
    structlog.get_logger().info(
        "watcher_decision_imports_acknowledged", records=receipt.records, batches=receipt.batches
    )


if __name__ == "__main__":
    asyncio.run(main())
