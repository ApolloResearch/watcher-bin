"""Call the monitored Agent Router route with an ordinary OpenAI client.

The gateway operator runs the Watcher processor. This client needs only the
gateway URL, the gateway client key and a model name; it does not import
Watcher. It offers one tool, then prints the released call, or the assistant
text explaining why Watcher withheld it.
"""

import os

from openai import OpenAI, PermissionDeniedError


def main() -> None:
    """Request a tool call and report what the gateway delivered."""
    with OpenAI(
        base_url=os.environ["GATEWAY_BASE_URL"],
        # The gateway holds the provider key; clients authenticate to the gateway.
        api_key="unused",
        default_headers={"x-api-key": os.environ["GATEWAY_API_KEY"]},
    ) as client:
        try:
            raw = client.chat.completions.with_raw_response.create(
                model=os.environ["PROVIDER_MODEL"],
                messages=[{"role": "user", "content": "Use the tool to list the files in the current directory."}],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "run_shell_command",
                            "description": "Run a shell command and return its output.",
                            "parameters": {
                                "type": "object",
                                "properties": {"command": {"type": "string"}},
                                "required": ["command"],
                            },
                        },
                    }
                ],
            )
        except PermissionDeniedError as denied:
            # Only technical failures are errors; a Watcher refusal arrives as ordinary text.
            print(
                "Gateway could not verify the response; conversation",
                denied.response.headers.get("x-watcher-conversation-id"),
            )
            return
    message = raw.parse().choices[0].message
    print("Conversation", raw.headers.get("x-watcher-conversation-id"))
    for call in message.tool_calls or []:
        if call.type == "function":
            print("Released tool call:", call.function.name, call.function.arguments)
    if message.content:
        print("Assistant:", message.content)


if __name__ == "__main__":
    main()
