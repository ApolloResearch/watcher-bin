"""Exercise shipped Collector configurations against local vendor protocol fixtures.

Run inside the network-disabled native-test container. Real Collector requests
are decoded, AWS signatures are independently checked with fixture credentials,
and raw request/response receipts are retained. These checks do not authenticate
to hosted accounts, prove vendor indexing, or exercise a production IAM policy.
"""

import asyncio
import gzip
import hashlib
import hmac
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path
from uuid import UUID

import httpx
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest, ExportLogsServiceResponse
from watcher_opentelemetry import DecisionRecord, OtlpLogSink

DESTINATIONS = {
    "grafana": ("/otlp/v1/logs", "authorization", "Basic fixture-only"),
    "loki": ("/otlp/v1/logs", None, None),
    "datadog": ("/v1/logs", "dd-api-key", "fixture-only"),
    "elastic": ("/v1/logs", "authorization", "ApiKey fixture-only"),
    "newrelic": ("/v1/logs", "api-key", "fixture-only"),
    "dynatrace": ("/api/v2/otlp/v1/logs", "authorization", "Api-Token fixture-only"),
    "cloudwatch": ("/v1/logs", None, None),
    "opensearch": ("/watcher/v1/logs", None, None),
    "dataprepper": ("/watcher/v1/logs", None, None),
}


def verify_sigv4(headers: dict[str, str], path: str, payload: bytes, service: str) -> None:
    """Validate the real Collector's AWS signature without any AWS connection.

    The fixture independently reconstructs the canonical request and signing key.
    A syntactically plausible Authorization header alone is insufficient proof.
    """
    algorithm, authorization = headers["authorization"].split(" ", 1)
    assert algorithm == "AWS4-HMAC-SHA256"
    fields = dict(part.strip().split("=", 1) for part in authorization.split(","))
    credential = fields["Credential"].split("/")
    assert credential[0] == "fixture-access-key"
    assert credential[2:] == ["us-east-1", service, "aws4_request"]
    assert headers["x-amz-security-token"] == "fixture-session-token"
    signed = fields["SignedHeaders"].split(";")
    canonical_headers = "".join(f"{name}:{' '.join(headers[name].split())}\n" for name in signed)
    canonical = "\n".join(
        ["POST", path, "", canonical_headers, fields["SignedHeaders"], hashlib.sha256(payload).hexdigest()]
    )
    scope = "/".join(credential[1:])
    to_sign = "\n".join([algorithm, headers["x-amz-date"], scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = b"AWS4fixture-secret-key"
    for part in credential[1:]:
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    expected = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    assert hmac.compare_digest(fields["Signature"], expected)


async def verify(config: Path, output: Path, scenario: str = "accepted") -> None:
    """Check forwarding plus one destination response, retaining every HTTP attempt."""
    destination_name = config.stem.removeprefix("collector-")
    case = f"{destination_name}-{scenario}"
    received: queue.Queue[dict[str, object]] = queue.Queue()
    captures: list[dict[str, object]] = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            payload = gzip.decompress(raw) if self.headers.get("Content-Encoding") == "gzip" else raw
            request = ExportLogsServiceRequest.FromString(payload)
            headers = {name.lower(): value for name, value in self.headers.items()}
            number = len(captures) + 1
            status = 503 if scenario == "retry" and number == 1 else 200
            if scenario == "unauthorized":
                status = 401
            if scenario == "oversized":
                status = 413
            reply = ExportLogsServiceResponse()
            if scenario == "partial":
                reply.partial_success.rejected_log_records = 1
                reply.partial_success.error_message = "fixture rejects this one log"
            response = reply.SerializeToString() if status == 200 else b"fixture rejection"
            capture = {
                "path": self.path,
                "headers": headers,
                "request_bytes": len(payload),
                "request_sha256": hashlib.sha256(payload).hexdigest(),
                "response_status": status,
                "response_hex": response.hex(),
            }
            captures.append(capture)
            (output / f"{case}-{number}.pb").write_bytes(payload)
            received.put({"capture": capture, "request": request})
            self.send_response(status)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", str(len(response)))
            if status == 503:
                self.send_header("Retry-After", "0")
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    destination = f"http://127.0.0.1:{server.server_port}"
    environment = {
        "PATH": os.environ["PATH"],
        "HOME": str(output),
        "GRAFANA_OTLP_ENDPOINT": destination + "/otlp",
        "GRAFANA_OTLP_AUTHORIZATION": "Basic fixture-only",
        "LOKI_OTLP_ENDPOINT": destination + "/otlp",
        "DATADOG_OTLP_LOGS_ENDPOINT": destination + "/v1/logs",
        "DD_API_KEY": "fixture-only",
        "ELASTIC_OTLP_ENDPOINT": destination,
        "ELASTIC_API_KEY": "fixture-only",
        "NEW_RELIC_OTLP_ENDPOINT": destination,
        "NEW_RELIC_LICENSE_KEY": "fixture-only",
        "DYNATRACE_OTLP_LOGS_ENDPOINT": destination + "/api/v2/otlp/v1/logs",
        "DYNATRACE_AUTHORIZATION": "Api-Token fixture-only",
        "CLOUDWATCH_OTLP_LOGS_ENDPOINT": destination + "/v1/logs",
        "CLOUDWATCH_LOG_GROUP": "watcher-fixture",
        "CLOUDWATCH_LOG_STREAM": "decisions",
        "OPENSEARCH_INGESTION_LOGS_ENDPOINT": destination + "/watcher/v1/logs",
        "DATA_PREPPER_LOGS_ENDPOINT": destination + "/watcher/v1/logs",
        "AWS_REGION": "us-east-1",
        "AWS_ACCESS_KEY_ID": "fixture-access-key",
        "AWS_SECRET_ACCESS_KEY": "fixture-secret-key",
        "AWS_SESSION_TOKEN": "fixture-session-token",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_CONFIG_FILE": "/dev/null",
        "AWS_SHARED_CREDENTIALS_FILE": "/dev/null",
    }
    if scenario == "unset-credential":
        del environment["DD_API_KEY"]
    logfile = output / f"{case}.log"
    outcome = "accepted by collector"
    upstream_status = 200
    with logfile.open("w") as log:
        process = subprocess.Popen(
            ["otelcol-contrib", "--config", str(config)], env=environment, stdout=log, stderr=subprocess.STDOUT
        )
        try:
            async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
                deadline = time.monotonic() + 20
                while True:
                    if process.poll() is not None:
                        raise RuntimeError(f"Collector exited during startup; inspect {logfile.name}")
                    try:
                        await client.get("http://127.0.0.1:4318/")
                        break
                    except httpx.TransportError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Collector did not start within 20 seconds") from None
                        await asyncio.sleep(0.05)
                record = DecisionRecord(
                    tool_call_id=UUID(int=1),
                    session_id=UUID(int=2),
                    occurred_at=datetime.now(UTC),
                    severity_score=7,
                    coverage_state="decided",
                    decision_category="auto_denied",
                    content_state="available",
                )
                try:
                    await OtlpLogSink(client, "http://127.0.0.1:4318/v1/logs", attempts=1).send(
                        [record], observed_at=datetime.now(UTC)
                    )
                except httpx.HTTPStatusError as error:
                    upstream_status = error.response.status_code
                    assert upstream_status not in (429, 502, 503, 504)
                    assert scenario in ("unauthorized", "oversized")
                    outcome = "rejected by collector"
                else:
                    assert scenario not in ("unauthorized", "oversized")
                if destination_name != "local":
                    result = await asyncio.to_thread(received.get, True, 10)
                    request = result["request"]
                    assert isinstance(request, ExportLogsServiceRequest)
                    assert len(request.resource_logs[0].scope_logs[0].log_records) == 1
                    expected_path, header, value = DESTINATIONS[destination_name]
                    for capture in captures:
                        assert capture["path"] == expected_path
                        headers = capture["headers"]
                        assert isinstance(headers, dict)
                        assert headers["content-type"] == "application/x-protobuf"
                        if header is not None:
                            assert headers[header] == ("" if scenario == "unset-credential" else value)
                        if destination_name in ("cloudwatch", "opensearch"):
                            verify_sigv4(
                                headers,
                                expected_path,
                                (output / f"{case}-1.pb").read_bytes(),
                                "logs" if destination_name == "cloudwatch" else "osis",
                            )
                        if destination_name == "cloudwatch":
                            assert headers["x-aws-log-group"] == "watcher-fixture"
                            assert headers["x-aws-log-stream"] == "decisions"
                    assert len(captures) == (2 if scenario == "retry" else 1)
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            (output / f"{case}.json").write_text(
                json.dumps(
                    {"outcome": outcome, "upstream_status": upstream_status, "http_requests": captures}, indent=2
                )
                + "\n"
            )
    if destination_name == "local":
        assert "watcher.tool_call_id" in logfile.read_text()
    if scenario == "partial":
        assert "Partial success" in logfile.read_text()


async def main() -> None:
    """Retain raw requests, response outcomes and logs for every completed check."""
    output = Path(os.environ.get("COLLECTOR_TEST_OUTPUT", tempfile.mkdtemp(prefix="watcher-collector-")))
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    completed = []
    checks = []
    for config in sorted(root.joinpath("config").glob("collector-*.yaml")):
        await verify(config, output)
        completed.append(config.name)
        checks.append(config.stem + "-accepted")
    assert len(completed) == 10
    for scenario in ("retry", "unauthorized", "oversized", "partial"):
        await verify(root / "config/collector-newrelic.yaml", output, scenario)
        checks.append("collector-newrelic-" + scenario)
    await verify(root / "config/collector-datadog.yaml", output, "unset-credential")
    checks.append("collector-datadog-unset-credential")
    collector_version = subprocess.check_output(["otelcol-contrib", "--version"], text=True).strip()
    (output / "result.json").write_text(
        json.dumps(
            {
                "collector": collector_version,
                "watcher_sdk": version("watcher-sdk"),
                "opentelemetry_proto": version("opentelemetry-proto"),
                "configs_passed": completed,
                "checks_passed": checks,
                "destinations": "loopback protocol fixtures only; AWS credentials are synthetic",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
