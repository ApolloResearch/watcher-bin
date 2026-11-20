from enum import StrEnum


class AgentInventoryAgentHealthStateState(StrEnum):
    AGENT_NOT_FOUND = "agent_not_found"
    HOOKS_MISSING = "hooks_missing"
    HOOKS_TURNED_OFF_IN_AGENT = "hooks_turned_off_in_agent"
    HOOKS_UNTRUSTED = "hooks_untrusted"
    ON = "on"
    SETUP_OUT_OF_DATE = "setup_out_of_date"
    SETUP_UNKNOWN = "setup_unknown"
    TURNED_OFF = "turned_off"
    TURNED_OFF_BY_ORGANIZATION = "turned_off_by_organization"
    TURNED_OFF_NOT_FOUND = "turned_off_not_found"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return str(self.value)
