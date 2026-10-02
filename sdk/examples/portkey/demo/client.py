"""Send a normal Chat Completions request to the monitored gateway."""

import os

import httpx


def main() -> None:
    """Use the gateway API without importing Watcher into the client application."""
    response = httpx.post(
        os.environ["GATEWAY_URL"].rstrip("/") + "/chat/completions",
        headers={"Authorization": "Bearer " + os.environ["GATEWAY_API_KEY"]},
        json={"model": os.environ["PROVIDER_MODEL"], "messages": [{"role": "user", "content": "Say hello."}]},
        timeout=450,
    )
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
