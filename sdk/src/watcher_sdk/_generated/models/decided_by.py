from enum import Enum


class DecidedBy(str, Enum):
    AGENT_REVIEW = "agent_review"
    INTERRUPT = "interrupt"
    PERSON = "person"

    def __str__(self) -> str:
        return str(self.value)
