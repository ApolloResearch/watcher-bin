from enum import Enum


class GradeByMonitorV1MonitorsRoleGradePostRole(str, Enum):
    GATEWAY = "gateway"
    TRIAGE = "triage"

    def __str__(self) -> str:
        return str(self.value)
