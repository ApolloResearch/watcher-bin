"""Pydantic schema for the Watcher settings YAML document and its effective-value models."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from watcher_sdk.settings_schema.agents import ALL_AGENTS, AgentName

type Permission = Literal["locked", "modifiable", "additions_allowed"]
type ScalarPermission = Literal["locked", "modifiable"]
type Decision = Literal["off", "human", "triage", "allow", "deny"]
type SettingsSource = Literal["admin", "local"]
type GradingFailureDecision = Literal["allow", "deny", "escalate"]
type SettingsWriteScope = Literal["profile", "global"]
type EnforcementMode = Literal["enforce", "observe", "paused"]
type ContextWindowAll = Literal["all"]

CONTEXT_WINDOW_ALL: ContextWindowAll = "all"

ACTION_TO_DECISION: dict[str, Decision] = {
    "allow": "allow",
    "escalate_triage": "triage",
    "escalate_human": "human",
    "deny": "deny",
    "off": "off",
}
DECISION_TO_ACTION: dict[Decision, str] = {
    "allow": "allow",
    "triage": "escalate_triage",
    "human": "escalate_human",
    "deny": "deny",
    "off": "off",
}


class StrictSettingsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SettingWithPermission[T](StrictSettingsModel):
    value: T
    permission: ScalarPermission = "modifiable"


class PermissionedSettingsModel(StrictSettingsModel):
    permission: Permission = "modifiable"


type IntSetting = int | SettingWithPermission[int]
type FloatSetting = int | float | SettingWithPermission[float]
type BoolSetting = bool | SettingWithPermission[bool]
type StrSetting = str | SettingWithPermission[str]
type OptionalStrSetting = str | None | SettingWithPermission[str | None]
type DecisionSetting = Decision | SettingWithPermission[Decision]
type GradingFailureDecisionSetting = GradingFailureDecision | SettingWithPermission[GradingFailureDecision]
type EnforcementModeSetting = EnforcementMode | SettingWithPermission[EnforcementMode]
# The grading context window: a count of trailing user messages, or the whole transcript (literal "all").
# We use StrictInt to reject values like `true` or "0", which Pydantic would loosely validate as an int.
type ContextWindow = StrictInt | ContextWindowAll
type ContextWindowSetting = ContextWindow | SettingWithPermission[ContextWindow]


def _setting_value[T](setting: T | SettingWithPermission[T]) -> T:
    if isinstance(setting, SettingWithPermission):
        return setting.value
    return setting


def _setting_locked(setting: object) -> bool:
    """Whether a scalar carries its own ``locked`` permission. Inherited locks live on the
    enclosing nodes, so a caller that cares about those has to check them too.
    """
    return isinstance(setting, SettingWithPermission) and setting.permission == "locked"


THRESHOLD_ORDER_ERROR = "flag_threshold must be less than deny_threshold when both thresholds are active"
CONTEXT_WINDOW_ERROR = 'context_user_messages must be a positive count of user messages, or "all"'


def is_valid_threshold_order(flag: int, deny: int) -> bool:
    """Return whether a (flag, deny) threshold pair has a usable order.

    The thresholds compare against a 1..10 suspicion score, with 0 ("always act") and 11
    ("never act") as sentinels that sit outside that band. Ordering only matters when both
    thresholds are inside the active band: a tool call must be flagged for review at a lower
    score than it is auto-denied at, so ``flag`` must be strictly below ``deny``. When either
    threshold is a sentinel the pair is always acceptable, because there is no overlap to order.
    """
    if 1 <= flag <= 10 and 1 <= deny <= 10:
        return flag < deny
    return True


class ToolThresholdSetting(PermissionedSettingsModel):
    """Per-tool suspicion-score thresholds that decide when the grader flags or blocks a call."""

    flag_threshold: IntSetting = Field(
        description="Suspicion score (1-10) at or above which a call is escalated for review; 0 always flags, 11 never does.",
    )
    deny_threshold: IntSetting = Field(
        description="Suspicion score (1-10) at or above which a call is denied outright; 0 always denies, 11 never does.",
    )
    # Legacy key, accepted and ignored. Older Watcher versions wrote
    # "common: false" into user-profile YAML when auto-registering tools, and
    # admin-distributed baselines may carry it (including the
    # {value: ..., permission: ...} wrapper form). StrictSettingsModel forbids
    # unknown keys, so dropping this field would hard-fail every existing
    # settings file on upgrade.
    common: BoolSetting = Field(
        default=False,
        description="Legacy field, accepted and ignored.",
        json_schema_extra={"deprecated": True},
    )

    @model_validator(mode="after")
    def validate_threshold_order(self) -> ToolThresholdSetting:
        flag = _setting_value(self.flag_threshold)
        deny = _setting_value(self.deny_threshold)
        if not is_valid_threshold_order(flag, deny):
            raise ValueError(THRESHOLD_ORDER_ERROR)
        return self


class CommandRuleSetting(PermissionedSettingsModel):
    """A deterministic regex rule evaluated against a tool call before the LLM grader runs."""

    id: str = Field(description="Stable unique identifier for the rule.")
    tool_name: StrSetting | None = Field(
        default=None,
        description="Tool the rule applies to (e.g. Bash, Edit, Write, apply_patch).",
    )
    name: StrSetting | None = Field(default=None, description="Human-readable label shown in the UI.")
    category: StrSetting | None = Field(
        default=None,
        description="Grouping label for the UI (e.g. file_directory, git, security_system).",
    )
    regex: StrSetting | None = Field(
        default=None,
        description="Pattern matched against the command or file path; a match applies this rule's decision.",
    )
    decision: DecisionSetting = Field(
        default="triage",
        description="What to do on match: allow, triage, human (review), deny, or off.",
    )
    last_decision: DecisionSetting | None = Field(
        default=None,
        description="The decision this rule carried before it was last changed.",
    )
    priority: IntSetting | None = Field(
        default=None,
        description="Evaluation order; lower numbers are checked first, so the lowest-numbered matching rule wins.",
    )


class CommandRulesSetting(PermissionedSettingsModel):
    """The org's list of deterministic command rules."""

    rules: list[CommandRuleSetting] = Field(
        description="Command rules evaluated in priority order before grading.",
    )


class ManagedInstructionSection(StrictSettingsModel):
    """One titled block of managed instructions injected into the agent."""

    id: str = Field(description="Stable unique identifier for the section.")
    title: str = Field(description="Section heading.")
    body: str = Field(description="Instruction text for the section.")


class ManagedInstructionsSettings(PermissionedSettingsModel):
    """Org-managed instruction text distributed to agents."""

    enabled: bool = Field(default=True, description="Whether managed instructions are injected.")
    sections: list[ManagedInstructionSection] = Field(
        default_factory=list,
        description="Ordered instruction sections.",
    )


class SnoozeSettings(PermissionedSettingsModel):
    """Policy for the menu-bar grading snooze. Admins can lock the field to disable it."""

    enabled: BoolSetting = Field(default=False, description="Whether users may snooze grading from the menu bar.")


class EnforcementSettings(PermissionedSettingsModel):
    """How Watcher acts on tool calls. Admin-only and machine-wide; lock the field to pin a mode.

    enforce: grade and apply the result (allow, escalate, deny). observe: grade and record what would
    have been blocked, but defer every call (including ones judged safe) to the host agent's own
    permission flow, never acting on the result. paused: skip grading and defer to the host agent.
    """

    mode: EnforcementModeSetting = Field(
        default="enforce",
        description="enforce (act on grades), observe (grade but defer to the host agent), or paused (skip grading).",
    )
    escalate_after_consecutive_denies: IntSetting = Field(
        default=2,
        description=(
            "After this many consecutive gateway-grader denies, the next would-be deny escalates to a human instead."
        ),
    )
    escalate_after_accumulated_denies: IntSetting = Field(
        default=10,
        description=(
            "After this many gateway-grader denies since the last human interaction (a user prompt or an"
            " escalation a human answered), consecutive or not, the next would-be deny escalates instead."
        ),
    )


class WatcherIgnoreFilesSettings(PermissionedSettingsModel):
    """Policy for honoring in-repo ``.watcher-ignore`` files (see ``hooks/ignore_file.py``).

    Admin-only and off by default: resolved from the admin baseline like ``snooze``, so a user
    cannot self-enable it. Admins can pin the value with ``permission: locked``.
    """

    enabled: BoolSetting = Field(default=False, description="Whether in-repo .watcher-ignore files are honored.")


class PolicyMonitorSettings(PermissionedSettingsModel):
    """Graders and thresholds for the live policy pipeline that gates tool calls."""

    policy_gateway_grader_id: StrSetting = Field(
        description="Legacy custom gateway grader. Blocking review always runs the managed gateway monitor; current Watcher clients ignore this field.",
    )
    policy_triage_grader_id: StrSetting = Field(
        description="Legacy custom triage grader. Blocking review always runs the managed triage monitor; current Watcher clients ignore this field.",
    )
    # Legacy key, accepted and ignored. The pre-tool guard stage never ran: no
    # hook consumed this grader id. StrictSettingsModel forbids unknown keys, and
    # this schema validates both on-disk settings layers (including MDM-written
    # admin baselines, which are not version-managed) and org managed-settings
    # documents stored in Xylon, so dropping the field would hard-fail every
    # existing document that still names it.
    pretool_guard_grader_id: StrSetting = Field(
        default="",
        description="Legacy field, accepted and ignored.",
        json_schema_extra={"deprecated": True},
    )
    triage_max_allow_score: IntSetting = Field(
        description="Highest triage score still allowed automatically; above it the call is escalated.",
    )
    context_user_messages: ContextWindowSetting = Field(
        description='How many recent user messages a custom grader saw as context, or "all" for the whole transcript. '
        "Live grading runs the managed monitors on the whole transcript under their own context policy, so this has "
        "no effect there.",
    )
    include_tool_outputs: BoolSetting = Field(
        default=True,
        description="Whether tool results were shown to a custom grader; the tool calls themselves always were. Live "
        "grading runs the managed monitors under their own context policy, so this has no effect there.",
    )
    include_agent_reasoning: BoolSetting = Field(
        default=True,
        description="Whether the agent's reasoning blocks were shown to a custom grader. Live grading runs the managed "
        "monitors under their own context policy, so this has no effect there.",
    )
    include_triage_assessment: BoolSetting = Field(
        default=True,
        description="Whether the deep review is shown triage's score and reasoning, or grades independently.",
    )
    # deprecated(0.29.0, 2026-10-31): settings written through 0.29.x may still contain this key.
    # Keep accepting it so strict validation does not break upgrades; grading ignores its value.
    grade_by_role: BoolSetting = Field(
        default=False,
        description="Legacy field, accepted and ignored.",
        json_schema_extra={"deprecated": True},
    )
    pending_orphan_timeout_seconds: FloatSetting = Field(
        description="Seconds before a tool call still awaiting a decision is treated as orphaned.",
    )
    on_grading_failure: GradingFailureDecisionSetting = Field(
        default="escalate",
        description="What to do when grading fails: allow, deny, or escalate.",
    )
    on_grading_failure_retries: IntSetting = Field(
        default=1,
        description="How many times to retry grading before applying on_grading_failure.",
    )

    @model_validator(mode="after")
    def validate_context_user_messages(self) -> PolicyMonitorSettings:
        window = _setting_value(self.context_user_messages)
        if window != CONTEXT_WINDOW_ALL and window < 1:
            raise ValueError(CONTEXT_WINDOW_ERROR)
        return self


class TurnReviewSettings(PermissionedSettingsModel):
    """Accepted but ignored: client-side trailing turn review was removed.

    Trailing (turn-level) grading now runs server-side, so these keys no
    longer configure anything on the machine. The settings tree forbids
    unknown keys, and nothing ever deletes dead keys from a user's persisted
    settings files (writes deliberately preserve unrecognized content), so
    dropping this section would fail loading for every settings.local.yaml
    (or org/MDM overlay) that ever carried it — regardless of how many
    releases have passed. It stays until a settings-file migration scrubs
    dead keys from persisted files; there is no version-window sweep for it.
    """

    enabled: BoolSetting = Field(
        default=True,
        description="Legacy field, accepted and ignored.",
        json_schema_extra={"deprecated": True},
    )
    trailing_grader_id: StrSetting = Field(
        default="00000000-0000-0000-0000-000000000002",
        description="Legacy field, accepted and ignored.",
        json_schema_extra={"deprecated": True},
    )
    trailing_backoff_percent: IntSetting = Field(
        default=200,
        description="Legacy field, accepted and ignored.",
        json_schema_extra={"deprecated": True},
    )
    trailing_catchup_idle_seconds: IntSetting = Field(
        default=600,
        description="Legacy field, accepted and ignored.",
        json_schema_extra={"deprecated": True},
    )
    trailing_max_grade_interval_seconds: IntSetting = Field(
        default=3600,
        description="Legacy field, accepted and ignored.",
        json_schema_extra={"deprecated": True},
    )


class DecisionSyncSettings(PermissionedSettingsModel):
    """Delivery of recorded tool-call decisions to the cloud.

    Its own section rather than a key under ``turn_review``: the drain has to keep running when
    turn review is switched off, and ``turn_review.enabled`` reads as a kill switch for everything
    beneath it.
    """

    drain_interval_seconds: IntSetting = Field(
        default=30,
        description="Seconds between sweeps that retry tool-call decisions still waiting to reach the cloud.",
    )


class SuggestionSettings(PermissionedSettingsModel):
    """Accepted but ignored: suggestion mode was removed with the trailing-review UI.

    The settings tree forbids unknown keys, and nothing ever deletes dead keys
    from a user's persisted settings files, so dropping this section would
    fail loading for every existing settings.local.yaml that carried it —
    regardless of how many releases have passed. It stays until a
    settings-file migration scrubs dead keys; there is no version-window
    sweep for it.
    """

    score_threshold: IntSetting = 10
    previous_score_threshold: IntSetting = 8
    prompt_template: StrSetting = ""


class GradingSettings(PermissionedSettingsModel):
    """Grading model configuration."""

    model: OptionalStrSetting = Field(
        default=None,
        description="Override model id for grading; null uses the default model.",
    )


class UiSettings(PermissionedSettingsModel):
    """Watcher desktop UI preferences."""

    # Legacy keys, accepted and ignored. They configured the removed in-app
    # terminal (shell persistence and the terminal/detail layout preset), and
    # existing settings files (local or MDM-distributed) may still carry them
    # (including the {value: ..., permission: ...} wrapper form).
    # StrictSettingsModel forbids unknown keys, so dropping these fields would
    # hard-fail every such settings file on upgrade.
    persist_shell_terminals: BoolSetting = Field(
        default=True,
        description="Legacy field, accepted and ignored.",
        json_schema_extra={"deprecated": True},
    )
    window_management: StrSetting = Field(
        default="claude-outside-watcher",
        description="Legacy field, accepted and ignored.",
        json_schema_extra={"deprecated": True},
    )
    # deprecated(0.32.3, 2026-10-31): autostart is a machine-wide toggle, so its home is the
    # document's top level, but every client through 0.32.x persisted it here. Unlike the
    # tombstones above this key is still interpreted: a document with no top-level
    # autostart_on_login falls through to this one, so an existing machine keeps its toggle.
    autostart_on_login: BoolSetting = Field(
        default=False,
        description="Deprecated home for autostart; read only when the top-level key is absent.",
    )


class StatuslineSettings(PermissionedSettingsModel):
    """Tombstone for the removed dynamic-statusline section toggles.

    The dynamic statusline and its per-section toggles were removed (the current
    statusline is static-only, with no settings), but this model
    forbids unknown keys, so dropping the ``statusline:`` block outright would
    fail settings loading for every existing settings file (local or
    MDM-distributed) that persisted any of these fields. Everything here is
    accepted and ignored. Remove the block once persisted settings files no
    longer carry these keys — they linger until each file is rewritten, so this
    outlives the usual client compatibility window.
    """

    health_dot: BoolSetting = True
    status_label: BoolSetting = True
    score_dots: BoolSetting = True
    suggestion: BoolSetting = True
    profile_badge: BoolSetting = True
    watcher_link: BoolSetting = True


class ProfileCatalogEntry(PermissionedSettingsModel):
    """A profile entry in the catalog; its presence declares the profile and its permission governs overrides.

    Besides the permission marker and display metadata, an entry may inline a profile
    overlay: any subset of the top-level settings keys, with the same shape and merge
    semantics as a separate ``settings.<id>.yaml`` file. This lets one distributable
    ``settings.yaml`` carry full profile configuration. Inline values are only shallowly
    validated here (sub-sections have required fields a partial overlay legitimately
    omits); deep validation happens when the profile is applied, exactly like a profile
    file. ``version``, ``active_profile``, and ``profiles`` are not allowed inside an
    entry. When both an inline entry and a separate profile file configure the same
    profile, the file is applied after the inline entry and wins where they overlap.

    Two permissions apply to an entry and they govern different things. ``permission``
    says who may edit the catalog entry. ``content_permission`` says who may override
    what the entry configures, and is the entry's equivalent of the top-level
    ``permission`` in a separate profile file.
    """

    model_config = ConfigDict(extra="allow")

    name: str | None = Field(default=None, description="Display name for the profile.")
    description: str | None = Field(default=None, description="Human-readable description of the profile.")
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternate names that resolve to this profile.",
    )
    content_permission: Permission | None = Field(
        default=None,
        description=(
            "Permission applied to everything this entry configures, so one key can lock "
            "the whole profile: locked, modifiable, or additions_allowed."
        ),
    )

    @model_validator(mode="after")
    def _validate_inline_overlay_keys(self) -> ProfileCatalogEntry:
        unknown = set(self.model_extra or ()) - inline_profile_overlay_keys()
        if unknown:
            raise ValueError(
                f"Unknown keys in profile entry: {', '.join(sorted(unknown))}. "
                "A profile entry may only inline top-level settings keys."
            )
        return self


class AgentsSettings(PermissionedSettingsModel):
    """Which coding agents Watcher integrates with."""

    enabled: list[AgentName] = Field(
        default_factory=lambda: sorted(ALL_AGENTS),
        description="Coding agents Watcher monitors (claude_code, codex).",
    )


class WatcherSettings(StrictSettingsModel):
    version: int = Field(description="Schema version of this settings document.")
    name: str | None = Field(default=None, description="Display name for this settings profile.")
    description: str | None = Field(default=None, description="Human-readable description of this settings document.")
    aliases: list[str] = Field(default_factory=list, description="Alternate names that resolve to this profile.")
    active_profile: OptionalStrSetting = Field(
        default=None,
        description=(
            "Profile applied by default when none is selected. "
            "Wrap as {value: <id>, permission: locked} to pin the profile."
        ),
    )
    permission: Permission = Field(
        default="modifiable",
        description="Whether lower layers may override the document: locked, modifiable, or additions_allowed.",
    )
    profiles: dict[str, ProfileCatalogEntry | Permission] = Field(
        description="Named profiles that layer overrides on top of these settings.",
    )
    autostart_on_login: BoolSetting | None = Field(
        default=None,
        description=(
            "Launch Watcher automatically at login. Omit it (or set null) to fall back to the "
            "deprecated ui.autostart_on_login."
        ),
    )
    ui: UiSettings = Field(description="Watcher desktop UI preferences.")
    statusline: StatuslineSettings = Field(
        default=StatuslineSettings(),
        description="Accepted for backward compatibility and ignored; the dynamic statusline was removed.",
        json_schema_extra={"deprecated": True},
    )
    policy_monitors: PolicyMonitorSettings = Field(
        description="Graders and thresholds for the live policy pipeline that gates tool calls.",
    )
    snooze: SnoozeSettings = Field(
        default=SnoozeSettings(),
        description="Policy for the menu-bar grading snooze (admin-only).",
    )
    enforcement: EnforcementSettings = Field(
        default=EnforcementSettings(),
        description="How Watcher acts on tool calls: enforce, observe, or paused (admin-only).",
    )
    turn_review: TurnReviewSettings = Field(
        default=TurnReviewSettings(),
        description="Accepted for backward compatibility and ignored; client-side trailing review was removed.",
        json_schema_extra={"deprecated": True},
    )
    decision_sync: DecisionSyncSettings = Field(
        default_factory=DecisionSyncSettings,
        description="Delivery of recorded tool-call decisions to the cloud.",
    )
    suggestions: SuggestionSettings = Field(
        default=SuggestionSettings(),
        description="Accepted for backward compatibility and ignored; suggestion mode was removed.",
        json_schema_extra={"deprecated": True},
    )
    grading: GradingSettings = Field(description="Grading model configuration.")
    tool_thresholds: dict[str, ToolThresholdSetting | Permission] = Field(
        description="Per-tool suspicion-score thresholds mapping a tool name to its flag/deny thresholds. "
        "The reserved key 'unknown' holds the pair for a tool no entry, glob, or builtin default covers.",
    )
    command_rules: CommandRulesSetting = Field(
        description="Deterministic regex rules evaluated against tool calls before grading.",
    )
    managed_instructions: ManagedInstructionsSettings = Field(
        default=ManagedInstructionsSettings(),
        description="Org-managed instruction text distributed to agents.",
    )
    watcher_ignore_files: WatcherIgnoreFilesSettings = Field(
        default=WatcherIgnoreFilesSettings(),
        description="Policy for honoring in-repo .watcher-ignore files (admin-only).",
    )
    agents: AgentsSettings = Field(
        default_factory=AgentsSettings,
        description="Which coding agents Watcher integrates with.",
    )

    def autostart_on_login_enabled(self) -> bool:
        """Whether Watcher launches at login, resolved across the two places the key can live.

        The top-level key is autostart's home; ``ui.autostart_on_login`` is where clients
        through 0.32.x wrote it. Only an explicitly set top-level value wins, which is why the
        field is optional: a top-level default would permanently shadow a machine that still
        carries the nested value. Every reader resolves through here so no caller can disagree
        about which location applies.

        Top-level precedence holds only between values of equal authority: an admin lock binds
        whichever of the two locations the admin wrote it on, or a machine could shake off a
        lock on the nested key just by having saved the top-level one.
        """
        if self.autostart_on_login is None or self._autostart_locked_on_the_nested_key_only():
            return _setting_value(self.ui.autostart_on_login)
        return _setting_value(self.autostart_on_login)

    def _autostart_locked_on_the_nested_key_only(self) -> bool:
        """Whether an admin lock reaches ``ui.autostart_on_login`` but not the top-level key.

        Both a ``ui`` section lock and a document-wide one are inherited by the leaves beneath
        them, and a document-wide lock covers both locations, leaving the two equally binding.
        """
        if self.permission == "locked":
            return False
        nested_locked = self.ui.permission == "locked" or _setting_locked(self.ui.autostart_on_login)
        return nested_locked and not _setting_locked(self.autostart_on_login)


# Settings that describe the whole machine rather than one profile's behavior. A
# machine reads these from the admin baseline's top level and nowhere else, so a copy
# in a local file, a profile file, or an inline profile entry parses fine and then
# never takes effect. Both the client's diagnostic scan and the server's save-time
# validation work from this one set, so the two cannot drift apart.
ADMIN_ONLY_TOP_LEVEL_KEYS: frozenset[str] = frozenset({"enforcement", "snooze", "watcher_ignore_files"})

# Both document locations the autostart toggle can occupy, for the callers that ask about the
# key itself rather than its value. A lock on either one binds the machines whose value lives
# there, so a permission check has to consider both.
AUTOSTART_ON_LOGIN_PATHS: tuple[tuple[str, ...], ...] = (("autostart_on_login",), ("ui", "autostart_on_login"))

# Alias groups for the permission engine. This is what makes an admin lock unbypassable: a write
# to one alias is refused while any member of its group is locked.
_PERMISSION_ALIAS_GROUPS: tuple[tuple[tuple[str, ...], ...], ...] = (AUTOSTART_ON_LOGIN_PATHS,)


def permission_alias_paths(path: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Every document location whose permission binds ``path``, ``path`` itself included."""
    for group in _PERMISSION_ALIAS_GROUPS:
        if path in group:
            return group
    return (path,)


@lru_cache(maxsize=1)
def inline_profile_overlay_keys() -> frozenset[str]:
    """Top-level settings keys a profile catalog entry may inline as overlay content.

    Derived from :class:`WatcherSettings` so new top-level settings become inlinable
    without touching this list. Document-identity keys are excluded: ``version``
    describes the enclosing document, and ``active_profile`` / ``profiles`` inside a
    profile would be self-referential. ``ProfileCatalogEntry`` calls this lazily
    because it is defined before :class:`WatcherSettings`.

    The machine-wide keys in ``ADMIN_ONLY_TOP_LEVEL_KEYS`` stay in this set even
    though a profile overlay never gets to decide them. Files already on disk carry
    them, and a machine has to keep loading such a file and quietly ignoring the key
    rather than failing over it. New documents are stopped at the point where someone
    can still act on the message, which is the managed-settings save.
    """
    return frozenset(WatcherSettings.model_fields) - {"version", "active_profile", "profiles"}


class SettingsLoadIssue(BaseModel):
    source: SettingsSource
    file_path: str
    setting_path: str | None = None
    message: str


class EffectiveManagedInstructionSection(BaseModel):
    id: str
    title: str
    body: str


class EffectiveSnoozePolicy(BaseModel):
    enabled: bool
    enabled_locked: bool


class EffectiveEnforcementPolicy(BaseModel):
    """Resolved enforcement policy. The limit defaults mirror ``EnforcementSettings``
    as a convenience for tests that construct the model directly; the resolver
    (``get_enforcement_policy``) always supplies explicit values from the YAML.
    """

    mode: EnforcementMode
    escalate_after_consecutive_denies: int = 2
    escalate_after_accumulated_denies: int = 10


class EffectiveIgnoreFilePolicy(BaseModel):
    enabled: bool
    enabled_locked: bool


class IgnoredAdminOnlySetting(BaseModel):
    """An admin-only key found in a settings file that cannot set it.

    ``enforcement``, ``snooze``, and ``watcher_ignore_files`` resolve from the admin baseline only (the
    builtin default plus the global admin ``settings.yaml``). A copy of one of these keys in a local file
    or a profile file still validates against the schema but is silently dropped. ``key`` is the top-level
    key and ``file_path`` is the file it was found in, so a diagnostic can point the author at both.
    """

    key: str
    file_path: str


class EffectiveToolThreshold(BaseModel):
    flag_threshold: int
    deny_threshold: int


class ToolThresholdLockInfo(BaseModel):
    locked: bool
    flag_threshold_locked: bool
    deny_threshold_locked: bool


class EffectiveSettingsProfile(BaseModel):
    """One profile a machine can run, with the layers that declared it.

    ``builtin`` / ``admin`` / ``local`` are not exclusive: the same profile can be
    shipped by Watcher and then extended by the organization and again by the user.
    A layer counts as declaring the profile whether it used its own
    ``settings.<id>`` file or an entry in that layer's ``profiles`` catalog, since
    both are that layer saying the profile exists.
    """

    id: str
    name: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    builtin: bool
    admin: bool
    local: bool
    locked: bool


class EffectiveCommandRule(BaseModel):
    id: str
    tool_name: str
    pattern: str
    action: str
    priority: int
    label: str
    category: str
    enabled: bool
    builtin: bool
    locked: bool
    can_modify: bool
    can_delete: bool
    enabled_locked: bool
    action_locked: bool
    pattern_locked: bool
    label_locked: bool
