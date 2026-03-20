from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .agent import Agent
from .types import AgentConfig
from .utils import ensure_repo_path

DEFAULT_MODEL = "devstral-small-2:24b-cloud"
DEFAULT_HOST = "http://localhost:11434"
VERSION = "0.5.0"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent",
        description="GitHub Repository Agent for code review, issue/PR drafting, and improvement",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
            Examples:
            agent review --base main
            agent review --range HEAD~3..HEAD
            agent draft issue --instruction "Add rate limiting to login endpoint"
            agent draft pr --instruction "Refactor duplicated pricing logic"
            agent approve --draft <draft_id> --yes
            agent improve issue --number 42
            agent improve pr --number 17
        """,
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    p.add_argument("--repo", default=".", help="Repository path (default: current directory)")
    p.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL),
        help=f"Ollama model (default: {DEFAULT_MODEL})",
    )
    p.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", DEFAULT_HOST),
        help=f"Ollama host (default: {DEFAULT_HOST})",
    )
    p.add_argument(
        "--temperature",
        type=float,
        default=float(os.environ.get("OLLAMA_TEMPERATURE", "0.0")),
        help="Sampling temperature (default: 0.0)",
    )
    p.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN", ""),
        help="GitHub API token (from GITHUB_TOKEN env var)",
    )
    p.add_argument(
        "--github-owner",
        default=os.environ.get("GITHUB_OWNER", ""),
        help="GitHub owner/org (from GITHUB_OWNER env var)",
    )
    p.add_argument(
        "--github-repo",
        default=os.environ.get("GITHUB_REPO", ""),
        help="GitHub repo name (from GITHUB_REPO env var)",
    )
    p.add_argument(
        "--mcp-server-command",
        default=os.environ.get("MCP_SERVER_COMMAND", ""),
        help="MCP server command (default: internal stdio MCP server)",
    )
    p.add_argument(
        "--mcp-server-arg",
        action="append",
        default=[],
        help="Additional MCP server argument (repeatable)",
    )
    p.add_argument(
        "--mcp-timeout",
        type=int,
        default=int(os.environ.get("MCP_TIMEOUT_S", "30")),
        help="MCP request timeout in seconds (default: 30)",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    # Review command
    rv = sub.add_parser("review", help="Review code changes")
    rv.add_argument("--base", default="main", help="Base branch (default: main)")
    rv.add_argument("--range", help="Commit range (e.g., HEAD~3..HEAD)")

    # Draft command
    dr = sub.add_parser("draft", help="Draft GitHub Issue or PR")
    dr.add_argument("type", choices=["issue", "pr"], help="What to draft")
    dr.add_argument(
        "--instruction",
        required=True,
        help="Explicit instruction for what to draft",
    )

    # Approve command
    ap = sub.add_parser("approve", help="Approve and create Issue/PR on GitHub")
    ap.add_argument("--draft", required=True, help="Draft ID to approve")
    ap.add_argument("--yes", action="store_true", help="Approve and create")
    ap.add_argument("--no", action="store_true", help="Reject draft")

    # Improve command
    im = sub.add_parser("improve", help="Improve existing Issue or PR")
    im.add_argument("type", choices=["issue", "pr"], help="What to improve")
    im.add_argument("--number", type=int, required=True, help="Issue or PR number")

    return p


def display_code_review(review) -> None:
    """Display code review results."""
    print("\n" + "=" * 70)
    print("[Reviewer] Code Analysis Complete")
    print("=" * 70)
    print(f"Change Type:  {review.change_type.upper()}")
    print(f"Risk Level:   {review.risk_level.upper()}")
    print(f"Recommendation: {review.recommendation.upper()}")
    print(f"\nSummary:\n{review.changes_summary}")

    if review.issues_found:
        print(f"\nIssues Found:")
        for issue in review.issues_found:
            print(f"  • {issue}")

    if review.improvements:
        print(f"\nSuggested Improvements:")
        for imp in review.improvements:
            print(f"  • {imp}")
    print()


def display_draft(draft, reflection, draft_id: str) -> None:
    """Display draft and get approval. Uses provided draft_id."""
    print("\n" + "=" * 70)
    print(f"[Writer] {draft.draft_type.upper()} Draft Created (ID: {draft_id})")
    print("=" * 70)
    print(f"\nTitle:\n{draft.title}")
    print(f"\nBody:\n{draft.body}")

    print("\n" + "-" * 70)
    print("[Gatekeeper] Reflection Verdict")
    print("-" * 70)
    status = "PASS" if reflection.passed else "FAIL"
    print(f"Verdict: {status}")

    if reflection.issues:
        print("\nIssues:")
        for issue in reflection.issues:
            print(f"  • {issue}")

    if reflection.suggestions:
        print("\nSuggestions:")
        for sugg in reflection.suggestions:
            print(f"  • {sugg}")

    print(f"\nTo approve or reject this draft, use:")
    print(f"  agent approve --draft {draft_id} --yes")
    print(f"  agent approve --draft {draft_id} --no")
    print()


def display_improvement(critique, improved_draft) -> None:
    """Display improvement suggestions."""
    print("\n" + "=" * 70)
    print("[Reviewer] Critique of Current Content")
    print("=" * 70)
    print(critique)

    print("\n" + "=" * 70)
    print("[Writer] Proposed Improved Version")
    print("=" * 70)
    print(f"\nTitle:\n{improved_draft.title}")
    print(f"\nBody:\n{improved_draft.body}")

    print("\n" + "-" * 70)
    print("[Gatekeeper] Review complete. Improvements suggested above.")
    print("-" * 70)
    print()


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Ensure repo exists
    ensure_repo_path(args.repo)

    cfg = AgentConfig(
        repo=args.repo,
        model=args.model,
        host=args.host,
        temperature=args.temperature,
        github_token=args.github_token,
        github_owner=args.github_owner,
        github_repo=args.github_repo,
        mcp_server_command=args.mcp_server_command,
        mcp_server_args=args.mcp_server_arg,
        mcp_timeout_s=args.mcp_timeout,
        verbose=args.verbose,
    )

    agent = Agent(cfg)

    try:
        if args.cmd == "review":
            # Task 1: Review changes
            review = agent.review_changes(args.base, args.range)
            display_code_review(review)
            return 0

        elif args.cmd == "draft":
            # Task 2: Draft Issue or PR
            approval, _ = agent.draft_issue_or_pr(draft_type=args.type, instruction=args.instruction)
            draft_id = approval.draft_id
            display_draft(approval.draft_content, approval.reflection, draft_id)
            return 0

        elif args.cmd == "approve":
            # Approval/Rejection step for Task 2
            if args.yes:
                result = agent.approve_and_create(args.draft)
                print(result.details)
                return 0 if result.ok else 1
            elif args.no:
                result = agent.reject_draft(args.draft)
                print(result.details)
                return 0
            else:
                print("Please specify --yes or --no")
                return 1

        elif args.cmd == "improve":
            # Task 3: Improve existing Issue or PR
            if args.type == "issue":
                critique, improved = agent.improve_issue(args.number)
            else:
                critique, improved = agent.improve_pr(args.number)

            display_improvement(critique, improved)
            return 0

        else:
            print(f"Unknown command: {args.cmd}", file=sys.stderr)
            return 1

    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def main() -> None:
    if len(sys.argv) == 1:
        from .interactive import repl
        raise SystemExit(repl())
    raise SystemExit(run())


if __name__ == "__main__":
    main()
