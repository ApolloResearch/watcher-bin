"""Export an explicit Watcher occurrence-time window to an OTLP logs receiver."""

import asyncio
import os
from datetime import datetime

import httpx
import structlog
from watcher_opentelemetry import OtlpLogSink, export_window

from watcher_sdk import AsyncWatcherClient


async def main() -> None:
    """Use a local Collector by default; vendor credentials stay in Collector config."""
    async with (
        AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as watcher,
        httpx.AsyncClient(timeout=30, trust_env=False) as receiver,
    ):
        receipt = await export_window(
            watcher,
            OtlpLogSink(
                receiver,
                os.environ.get("OTLP_LOGS_ENDPOINT", "http://127.0.0.1:4318/v1/logs"),
                max_request_bytes=int(os.environ.get("WATCHER_EXPORT_MAX_REQUEST_BYTES", "900000")),
            ),
            start=datetime.fromisoformat(os.environ["WATCHER_EXPORT_START"]),
            end=datetime.fromisoformat(os.environ["WATCHER_EXPORT_END"]),
        )
    # log_safety: Aggregate export counts only; record IDs and source content are excluded.
    structlog.get_logger().info("watcher_logs_exported", records=receipt.records, batches=receipt.batches)


if __name__ == "__main__":
    asyncio.run(main())
