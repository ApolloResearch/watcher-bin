"""Shared vocabulary for agent inventory: enums, caps and the inventory section of a report.

Agent IDs and what inventory can detect about each come from the agent catalog (``watcher_sdk.agent_catalog``).

The Watcher client builds the ``inventory`` section of its installation report
(``watcher_sdk.installation_report``) from these values and the server validates it against them. The fields
are open strings on the wire so that a newer client naming an agent or value this server does not know still
reports successfully; the server drops what it does not recognize. Values may be added but never renamed.
"""

from datetime import date
from typing import Final, Literal, get_args

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# Re-exported: inventory code names agents and detection levels through this module.
from watcher_sdk.agent_catalog import AgentId as AgentId
from watcher_sdk.agent_catalog import DetectionLevel as DetectionLevel

Surface = Literal["cli", "ide", "ide_extension", "desktop_app", "sdk"]
# Whether Watcher's own hooks are set up for the agent on this machine: `on` when they are installed,
# `off` when the agent is turned on in Watcher's settings but its hooks are not installed, and `disabled`
# when the agent is turned off in Watcher's settings. Agents Watcher has no hooks for report
# `not_applicable`.
WatcherHooks = Literal["on", "off", "disabled", "not_applicable"]
InventoryOs = Literal["macos", "linux"]
InventoryArch = Literal["arm64", "x86_64"]

AGENT_IDS: Final = frozenset(agent.value for agent in AgentId)
SURFACES: Final = frozenset[str](get_args(Surface))
WATCHER_HOOKS_VALUES: Final = frozenset[str](get_args(WatcherHooks))
INVENTORY_OSES: Final = frozenset[str](get_args(InventoryOs))
INVENTORY_ARCHES: Final = frozenset[str](get_args(InventoryArch))

# "Recent" everywhere in agent inventory: used recently, recent sessions, coverage and gateway sightings.
RECENT_DAYS: Final = 7

# Wire caps. The client truncates to them; the server answers 422 above them.
MAX_AGENTS: Final = 64
MAX_SURFACES: Final = 8
MAX_RECENT_SESSIONS: Final = 100_000

# Used as a Pydantic `pattern=`, where `$` means end of text.
AGENT_ID_PATTERN: Final = r"^[a-z0-9][a-z0-9_]{0,63}$"


class AgentInventoryReportAgent(BaseModel):
    """One agent found on the machine."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(pattern=AGENT_ID_PATTERN, max_length=64, description="The agent's inventory ID.")
    surfaces: list[str] = Field(
        default_factory=list,
        max_length=MAX_SURFACES,
        description="Where the agent is installed: `cli`, `ide`, `ide_extension`, `desktop_app` or `sdk`.",
    )
    version: str | None = Field(default=None, max_length=64, description="The newest installed version, if known.")
    last_used_on: date | None = Field(default=None, description="The UTC date the agent was last used, if known.")
    recent_sessions: int | None = Field(
        default=None,
        ge=0,
        le=MAX_RECENT_SESSIONS,
        description="Session files modified in the last 7 days, or null when they cannot be counted.",
    )
    watcher_hooks: str = Field(
        default="not_applicable",
        max_length=32,
        description=(
            "Whether Watcher's hooks are set up for this agent: `on`; `off` when the agent is turned on in "
            "Watcher but its hooks are not installed; `disabled` when the agent is turned off in Watcher; "
            "or `not_applicable` when Watcher has no hooks for it."
        ),
    )
    settings_folder_only: bool = Field(
        default=False,
        description=(
            "True when the only trace of the agent is its settings folder: no installed program, extension or "
            "app, and no session files. Someone set the agent up on this machine once; it may have been removed."
        ),
    )


class AgentInventoryStatus(BaseModel):
    """The `inventory` section of an installation report: the coding agents one scan found on the machine.

    Send the full list each time.
    """

    model_config = ConfigDict(extra="ignore")

    observed_at: AwareDatetime = Field(
        description="When the Watcher client ran the scan. A retried report keeps its original time."
    )
    client_version: str | None = Field(default=None, max_length=64)
    hostname: str | None = Field(default=None, max_length=255)
    os: str | None = Field(default=None, max_length=16, description="`macos` or `linux`.")
    arch: str | None = Field(default=None, max_length=16, description="`arm64` or `x86_64`.")
    agents: list[AgentInventoryReportAgent] = Field(default_factory=list, max_length=MAX_AGENTS)
