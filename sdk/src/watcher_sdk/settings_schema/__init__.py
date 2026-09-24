"""Watcher settings schema: the Pydantic model, validator, and merge engine for settings YAML.

This subpackage is the shared home of the Watcher settings document logic so that both
Watcher Live (``apollo_monitor``) and the Watcher API backend can validate and merge settings
documents without depending on each other. It also packages the builtin ``settings.yaml``
defaults (and builtin profile overlays) as importlib resources.
"""

from watcher_sdk.settings_schema.agents import ALL_AGENTS, AgentName
from watcher_sdk.settings_schema.watcher_settings_yaml_helpers import merge_admin
from watcher_sdk.settings_schema.watcher_settings_yaml_layers import (
    builtin_settings_digest,
    inline_profile_ids,
    inline_profile_validation_error,
    load_builtin_settings,
    load_settings_yaml,
)
from watcher_sdk.settings_schema.watcher_settings_yaml_schema import WatcherSettings
from watcher_sdk.settings_schema.watcher_settings_yaml_validation import (
    candidate_validation_error,
    validate_settings_tree,
)

__all__ = [
    "ALL_AGENTS",
    "AgentName",
    "WatcherSettings",
    "builtin_settings_digest",
    "candidate_validation_error",
    "inline_profile_ids",
    "inline_profile_validation_error",
    "load_builtin_settings",
    "load_settings_yaml",
    "merge_admin",
    "validate_settings_tree",
]
