"""Export an explicit finite Watcher decision window using configured credentials."""

import asyncio
import os
from datetime import datetime

import httpx
import structlog
from watcher_microsoft_sentinel import LogsIngestionSink, export_window

from watcher_sdk import AsyncWatcherClient


async def main() -> None:
    """Use only explicit environment settings; report aggregate accepted-record counts."""
    async with (
        AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as watcher,
        httpx.AsyncClient(timeout=30, trust_env=False) as http,
    ):
        sink = LogsIngestionSink(
            http,
            os.environ["AZURE_LOGS_ENDPOINT"],
            os.environ["AZURE_MONITOR_TOKEN"],
            rule_id=os.environ["AZURE_DCR_IMMUTABLE_ID"],
            stream=os.environ.get("AZURE_DCR_STREAM", "Custom-WatcherDecisions"),
        )
        receipt = await export_window(
            watcher,
            sink,
            start=datetime.fromisoformat(os.environ["WATCHER_EXPORT_START"]),
            end=datetime.fromisoformat(os.environ["WATCHER_EXPORT_END"]),
        )
    # log_safety: Aggregate counts only; no record IDs, destination credentials or content.
    structlog.get_logger().info("watcher_decisions_accepted", records=receipt.records, batches=receipt.batches)


if __name__ == "__main__":
    asyncio.run(main())
