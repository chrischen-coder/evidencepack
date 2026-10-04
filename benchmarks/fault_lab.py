"""Real subprocess/HTTP fault capture and a transparent rule-based repair experiment."""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from .cases import Case, Output


def health(port: int, request_id: str) -> int:
    """Perform an actual HTTP request, retaining HTTP failure status as an observation."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/health", headers={"X-Request-ID": request_id}
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


@dataclass
class Incident:
    """One live lab incident; inputs are frozen before evaluating any selection arm."""

    case: Case
    config_path: Path
    original: dict[str, Any]
    frontend_port: int
    before_status: int

    def try_repair(self, selected_text: str) -> dict[str, Any]:
        """Derive a patch solely from selected observations, then measure an actual health check."""
        config_match = re.search(r"CONFIG (\{[^\n]+\})", selected_text)
        runtime_match = re.search(r"LISTENER (\{[^\n]+\})", selected_text)
        diagnosis = None
        patch: dict[str, Any] = {}
        if config_match and runtime_match:
            config = json.loads(config_match.group(1))
            runtime = json.loads(runtime_match.group(1))
            if config["upstream_port"] != runtime["bound_port"]:
                diagnosis, patch = "port_mismatch", {"upstream_port": runtime["bound_port"]}
            elif config["health_path"] != runtime["health_path"]:
                diagnosis, patch = "path_mismatch", {"health_path": runtime["health_path"]}
            elif config["auth_token"] != runtime["auth_token"]:
                diagnosis, patch = "token_mismatch", {"auth_token": runtime["auth_token"]}
        self.config_path.write_text(json.dumps({**self.original, **patch}))
        after = health(self.frontend_port, "repair-check")
        self.config_path.write_text(json.dumps(self.original))
        return {
            "diagnosis": diagnosis,
            "patch": patch,
            "before": self.before_status,
            "after": after,
            "repaired": bool(patch) and after == 200,
        }


@contextmanager
def incident(family: str, index: int, *, traffic_requests: int = 180) -> Iterator[Incident]:
    """Start two loopback processes, capture a real failure, and always clean up both children."""
    processes: list[subprocess.Popen[bytes]] = []
    logs: list[Any] = []
    with TemporaryDirectory(prefix="evidencepack-fault-") as directory:
        root = Path(directory)
        try:
            backend_config = root / "backend.json"
            expected = {"health_path": "/health", "auth_token": f"demo-token-{index}"}
            backend_config.write_text(json.dumps(expected))

            def launch(role: str, config: Path) -> dict[str, Any]:
                log = (root / f"{role}.log").open("wb")
                logs.append(log)
                ready = root / f"{role}.ready"
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "benchmarks.fault_worker",
                        "--role",
                        role,
                        "--config",
                        str(config),
                        "--ready",
                        str(ready),
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                processes.append(process)
                deadline = time.monotonic() + 8
                while not ready.exists():
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(f"{role} fixture failed to start")
                    time.sleep(0.01)
                return json.loads(ready.read_text())

            backend = launch("backend", backend_config)
            original = {**expected, "upstream_port": backend["bound_port"], "service": "checkout"}
            if family == "port_mismatch":
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    original["upstream_port"] = sock.getsockname()[1]
            elif family == "path_mismatch":
                original["health_path"] = "/ready"
            elif family == "token_mismatch":
                original["auth_token"] = f"demo-wrong-{index}"
            else:
                raise ValueError(f"Unknown fault family: {family}")
            frontend_config = root / "frontend.json"
            frontend_config.write_text(json.dumps(original))
            frontend = launch("frontend", frontend_config)
            port = frontend["bound_port"]
            for _i in range(traffic_requests):
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=3):
                    pass
            request_id = "req-" + uuid4().hex[:12]
            before = health(port, request_id)
            if before != 502:
                raise RuntimeError(f"Expected a real 502 failure, observed {before}")
            for _i in range(traffic_requests):
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=3):
                    pass
            config_line = "CONFIG " + json.dumps(original, separators=(",", ":"))
            config_noise = [
                f"INFO configuration metadata row={i} service=sidecar" for i in range(300)
            ]
            config_tool = subprocess.run(
                [sys.executable, "-c", "import sys; print(sys.stdin.read(), end='')"],
                input="\n".join([*config_noise[:150], config_line, *config_noise[150:]]) + "\n",
                text=True,
                capture_output=True,
                check=True,
            )
            outputs = (
                Output("traffic", (root / "frontend.log").read_text()),
                Output("configuration", config_tool.stdout),
                Output("backend-runtime", (root / "backend.log").read_text()),
            )
            listener_line = "LISTENER " + json.dumps(backend, separators=(",", ":"))
            failure_line = next(
                line for line in outputs[0].text.splitlines() if f"request={request_id} " in line
            )
            case = Case(
                f"real-{family}-{index}",
                family,
                f"Diagnose checkout health failure for request {request_id}. Compare the upstream "
                "configuration with the backend listener; return the minimal repair.",
                outputs,
                (config_line, listener_line, failure_line),
            )
            yield Incident(case, frontend_config, original, port, before)
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            for log in logs:
                log.close()
