from enum import Enum


class AuthClientConfigAuthMode(str, Enum):
    PROXY = "proxy"
    WORKOS = "workos"

    def __str__(self) -> str:
        return str(self.value)
