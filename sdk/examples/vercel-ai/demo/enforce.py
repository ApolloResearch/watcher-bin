"""Run the installed vercel-ai enforce example with configured Watcher credentials."""

import asyncio

from watcher_vercel_ai_bridge.synchronous import main

if __name__ == "__main__":
    asyncio.run(main())
