"""Framework-neutral host integration; the model never controls storage scope."""

from collections.abc import Awaitable, Callable

from evidencepack import EvidenceService, Pack


class ToolEvidence:
    """Collect tool invocations in trusted middleware and project them at a model boundary."""

    def __init__(self, service: EvidenceService) -> None:
        self.service = service
        self.artifacts: list[str] = []

    async def observe(self, source: str, operation: Callable[[], Awaitable[str]]) -> str:
        """Execute the host's existing tool and capture its exact textual result."""
        text = await operation()
        artifact = self.service.capture(source, text)
        self.artifacts.append(artifact.id)
        return artifact.id

    def project(self, task: str, *, budget: int) -> Pack:
        """Return one bounded view across accumulated invocations, with a verifiable receipt."""
        return self.service.pack(task, self.artifacts, budget=budget)
