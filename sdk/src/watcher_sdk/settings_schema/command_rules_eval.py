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
import shlex
import time
from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Protocol

import regex as regex_module
from pydantic import BaseModel, ConfigDict, SkipValidation, TypeAdapter, ValidationError

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

RULE_MATCH_TIMEOUT_SECONDS = 0.25
RULE_EVALUATION_BUDGET_SECONDS = 2.0
MAX_RULE_PATTERN_LENGTH = 16_384
MAX_COMMAND_LENGTH = 131_072


class RuleEvaluationLimitError(Exception):
    """The input exceeds the rule evaluator's supported resource limits."""


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


class _CompiledPattern(Protocol):
    """The parts of a compiled ``regex`` pattern the evaluator uses; the package ships no type stubs."""

    @property
    def pattern(self) -> str: ...
    def search(self, string: str, *, timeout: float | None = None) -> object | None: ...
    def match(self, string: str, *, timeout: float | None = None) -> object | None: ...


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


_SHELL_TOOL_NAMES = frozenset(
    {"bash", "sh", "zsh", "shell", "shell_command", "exec_command", "powershell", "pwsh", "cmd"}
)
_SHELL_CONTROL_WORDS = frozenset(
    {
        "!",
        ".",
        "if",
        "then",
        "elif",
        "else",
        "fi",
        "for",
        "while",
        "until",
        "do",
        "done",
        "case",
        "esac",
        "select",
        "in",
        "function",
        "time",
        "repeat",
        "foreach",
        "end",
        "coproc",
        "builtin",
        "command",
        "exec",
        "eval",
        "source",
        "noglob",
        "nocorrect",
        "export",
        "declare",
        "typeset",
        "local",
        "readonly",
        "set",
        "unset",
        "alias",
        "unalias",
        "hash",
        "enable",
        "trap",
        "setopt",
        "unsetopt",
        "emulate",
    }
)


def is_shell_input(tool_name: str, tool_input: ToolInput) -> bool:
    """Recognize shell input without granting aliases another tool's allow rules."""
    if tool_name in {"Edit", "Write", "apply_patch"}:
        return False
    if tool_name.casefold() in _SHELL_TOOL_NAMES:
        return True
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except ValueError:
            return False
    return isinstance(tool_input, dict) and ("command" in tool_input or "cmd" in tool_input)


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
    """Whether a Bash segment changes to an unknown or out-of-project directory.

    Directory stacks and wrapped directory changes need shell state the rule
    evaluator does not have. Only a plain relative ``cd`` can use allow rules.
    """
    try:
        words = shlex.split(segment)
    except ValueError:
        return True
    if not words:
        return False
    if words[0] in {"pushd", "popd"}:
        return True
    if any(word in {"cd", "pushd", "popd"} for word in words[1:]) and (
        words[0] in {"builtin", "command", "env", "!", "time", "noglob", "nocorrect"}
        or "=" in words[0]
        or ">" in words[0]
    ):
        return True
    match = _CD_SEGMENT.match(segment)
    if match is None:
        return words[0] == "cd"  # quoted command names are not plain `cd` segments
    arg = (match.group("arg") or "").strip()
    if not arg:
        return True  # bare `cd` → $HOME, outside the project
    if _SAFE_RELATIVE_PATH.fullmatch(arg) is None:
        return True  # absolute, ~, -, $VAR, quoted, multi-token, …
    return ".." in arg.split("/")  # no parent-dir escape


def shell_command_needs_review(command: str) -> bool:
    """Reject automatic approval when shell expansion can change the matched text.

    This is a conservative syntax check, not a shell interpreter. Literal quoted
    arguments are supported; expansions, grouped commands and escaped word
    spellings need grading. Deny and human rules still apply.
    """
    quote: str | None = None
    word_prefix = ""
    index = 0
    while index < len(command):
        char = command[index]
        index += 1
        if quote == "'":
            if char == "'":
                quote = None
                if index < len(command) and command[index] not in " \t\n;|&<>":
                    return True
            continue
        if char == "\\":
            if quote == '"' and index < len(command) and command[index] not in '$`"\\\n':
                continue
            if index == len(command) or command[index] not in " \t;&|\"'()<>\\$`":
                return True
            index += 1
            if quote is None:
                word_prefix += "escaped"
            continue
        if char in "$`":
            return True
        if quote == '"':
            if char == '"':
                quote = None
                if index < len(command) and command[index] not in " \t\n;|&<>":
                    return True
            continue
        if char in "'\"":
            # A literal prefix glued to a quote can hide part of a flag or value
            # from an allow rule (`git branch -v"D"` runs `-vD`). A complete
            # `NAME=` or a lone `+` (as in `date +"%F"`) shows as much as the
            # fully quoted spelling does, so those are accepted.
            if (
                word_prefix
                and word_prefix != "+"
                and re.fullmatch(r"(?:[a-zA-Z_][a-zA-Z_0-9]*|--?[a-zA-Z][a-zA-Z0-9-]*)=", word_prefix) is None
            ):
                return True
            quote = char
        elif char in "(){}<#" or (char.isspace() and char not in " \t\n") or ord(char) < 9:
            return True
        elif char in " \t\n;|&>":
            word_prefix = ""
        else:
            word_prefix += char
    if quote is not None:
        return True
    for segment in split_compound_command(command):
        try:
            words = shlex.split(segment)
        except ValueError:
            return True
        if words and (
            words[0] in _SHELL_CONTROL_WORDS or ">" in words[0] or re.match(r"[a-zA-Z_][a-zA-Z_0-9]*=", words[0])
        ):
            return True
    return any(any(char in destination for char in "*?[]~=") for destination in extract_redirect_destinations(command))


def extract_redirect_destinations(cmd: str) -> list[str]:
    """File paths a Bash command redirects output into (``>``/``>>``/``>|``/``>&`` targets).

    ``>|`` is ``>`` with bash's noclobber guard overridden — it writes the file
    the same way — so its target is extracted like a plain ``>`` target;
    otherwise ``echo x >| .env`` would slip past the redirect→Write rematch. An
    optional fd prefix (``2>|``) is handled by the segment already excluding it.
    ``>&``/``>>&`` send stdout+stderr to a FILE (``echo A >& out`` writes
    ``out``), so the destination has to be extracted like any other; ``2>&1``,
    ``>&2`` and ``>&-`` are fd duplications, not files. The whole word must be a
    descriptor; a path beginning with a digit is still a file. Zsh's ``>!``
    variants also write files, since the Bash hook name can carry zsh commands.
    """
    matches = re.finditer(
        r"""(?P<operator>(?:&>>?|>>?&|>>?)[!|]?)\s*"""
        r"""(?P<word>(?:[^\s|;&<>"'\\]|\\[\s\S]|"(?:[^"\\]|\\[\s\S])*"|'[^']*')+)""",
        cmd,
    )
    destinations: list[str] = []
    for match in matches:
        raw_word = match["word"]
        for spelling in dict.fromkeys([raw_word, raw_word.replace("\\\n", "")]):
            try:
                words = shlex.split(spelling)
            except ValueError:
                continue
            if not words:
                continue
            destination = words[0]
            if match["operator"] in {">&", ">>&"} and re.fullmatch(r"(?:[0-9]+-?|-)", destination):
                continue
            destinations.append(destination)
        # A quoted path inside an embedded program can end before the following
        # language punctuation, which is not part of the destination filename.
        quoted = re.match(r"""(?:"([^"]*)"|'([^']*)')""", raw_word)
        if quoted is not None:
            quoted_path = quoted[1] or quoted[2]
            if quoted_path and not (
                match["operator"] in {">&", ">>&"} and re.fullmatch(r"(?:[0-9]+-?|-)", quoted_path)
            ):
                destinations.append(quoted_path)
    return list(dict.fromkeys(destinations))


def _pattern_matches(pattern: _CompiledPattern, segment: str, match_timeout: float, *, match_from_start: bool) -> bool:
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
    evaluate" and grades. Patterns arrive compiled by `_valid_rules`, once per
    evaluation; a malformed active rule suppresses all automatic approvals for
    this call.

    ``match_from_start`` keeps normalized echo/printf output from introducing a
    command match inside its literal arguments. Raw candidates always use search.
    """
    match = pattern.match if match_from_start else pattern.search
    return match(segment, timeout=match_timeout) is not None


# Tools whose matched string is a filesystem path rather than shell text. Redirect
# destinations are matched under "Write" and get the same treatment. Bash segments are
# excluded: canonicalising arbitrary command text would change what the command says.
_PATH_ARGUMENT_TOOLS = frozenset({"Edit", "Write"})


def _remaining_time(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("command-rule evaluation passed its deadline")
    return remaining


class _CompiledRule(BaseModel):
    """An applicable rule and its pattern, compiled once for one evaluation."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    rule: SkipValidation[EvaluableCommandRule]
    compiled: SkipValidation[_CompiledPattern]


def _valid_rules(rules: Sequence[EvaluableCommandRule], tool_names: set[str], deadline: float) -> list[_CompiledRule]:
    """Keep applicable restrictions, suppressing allows if any active rule is invalid."""
    valid: list[_CompiledRule] = []
    has_invalid_rule = False
    for rule in rules:
        _remaining_time(deadline)
        if rule.action == RuleAction.OFF or not any(fnmatch.fnmatchcase(name, rule.tool_name) for name in tool_names):
            continue
        if rule.action not in ACTION_SEVERITY or len(rule.pattern) > MAX_RULE_PATTERN_LENGTH:
            has_invalid_rule = True
            continue
        try:
            compiled = regex_module.compile(rule.pattern, regex_module.IGNORECASE)
        except (regex_module.error, RecursionError, ValueError, OverflowError):
            has_invalid_rule = True
            continue
        valid.append(_CompiledRule(rule=rule, compiled=compiled))
    return [entry for entry in valid if entry.rule.action != RuleAction.ALLOW] if has_invalid_rule else valid


def _decisive_rules(rules: list[_CompiledRule]) -> list[_CompiledRule]:
    """The rules that can still change the outcome once approval is impossible.

    Only a deny or human-review match decides a call that cannot be approved.
    Every rule before the last of those stays, because each segment takes the
    first matching rule in priority order: an earlier allow or triage rule can
    shadow a later deny for the same segment, and dropping it would let that
    deny fire.
    """
    decisive = (RuleAction.DENY, RuleAction.ESCALATE_HUMAN)
    last = max((index for index, entry in enumerate(rules) if entry.rule.action in decisive), default=-1)
    return rules[: last + 1]


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
    Defaults cap each search at 250 ms, with a two-second budget checked between
    operations. Compilation of trusted policy patterns cannot be interrupted.
    Invalid applicable rules suppress allows while preserving valid restrictions.
    """
    if len(segment) > MAX_COMMAND_LENGTH and is_shell_input(tool_name, segment):
        raise RuleEvaluationLimitError("command exceeds the rule input limit")
    deadline = (
        min(deadline, time.monotonic() + RULE_EVALUATION_BUDGET_SECONDS)
        if deadline is not None
        else (time.monotonic() + RULE_EVALUATION_BUDGET_SECONDS)
    )
    compiled_rules = _valid_rules(rules, {tool_name}, deadline)
    return _match_segment(segment, tool_name, compiled_rules, match_timeout, deadline, normalize_shell=True)


def _match_segment(
    segment: str,
    tool_name: str,
    rules: Sequence[_CompiledRule],
    match_timeout: float | None,
    deadline: float,
    *,
    normalize_shell: bool,
) -> EvaluableCommandRule | None:
    candidates = [segment]
    if tool_name in _PATH_ARGUMENT_TOOLS and segment:
        # `//etc/x` and `/repo/../etc/x` open the file `/etc/x` names but dodge every rule
        # anchored on it. Collapsing is lexical only — the hook must not stat anything — and
        # `posixpath.normpath` keeps a leading `//` verbatim, so those are collapsed here too.
        # The raw spelling stays first, so a rule can only gain matches and never lose one.
        collapsed = re.sub(r"^/+", "/", posixpath.normpath(segment))
        if collapsed != segment:
            candidates.append(collapsed)
    restriction_candidates = candidates.copy()
    output_command_candidate: str | None = None
    if tool_name == "Bash" and normalize_shell:
        try:
            words = shlex.split(segment)
        except ValueError:
            words = None
        if words is not None:
            normalized = shlex.join(words)
            if normalized != segment:
                restriction_candidates.append(normalized)
                if words and words[0] in {"echo", "printf"}:
                    output_command_candidate = normalized
    for entry in rules:
        rule = entry.rule
        if not fnmatch.fnmatchcase(tool_name, rule.tool_name):
            continue
        ceiling = (
            RULE_MATCH_TIMEOUT_SECONDS if match_timeout is None else min(match_timeout, RULE_MATCH_TIMEOUT_SECONDS)
        )
        for candidate in restriction_candidates if rule.action in ESCALATION_ACTIONS else candidates:
            timeout = min(ceiling, _remaining_time(deadline))
            if _pattern_matches(
                entry.compiled, candidate, timeout, match_from_start=candidate == output_command_candidate
            ):
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
    evaluation as a whole (see `match_segment`). Both have finite defaults on
    client and server; callers can supply tighter budgets. Exceeding either
    raises ``TimeoutError`` for the caller to treat as "could not evaluate".
    Shell input longer than ``MAX_COMMAND_LENGTH`` raises
    ``RuleEvaluationLimitError``, because its parsing runs outside those
    budgets. Other tools only run bounded searches, so any length is evaluated.
    """
    if terminal_action is not None:
        return CommandRuleMatch(
            action=terminal_action,
            label=TERMINAL_THRESHOLD_LABEL,
            pattern=TERMINAL_THRESHOLD_PATTERN,
        )

    deadline = (
        min(deadline, time.monotonic() + RULE_EVALUATION_BUDGET_SECONDS)
        if deadline is not None
        else (time.monotonic() + RULE_EVALUATION_BUDGET_SECONDS)
    )
    command_str = extract_command_string(tool_name, tool_input)
    if not command_str:
        return None
    shell_input = is_shell_input(tool_name, tool_input)
    if shell_input and len(command_str) > MAX_COMMAND_LENGTH:
        raise RuleEvaluationLimitError("command exceeds the rule input limit")

    compiled_rules = _valid_rules(rules, {tool_name, "Write"} if shell_input else {tool_name}, deadline)
    segments = split_compound_command(command_str) if shell_input else [command_str]
    # A command that is only control operators or whitespace (";", "&&", …)
    # splits to zero segments. Nothing matched anything, so no rule may allow
    # it — fall through to the grader.
    if not segments:
        return None
    # A `cd` to an out-of-project / unknown directory can't auto-allow: later
    # relative reads (`cd /etc` → `cat passwd`) would dodge the outside-project
    # triage. Fall through to the grader (human escalations below still win).
    approval_possible = not shell_input or (
        tool_name == "Bash"
        and not shell_command_needs_review(command_str)
        and not any(cd_is_unsafe(segment) for segment in segments)
    )
    decisive_rules = _decisive_rules(compiled_rules)
    active_rules = compiled_rules if approval_possible else decisive_rules
    segment_matches: dict[str, EvaluableCommandRule | None] = {}
    matches: list[EvaluableCommandRule | None] = []
    timed_out = False
    try:
        for segment in segments:
            if segment not in segment_matches:
                segment_matches[segment] = _match_segment(
                    segment, tool_name, active_rules, match_timeout, deadline, normalize_shell=True
                )
            match = segment_matches[segment]
            matches.append(match)
            if match is None or match.action != RuleAction.ALLOW:
                active_rules = decisive_rules

        if shell_input:
            # Segment splitting (including on newlines) hides rules that need the
            # whole command for context — e.g. a destructive SQL statement inside a
            # heredoc piped to `psql`. Re-match the full command, but only let it
            # ESCALATE, never relax: this keeps compound-command allow-listing
            # working while still catching multiline destructive constructs.
            full_match = _match_segment(
                command_str, tool_name, active_rules, match_timeout, deadline, normalize_shell=False
            )
            if full_match is not None and full_match.action in ESCALATION_ACTIONS:
                matches.append(full_match)
            for dest in extract_redirect_destinations(command_str):
                redirect_match = _match_segment(
                    dest, "Write", active_rules, match_timeout, deadline, normalize_shell=False
                )
                if redirect_match is not None:
                    matches.append(redirect_match)
    except TimeoutError:
        timed_out = True

    matched_rules = [match for match in matches if match is not None]
    if matched_rules:
        most_severe_match = min(matched_rules, key=lambda match: ACTION_SEVERITY[match.action])
        if most_severe_match.action in (RuleAction.DENY, RuleAction.ESCALATE_HUMAN):
            return CommandRuleMatch(
                action=most_severe_match.action,
                label=most_severe_match.label,
                pattern=most_severe_match.pattern,
            )

    if timed_out:
        raise TimeoutError("command-rule evaluation exceeded its budget")

    if not approval_possible:
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
    try:
        return evaluate_command_rules(
            tool_name,
            tool_input,
            command_rules_from_tree(tree),
            terminal_rule_action(thresholds.flag_threshold, thresholds.deny_threshold),
            match_timeout=match_timeout,
        )
    except (TimeoutError, RuleEvaluationLimitError):
        return None


def command_rules_from_tree(tree: dict[str, Any]) -> list[TreeCommandRule]:
    """The enabled command rules of a merged settings tree, in evaluation order.

    The projection the server evaluates an org's admin baseline with: enabled
    rules only (``decision != "off"``), sorted by priority, each field
    unwrapped from its optional ``{value, permission}`` form. A rule whose tool
    has terminal thresholds carries that terminal action instead of its own
    (matching the client store, where a tool threshold overrides every rule for
    that tool — this matters for cross-tool matching such as redirect
    destinations checked against Write rules). A malformed active entry disables
    every allow in the list while preserving valid restrictions. Otherwise a
    missing restriction could leave a broader approval rule in force.
    ``category`` is required even though the evaluator never reads it, because
    the client store skips rules without one — a rule enforced at the gateway
    but not on machines (or vice versa) is exactly the divergence this module
    exists to prevent.
    """
    raw_rules = get_path_or_none(dict(tree), ("command_rules", "rules"))
    if not isinstance(raw_rules, list):
        return []
    rules: list[TreeCommandRule] = []
    has_invalid_rule = False
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            has_invalid_rule = True
            continue
        if unwrap(raw_rule.get("decision", "triage")) == "off":
            continue
        rule = _tree_command_rule(tree, raw_rule)
        if rule is None:
            has_invalid_rule = True
            continue
        rules.append(rule)
    if has_invalid_rule:
        rules = [rule for rule in rules if rule.action in ESCALATION_ACTIONS]
    return sorted(rules, key=lambda rule: rule.priority)


def command_rules_have_invalid_entries(tree: dict[str, Any]) -> bool:
    """Whether a merged tree contains active rules that cannot be evaluated.

    Disabled entries need no matching fields. Validate after merging so a
    partial override can inherit those fields from an earlier settings layer.
    """
    raw_rules = get_path_or_none(tree, ("command_rules", "rules"))
    if raw_rules is None:
        return False
    if not isinstance(raw_rules, list):
        return True
    return any(
        not isinstance(raw_rule, dict)
        or (unwrap(raw_rule.get("decision", "triage")) != "off" and _tree_command_rule(tree, raw_rule) is None)
        for raw_rule in raw_rules
    )


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
    if not isinstance(decision, str) or decision == "off" or decision not in DECISION_TO_ACTION:
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
