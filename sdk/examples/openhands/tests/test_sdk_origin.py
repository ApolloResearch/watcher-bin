"""The native library tests must exercise the installed noneditable public SDK wheel."""

import json
from importlib.metadata import distribution
from pathlib import Path

import watcher_sdk


def test_sdk_import_is_from_noneditable_wheel():
    package = distribution("watcher-sdk")
    origin = json.loads(package.read_text("direct_url.json"))
    assert origin["url"].endswith(".whl")
    assert not origin.get("dir_info", {}).get("editable", False)
    assert Path(watcher_sdk.__file__).parent == package.locate_file("watcher_sdk")
