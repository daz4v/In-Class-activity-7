from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class AgentConfig:
    repo: str
    model: str
    host: str
    temperature: float
    github_token: str = ""
    github_owner: str = ""
    github_repo: str = ""
    mcp_server_command: str = ""
    mcp_server_args: list[str] = field(default_factory=list)
    mcp_timeout_s: int = 30
    verbose: bool = False


@dataclass(frozen=True)
class RunResult:
    ok: bool
    details: str


@dataclass
class CodeReview:
    """Result of code review analysis."""
    changes_summary: str
    change_type: str  # feature, bugfix, refactor, docs, other
    risk_level: str  # low, medium, high
    issues_found: list[str]
    improvements: list[str]
    recommendation: str  # issue, pr, nothing
    evidence: str


@dataclass
class DraftContent:
    """Draft Issue or PR content."""
    title: str
    body: str
    draft_type: str  # issue or pr
    is_approved: bool = False


@dataclass
class ReflectionVeredict:
    """Critic's reflection on draft quality."""
    passed: bool
    issues: list[str]
    suggestions: list[str]
    evidence: str


@dataclass
class ApprovalState:
    """Tracks draft approval workflow."""
    draft_id: str
    draft_content: DraftContent = field(default_factory=lambda: DraftContent("", "", "issue"))
    reflection: Optional[ReflectionVeredict] = None
    user_approved: bool = False
    created_url: Optional[str] = None


@dataclass(frozen=True)
class A2AMessage:
    """A2A protocol message envelope passed between agents."""

    message_id: str
    from_agent: str
    to_agent: str
    intent: str
    payload: dict[str, Any]
    protocol: str = "A2A/1.0"
    trace_id: str = ""


@dataclass(frozen=True)
class A2AResponse:
    """A2A protocol response envelope."""

    message_id: str
    from_agent: str
    to_agent: str
    ok: bool
    payload: dict[str, Any]
    error: str = ""