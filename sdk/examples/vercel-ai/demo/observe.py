"""Run the installed vercel-ai observe example with configured Watcher credentials."""

import asyncio

from watcher_vercel_ai_bridge.observation import main

if __name__ == "__main__":
    asyncio.run(main())
