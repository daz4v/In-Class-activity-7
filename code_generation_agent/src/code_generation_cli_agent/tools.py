from __future__ import annotations

import requests
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

    def __init__(self, token: str, owner: str, repo: str):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def get_issue(self, issue_number: int) -> Optional[dict]:
        """Fetch issue details."""
        resp = requests.get(
            f"{self.base_url}/issues/{issue_number}",
            headers=self.headers,
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        return None

    def create_issue(self, title: str, body: str, labels: list[str] = None) -> Optional[dict]:
        """Create a GitHub issue."""
        payload = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        try:
            resp = requests.post(
                f"{self.base_url}/issues",
                headers=self.headers,
                json=payload,
                timeout=10,
            )
            if resp.status_code == 201:
                return resp.json()
            else:
                raise RuntimeError(f"GitHub API error ({resp.status_code}): {resp.text}")
        except Exception as e:
            raise RuntimeError(f"Failed to create issue: {e}")

    def create_pull_request(
        self, title: str, body: str, head: str, base: str = "main"
    ) -> Optional[dict]:
        """Create a GitHub pull request."""
        payload = {"title": title, "body": body, "head": head, "base": base}
        try:
            resp = requests.post(
                f"{self.base_url}/pulls",
                headers=self.headers,
                json=payload,
                timeout=10,
            )
            if resp.status_code == 201:
                return resp.json()
            else:
                raise RuntimeError(f"GitHub API error ({resp.status_code}): {resp.text}")
        except Exception as e:
            raise RuntimeError(f"Failed to create PR: {e}")

    def update_issue(self, issue_number: int, title: str = None, body: str = None) -> Optional[dict]:
        """Update an existing issue."""
        payload = {}
        if title:
            payload["title"] = title
        if body:
            payload["body"] = body
        resp = requests.patch(
            f"{self.base_url}/issues/{issue_number}",
            headers=self.headers,
            json=payload,
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        return None

    def create_comment(self, issue_number: int, body: str) -> Optional[dict]:
        """Add a comment to an issue."""
        payload = {"body": body}
        resp = requests.post(
            f"{self.base_url}/issues/{issue_number}/comments",
            headers=self.headers,
            json=payload,
            timeout=10,
        )
        if resp.status_code == 201:
            return resp.json()
        return None
