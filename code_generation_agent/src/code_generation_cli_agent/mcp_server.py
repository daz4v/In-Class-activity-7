from __future__ import annotations

import argparse
import json
import subprocess
import sys
from urllib import error, request
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
            {"name": "github_get_issue", "description": "Get a GitHub issue or PR", "inputSchema": {"type": "object"}},
            {"name": "github_create_issue", "description": "Create a GitHub issue", "inputSchema": {"type": "object"}},
            {"name": "github_create_pull_request", "description": "Create a GitHub pull request", "inputSchema": {"type": "object"}},
            {"name": "github_update_issue", "description": "Update a GitHub issue", "inputSchema": {"type": "object"}},
            {"name": "github_create_comment", "description": "Create a GitHub issue comment", "inputSchema": {"type": "object"}},
        ]

    def _github_request(
        self,
        token: str,
        owner: str,
        repo: str,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        if not token or not owner or not repo:
            return False, "Missing token/owner/repo for GitHub call"

        url = f"https://api.github.com/repos/{owner}/{repo}{path}"
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        req = request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json",
                "User-Agent": "cca-mcp-server/1.0",
            },
        )

        try:
            with request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                return True, text or "{}"
        except error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            return False, f"GitHub API error ({exc.code}): {err_body}"
        except Exception as exc:
            return False, f"GitHub request failed: {exc}"

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

        if name == "github_get_issue":
            token = arguments.get("token", "")
            owner = arguments.get("owner", "")
            repo = arguments.get("repo", "")
            issue_number = arguments.get("issue_number")
            if issue_number is None:
                return "ERROR: Missing issue_number"
            ok, out = self._github_request(token, owner, repo, "GET", f"/issues/{issue_number}")
            return out if ok else f"ERROR: {out}"

        if name == "github_create_issue":
            token = arguments.get("token", "")
            owner = arguments.get("owner", "")
            repo = arguments.get("repo", "")
            title = arguments.get("title", "")
            body = arguments.get("body", "")
            labels = arguments.get("labels")
            payload: dict[str, Any] = {"title": title, "body": body}
            if labels:
                payload["labels"] = labels
            ok, out = self._github_request(token, owner, repo, "POST", "/issues", payload)
            return out if ok else f"ERROR: {out}"

        if name == "github_create_pull_request":
            token = arguments.get("token", "")
            owner = arguments.get("owner", "")
            repo = arguments.get("repo", "")
            title = arguments.get("title", "")
            body = arguments.get("body", "")
            head = arguments.get("head", "")
            base = arguments.get("base", "main")
            payload = {"title": title, "body": body, "head": head, "base": base}
            ok, out = self._github_request(token, owner, repo, "POST", "/pulls", payload)
            return out if ok else f"ERROR: {out}"

        if name == "github_update_issue":
            token = arguments.get("token", "")
            owner = arguments.get("owner", "")
            repo = arguments.get("repo", "")
            issue_number = arguments.get("issue_number")
            if issue_number is None:
                return "ERROR: Missing issue_number"
            payload: dict[str, Any] = {}
            if "title" in arguments and arguments.get("title") is not None:
                payload["title"] = arguments.get("title")
            if "body" in arguments and arguments.get("body") is not None:
                payload["body"] = arguments.get("body")
            ok, out = self._github_request(
                token,
                owner,
                repo,
                "PATCH",
                f"/issues/{issue_number}",
                payload,
            )
            return out if ok else f"ERROR: {out}"

        if name == "github_create_comment":
            token = arguments.get("token", "")
            owner = arguments.get("owner", "")
            repo = arguments.get("repo", "")
            issue_number = arguments.get("issue_number")
            body = arguments.get("body", "")
            if issue_number is None:
                return "ERROR: Missing issue_number"
            ok, out = self._github_request(
                token,
                owner,
                repo,
                "POST",
                f"/issues/{issue_number}/comments",
                {"body": body},
            )
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
