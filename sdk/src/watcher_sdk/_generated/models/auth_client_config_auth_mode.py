from enum import StrEnum


class AuthClientConfigAuthMode(StrEnum):
    PROXY = "proxy"
    WORKOS = "workos"

    def __str__(self) -> str:
        return str(self.value)
