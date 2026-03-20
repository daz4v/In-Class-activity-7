from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

from .mcp import MCPClient


class Tools:
    def __init__(self, repo_path: Path, mcp_client: MCPClient):
        self.repo_path = repo_path.resolve()
        self.mcp_client = mcp_client

    def _safe(self, rel_path: str) -> Path:
        p = (self.repo_path / rel_path).resolve()
        if not str(p).startswith(str(self.repo_path)):
            raise ValueError("Unsafe path traversal blocked.")
        return p

    def read(self, rel_path: str, max_chars: int = 100000) -> str:
        p = self._safe(rel_path)
        if not p.exists():
            return ""
        return p.read_text(encoding="utf-8", errors="replace")[:max_chars]

    def write(self, rel_path: str, content: str) -> None:
        p = self._safe(rel_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def run(self, cmd: str, timeout_s: int = 600) -> Tuple[bool, str]:
        out = self.mcp_client.call_tool("git_run", {"cmd": cmd})
        if out.startswith("ERROR:"):
            return False, out.replace("ERROR:", "", 1).strip()
        return True, out or "[NO OUTPUT]"

    def git_diff(self, base_ref: str = "main", commit_range: Optional[str] = None) -> Tuple[bool, str]:
        """Get git diff for changes."""
        out = self.mcp_client.call_tool(
            "git_diff",
            {"base_ref": base_ref, "commit_range": commit_range},
        )
        if out.startswith("ERROR:"):
            return False, out.replace("ERROR:", "", 1).strip()
        return True, out

    def git_get_current_branch(self) -> Tuple[bool, str]:
        """Get current branch name."""
        out = self.mcp_client.call_tool("git_get_current_branch", {})
        if out.startswith("ERROR:"):
            return False, out.replace("ERROR:", "", 1).strip()
        return True, out

    def git_get_changed_files(self, base_ref: str = "main") -> Tuple[bool, str]:
        """Get list of changed files."""
        out = self.mcp_client.call_tool("git_get_changed_files", {"base_ref": base_ref})
        if out.startswith("ERROR:"):
            return False, out.replace("ERROR:", "", 1).strip()
        return True, out

    def git_get_commit_log(self, commit_range: str) -> Tuple[bool, str]:
        """Get commit log for a range."""
        return self.run(f"git log --oneline {commit_range}")

    def git_show(self, ref: str) -> Tuple[bool, str]:
        """Show commit details."""
        return self.run(f"git show {ref}")


class GitHubTools:
    """Interface to GitHub API."""

    def __init__(self, token: str, owner: str, repo: str, mcp_client: MCPClient):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.mcp_client = mcp_client

    def _call_json(self, tool_name: str, arguments: dict) -> dict:
        out = self.mcp_client.call_tool(tool_name, arguments)
        if out.startswith("ERROR:"):
            raise RuntimeError(out.replace("ERROR:", "", 1).strip())
        try:
            return json.loads(out)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON returned by MCP tool '{tool_name}': {out}") from exc

    def get_issue(self, issue_number: int) -> Optional[dict]:
        """Fetch issue details."""
        out = self.mcp_client.call_tool(
            "github_get_issue",
            {
                "token": self.token,
                "owner": self.owner,
                "repo": self.repo,
                "issue_number": issue_number,
            },
        )
        if out.startswith("ERROR:"):
            return None
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return None

    def create_issue(self, title: str, body: str, labels: list[str] = None) -> Optional[dict]:
        """Create a GitHub issue."""
        args = {
            "token": self.token,
            "owner": self.owner,
            "repo": self.repo,
            "title": title,
            "body": body,
        }
        if labels:
            args["labels"] = labels
        try:
            return self._call_json("github_create_issue", args)
        except Exception as e:
            raise RuntimeError(f"Failed to create issue: {e}")

    def create_pull_request(
        self, title: str, body: str, head: str, base: str = "main"
    ) -> Optional[dict]:
        """Create a GitHub pull request."""
        try:
            return self._call_json(
                "github_create_pull_request",
                {
                    "token": self.token,
                    "owner": self.owner,
                    "repo": self.repo,
                    "title": title,
                    "body": body,
                    "head": head,
                    "base": base,
                },
            )
        except Exception as e:
            raise RuntimeError(f"Failed to create PR: {e}")

    def update_issue(self, issue_number: int, title: str = None, body: str = None) -> Optional[dict]:
        """Update an existing issue."""
        args = {
            "token": self.token,
            "owner": self.owner,
            "repo": self.repo,
            "issue_number": issue_number,
            "title": title,
            "body": body,
        }
        out = self.mcp_client.call_tool("github_update_issue", args)
        if out.startswith("ERROR:"):
            return None
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return None

    def create_comment(self, issue_number: int, body: str) -> Optional[dict]:
        """Add a comment to an issue."""
        out = self.mcp_client.call_tool(
            "github_create_comment",
            {
                "token": self.token,
                "owner": self.owner,
                "repo": self.repo,
                "issue_number": issue_number,
                "body": body,
            },
        )
        if out.startswith("ERROR:"):
            return None
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return None
