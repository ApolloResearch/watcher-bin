"""Call the monitored gateway using an ordinary OpenAI client.

The gateway operator installs Watcher. This client needs only its gateway URL,
gateway credential, and configured model name; it does not import Watcher.
"""

import os

from openai import OpenAI


def main() -> None:
    """Send a sample text request; use the gateway response header for readback."""
    with OpenAI(
        api_key="unused",
        base_url=os.environ["GATEWAY_BASE_URL"],
        default_headers={"apikey": os.environ["GATEWAY_API_KEY"]},
    ) as client:
        client.chat.completions.create(
            model=os.environ["PROVIDER_MODEL"],
            messages=[{"role": "user", "content": "Reply with a short greeting."}],
        )


if __name__ == "__main__":
    main()
