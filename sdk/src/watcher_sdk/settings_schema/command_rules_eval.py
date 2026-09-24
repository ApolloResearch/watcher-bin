"""Pure evaluation of command rules and per-tool thresholds against one tool call.

This is the deterministic half of Watcher's hierarchical monitoring pipeline —
the checks that run before any LLM grade — as pure functions of their inputs.
It lives in the SDK because two packages that must never import each other both
need exactly these semantics:

- **Watcher Live** (``apollo_monitor.core.command_rules_store``) feeds it rules
  and terminal actions resolved from the machine's layered settings store.
- **Xylon** (the ``/v1/hooks/pre-tool-use`` endpoint) feeds it rules and
  thresholds read from the org's managed-settings document merged onto the
  packaged builtin defaults (a tree this module can also read directly via the
  ``*_from_tree`` helpers).

A fork of the matching logic would drift — a rule that fires on the machine but
not at the gateway is a policy hole — so the store-free core lives here and the
callers stay thin.

Rule matching semantics (shared with the settings-YAML schema): a rule's
``tool_name`` is an fnmatch glob over the calling tool's name; its ``pattern``
is a Python regex searched case-insensitively (unanchored) against the command
string extracted from the tool input. Bash commands are split quote-awarely
into segments on control operators and each segment must be covered; the most
severe matching action wins (deny > escalate_human > escalate_triage > allow).
"""

from __future__ import annotations

import fnmatch
import json
import posixpath
import re
import time
from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Protocol

import regex as regex_module
from pydantic import BaseModel, TypeAdapter, ValidationError

from watcher_sdk.settings_schema.watcher_settings_yaml_helpers import (
    UNKNOWN_TOOL_THRESHOLD_KEY,
    get_path_or_none,
    resolve_tool_pattern,
    unwrap,
)
from watcher_sdk.settings_schema.watcher_settings_yaml_schema import DECISION_TO_ACTION

# The schema's lax-int coercion, reused so threshold resolution accepts exactly
# what validation accepted (see _threshold_int).
_LAX_INT: TypeAdapter[int] = TypeAdapter(int)

# Sentinels on the 1-10 suspicion scale: a threshold of 0 means "always act"
# (always flag / always deny), 11 means "never".
THRESHOLD_ALWAYS = 0
THRESHOLD_DISABLED = 11


class RuleAction(StrEnum):
    """Action a command rule can expose to the command-rule evaluator/UI.

    A ``StrEnum`` so comparisons against the raw strings stored in / loaded from
    the settings YAML keep working, while the constants give us a single source
    of truth instead of scattering ``"escalate_human"`` literals around.
    """

    DENY = "deny"
    ALLOW = "allow"
    ESCALATE_TRIAGE = "escalate_triage"
    ESCALATE_HUMAN = "escalate_human"
    OFF = "off"


# Actions that may only ever tighten a decision, never relax it.
ESCALATION_ACTIONS: frozenset[RuleAction] = frozenset(
    {RuleAction.DENY, RuleAction.ESCALATE_HUMAN, RuleAction.ESCALATE_TRIAGE}
)

# Lower number = more severe; used to pick the winning rule across matches.
# Keyed by the enum's string values so a plain-string ``action`` looks up fine.
ACTION_SEVERITY: dict[str, int] = {
    RuleAction.DENY: 0,
    RuleAction.ESCALATE_HUMAN: 1,
    RuleAction.ESCALATE_TRIAGE: 2,
    RuleAction.ALLOW: 3,
    RuleAction.OFF: 4,
}

# Provenance recorded when a tool's terminal thresholds decide instead of a rule.
TERMINAL_THRESHOLD_LABEL = "Tool threshold"
TERMINAL_THRESHOLD_PATTERN = "*"


class EvaluableCommandRule(Protocol):
    """The attributes rule evaluation reads, as a structural type.

    Both the client's store-backed ``CommandRule`` (which additionally carries
    lock/permission bookkeeping for the UI) and the server's tree-derived
    :class:`TreeCommandRule` satisfy it, so neither has to convert into the
    other's shape on the hot path.
    """

    @property
    def tool_name(self) -> str: ...
    @property
    def pattern(self) -> str: ...
    @property
    def action(self) -> str: ...
    @property
    def label(self) -> str: ...


class CommandRuleMatch(BaseModel):
    """Effective command-rule match with enough provenance to store on the decision."""

    action: str
    label: str
    pattern: str


class TreeCommandRule(BaseModel):
    """One enabled command rule read off a merged settings tree, ready for evaluation.

    The lean projection of a ``command_rules`` entry: identity plus the four
    fields matching reads (:class:`EvaluableCommandRule`) and ``priority`` for
    evaluation order. The client's richer ``EffectiveCommandRule`` adds
    lock/permission provenance, which is UI bookkeeping the evaluator never
    reads and a server has no layers to compute from.
    """

    id: str
    tool_name: str
    pattern: str
    action: str
    priority: int
    label: str


class ToolThresholdPair(BaseModel):
    """A tool's resolved (flag, deny) suspicion-score thresholds."""

    flag_threshold: int
    deny_threshold: int


type ToolInput = str | dict[str, Any] | list[Any] | None


def _stringify_tool_input(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def _extract_named_input(tool_input: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = tool_input.get(key)
        if value is not None:
            return _stringify_tool_input(value)
    return None


def extract_command_string(tool_name: str, tool_input: ToolInput) -> str | None:
    """The string rule patterns are matched against, per tool.

    Bash reads its ``command``/``cmd`` field, file tools their ``file_path``;
    every other dict input is JSON-serialized whole so a rule can still match
    on any part of it. ``None`` means there is nothing to match (the caller
    treats that as "no rule fires").
    """
    if tool_input is None:
        return None
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except (json.JSONDecodeError, TypeError):
            return tool_input

    if isinstance(tool_input, dict):
        if tool_name == "Bash":
            return _extract_named_input(tool_input, ("command", "cmd"))
        if tool_name in ("Edit", "Write"):
            return _extract_named_input(tool_input, ("file_path",))
        return _stringify_tool_input(tool_input)
    if tool_name in ("Bash", "Edit", "Write"):
        return None
    return _stringify_tool_input(tool_input)


# Multi-char control operators, checked before their single-char prefixes so
# `&&`/`||`/`|&` win over `&`/`|`.
_TWO_CHAR_OPERATORS = ("&&", "||", "|&")


def _control_operator_at(cmd: str, i: int) -> str | None:
    # Return the command-separating shell operator starting at cmd[i], or None.
    # Caller guarantees i is OUTSIDE any quotes. Redirect tokens are excluded so
    # they stay attached to their command rather than splitting it:
    #   - background/sequencing `&` must not match `&&`, `&>` (stdout+stderr
    #     redirect), or fd-dup like `2>&1` / `>&2` / `<&-`.
    #   - a lone `|` (pipe) must not match the `>|` noclobber-override redirect.
    if cmd[i : i + 2] in _TWO_CHAR_OPERATORS:
        return cmd[i : i + 2]
    char = cmd[i]
    if char in (";", "\n"):
        return char
    prev = cmd[i - 1] if i > 0 else ""
    nxt = cmd[i + 1] if i + 1 < len(cmd) else ""
    if char == "|" and prev != ">":
        return char
    if char == "&" and prev not in ("<", ">", "&") and nxt != ">":
        return char
    return None


def split_compound_command(cmd: str) -> list[str]:
    """Split a compound Bash command on UNQUOTED control operators only.

    Operators inside single/double quotes (e.g. ``echo 'R&D'``,
    ``echo "done & git push"``) are literal text and must not split — otherwise
    benign commands fall through to grading and quoted text is mistaken for a
    real command. Newlines split like ``;``; heredoc bodies are re-matched whole
    by :func:`evaluate_command_rules`'s full-command path.
    """
    segments: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    i, n = 0, len(cmd)
    while i < n:
        char = cmd[i]
        if quote is not None:
            buf.append(char)
            # Inside double quotes a backslash escapes the next char (incl. `"`);
            # single quotes have no escapes.
            if char == "\\" and quote == '"' and i + 1 < n:
                buf.append(cmd[i + 1])
                i += 2
                continue
            if char == quote:
                quote = None
            i += 1
            continue
        if char in ("'", '"'):
            quote = char
            buf.append(char)
            i += 1
            continue
        if char == "\\" and i + 1 < n:
            # An escaped operator (e.g. `\&`) is literal, never a separator.
            buf.append(char)
            buf.append(cmd[i + 1])
            i += 2
            continue
        operator = _control_operator_at(cmd, i)
        if operator is not None:
            segments.append("".join(buf))
            buf = []
            i += len(operator)
            continue
        buf.append(char)
        i += 1
    segments.append("".join(buf))
    return [segment.strip() for segment in segments if segment.strip()]


# A `cd` whose target we can't prove stays inside the project tree makes later
# relative-path rules untrustworthy — e.g. `cd /etc` then `cat passwd` reads
# /etc/passwd while still matching the read-only allow rule, bypassing the
# "Read outside project tree" triage. Only a plain relative path with no `..`
# escape (and no `~`/`/` absolute-or-home, `-` previous-dir, `$`/quotes/spaces
# variable-or-expansion) is treated as in-project; anything else makes the whole
# command fall through to the grader instead of auto-allowing.
_CD_SEGMENT = re.compile(r"cd(?:\s+(?P<arg>.*))?$")
_SAFE_RELATIVE_PATH = re.compile(r"(?:\./)?[\w.][\w./-]*")


def cd_is_unsafe(segment: str) -> bool:
    """Whether a Bash segment is a ``cd`` that may leave the project tree."""
    match = _CD_SEGMENT.match(segment)
    if match is None:
        return False  # not a `cd` segment
    arg = (match.group("arg") or "").strip()
    if not arg:
        return True  # bare `cd` → $HOME, outside the project
    if _SAFE_RELATIVE_PATH.fullmatch(arg) is None:
        return True  # absolute, ~, -, $VAR, quoted, multi-token, …
    return ".." in arg.split("/")  # no parent-dir escape


def extract_redirect_destinations(cmd: str) -> list[str]:
    """File paths a Bash command redirects output into (``>``/``>>``/``>|``/``>&`` targets).

    ``>|`` is ``>`` with bash's noclobber guard overridden — it writes the file
    the same way — so its target is extracted like a plain ``>`` target;
    otherwise ``echo x >| .env`` would slip past the redirect→Write rematch. An
    optional fd prefix (``2>|``) is handled by the segment already excluding it.
    ``>&``/``>>&`` send stdout+stderr to a FILE (``echo A >& out`` writes
    ``out``), so the destination has to be extracted like any other; ``2>&1``,
    ``>&2`` and ``>&-`` are fd duplications, not files, and the lookahead is
    what keeps them out.
    """
    matches = re.findall(
        r">>?(?:\||&(?![0-9-]))?\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s|;&<>]+))",
        cmd,
    )
    return [dq or sq or bare for dq, sq, bare in matches if dq or sq or bare]


def _pattern_matches(pattern: str, segment: str, match_timeout: float | None) -> bool:
    """Whether an org-supplied ``pattern`` matches ``segment``, execution bounded.

    ``pattern`` is org-authored and matched against a command string that, at
    the hook endpoint, is influenced by the watched agent — so on that shared
    path a catastrophic-backtracking pattern could peg a worker. Every search
    runs under the ``regex`` module (a re-compatible superset with far better
    backtracking behaviour and a per-search timeout) whether or not a timeout
    is requested: one engine and one flag set mean enabling the timeout, or
    moving evaluation between client and server, can never change whether a
    rule matches — the exact disagreement this shared evaluator exists to
    prevent (stdlib ``re`` and ``regex`` case-fold some Unicode differently
    under IGNORECASE). With ``match_timeout`` set the search raises
    ``TimeoutError`` past the deadline; the caller treats that as "could not
    evaluate" and grades. An uncompilable pattern is skipped (the save-time
    validators reject those, so one here means a hand-edited local file).
    """
    try:
        return regex_module.compile(pattern, regex_module.IGNORECASE).search(segment, timeout=match_timeout) is not None
    except regex_module.error:
        return False


# Tools whose matched string is a filesystem path rather than shell text. Redirect
# destinations are matched under "Write" and get the same treatment. Bash segments are
# excluded: canonicalising arbitrary command text would change what the command says.
_PATH_ARGUMENT_TOOLS = frozenset({"Edit", "Write"})


def match_segment(
    segment: str,
    tool_name: str,
    rules: Sequence[EvaluableCommandRule],
    match_timeout: float | None = None,
    deadline: float | None = None,
) -> EvaluableCommandRule | None:
    """The first rule (in the given order) matching one command segment.

    ``rules`` must already be in evaluation order (ascending priority); a rule's
    ``tool_name`` is an fnmatch glob, its ``pattern`` an unanchored
    case-insensitive regex. ``match_timeout`` bounds each pattern search (see
    `_pattern_matches`); ``deadline`` (a ``time.monotonic()`` instant) bounds
    the whole evaluation across rules and segments — it is checked before every
    search and also caps that search's timeout, so a call with many segments
    and many near-ceiling patterns stops at the deadline rather than at
    rules × segments × ceiling. Either bound raises ``TimeoutError``.
    """
    candidates = [segment]
    if tool_name in _PATH_ARGUMENT_TOOLS and segment:
        # `//etc/x` and `/repo/../etc/x` open the file `/etc/x` names but dodge every rule
        # anchored on it. Collapsing is lexical only — the hook must not stat anything — and
        # `posixpath.normpath` keeps a leading `//` verbatim, so those are collapsed here too.
        # The raw spelling stays first, so a rule can only gain matches and never lose one.
        collapsed = re.sub(r"^/+", "/", posixpath.normpath(segment))
        if collapsed != segment:
            candidates.append(collapsed)
    for rule in rules:
        if not fnmatch.fnmatchcase(tool_name, rule.tool_name):
            continue
        timeout = match_timeout
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("command-rule evaluation passed its deadline")
            timeout = remaining if timeout is None else min(timeout, remaining)
        if any(_pattern_matches(rule.pattern, candidate, timeout) for candidate in candidates):
            return rule
    return None


def evaluate_command_rules(
    tool_name: str,
    tool_input: ToolInput,
    rules: Sequence[EvaluableCommandRule],
    terminal_action: str | None,
    match_timeout: float | None = None,
    deadline: float | None = None,
) -> CommandRuleMatch | None:
    """The effective command-rule decision for one tool call, or ``None`` to grade.

    ``terminal_action`` is the caller-resolved terminal threshold action for
    ``tool_name`` (see :func:`terminal_rule_action`); when set it pre-empts the
    rule engine entirely. Otherwise: Bash inputs are split into segments and
    each matched independently; the full command is re-matched but may only
    escalate (so multiline constructs like destructive SQL in a heredoc are
    caught without breaking compound allow-listing); redirect destinations are
    re-matched against Write rules. The most severe match wins if it denies or
    escalates to a human; an unsafe ``cd`` or any ``escalate_triage`` match or
    any unmatched segment falls through to the grader (returns ``None``); a
    fully allow-covered command returns its allow match.

    ``match_timeout`` bounds every org-pattern search and ``deadline`` the
    evaluation as a whole (see `match_segment`); pass them on shared-infra
    paths where the command string is attacker-influenced. Exceeding either
    raises ``TimeoutError`` for the caller to treat as "could not evaluate".
    """
    if terminal_action is not None:
        return CommandRuleMatch(
            action=terminal_action,
            label=TERMINAL_THRESHOLD_LABEL,
            pattern=TERMINAL_THRESHOLD_PATTERN,
        )

    command_str = extract_command_string(tool_name, tool_input)
    if not command_str:
        return None

    segments = split_compound_command(command_str) if tool_name == "Bash" else [command_str]
    # A command that is only control operators or whitespace (";", "&&", …)
    # splits to zero segments. Nothing matched anything, so no rule may allow
    # it — fall through to the grader.
    if not segments:
        return None
    matches = [match_segment(segment, tool_name, rules, match_timeout, deadline) for segment in segments]

    if tool_name == "Bash":
        # Segment splitting (including on newlines) hides rules that need the
        # whole command for context — e.g. a destructive SQL statement inside a
        # heredoc piped to `psql`. Re-match the full command, but only let it
        # ESCALATE, never relax: this keeps compound-command allow-listing
        # working while still catching multiline destructive constructs.
        full_match = match_segment(command_str, tool_name, rules, match_timeout, deadline)
        if full_match is not None and full_match.action in ESCALATION_ACTIONS:
            matches.append(full_match)
        for dest in extract_redirect_destinations(command_str):
            redirect_match = match_segment(dest, "Write", rules, match_timeout, deadline)
            if redirect_match is not None:
                matches.append(redirect_match)

    matched_rules = [match for match in matches if match is not None]
    if matched_rules:
        most_severe_match = min(matched_rules, key=lambda match: ACTION_SEVERITY[match.action])
        if most_severe_match.action in (RuleAction.DENY, RuleAction.ESCALATE_HUMAN):
            return CommandRuleMatch(
                action=most_severe_match.action,
                label=most_severe_match.label,
                pattern=most_severe_match.pattern,
            )

    # A `cd` to an out-of-project / unknown directory can't auto-allow: later
    # relative reads (`cd /etc` → `cat passwd`) would dodge the outside-project
    # triage. Fall through to the grader (human escalations above still win).
    if tool_name == "Bash" and any(cd_is_unsafe(segment) for segment in segments):
        return None

    if any(match and match.action == RuleAction.ESCALATE_TRIAGE for match in matches):
        return None

    if any(match is None for match in matches):
        return None

    # Segments are non-empty and every one matched, so this is the first
    # segment's (allow) match; the assert is for the type checker.
    first = matches[0]
    assert first is not None
    return CommandRuleMatch(action=first.action, label=first.label, pattern=first.pattern)


def apply_org_posture(judged: str | None, mode: str) -> str:
    """Derive the caller-facing decision from a judgment and the org posture.

    The hook API's string vocabulary: `judged` is `allow`/`deny`/
    `escalate` (or `None` when grading never ran), `mode` is the org's
    enforcement mode, and the result is the judged value or `deferred`.
    `enforce` applies the judgment verbatim; `observe` defers everything,
    judged allows included, because observe exists to measure without changing
    behaviour; `paused` still applies deterministic denies but defers
    escalations, since nobody is watching a review queue on a paused org.
    Any unrecognized mode applies verbatim, matching the server's coercion of
    an unknown stored mode to `enforce`.

    This table lives SDK-side so a client applying decisions locally (the
    `pre_tool_use` convenience) and the hook endpoint can never disagree —
    the server's `apply_org_posture` delegates here.
    """
    if judged is None or mode == "observe" or (mode == "paused" and judged == "escalate"):
        return "deferred"
    return judged


def terminal_rule_action(flag_threshold: int, deny_threshold: int) -> str | None:
    """The action a tool's threshold pair forces regardless of rules, or ``None``.

    Both disabled → always allow; deny at 0 → always deny; flag at 0 with deny
    disabled → always escalate to a human. Any other pair leaves the decision to
    the rules and graders.
    """
    if flag_threshold >= THRESHOLD_DISABLED and deny_threshold >= THRESHOLD_DISABLED:
        return RuleAction.ALLOW
    if deny_threshold == THRESHOLD_ALWAYS:
        return RuleAction.DENY
    if flag_threshold == THRESHOLD_ALWAYS and deny_threshold >= THRESHOLD_DISABLED:
        return RuleAction.ESCALATE_HUMAN
    return None


def _is_tool_threshold_entry(value: object) -> bool:
    return isinstance(value, dict)


def _threshold_int(value: Any) -> int | None:
    """A threshold value as an int, accepting what the settings schema coerces.

    The schema's lax-int validation accepts every numeric spelling a YAML
    author plausibly writes — a quoted `"0"`, an exact-integer float `0.0`,
    a quoted `"0.0"` — so a schema-valid tree can carry one, and reading it
    strictly here would silently swap the author's pair for the fallback,
    exactly the believed-but-not-in-force policy the override validation
    rejects. Coercion is pydantic's own lax-int rule, so the two layers cannot
    drift. The one deliberate exception is a bool: the schema tolerates
    `true` (as 1), but a boolean threshold is an authoring mistake rather
    than a spelling of a number, and treating it as malformed is longstanding,
    pinned behavior on the client path.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return _LAX_INT.validate_python(value)
    except ValidationError:
        return None


def _pair_from_entry(entry: Any) -> ToolThresholdPair | None:
    """A threshold entry's (flag, deny) pair, unwrapped; ``None`` when malformed."""
    if not isinstance(entry, dict):
        return None
    flag_threshold = _threshold_int(unwrap(entry.get("flag_threshold")))
    deny_threshold = _threshold_int(unwrap(entry.get("deny_threshold")))
    if flag_threshold is None or deny_threshold is None:
        return None
    return ToolThresholdPair(flag_threshold=flag_threshold, deny_threshold=deny_threshold)


def tool_threshold_pair_from_tree(tree: dict[str, Any], tool_name: str) -> ToolThresholdPair | None:
    """The (flag, deny) pair a merged settings tree gives a tool, or ``None``.

    Resolution matches the client store: the tool's own entry wins, else the
    last-defined matching glob entry. ``None`` when nothing covers the tool or
    the covering entry is malformed — callers decide the fallback (the client
    consults its builtin table; the server uses
    :func:`resolve_tool_thresholds_from_tree`, whose merged tree always carries
    the reserved ``unknown`` entry).
    """
    tool_thresholds = get_path_or_none(tree, ("tool_thresholds",))
    if not isinstance(tool_thresholds, dict):
        return None
    threshold_name = resolve_tool_pattern(tool_thresholds, tool_name, _is_tool_threshold_entry)
    if threshold_name is None:
        return None
    return _pair_from_entry(tool_thresholds.get(threshold_name))


def terminal_rule_action_for_tool(tree: dict[str, Any], tool_name: str) -> str | None:
    """The terminal threshold action a merged settings tree forces for a tool."""
    threshold = tool_threshold_pair_from_tree(tree, tool_name)
    if threshold is None:
        return None
    return terminal_rule_action(threshold.flag_threshold, threshold.deny_threshold)


def resolve_tool_thresholds_from_tree(tree: dict[str, Any], tool_name: str) -> ToolThresholdPair:
    """A tool's effective thresholds from a merged settings tree, fallback included.

    For a tool nothing covers, the reserved ``unknown`` entry supplies the pair
    (the merge base is the packaged builtin document, which always carries it).
    The literal below is reached only when the tree was not built on those
    builtins — it reproduces the pair the client hardcodes for the same broken
    state.
    """
    resolved = tool_threshold_pair_from_tree(tree, tool_name)
    if resolved is not None:
        return resolved
    table = get_path_or_none(tree, ("tool_thresholds",))
    unknown = _pair_from_entry(table.get(UNKNOWN_TOOL_THRESHOLD_KEY)) if isinstance(table, dict) else None
    if unknown is not None:
        return unknown
    return ToolThresholdPair(flag_threshold=6, deny_threshold=THRESHOLD_DISABLED)


def evaluate_tool_call_from_tree(
    tree: dict[str, Any], tool_name: str, tool_input: ToolInput, match_timeout: float | None = None
) -> CommandRuleMatch | None:
    """One-call deterministic evaluation of a tool call against a settings tree.

    The client-side entry point for SDK consumers: the same composition the
    Xylon hook endpoint runs server-side — the tool's terminal threshold
    action, then the tree's command rules — so an integrator can pre-filter
    tool calls locally at zero latency and reserve the hook endpoint for the
    graded stages. ``tree`` is a merged settings tree: the packaged builtins
    (``load_builtin_settings("settings.yaml")``) with the org's resolved
    managed-settings document applied via ``merge_admin``. Returns ``None``
    when nothing deterministic decides and the call should be graded.
    ``match_timeout`` bounds each org-pattern search (see
    :func:`_pattern_matches`); pass it when the command string is
    attacker-influenced.

    Extracts the rule list from the tree on every call; a hot loop should
    pre-extract once with :func:`command_rules_from_tree` and call
    :func:`evaluate_command_rules` directly — deriving the terminal action from
    :func:`resolve_tool_thresholds_from_tree` as done here, not from
    :func:`terminal_rule_action_for_tool`, which skips the reserved ``unknown``
    fallback and would let a rule match past a terminal fallback policy the
    endpoint enforces.
    """
    thresholds = resolve_tool_thresholds_from_tree(tree, tool_name)
    return evaluate_command_rules(
        tool_name,
        tool_input,
        command_rules_from_tree(tree),
        terminal_rule_action(thresholds.flag_threshold, thresholds.deny_threshold),
        match_timeout=match_timeout,
    )


def command_rules_from_tree(tree: dict[str, Any]) -> list[TreeCommandRule]:
    """The enabled command rules of a merged settings tree, in evaluation order.

    The projection the server evaluates an org's admin baseline with: enabled
    rules only (``decision != "off"``), sorted by priority, each field
    unwrapped from its optional ``{value, permission}`` form. A rule whose tool
    has terminal thresholds carries that terminal action instead of its own
    (matching the client store, where a tool threshold overrides every rule for
    that tool — this matters for cross-tool matching such as redirect
    destinations checked against Write rules). Structurally malformed rules are
    skipped: the save-time validators reject them, so one here means a
    hand-built tree, and dropping the rule beats failing the whole evaluation.
    ``category`` is required even though the evaluator never reads it, because
    the client store skips rules without one — a rule enforced at the gateway
    but not on machines (or vice versa) is exactly the divergence this module
    exists to prevent.
    """
    raw_rules = get_path_or_none(dict(tree), ("command_rules", "rules"))
    if not isinstance(raw_rules, list):
        return []
    rules: list[TreeCommandRule] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            continue
        rule = _tree_command_rule(tree, raw_rule)
        if rule is not None:
            rules.append(rule)
    return sorted(rules, key=lambda rule: rule.priority)


def _tree_command_rule(tree: dict[str, Any], raw_rule: dict[str, Any]) -> TreeCommandRule | None:
    rule_id = raw_rule.get("id")
    if not isinstance(rule_id, str):
        return None
    tool_name = unwrap(raw_rule.get("tool_name"))
    pattern = unwrap(raw_rule.get("regex"))
    label = unwrap(raw_rule.get("name"))
    category = unwrap(raw_rule.get("category"))
    priority = unwrap(raw_rule.get("priority"))
    decision = unwrap(raw_rule.get("decision", "triage"))
    if not isinstance(tool_name, str) or not isinstance(pattern, str) or not isinstance(label, str):
        return None
    if not isinstance(category, str):
        return None
    if not isinstance(priority, int) or isinstance(priority, bool):
        return None
    if decision == "off" or decision not in DECISION_TO_ACTION:
        return None
    action = terminal_rule_action_for_tool(tree, tool_name) or DECISION_TO_ACTION[decision]
    return TreeCommandRule(
        id=rule_id,
        tool_name=tool_name,
        pattern=pattern,
        action=action,
        priority=priority,
        label=label,
    )
