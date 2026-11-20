"""The report a Watcher client sends about its installation, and the limits on it.

Every report carries a client-generated ``report_id``, so a retried request stores nothing new, and a
``status`` object of named sections: ``inventory``
(``watcher_sdk.agent_inventory.vocabulary.AgentInventoryStatus``), ``client``, the client heartbeat
(``ClientHeartbeat``), and ``health``, the endpoint health the heartbeat carries (``EndpointHealthStatus``).
A missing section means "unknown", never "nothing found", and each section describes itself, so a later
section can be added without touching the ones before it or versioning the report. The server stores every
accepted report as its own row.
"""

from typing import Final, Literal, cast, get_args
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from watcher_sdk.agent_inventory.vocabulary import AgentInventoryStatus
from watcher_sdk.settings_schema.watcher_settings_yaml_schema import EnforcementMode

# The server refuses a larger request body with 413 before reading it.
MAX_REPORT_BYTES: Final = 64 * 1024
MAX_BIGINT: Final = 2**63 - 1


# What the client was doing when it sent a heartbeat outside its 15-minute schedule. An open string on the wire,
# like the health vocabulary, so a newer client naming an event this server does not know is still stored; the
# server stores only the events it knows. Values may be added but never renamed.
# - `going_to_sleep`: the operating system announced it is about to sleep (macOS only today).
# - `woke`: the client noticed the machine had been asleep (its wall clock moved further than its monotonic
#   clock), and reported at once; `asleep_since` says when the sleep began.
# - `stopping`: the client process is stopping and no one asked it to through Watcher: the machine shutting down
#   or restarting, the user logging out of the OS, or an update restarting the client.
# - `stopped_by_user`: someone stopped the client through Watcher (`watcher autostart stop`).
# - `signing_out`: someone is signing the client out (`watcher logout`); a signed-out client sends no heartbeat.
ClientEventValue = Literal["going_to_sleep", "woke", "stopping", "stopped_by_user", "signing_out"]
CLIENT_EVENTS: Final = frozenset[str](get_args(ClientEventValue))


def known_client_event(value: str | None) -> ClientEventValue | None:
    """``value`` when it is an event in ``ClientEventValue``, else None (no event, or one this version does not know)."""
    return cast("ClientEventValue", value) if value in CLIENT_EVENTS else None


class ClientHeartbeat(BaseModel):
    """The client's heartbeat, sent every 15 minutes whatever the organization's agent inventory setting.

    The client also sends one at once when something changes whether it can report: the machine going to sleep
    or waking, the client stopping, or someone signing it out (``event``). Unknown fields are ignored.
    """

    model_config = ConfigDict(extra="ignore")
    observed_at: AwareDatetime = Field(description="When the client built this heartbeat, by its own clock.")
    client_version: str = Field(max_length=64, description="The Watcher client's version.")
    event: str | None = Field(
        default=None,
        max_length=32,
        description=(
            "Why this heartbeat was sent outside the schedule: `going_to_sleep`, `woke`, `stopping`, "
            "`stopped_by_user` or `signing_out` (see `ClientEventValue`); null for a scheduled heartbeat. An open "
            "string: a server ignores an event it does not know."
        ),
    )
    asleep_since: AwareDatetime | None = Field(
        default=None,
        description=(
            "With `woke`: when the machine went to sleep, by the client's clock (the last time the client saw "
            "itself running before the sleep). Null otherwise."
        ),
    )
    process_started_at: AwareDatetime | None = Field(
        default=None,
        description="When the client's background process started, by its clock. Null when unknown.",
    )
    system_booted_at: AwareDatetime | None = Field(
        default=None,
        description="When the machine last booted, by its clock. Null when the client could not read it.",
    )


# Endpoint health vocabulary. The fields are open strings on the wire, like the inventory section's, so a newer
# client naming a value this server does not know still reports; the server drops what it does not recognize.
# Values may be added but never renamed. The enforcement modes are the settings schema's ``EnforcementMode``.
# Whether Watcher's hooks are in an agent's configuration and the agent runs them: `installed`, `missing`, or
# `agent_not_found` (missing, and the agent itself was not found on the machine). Hooks that are in place but that
# the agent will not run read `untrusted` (the agent wants the person to trust them first, or to trust them again
# because they changed since) or `turned_off_in_agent` (the person turned at least one off in the agent's own hook
# list); today only Codex asks for trust. Only the hooks count, not Watcher's other setup assets such as a status
# line, profile command or skill; those show in `setup_current`.
AgentHookStateValue = Literal["installed", "missing", "agent_not_found", "untrusted", "turned_off_in_agent"]
SelfCheckSection = Literal["database", "target", "hooks", "enforcement", "settings", "decisions"]
SelfCheckStatus = Literal["ok", "warning", "error"]
ENFORCEMENT_MODES: Final = frozenset[str](get_args(EnforcementMode.__value__))
AGENT_HOOK_STATES: Final = frozenset[str](get_args(AgentHookStateValue))
SELF_CHECK_SECTIONS: Final = frozenset[str](get_args(SelfCheckSection))
SELF_CHECK_STATUSES: Final = frozenset[str](get_args(SelfCheckStatus))
MAX_HEALTH_AGENTS: Final = 16
MAX_SELF_CHECK_SECTIONS: Final = 16


class EndpointHealthSnooze(BaseModel):
    """Whether the user has snoozed grading on the machine, and the active snooze's window."""

    model_config = ConfigDict(extra="ignore")
    active: bool = Field(description="Whether a snooze is in effect now.")
    started_at: AwareDatetime | None = Field(
        default=None, description="When the active snooze began; null when none is active or it could not be read."
    )
    until: AwareDatetime | None = Field(
        default=None,
        description="When the active snooze is set to end; null when none is active or it could not be read.",
    )


class EndpointHealthAgent(BaseModel):
    """One coding agent Watcher has hooks for: whether it is turned on in Watcher and how its hooks stand."""

    model_config = ConfigDict(extra="ignore")
    agent: str = Field(max_length=64, description="The agent's inventory ID, such as `claude_code`.")
    enabled: bool = Field(description="Whether the agent is turned on in Watcher's settings on the machine.")
    hooks: str | None = Field(
        default=None,
        max_length=32,
        description="`installed`, `missing`, `agent_not_found`, `untrusted` (in place, but the agent will not run "
        "them until the person trusts them) or `turned_off_in_agent` (in place, but turned off in the agent's own "
        "hook list); null when the check failed.",
    )
    setup_current: bool | None = Field(
        default=None,
        description="Whether running Watcher's setup would change nothing for this agent: its hooks are up to date "
        "and its other setup assets are in place (or, for an agent turned off, fully removed); null when the "
        "client could not tell.",
    )
    locked: bool | None = Field(
        default=None,
        description="Whether the organization's settings stop a developer from flipping the agent's current on/off "
        "choice: `permission: locked` on `agents.enabled.<name>`, set there or inherited from `agents.enabled`, `agents` or "
        "the document root; or `additions_allowed` with the agent on because the organization's baseline turns it "
        "on. An agent off under `additions_allowed` is not locked, because a developer may turn it on. This is the "
        "rule `watcher agents enable` and `disable` refuse by. Null when the client could not read it.",
    )
    since: AwareDatetime | None = Field(
        default=None,
        description="When the client first saw the agent's current state: for an agent turned off, when it was "
        "first seen off, whatever its hooks did since; otherwise when the current `enabled` and `hooks` values "
        "were first seen together. Null when the client could not keep track.",
    )
    since_first_check: bool = Field(
        default=False,
        description="The state may be older than `since`: it was already in place when the client first checked, "
        "when it checked after a stretch without checks, or when it next read the agent's hooks after failing "
        "to.",
    )


class EndpointHealthDelivery(BaseModel):
    """What the machine is still waiting to upload. A null count means the client could not read it."""

    model_config = ConfigDict(extra="ignore")
    decisions_waiting: int | None = Field(
        default=None, ge=0, le=MAX_BIGINT, description="Tool-call decisions waiting to upload."
    )
    oldest_decision_at: AwareDatetime | None = Field(
        default=None, description="When the oldest decision still waiting was made; null when none is waiting."
    )
    decisions_gave_up: int | None = Field(
        default=None, ge=0, le=MAX_BIGINT, description="Decisions from the last 7 days the client stopped retrying."
    )
    transcripts_waiting: int | None = Field(
        default=None, ge=0, le=MAX_BIGINT, description="Session transcripts waiting to upload that have retries left."
    )
    call_records_waiting: int | None = Field(
        default=None,
        ge=0,
        le=MAX_BIGINT,
        description="Records of tool calls Watcher observed but did not grade, captured and not yet sent.",
    )


class EndpointHealthStatus(BaseModel):
    """Whether Watcher is fully on for the machine, as the client saw it at ``observed_at``.

    Only states, times and counts: never paths, folder or project names, snooze reasons, session IDs, settings
    contents or the self-check's text. A missing field means the client could not read it.
    """

    model_config = ConfigDict(extra="ignore")
    observed_at: AwareDatetime = Field(description="When the client read these values, by the machine's clock.")
    enforcement_mode: str | None = Field(
        default=None,
        max_length=32,
        description="`enforce` (risky calls can be blocked), `observe` (graded, never blocked) or `paused` "
        "(nothing is evaluated, not even rules); null when the client could not read it.",
    )
    snooze: EndpointHealthSnooze | None = Field(
        default=None, description="Whether grading is snoozed; null when the client could not read it."
    )
    agents: list[EndpointHealthAgent] | None = Field(
        default=None,
        max_length=MAX_HEALTH_AGENTS,
        description="Every coding agent Watcher has hooks for; null when the client could not read them.",
    )
    delivery: EndpointHealthDelivery | None = Field(
        default=None, description="The upload backlog; null when the client could not read it."
    )
    self_check: dict[str, str] | None = Field(
        default=None,
        max_length=MAX_SELF_CHECK_SECTIONS,
        description="`watcher doctor` section name to `ok`, `warning` or `error`, for the sections the client "
        "checks in the background. A section is missing when its check failed to run; null when the client could "
        "not run the self-check at all.",
    )


class InstallationStatus(BaseModel):
    """What the installation is reporting, by section. Omit a section to report nothing about it."""

    model_config = ConfigDict(extra="ignore")

    inventory: AgentInventoryStatus | None = Field(
        default=None, description="The coding agents found on the machine, when agent inventory is on."
    )
    client: ClientHeartbeat | None = Field(
        default=None, description="The client's heartbeat, sent every 15 minutes: when it was sent and its version."
    )
    health: EndpointHealthStatus | None = Field(
        default=None, description="Snooze, per-agent hooks, enforcement mode, upload backlog and self-check."
    )


class InstallationReport(BaseModel):
    """One report from a Watcher client installation."""

    model_config = ConfigDict(extra="ignore")

    report_id: UUID = Field(
        description="A random ID for this report. Retry a failed request with the same ID; it is stored once."
    )
    status: InstallationStatus
