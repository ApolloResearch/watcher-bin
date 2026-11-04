"""The report a Watcher client sends about its installation, and the limits on it.

Every report carries a client-generated ``report_id``, so a retried request stores nothing new, and a
``status`` object of named sections. There is one section today, ``inventory``
(``watcher_sdk.agent_inventory.vocabulary.AgentInventoryStatus``). A missing section means "unknown", never
"nothing found", and each section describes itself, so a later section can be added without touching the
ones before it or versioning the report. The server stores every accepted report as its own row.
"""

from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from watcher_sdk.agent_inventory.vocabulary import AgentInventoryStatus

# The server refuses a larger request body with 413 before reading it.
MAX_REPORT_BYTES: Final = 64 * 1024


class InstallationStatus(BaseModel):
    """What the installation is reporting, by section. Omit a section to report nothing about it."""

    model_config = ConfigDict(extra="ignore")

    inventory: AgentInventoryStatus | None = Field(
        default=None, description="The coding agents found on the machine, when agent inventory is on."
    )


class InstallationReport(BaseModel):
    """One report from a Watcher client installation."""

    model_config = ConfigDict(extra="ignore")

    report_id: UUID = Field(
        description="A random ID for this report. Retry a failed request with the same ID; it is stored once."
    )
    status: InstallationStatus
