import json
import subprocess
import sys

import pytest


def test_cli_capture_pack_verify_and_raw(tmp_path):
    base = [
        sys.executable,
        "-m",
        "evidencepack.cli",
        "--vault",
        str(tmp_path / "vault.sqlite"),
        "--tenant",
        "test",
        "--session",
        "cli",
    ]
    text = "INFO starting\nERROR bad port\r\n"
    capture = subprocess.run(
        [*base, "capture", "-", "--source", "probe"],
        input=text.encode(),
        capture_output=True,
        check=True,
    )
    artifact = json.loads(capture.stdout)["artifact"]
    packed = subprocess.run(
        [*base, "pack", artifact, "--query", "bad port", "--budget", "1500"],
        capture_output=True,
        check=True,
    )
    pack = json.loads(packed.stdout)
    citation = pack["excerpts"][0]["citation"]
    accepted = subprocess.run(
        [*base, "verify", pack["receipt"], citation, "bad port"], capture_output=True
    )
    rejected = subprocess.run(
        [*base, "verify", pack["receipt"], citation, "repaired"], capture_output=True
    )
    assert accepted.returncode == 0
    assert rejected.returncode == 1
    raw = subprocess.run([*base, "raw", artifact], capture_output=True, check=True)
    assert raw.stdout == text.encode()


def test_real_mcp_stdio_roundtrip_and_host_scope(tmp_path):
    pytest.importorskip("mcp")
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def scenario():
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "evidencepack.cli",
                "--vault",
                str(tmp_path / "mcp.sqlite"),
                "--tenant",
                "trusted-host",
                "--session",
                "fixed-session",
                "serve",
                "--max-budget",
                "2000",
            ],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                inventory = await client.list_tools()
                assert len(inventory.tools) == 5
                for tool in inventory.tools:
                    assert "tenant" not in tool.inputSchema.get("properties", {})
                    assert "session" not in tool.inputSchema.get("properties", {})
                capture = await client.call_tool(
                    "evidence_capture",
                    {
                        "source": "probe",
                        "text": "ERROR real stdio failed\n",
                    },
                )
                artifact = json.loads(capture.content[0].text)["artifact"]
                result = await client.call_tool(
                    "evidence_pack",
                    {
                        "query": "stdio failed",
                        "artifacts": [artifact],
                        "budget": 1600,
                    },
                )
                pack = json.loads(result.content[0].text)
                verdict = await client.call_tool(
                    "evidence_verify",
                    {
                        "receipt": pack["receipt"],
                        "citation": pack["excerpts"][0]["citation"],
                        "quote": "stdio failed",
                    },
                )
                assert json.loads(verdict.content[0].text)["valid"]
                invalid = await client.call_tool(
                    "evidence_pack",
                    {
                        "query": "stdio",
                        "artifacts": [artifact],
                        "budget": 5000,
                    },
                )
                assert invalid.isError
                reread = await client.call_tool(
                    "evidence_read",
                    {
                        "artifact": artifact,
                        "locator": "L1-L1",
                        "budget": 1600,
                    },
                )
                assert json.loads(reread.content[0].text)["excerpts"][0]["text"].endswith("\n")

    anyio.run(scenario)
