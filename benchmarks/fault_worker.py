"""An isolated HTTP fixture that emits actual request failures and runtime state."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def main() -> None:
    """Run a disposable loopback service; configuration is reread for every health request."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("backend", "frontend"), required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--ready", type=Path, required=True)
    args = parser.parse_args()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *values: object) -> None:
            return None

        def do_GET(self) -> None:
            config = json.loads(args.config.read_text())
            request_id = self.headers.get("X-Request-ID", "unknown")
            status = 200
            detail = "healthy"
            if self.path == "/ping":
                pass
            elif args.role == "backend":
                if self.path != config["health_path"]:
                    status, detail = 404, "health route not found"
                elif self.headers.get("X-Demo-Token") != config["auth_token"]:
                    status, detail = 401, "demo token mismatch"
            else:
                target = f"http://127.0.0.1:{config['upstream_port']}{config['health_path']}"
                request = urllib.request.Request(
                    target,
                    headers={"X-Demo-Token": config["auth_token"], "X-Request-ID": request_id},
                )
                try:
                    with urllib.request.urlopen(request, timeout=2) as response:
                        status = response.status
                except (urllib.error.URLError, TimeoutError) as error:
                    status = 502
                    detail = str(error)
            level = "ERROR" if status >= 400 else "INFO"
            print(
                f"{level} checkout role={args.role} request={request_id} "
                f"path={self.path} status={status} detail={detail}",
                flush=True,
            )
            self.send_response(status)
            self.end_headers()
            self.wfile.write(detail.encode())

    server = HTTPServer(("127.0.0.1", 0), Handler)
    state = json.loads(args.config.read_text())
    state["bound_port"] = server.server_address[1]
    state["service"] = "checkout"
    state["role"] = args.role
    for i in range(240):
        print(f"INFO boot telemetry sample={i} service=sidecar value={i % 9}", flush=True)
    print("LISTENER " + json.dumps(state, separators=(",", ":")), flush=True)
    for i in range(240):
        print(f"INFO boot telemetry sample={i + 240} service=sidecar value={i % 13}", flush=True)
    args.ready.write_text(json.dumps(state))
    server.serve_forever()


if __name__ == "__main__":
    main()
