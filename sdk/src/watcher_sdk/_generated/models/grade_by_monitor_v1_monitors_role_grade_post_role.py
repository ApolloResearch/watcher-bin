from enum import StrEnum


class GradeByMonitorV1MonitorsRoleGradePostRole(StrEnum):
    GATEWAY = "gateway"
    TRIAGE = "triage"

    def __str__(self) -> str:
        return str(self.value)
