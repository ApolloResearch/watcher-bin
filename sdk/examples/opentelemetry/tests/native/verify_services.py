"""Prove indexed decision fields in real loopback-only Loki or OpenSearch services.

The services runner shares a network-disabled container namespace with the
selected service. Fixtures contain no customer data or credentials. OpenSearch
uses Data Prepper's actual protobuf decoder and sink; this is not an AWS test.
"""

import asyncio
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import UUID

import httpx
from watcher_opentelemetry import DecisionRecord, OtlpLogSink, export_window, fetch_records

from watcher_sdk import AsyncWatcherClient


async def export_actual_source(client: httpx.AsyncClient, output: Path) -> DecisionRecord:
    """Seed one denied tool through the public hook and export its actual stored row.

    The parent fixture owns the isolated Watcher API, policy and database. This
    branch never runs against a hosted account: WATCHER_URL is the native test
    relay on container loopback, and the input is a synthetic local test case.
    """
    case = json.loads((output / "input.json").read_text())
    start = datetime.now(UTC) - timedelta(seconds=1)
    arguments = {"file_path": "fixture.txt", "content": case["token"]}
    messages = [
        {"role": "user", "content": case["token"]},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": case["call_id"], "type": "function", "function": "Write", "arguments": arguments}],
        },
    ]
    async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key", max_retries=0) as watcher:
        outcome = await watcher.pre_tool_use_hook(
            {"tool_name": "Write", "tool_input": arguments, "tool_use_id": case["call_id"]},
            messages=messages,
            external_ids={"other": "destination-fixture:" + case["call_id"]},
        )
        assert outcome.to_dict()["decision"] == "deny", outcome.to_dict()
        (output / "seed-decision.json").write_text(json.dumps(outcome.to_dict(), indent=2))
        deadline = time.monotonic() + 20
        while True:
            page = await watcher.search_tool_calls(start_date=start, end_date=datetime.now(UTC), limit=200)
            rows = [item.to_dict() for item in page.tool_calls]
            (output / "source-tool-calls.json").write_text(json.dumps(rows, indent=2))
            if len(rows) == 1 and rows[0]["tool_use_id"] == case["call_id"]:
                break
            assert time.monotonic() < deadline, "Seeded decision did not become readable"
            await asyncio.sleep(0.1)
        end = datetime.now(UTC) + timedelta(seconds=1)
        records = await fetch_records(watcher, start=start, end=end)
        assert len(records) == 1
        record = records[0]
        assert record.decision_category == "auto_denied" and record.severity_score == 9
        receipt = await export_window(
            watcher, OtlpLogSink(client, "http://127.0.0.1:4318/v1/logs"), start=start, end=end
        )
        assert receipt.records == 1 and receipt.batches == 1
        (output / "export-receipt.json").write_text(receipt.model_dump_json(indent=2))
        (output / "watcher-source.json").write_text(json.dumps(rows[0], indent=2))
        return record


async def main(destination: str) -> None:
    """Export one current decision through the shipped Collector config and query it."""
    assert {name for _, name in socket.if_nameindex()} == {"lo"}
    output = Path("/evidence")
    output.mkdir(exist_ok=True)
    (output / "collector-version.txt").write_text(subprocess.check_output(["otelcol-contrib", "--version"], text=True))
    collector = shutil.which("otelcol-contrib")
    assert collector is not None
    (output / "collector-binary-sha256.txt").write_text(hashlib.sha256(Path(collector).read_bytes()).hexdigest() + "\n")
    environment = {
        "PATH": os.environ["PATH"],
        "HOME": "/tmp/collector-home",
        "LOKI_OTLP_ENDPOINT": "http://127.0.0.1:3100/otlp",
        "DATA_PREPPER_LOGS_ENDPOINT": "http://127.0.0.1:21892/watcher/v1/logs",
    }
    config = "loki" if destination == "loki" else "dataprepper"
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        ready = "http://127.0.0.1:3100/ready" if destination == "loki" else "http://127.0.0.1:9200/_cluster/health"
        deadline = time.monotonic() + 180
        while True:
            try:
                response = await client.get(ready)
                if response.status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError(f"{destination} service did not become ready")
            await asyncio.sleep(1)
        version_url = (
            "http://127.0.0.1:3100/loki/api/v1/status/buildinfo" if destination == "loki" else "http://127.0.0.1:9200/"
        )
        version_response = await client.get(version_url)
        version_response.raise_for_status()
        (output / "destination-version.json").write_text(version_response.text + "\n")
        if destination != "loki":
            while True:
                try:
                    response = await client.get("http://127.0.0.1:21892/watcher/v1/logs")
                    break
                except httpx.TransportError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Data Prepper did not become ready") from None
                    await asyncio.sleep(1)
        with (output / "collector.log").open("w") as log:
            process = subprocess.Popen(
                ["otelcol-contrib", "--config", f"config/collector-{config}.yaml"],
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 20
                while True:
                    try:
                        await client.get("http://127.0.0.1:4318/")
                        break
                    except httpx.TransportError:
                        if process.poll() is not None or time.monotonic() >= deadline:
                            raise RuntimeError("Collector did not start") from None
                        await asyncio.sleep(0.1)
                now = datetime.now(UTC)
                if os.environ.get("WATCHER_OTLP_REAL_SOURCE") == "1":
                    record = await export_actual_source(client, output)
                else:
                    record = DecisionRecord(
                        tool_call_id=UUID(int=101),
                        session_id=UUID(int=102),
                        occurred_at=now,
                        severity_score=7,
                        coverage_state="decided",
                        decision_category="auto_denied",
                        content_state="scrubbed",
                    )
                    source_requests = []
                    source_row = record.model_dump(mode="json") | {
                        "tool_name": "private_fixture_tool",
                        "tool_input_preview": "PRIVATE_FIXTURE_ARGUMENTS",
                        "user_email": "private-fixture@example.invalid",
                    }

                    class WatcherSource(BaseHTTPRequestHandler):
                        def do_POST(self) -> None:
                            assert self.path == "/v1/tool-calls/search"
                            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                            source_requests.append(request)
                            assert request["offset"] == 0
                            payload = json.dumps(
                                {
                                    "tool_calls": [source_row],
                                    "total": 1,
                                    "offset": 0,
                                    "limit": request["limit"],
                                }
                            ).encode()
                            self.send_response(200)
                            self.send_header("Content-Type", "application/json")
                            self.send_header("Content-Length", str(len(payload)))
                            self.end_headers()
                            self.wfile.write(payload)

                        def log_message(self, format: str, *args: object) -> None:
                            pass

                    source = ThreadingHTTPServer(("127.0.0.1", 0), WatcherSource)
                    source_thread = threading.Thread(target=source.serve_forever, daemon=True)
                    source_thread.start()
                    source_url = f"http://127.0.0.1:{source.server_port}"
                    try:
                        async with AsyncWatcherClient(
                            source_url,
                            api_key="fixture-only",
                            max_retries=0,
                            httpx_client=httpx.AsyncClient(base_url=source_url, trust_env=False),
                        ) as watcher:
                            receipt = await export_window(
                                watcher,
                                OtlpLogSink(client, "http://127.0.0.1:4318/v1/logs"),
                                start=now - timedelta(minutes=1),
                                end=now + timedelta(minutes=1),
                            )
                            assert receipt.records == 1 and receipt.batches == 1
                        assert len(source_requests) == 1
                        (output / "watcher-source.json").write_text(json.dumps(source_row, indent=2) + "\n")
                        (output / "watcher-requests.json").write_text(json.dumps(source_requests, indent=2) + "\n")
                    finally:
                        source.shutdown()
                        source.server_close()
                        source_thread.join(timeout=5)
                deadline = time.monotonic() + 60
                while True:
                    if destination == "loki":
                        response = await client.get(
                            "http://127.0.0.1:3100/loki/api/v1/query_range",
                            params={
                                "query": '{service_name="watcher-decisions"}',
                                "start": (now - timedelta(minutes=1)).isoformat(),
                                "end": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
                            },
                        )
                        response.raise_for_status()
                        result = response.json()
                        (output / "indexed-result.json").write_text(json.dumps(result, indent=2) + "\n")
                        records = result["data"]["result"]
                        if records:
                            assert len(records) == 1
                            stream = records[0]
                            assert stream["stream"]["service_name"] == "watcher-decisions"
                            assert stream["stream"]["watcher_tool_call_id"] == str(record.tool_call_id)
                            assert stream["stream"]["watcher_session_id"] == str(record.session_id)
                            assert stream["stream"]["watcher_content_state"] == record.content_state
                            assert stream["stream"]["watcher_coverage_state"] == record.coverage_state
                            assert stream["stream"]["watcher_decision_category"] == record.decision_category
                            assert stream["stream"]["watcher_severity_score"] == str(record.severity_score)
                            assert stream["values"][0][1] == "Watcher recorded a tool-call decision."
                            labels = (await client.get("http://127.0.0.1:3100/loki/api/v1/labels")).json()
                            assert "watcher_tool_call_id" not in labels["data"]
                            (output / "index-labels.json").write_text(json.dumps(labels, indent=2) + "\n")
                            break
                    else:
                        await client.post("http://127.0.0.1:9200/watcher-decisions/_refresh")
                        response = await client.get("http://127.0.0.1:9200/watcher-decisions/_search")
                        if response.status_code == 200:
                            result = response.json()
                            (output / "indexed-result.json").write_text(json.dumps(result, indent=2) + "\n")
                            hits = result["hits"]["hits"]
                            if hits:
                                assert len(hits) == 1
                                document = hits[0]["_source"]
                                assert document["body"] == "Watcher recorded a tool-call decision."
                                assert document["log.attributes.watcher@tool_call_id"] == str(record.tool_call_id)
                                assert document["log.attributes.watcher@session_id"] == str(record.session_id)
                                assert document["log.attributes.watcher@content_state"] == record.content_state
                                assert document["log.attributes.watcher@coverage_state"] == record.coverage_state
                                assert document["log.attributes.watcher@decision_category"] == record.decision_category
                                assert document["log.attributes.watcher@severity_score"] == record.severity_score
                                break
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Decision was acknowledged but not indexed within the fixture deadline")
                    await asyncio.sleep(1)
                (output / "indexed-result.json").write_text(json.dumps(result, indent=2) + "\n")
                assert "PRIVATE_FIXTURE_ARGUMENTS" not in json.dumps(result)
                if os.environ.get("WATCHER_OTLP_REAL_SOURCE") == "1":
                    assert json.loads((output / "input.json").read_text())["token"] not in json.dumps(result)
                assert "private-fixture@example.invalid" not in json.dumps(result)
                assert "private_fixture_tool" not in json.dumps(result)
                (output / "result.json").write_text(
                    json.dumps(
                        {
                            "destination": destination,
                            "indexed_records": 1,
                            "external_network": False,
                            "hosted_account": False,
                            "watcher_source": "local-api"
                            if os.environ.get("WATCHER_OTLP_REAL_SOURCE") == "1"
                            else "fixture-http",
                            "tool_call_id": str(record.tool_call_id),
                        },
                        indent=2,
                    )
                    + "\n"
                )
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
