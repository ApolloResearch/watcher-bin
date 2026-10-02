"""Run the native tool-loop demonstration with explicit enforce mode."""

import asyncio

from demo.app import main

if __name__ == "__main__":
    asyncio.run(main("enforce"))
