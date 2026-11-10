"""The catalog of coding agents Watcher knows about, and what Watcher can do for each.

Each ``AgentId`` member is one catalog entry: the agent's ID, its display names, how Watcher can receive its
sessions and how much agent inventory can detect about it. Everything else that lists agents reads this catalog:
the session platforms the server stores and labels, the SDK adapters' conversation prefixes, inventory coverage,
the Watcher client's inventory detectors and labels, and the Analyzer, through a generated TypeScript copy.

Adding an agent means adding one member here (and its inventory detector in the Watcher client). IDs are stored
in session rows and sent on the wire, so a value may be added but never renamed.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self, cast


class DetectionLevel(StrEnum):
    """How much the Watcher client's scan can tell about an agent. Each level includes everything before it."""

    INSTALLS_ONLY = "installs_only"
    """Installations and versions only."""
    RECENT_USE = "recent_use"
    """Also the last day of use and the recent session count, from the agent's own session store."""
    WATCHER_HOOKS = "watcher_hooks"
    """Also whether Watcher's hooks are on, for the agents Watcher integrates with."""


class MonitoringPath(StrEnum):
    """A way Watcher can receive an agent's sessions and tell that they came from that agent."""

    CLIENT_HOOKS = "client_hooks"
    """The Watcher client's own hooks on the developer's machine."""
    GATEWAY_HOOK = "gateway_hook"
    """A gateway hook, such as Aperture's, which recognizes the agent from its traffic."""
    SDK_EXAMPLE = "sdk_example"
    """An SDK example adapter, which sends the agent's sessions under its own conversation prefix."""


@dataclass(frozen=True, kw_only=True)
class AgentEntry:
    """What Watcher knows about one agent. Read it from the agent's ``AgentId`` member as ``agent.entry``.

    Attributes:
        label: The agent's product name, as agent inventory and the docs show it.
        detection: How much the Watcher client's inventory scan can tell about the agent. ``WATCHER_HOOKS``
            exactly when the agent has the Watcher client's hooks.
        monitoring: How Watcher can receive the agent's sessions, in display order; empty when it cannot.
        session_label: The name of sessions recorded from the agent, in the Analyzer and in notifications.
            Defaults to ``label``; set it when sessions come from one surface of a wider product.
        sdk_prefix: The conversation-ID prefix the agent's SDK adapter sessions carry. Those sessions are
            stored under the ``other`` platform, and the prefix names their agent in reports. Required for an
            SDK example; also kept for retired adapters whose stored sessions still carry it.
    """

    label: str
    detection: DetectionLevel
    monitoring: tuple[MonitoringPath, ...] = ()
    session_label: str = field(default="")
    sdk_prefix: str | None = None

    def __post_init__(self) -> None:
        """Fill the default session label and refuse an entry whose fields contradict each other.

        Raises:
            ValueError: A monitoring path is listed twice; the detection level and client hooks disagree; or an
                SDK example has no conversation prefix.
        """
        if not self.session_label:
            object.__setattr__(self, "session_label", self.label)
        if len(set(self.monitoring)) != len(self.monitoring):
            raise ValueError(f"{self.label}: a monitoring path is listed twice")
        if (self.detection is DetectionLevel.WATCHER_HOOKS) != (MonitoringPath.CLIENT_HOOKS in self.monitoring):
            raise ValueError(f"{self.label}: only agents with the Watcher client's hooks report their hook state")
        if MonitoringPath.SDK_EXAMPLE in self.monitoring and not self.sdk_prefix:
            raise ValueError(f"{self.label}: an SDK example needs its conversation prefix")


_CLIENT = MonitoringPath.CLIENT_HOOKS
_GATEWAY = MonitoringPath.GATEWAY_HOOK
_SDK = MonitoringPath.SDK_EXAMPLE
_INSTALLS = DetectionLevel.INSTALLS_ONLY
_USE = DetectionLevel.RECENT_USE
_HOOKS = DetectionLevel.WATCHER_HOOKS


class _IdWithEntry(str):
    """An agent ID string that carries its catalog entry into ``AgentId``'s member constructor."""

    entry: AgentEntry


def _agent(agent_id: str, entry: AgentEntry) -> str:
    """Declare one ``AgentId`` member: its ID string with its catalog entry attached.

    Typed as returning ``str`` so type checkers see each member's value as the ID string, which keeps
    comparisons such as ``agent == "cursor"`` well-typed; a ``(value, entry)`` tuple member would not.
    """
    value = _IdWithEntry(agent_id)
    value.entry = entry
    return value


class AgentId(StrEnum):
    """Every coding agent Watcher knows, each with its catalog entry (``AgentId.CURSOR.entry``).

    Agents Watcher stores sessions for under their own platform reuse that platform's ID. Declare a member
    with ``_agent``; ``AgentId("cursor")`` looks a member up by its ID as with any enum.
    """

    entry: AgentEntry

    def __new__(cls, value: str) -> Self:
        """Create a member from an ``_agent`` declaration: the ID string is its value and it keeps the entry.

        A member declared with a plain string has no entry and fails here when the module loads.
        """
        member = str.__new__(cls, value)
        member._value_ = str(value)
        member.entry = cast("_IdWithEntry", value).entry
        return member

    CLAUDE_CODE = _agent(
        "claude_code", AgentEntry(label="Claude Code", detection=_HOOKS, monitoring=(_CLIENT, _GATEWAY))
    )
    CODEX = _agent("codex", AgentEntry(label="Codex", detection=_HOOKS, monitoring=(_CLIENT, _GATEWAY)))
    # Sessions from the retired SDK Copilot integration keep its prefix under `other`.
    GITHUB_COPILOT_CLI = _agent(
        "github_copilot_cli",
        AgentEntry(
            label="GitHub Copilot CLI", detection=_HOOKS, monitoring=(_CLIENT,), sdk_prefix="github-copilot-cli:"
        ),
    )
    GEMINI_CLI = _agent(
        "gemini_cli",
        AgentEntry(label="Gemini CLI", detection=_USE, monitoring=(_GATEWAY, _SDK), sdk_prefix="gemini-cli:"),
    )
    QWEN_CODE = _agent(
        "qwen_code",
        AgentEntry(label="Qwen Code", detection=_USE, monitoring=(_GATEWAY, _SDK), sdk_prefix="qwen-code:"),
    )
    OPENCODE = _agent(
        "opencode",
        AgentEntry(label="OpenCode", detection=_INSTALLS, monitoring=(_GATEWAY, _SDK), sdk_prefix="opencode:"),
    )
    ANTIGRAVITY_CLI = _agent(
        "antigravity_cli",
        AgentEntry(label="Antigravity", session_label="Antigravity CLI", detection=_INSTALLS, monitoring=(_GATEWAY,)),
    )
    MISTRAL_VIBE = _agent(
        "mistral_vibe",
        AgentEntry(label="Mistral Vibe", detection=_USE, monitoring=(_GATEWAY, _SDK), sdk_prefix="mistral-vibe:"),
    )
    PI = _agent("pi", AgentEntry(label="Pi", detection=_USE, monitoring=(_GATEWAY, _SDK), sdk_prefix="pi:"))
    OPENCLAW = _agent(
        "openclaw", AgentEntry(label="OpenClaw", detection=_USE, monitoring=(_SDK,), sdk_prefix="openclaw:")
    )
    HERMES = _agent(
        "hermes", AgentEntry(label="Hermes Agent", detection=_INSTALLS, monitoring=(_SDK,), sdk_prefix="hermes:")
    )
    OPENHANDS = _agent(
        "openhands", AgentEntry(label="OpenHands", detection=_USE, monitoring=(_SDK,), sdk_prefix="openhands:")
    )
    KILO_CODE = _agent(
        "kilo_code", AgentEntry(label="Kilo Code", detection=_INSTALLS, monitoring=(_SDK,), sdk_prefix="kilocode:")
    )
    CRUSH = _agent("crush", AgentEntry(label="Crush", detection=_INSTALLS))
    GOOSE = _agent("goose", AgentEntry(label="Goose", detection=_INSTALLS, monitoring=(_SDK,), sdk_prefix="goose:"))
    AIDER = _agent("aider", AgentEntry(label="Aider", detection=_INSTALLS, monitoring=(_SDK,), sdk_prefix="aider:"))
    AMP = _agent("amp", AgentEntry(label="Amp", detection=_INSTALLS, monitoring=(_SDK,), sdk_prefix="amp:"))
    FACTORY_DROID = _agent("factory_droid", AgentEntry(label="Factory Droid", detection=_INSTALLS))
    AUGMENT = _agent("augment", AgentEntry(label="Augment", detection=_USE))
    CONTINUE_CLI = _agent(
        "continue_cli",
        AgentEntry(
            label="Continue", session_label="Continue CLI", detection=_USE, monitoring=(_SDK,), sdk_prefix="continue:"
        ),
    )
    CLINE = _agent("cline", AgentEntry(label="Cline", detection=_USE, monitoring=(_SDK,), sdk_prefix="cline:"))
    ROO_CODE = _agent(
        "roo_code", AgentEntry(label="Roo Code", detection=_USE, monitoring=(_SDK,), sdk_prefix="roo-code:")
    )
    AMAZON_Q = _agent("amazon_q", AgentEntry(label="Amazon Q", detection=_INSTALLS))
    GEMINI_CODE_ASSIST = _agent("gemini_code_assist", AgentEntry(label="Gemini Code Assist", detection=_INSTALLS))
    VSCODE_GITHUB_COPILOT = _agent(
        "vscode_github_copilot", AgentEntry(label="GitHub Copilot in VS Code", detection=_USE)
    )
    CURSOR = _agent("cursor", AgentEntry(label="Cursor", detection=_USE, monitoring=(_SDK,), sdk_prefix="cursor:"))
    WINDSURF = _agent(
        "windsurf", AgentEntry(label="Windsurf", detection=_INSTALLS, monitoring=(_SDK,), sdk_prefix="windsurf:")
    )
    KIRO = _agent("kiro", AgentEntry(label="Kiro", detection=_USE))
    TRAE = _agent("trae", AgentEntry(label="Trae", detection=_INSTALLS))
    CLAUDE_DESKTOP = _agent("claude_desktop", AgentEntry(label="Claude Desktop", detection=_INSTALLS))
    CHATGPT_CODEX_DESKTOP = _agent(
        "chatgpt_codex_desktop", AgentEntry(label="ChatGPT/Codex desktop", detection=_INSTALLS)
    )
