#!/bin/sh
: "${WATCHER_PYTHON:?Set the installed bridge interpreter}"
exec "$WATCHER_PYTHON" -m watcher_cline_bridge.pre_tool
