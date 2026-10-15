"""List compatibility and permission-aware merges for sparse agent choices."""

from pydantic import JsonValue, TypeAdapter, ValidationError

from watcher_sdk.settings_schema.agents import ALL_AGENTS
from watcher_sdk.settings_schema.watcher_settings_yaml_schema import (
    AgentEnablement,
    BoolSetting,
    Permission,
    SettingWithPermission,
)

_ENABLEMENT = TypeAdapter(AgentEnablement)
_JSON = TypeAdapter(JsonValue)


def agent_choices_map(enabled: AgentEnablement, names: frozenset[str]) -> dict[str, BoolSetting]:
    """Expand a closed legacy list while keeping sparse maps and unknown names intact.

    ``names`` includes any names present in another layer, so a closed list also
    excludes those names when a newer mapping is merged with it.
    """
    if isinstance(enabled, dict):
        return dict(enabled)
    return {name: name in enabled for name in sorted(set(names) | ALL_AGENTS)}


def agent_enablement_json(enabled: AgentEnablement) -> JsonValue:
    return _JSON.validate_python(_ENABLEMENT.dump_python(enabled, mode="json"))


def merge_agent_enablement(
    base: JsonValue,
    overlay: JsonValue,
    permission: Permission,
    *,
    enforce_permissions: bool,
    permission_base: JsonValue,
    preserve_overlay_permissions: bool = False,
) -> JsonValue:
    """Merge choices without turning a closed legacy list into default-on omissions.

    Invalid input is left for the settings sanitizer. Local layers cannot change
    individually locked values or disable required members of additions-allowed
    settings. ``permission_base`` selects the authority whose individual locks
    apply, including the inherited administrator baseline for profile overlays.
    """
    if enforce_permissions and permission == "locked":
        return base
    try:
        prior = _ENABLEMENT.validate_python({} if base is None else base)
        incoming = _ENABLEMENT.validate_python(overlay)
        authority = _ENABLEMENT.validate_python({} if permission_base is None else permission_base)
    except ValidationError:
        return overlay
    if isinstance(incoming, list) and (base is None or isinstance(prior, list)):
        if enforce_permissions and permission == "additions_allowed" and isinstance(prior, list):
            required = (
                list(authority)
                if isinstance(authority, list)
                else [
                    name
                    for name, setting in authority.items()
                    if (setting if isinstance(setting, bool) else setting.value)
                ]
            )
            return list(dict.fromkeys([*required, *incoming]))
        return list(incoming)
    old = agent_choices_map(prior, frozenset())
    choices = agent_choices_map(incoming, frozenset(old))
    locked = agent_choices_map(authority, frozenset(choices))
    result = dict(old)
    for name, setting in choices.items():
        previous = old.get(name, True)
        protected = locked.get(name, True)
        value = setting.value if isinstance(setting, SettingWithPermission) else setting
        is_required = protected.value if isinstance(protected, SettingWithPermission) else protected
        if enforce_permissions:
            if isinstance(protected, SettingWithPermission) and protected.permission == "locked":
                continue
            if permission == "additions_allowed" and is_required and not value:
                continue
            if preserve_overlay_permissions:
                result[name] = setting
            else:
                result[name] = (
                    SettingWithPermission[bool](value=value, permission=previous.permission)
                    if isinstance(previous, SettingWithPermission)
                    else value
                )
        else:
            result[name] = setting
    return agent_enablement_json(result)


def locked_agent_override_names(base: JsonValue, overlay: JsonValue, permission: Permission) -> list[str]:
    """Name individual requests the permission-aware agent merge would refuse.

    Lists express a choice for every registered or previously named agent. Maps
    express only the choices they contain. Invalid shapes are reported by the
    existing schema validator rather than being labelled as permission errors.
    """
    try:
        prior = _ENABLEMENT.validate_python({} if base is None else base)
        incoming = _ENABLEMENT.validate_python(overlay)
    except ValidationError:
        return []
    old = agent_choices_map(prior, frozenset())
    choices = agent_choices_map(incoming, frozenset(old))
    blocked: list[str] = []
    for name, setting in choices.items():
        previous = old.get(name, True)
        enabled = setting.value if isinstance(setting, SettingWithPermission) else setting
        was_enabled = previous.value if isinstance(previous, SettingWithPermission) else previous
        if (isinstance(previous, SettingWithPermission) and previous.permission == "locked") or (
            permission == "additions_allowed" and was_enabled and not enabled
        ):
            blocked.append(name)
    return blocked
