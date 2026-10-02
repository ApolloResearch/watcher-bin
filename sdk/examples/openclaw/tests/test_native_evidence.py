"""Native evidence preserves SQLite events and committed WAL pages unchanged."""

import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def evidence_module(tmp_path):
    helper = Path(__file__).parent / "native/contained/native_evidence.py"
    if not helper.exists():
        helper = Path(__file__).parent / "native_evidence.py"
    spec = importlib.util.spec_from_file_location("openclaw_native_evidence", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.EVIDENCE = tmp_path / "evidence"
    module.EVIDENCE.mkdir()
    return module


def test_retains_committed_wal_events_without_reencoding(evidence_module, tmp_path):
    state = tmp_path / "native"
    state.mkdir()
    database = state / "openclaw-agent.sqlite"
    writer = sqlite3.connect(database)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE transcript_events(session_id TEXT, seq INTEGER, event_json TEXT)")
        raw_events = [
            '{ "type":"message", "message":{"role":"user","content":"café"} }',
            '{"type":"message","message":{"role":"assistant","content":[{"type":"toolCall","id":"call-1","name":"exec","arguments":{"command":"true"}}]}}',
            '{"type":"message","message":{"role":"toolResult","toolCallId":"call-1","content":[{"type":"text","text":"done"}]}}',
        ]
        for sequence, event in enumerate(raw_events):
            writer.execute("INSERT INTO transcript_events VALUES (?, ?, ?)", ("native-session", sequence, event))
        writer.commit()
        original = {path.name: path.read_bytes() for path in state.iterdir()}
        assert original["openclaw-agent.sqlite-wal"]
        evidence_module.retain_transcripts([state])
        retained = evidence_module.EVIDENCE / "native-transcripts"
        manifest = json.loads((retained / "manifest.json").read_text())
        originals = [row for row in manifest if row["format"] == "native-sqlite-file"]
        assert len(originals) == len(original)
        for row in originals:
            assert (retained / row["retained"]).read_bytes() == original[Path(row["native_path"]).name]
        (snapshot,) = [row for row in manifest if row["format"] == "sqlite-backup"]
        assert [row["seq"] for row in snapshot["events"]] == [0, 1, 2]
        assert {row["session_id"] for row in snapshot["events"]} == {"native-session"}
        assert [(retained / row["retained"]).read_text() for row in snapshot["events"]] == raw_events
        for row in manifest + snapshot["events"]:
            assert hashlib.sha256((retained / row["retained"]).read_bytes()).hexdigest() == row["sha256"]
        with sqlite3.connect(retained / snapshot["retained"]) as copied:
            assert copied.execute(snapshot["query"]).fetchall() == [
                ("native-session", sequence, event) for sequence, event in enumerate(raw_events)
            ]
    finally:
        writer.close()


def test_empty_native_store_is_not_transcript_evidence(evidence_module, tmp_path):
    database = tmp_path / "openclaw-agent.sqlite"
    with sqlite3.connect(database) as writer:
        writer.execute("CREATE TABLE transcript_events(session_id TEXT, seq INTEGER, event_json TEXT)")
    with pytest.raises(AssertionError, match="no transcript events"):
        evidence_module.retain_transcripts([tmp_path])


def test_original_jsonl_and_symlink_handling_remain_exact(evidence_module, tmp_path):
    native = tmp_path / "native"
    native.mkdir()
    content = b'{"native": "bytes"}\n'
    (native / "events.jsonl").write_bytes(content)
    (native / "alias.jsonl").symlink_to(native / "events.jsonl")
    (native / "openclaw-agent.sqlite").symlink_to(native / "events.jsonl")
    evidence_module.retain_transcripts([native])
    retained = evidence_module.EVIDENCE / "native-transcripts"
    manifest = json.loads((retained / "manifest.json").read_text())
    assert len(manifest) == 1
    assert (retained / manifest[0]["retained"]).read_bytes() == content
