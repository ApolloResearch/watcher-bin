"""Loopback HTTP fixture; tests reject sockets to any external address."""

import asyncio
import json
import socket
from contextlib import asynccontextmanager

import pytest


@pytest.fixture(autouse=True)
def deny_external_network(monkeypatch):
    original = socket.socket.connect

    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and address[0] not in ("127.0.0.1", "::1"):
            raise AssertionError("Tests may only connect to loopback fixtures")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)


@pytest.fixture
def http_fixture():
    @asynccontextmanager
    async def serve(handler):
        tasks = set()

        async def handle(reader, writer):
            task = asyncio.current_task()
            tasks.add(task)
            try:
                header = await reader.readuntil(b"\r\n\r\n")
                lines = header.decode("latin-1").split("\r\n")
                method, path, _ = lines[0].split(" ")
                headers = dict(line.split(": ", 1) for line in lines[1:] if line)
                length = next((int(value) for key, value in headers.items() if key.lower() == "content-length"), 0)
                body = await reader.readexactly(length)
                status, response_headers, payload = handler(method, path, headers, body)
                if not isinstance(payload, bytes):
                    payload = json.dumps(payload).encode()
                wire = f"HTTP/1.1 {status} Fixture\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n"
                wire += "".join(f"{key}: {value}\r\n" for key, value in response_headers.items())
                writer.write(wire.encode() + b"\r\n" + payload)
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
                tasks.discard(task)

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        try:
            yield f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        finally:
            server.close()
            await server.wait_closed()
            if tasks:
                await asyncio.gather(*tasks)

    return serve
