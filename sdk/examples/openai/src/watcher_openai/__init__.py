"""Check buffered OpenAI Responses and Chat Completions responses before client tool execution.

Use complete with application-owned provider/Watcher clients and full history.
The caller executes only returned tools and preserves their original IDs.
"""

from watcher_openai.integration import complete

__all__ = ["complete"]
