"""Shared vocabulary for agent inventory: agent IDs, enums, caps and the inventory section of a report.

The Watcher client builds the ``inventory`` section of its installation report
(``watcher_sdk.installation_report``) from these values and the server validates it against them. The fields
are open strings on the wire so that a newer client naming an agent or value this server does not know still
reports successfully; the server drops what it does not recognize. Values may be added but never renamed.
"""

from datetime import date
from enum import StrEnum
from typing import Final, Literal, get_args

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class AgentId(StrEnum):
    """Every agent the inventory knows. Supported agents reuse the session platform ID Watcher stores."""

    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    GITHUB_COPILOT_CLI = "github_copilot_cli"
    GEMINI_CLI = "gemini_cli"
    QWEN_CODE = "qwen_code"
    OPENCODE = "opencode"
    ANTIGRAVITY_CLI = "antigravity_cli"
    MISTRAL_VIBE = "mistral_vibe"
    PI = "pi"
    OPENCLAW = "openclaw"
    HERMES = "hermes"
    OPENHANDS = "openhands"
    KILO_CODE = "kilo_code"
    CRUSH = "crush"
    GOOSE = "goose"
    AIDER = "aider"
    AMP = "amp"
    FACTORY_DROID = "factory_droid"
    AUGMENT = "augment"
    CONTINUE_CLI = "continue_cli"
    CLINE = "cline"
    ROO_CODE = "roo_code"
    AMAZON_Q = "amazon_q"
    GEMINI_CODE_ASSIST = "gemini_code_assist"
    VSCODE_GITHUB_COPILOT = "vscode_github_copilot"
    CURSOR = "cursor"
    WINDSURF = "windsurf"
    KIRO = "kiro"
    TRAE = "trae"
    CLAUDE_DESKTOP = "claude_desktop"
    CHATGPT_CODEX_DESKTOP = "chatgpt_codex_desktop"


class DetectionLevel(StrEnum):
    """How much the Watcher client's scan can tell about an agent. Each level includes everything before it."""

    INSTALLS_ONLY = "installs_only"
    """Installations and versions only."""
    RECENT_USE = "recent_use"
    """Also the last day of use and the recent session count, from the agent's own session store."""
    WATCHER_HOOKS = "watcher_hooks"
    """Also whether Watcher's hooks are on, for the agents Watcher integrates with."""


# What the Watcher client's scan can report for each agent. An agent below RECENT_USE never reports a last-used
# date or session count, so their absence says nothing about whether it is used. Each client detector declares
# the same level, which its tests check.
AGENT_DETECTION_LEVELS: Final[dict[AgentId, DetectionLevel]] = {
    AgentId.CLAUDE_CODE: DetectionLevel.WATCHER_HOOKS,
    AgentId.CODEX: DetectionLevel.WATCHER_HOOKS,
    AgentId.GITHUB_COPILOT_CLI: DetectionLevel.WATCHER_HOOKS,
    AgentId.GEMINI_CLI: DetectionLevel.RECENT_USE,
    AgentId.QWEN_CODE: DetectionLevel.RECENT_USE,
    AgentId.OPENCODE: DetectionLevel.INSTALLS_ONLY,
    AgentId.ANTIGRAVITY_CLI: DetectionLevel.INSTALLS_ONLY,
    AgentId.MISTRAL_VIBE: DetectionLevel.RECENT_USE,
    AgentId.PI: DetectionLevel.RECENT_USE,
    AgentId.OPENCLAW: DetectionLevel.RECENT_USE,
    AgentId.HERMES: DetectionLevel.INSTALLS_ONLY,
    AgentId.OPENHANDS: DetectionLevel.RECENT_USE,
    AgentId.KILO_CODE: DetectionLevel.INSTALLS_ONLY,
    AgentId.CRUSH: DetectionLevel.INSTALLS_ONLY,
    AgentId.GOOSE: DetectionLevel.INSTALLS_ONLY,
    AgentId.AIDER: DetectionLevel.INSTALLS_ONLY,
    AgentId.AMP: DetectionLevel.INSTALLS_ONLY,
    AgentId.FACTORY_DROID: DetectionLevel.INSTALLS_ONLY,
    AgentId.AUGMENT: DetectionLevel.RECENT_USE,
    AgentId.CONTINUE_CLI: DetectionLevel.RECENT_USE,
    AgentId.CLINE: DetectionLevel.RECENT_USE,
    AgentId.ROO_CODE: DetectionLevel.RECENT_USE,
    AgentId.AMAZON_Q: DetectionLevel.INSTALLS_ONLY,
    AgentId.GEMINI_CODE_ASSIST: DetectionLevel.INSTALLS_ONLY,
    AgentId.VSCODE_GITHUB_COPILOT: DetectionLevel.RECENT_USE,
    AgentId.CURSOR: DetectionLevel.RECENT_USE,
    AgentId.WINDSURF: DetectionLevel.INSTALLS_ONLY,
    AgentId.KIRO: DetectionLevel.RECENT_USE,
    AgentId.TRAE: DetectionLevel.INSTALLS_ONLY,
    AgentId.CLAUDE_DESKTOP: DetectionLevel.INSTALLS_ONLY,
    AgentId.CHATGPT_CODEX_DESKTOP: DetectionLevel.INSTALLS_ONLY,
}

# The Watcher client's agent integrations are named differently from inventory agents. Inventory code
# looks Watcher's hooks up through this mapping instead of naming the integrations itself: shared client
# code may not name an integration (test_harness_plugin_boundary.py), so the mapping cannot live there.
INTEGRATION_AGENT_IDS: Final[dict[str, AgentId]] = {
    "claude_code": AgentId.CLAUDE_CODE,
    "codex": AgentId.CODEX,
    "copilot": AgentId.GITHUB_COPILOT_CLI,
}

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
