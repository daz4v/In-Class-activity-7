from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _send(payload: dict[str, Any]) -> None:
    body = json.dumps(payload)
    frame = f"Content-Length: {len(body.encode('utf-8'))}\r\n\r\n{body}"
    sys.stdout.write(frame)
    sys.stdout.flush()


def _read() -> dict[str, Any] | None:
    content_length = 0

    while True:
        line = sys.stdin.readline()
        if line == "":
            return None
        line = line.strip("\r\n")
        if line == "":
            break
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())

    if content_length <= 0:
        return None

    body = sys.stdin.read(content_length)
    return json.loads(body)


class MCPToolServer:
    def __init__(self, repo: Path):
        self.repo = repo.resolve()

    def _run(self, cmd: str) -> tuple[bool, str]:
        proc = subprocess.run(
            cmd,
            cwd=self.repo,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return proc.returncode == 0, (out.strip() or "[NO OUTPUT]")

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "git_diff", "description": "Get git diff", "inputSchema": {"type": "object"}},
            {"name": "git_get_changed_files", "description": "List changed files", "inputSchema": {"type": "object"}},
            {"name": "git_get_current_branch", "description": "Get current branch", "inputSchema": {"type": "object"}},
            {"name": "git_run", "description": "Run an arbitrary git command", "inputSchema": {"type": "object"}},
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "git_diff":
            base_ref = arguments.get("base_ref", "main")
            commit_range = arguments.get("commit_range")
            cmd = f"git diff {commit_range}" if commit_range else f"git diff {base_ref}"
            ok, out = self._run(cmd)
            return out if ok else f"ERROR: {out}"

        if name == "git_get_changed_files":
            base_ref = arguments.get("base_ref", "main")
            ok, out = self._run(f"git diff --name-only {base_ref}")
            return out if ok else f"ERROR: {out}"

        if name == "git_get_current_branch":
            ok, out = self._run("git rev-parse --abbrev-ref HEAD")
            return out if ok else f"ERROR: {out}"

        if name == "git_run":
            cmd = arguments.get("cmd", "")
            if not cmd:
                return "ERROR: Missing command"
            ok, out = self._run(cmd)
            return out if ok else f"ERROR: {out}"

        return f"ERROR: Unknown tool '{name}'"


def _handle(req: dict[str, Any], server: MCPToolServer) -> dict[str, Any]:
    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "serverInfo": {"name": "cca-mcp-server", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": server.list_tools()}}

    if method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})
        text = server.call_tool(tool_name, args)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": text}]},
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method '{method}'"},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CCA MCP tool server")
    parser.add_argument("--repo", default=".", help="Repository path")
    args = parser.parse_args()

    server = MCPToolServer(Path(args.repo))

    while True:
        req = _read()
        if req is None:
            return 0
        resp = _handle(req, server)
        _send(resp)


if __name__ == "__main__":
    raise SystemExit(main())
