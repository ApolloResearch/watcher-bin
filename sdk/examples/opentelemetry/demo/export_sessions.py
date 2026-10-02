"""Export flagged session summaries, with full transcript content only when explicitly enabled."""

import asyncio
import os
from datetime import datetime

import httpx
import structlog
from watcher_opentelemetry import OtlpLogSink, export_sessions

from watcher_sdk import AsyncWatcherClient


async def main() -> None:
    """Use a local Collector by default; vendor credentials stay in Collector config."""
    content_setting = os.environ.get("WATCHER_EXPORT_INCLUDE_TRANSCRIPTS", "false").lower()
    if content_setting not in {"true", "false"}:
        raise ValueError("WATCHER_EXPORT_INCLUDE_TRANSCRIPTS must be true or false")
    include_transcripts = content_setting == "true"
    async with (
        AsyncWatcherClient(os.environ["WATCHER_URL"], api_key=os.environ["WATCHER_API_KEY"]) as watcher,
        httpx.AsyncClient(timeout=30, trust_env=False) as receiver,
    ):
        receipt = await export_sessions(
            watcher,
            OtlpLogSink(
                receiver,
                os.environ.get("OTLP_LOGS_ENDPOINT", "http://127.0.0.1:4318/v1/logs"),
                max_request_bytes=int(os.environ.get("WATCHER_EXPORT_MAX_REQUEST_BYTES", "900000")),
            ),
            start=datetime.fromisoformat(os.environ["WATCHER_EXPORT_START"]),
            end=datetime.fromisoformat(os.environ["WATCHER_EXPORT_END"]),
            include_transcripts=include_transcripts,
        )
    # log_safety: Aggregate export counts only; record IDs and source content are excluded.
    structlog.get_logger().info("watcher_snapshots_accepted", records=receipt.records, batches=receipt.batches)


if __name__ == "__main__":
    asyncio.run(main())
