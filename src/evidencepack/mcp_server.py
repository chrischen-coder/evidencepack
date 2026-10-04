"""Optional MCP transport bound to the trusted host's tenant and session."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from .service import EvidenceService

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def create_server(service: EvidenceService, *, max_budget: int = 8192) -> FastMCP:
    """Expose scoped tools; model arguments cannot switch tenant, session or vault."""
    from mcp.server.fastmcp import FastMCP

    if max_budget < 1:
        raise ValueError("max_budget must be positive")
    server = FastMCP("EvidencePack")

    def bounded(budget: int) -> int:
        if isinstance(budget, bool) or not 1 <= budget <= max_budget:
            raise ValueError(f"budget must be between 1 and host limit {max_budget}")
        return budget

    @server.tool()
    def evidence_capture(
        source: str, text: str, media_type: Literal["text", "json"] = "text"
    ) -> str:
        """Archive text; capture large outputs in host middleware before model projection."""
        import json

        artifact = service.capture(source, text, media_type=media_type)
        return json.dumps({"artifact": artifact.id, "sha256": artifact.sha256})

    @server.tool()
    def evidence_pack(query: str, artifacts: list[str], budget: int = 4096) -> str:
        """Select complete relevant evidence. Budget covers the returned JSON, not MCP envelopes."""
        return service.pack(query, artifacts, budget=bounded(budget)).to_json()

    @server.tool()
    def evidence_read(artifact: str, locator: str, budget: int = 4096) -> str:
        """Read an exact L1-L3 range or J:/records/0 pointer and obtain a new exposure receipt."""
        return service.read(artifact, locator, budget=bounded(budget)).to_json()

    @server.tool()
    def evidence_verify(receipt: str, citation: str, quote: str) -> dict[str, bool | str]:
        """Validate an exact exposed quote; this does not prove that a diagnostic claim is true."""
        verdict = service.verify(receipt, citation, quote)
        return {"valid": verdict.valid, "reason": verdict.reason}

    @server.tool()
    def evidence_release(receipt: str) -> dict[str, str]:
        """Release a receipt's storage pin after the host has finished using its evidence."""
        service.release(receipt)
        return {"released": receipt}

    return server
