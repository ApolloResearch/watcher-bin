"""Capture synthetic native-test exchanges before running the installed bridge.

This helper is confined to local test fixtures. It records the precise gateway
body and validation failure, which an ordinary bridge deliberately does not log.
"""

import importlib
import json
import os
from pathlib import Path
from uuid import uuid4

module = importlib.import_module(os.environ["WATCHER_TEST_BRIDGE_MODULE"])
evaluate = module.evaluate
root = Path(os.environ["WATCHER_TEST_CAPTURE_DIR"])
root.mkdir(exist_ok=True)


async def capture(watcher, request, response, **kwargs):
    """Retain exact synthetic inputs and then invoke the unmodified evaluator."""
    receipt = {"request": request, "response": response, "configuration": kwargs}
    path = root / (str(uuid4()) + ".json")
    try:
        result = await evaluate(watcher, request, response, **kwargs)
        receipt["permitted"] = result
        return result
    except Exception as error:
        receipt["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        path.write_text(json.dumps(receipt, indent=2))


setattr(module, "evaluate", capture)
module.main()
