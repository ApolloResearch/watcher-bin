"""Import an encrypted Logpush fixture through an installed CLI to real Watcher.

The ciphertext is generated locally from the documented envelope. This test
does not establish that hosted Cloudflare emitted or delivered the same payload.
"""

import asyncio
import base64
import gzip
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from watcher_sdk import AsyncWatcherClient, TrajectoryView


def main():
    root = Path("/evidence")
    case = json.loads((root / "input.json").read_text())
    distribution = importlib.metadata.distribution("watcher-cloudflare-ai-example")
    (root / "integration-installation.json").write_text(distribution.read_text("direct_url.json"))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (root / "fixture-key.pem").write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    clear = {
        "RequestBody": {
            "model": "fixture",
            "messages": [
                {"role": "user", "content": case["token"]},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": case["call_id"],
                            "type": "function",
                            "function": {
                                "name": "Read",
                                "arguments": '{"file_path":"fixture.txt","count":0,"enabled":false}',
                            },
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": case["call_id"], "content": "Actual fixture result " + case["token"]},
            ],
        },
        "ResponseBody": {
            "choices": [
                {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": case["final_text"]}}
            ]
        },
    }
    encrypted = {}
    for name, value in clear.items():
        aes_key, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
        wrapped = key.public_key().encrypt(
            aes_key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
        )
        ciphertext = AESGCM(aes_key).encrypt(nonce, json.dumps(value).encode(), None)
        encrypted[name] = {
            field: base64.b64encode(data).decode()
            for field, data in (("key", wrapped), ("iv", nonce), ("data", ciphertext))
        }
    source = root / "fixture.jsonl.gz"
    source.write_bytes(gzip.compress((json.dumps(encrypted) + "\n").encode()))
    process = subprocess.run(
        [
            str(Path(sys.executable).parent / "watcher-cloudflare-import"),
            "import-file",
            str(source),
            str(root / "fixture-key.pem"),
            "fixture-account/gateway",
            case["token"],
        ],
        env={**os.environ, "WATCHER_API_KEY": "fixture-key"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    (root / "import.stdout").write_text(process.stdout)
    (root / "import.stderr").write_text(process.stderr)
    assert process.returncode == 0, process.stderr
    receipt = json.loads(process.stdout)
    assert receipt["submitted"] == 1

    async def verify():
        async with AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key") as client:
            await wait_for_conversation(
                client,
                external_ids={"other": receipt["conversation_ids"]},
                final_text=case["final_text"],
                decision_ids=set(),
                evidence=root,
            )

    asyncio.run(verify())


async def wait_for_conversation(
    client: AsyncWatcherClient,
    *,
    external_ids: dict[str, list[str]],
    final_text: str | None,
    decision_ids: set[str],
    evidence: Path,
    timeout: float = 15,
) -> dict[str, Any]:
    """Return one exact stored session's extended trajectory, or fail by deadline.

    External ID filters must identify one native conversation. Ambiguous matches
    fail immediately. An empty decision set supports paused/transcript-only runs;
    it does not claim they produced tool judgments. A null final_text is for an aborted native run with no final answer; it asserts only the selected decisions. Callers separately compare
    full tool names, typed arguments and actual native results to these records.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        result = await client.search_sessions(external_ids=external_ids)
        sessions = result.to_dict()
        (evidence / "sessions.json").write_text(json.dumps(sessions, indent=2))
        if sessions["total"] > 1:
            raise AssertionError("The native identity matched multiple Watcher sessions")
        if sessions["total"] == 1:
            item = sessions["sessions"][0]
            if item["latest_trajectory_id"] is not None:
                response = await client.get_trajectory(
                    item["session_id"], item["latest_trajectory_id"], view=TrajectoryView.EXTENDED
                )
                stored = response.to_dict()
                (evidence / "trajectory.json").write_text(json.dumps(stored, indent=2))
                has_final = any(
                    message.get("role") == "assistant" and message.get("content") == final_text
                    for message in stored["messages"]
                )
                if (has_final or final_text is None) and decision_ids <= stored["tool_call_decisions"].keys():
                    return stored
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(
                "The exact final transcript and tool decisions did not become readable through the SDK"
            )
        await asyncio.sleep(0.05)


if __name__ == "__main__":
    main()
