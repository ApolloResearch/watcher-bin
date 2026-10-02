"""Public interfaces for Watcher decision and session export examples."""

from watcher_microsoft_sentinel.integration import LogsIngestionSink, encode_record, export_sessions, export_window
from watcher_microsoft_sentinel.snapshots import SessionSnapshot, fetch_session_snapshots
from watcher_microsoft_sentinel.source import DecisionRecord, ExportError, ExportReceipt, fetch_records

__all__ = [
    "SessionSnapshot",
    "fetch_session_snapshots",
    "DecisionRecord",
    "ExportError",
    "ExportReceipt",
    "fetch_records",
    "LogsIngestionSink",
    "export_sessions",
    "export_window",
    "encode_record",
]
