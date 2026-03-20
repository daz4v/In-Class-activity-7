from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from .a2a import A2ABus
from .llm import OllamaLLM
from .mcp import MCPClient
from .prompt_manager import PromptManager
from .tools import Tools, GitHubTools
from .types import (
    A2AMessage,
    A2AResponse,
    AgentConfig,
    RunResult,
    CodeReview,
    DraftContent,
    ReflectionVeredict,
    ApprovalState,
)


class Reviewer:
    """Analyzes code changes and detects issues."""

    def __init__(self, llm_gen, prompt_manager: PromptManager, tools: Tools, verbose: bool = False):
        self.llm_gen = llm_gen
        self.prompt_manager = prompt_manager
        self.tools = tools
        self.verbose = verbose

    def _log(self, msg: str):
        if self.verbose:
            print(f"[Reviewer] {msg}")

    def review_changes(self, base_ref: str = "main", commit_range: Optional[str] = None) -> CodeReview:
        """Analyze git diff and produce review."""
        self._log("Analyzing code changes...")

        ok, diff_output = self.tools.git_diff(base_ref, commit_range)
        if not ok or not diff_output:
            return CodeReview(
                changes_summary="No changes found",
                change_type="other",
                risk_level="low",
                issues_found=[],
                improvements=[],
                recommendation="nothing",
                evidence="Empty diff",
            )

        ok, changed_files = self.tools.git_get_changed_files(base_ref)
        files_summary = changed_files if ok else "Unknown files"

        prompt = self.prompt_manager.get_prompt(
            "review",
            "default",
            diff=diff_output,
            files=files_summary,
        )
        self._log("Sending diff to LLM for analysis...")
        response = self.llm_gen(prompt)

        review = self._parse_review_response(response, diff_output)
        self._log(f"Review complete: {review.recommendation}")
        return review

    def handle_a2a(self, msg: A2AMessage) -> A2AResponse:
        if msg.intent != "review_changes":
            return A2AResponse(
                message_id=msg.message_id,
                from_agent="reviewer",
                to_agent=msg.from_agent,
                ok=False,
                payload={},
                error=f"Unsupported intent '{msg.intent}'",
            )

        review = self.review_changes(
            base_ref=msg.payload.get("base_ref", "main"),
            commit_range=msg.payload.get("commit_range"),
        )
        return A2AResponse(
            message_id=msg.message_id,
            from_agent="reviewer",
            to_agent=msg.from_agent,
            ok=True,
            payload={"review": review.__dict__},
        )

    def _parse_review_response(self, response: str, diff: str) -> CodeReview:
        """Parse LLM response into CodeReview structure."""
        lines = response.split("\n")

        change_type = "other"
        risk_level = "medium"
        recommendation = "nothing"
        issues = []
        improvements = []
        summary = response

        for line in lines:
            l = line.lower()
            if "feature" in l:
                change_type = "feature"
            elif "bugfix" in l or "fix" in l:
                change_type = "bugfix"
            elif "refactor" in l:
                change_type = "refactor"
            elif "doc" in l:
                change_type = "docs"

            if "high risk" in l or "critical" in l:
                risk_level = "high"
            elif "low risk" in l:
                risk_level = "low"

            if "issue" in l and "create" in l:
                recommendation = "issue"
            elif "pull request" in l or "pr" in l:
                recommendation = "pr"

            if "problem:" in l or "issue:" in l:
                issues.append(line.replace("problem:", "").replace("issue:", "").strip())
            elif "improve:" in l or "suggestion:" in l:
                improvements.append(line.replace("improve:", "").replace("suggestion:", "").strip())

        return CodeReview(
            changes_summary=summary,
            change_type=change_type,
            risk_level=risk_level,
            issues_found=[i for i in issues if i],
            improvements=[i for i in improvements if i],
            recommendation=recommendation,
            evidence=f"Analyzed {len(diff)} chars of diff",
        )


class Planner:
    """Decides what action to take based on review."""

    def __init__(self, llm_gen, prompt_manager: PromptManager, verbose: bool = False):
        self.llm_gen = llm_gen
        self.prompt_manager = prompt_manager
        self.verbose = verbose

    def _log(self, msg: str):
        if self.verbose:
            print(f"[Planner] {msg}")

    def plan_action(self, review: CodeReview) -> str:
        """Decide on action word from review."""
        self._log("Scope validated.")
        return review.recommendation

    def handle_a2a(self, msg: A2AMessage) -> A2AResponse:
        if msg.intent != "plan_action":
            return A2AResponse(
                message_id=msg.message_id,
                from_agent="planner",
                to_agent=msg.from_agent,
                ok=False,
                payload={},
                error=f"Unsupported intent '{msg.intent}'",
            )

        review = CodeReview(**msg.payload.get("review", {}))
        recommendation = self.plan_action(review)
        return A2AResponse(
            message_id=msg.message_id,
            from_agent="planner",
            to_agent=msg.from_agent,
            ok=True,
            payload={"recommendation": recommendation},
        )


class Writer:
    """Drafts Issue or PR content."""

    def __init__(self, llm_gen, prompt_manager: PromptManager, verbose: bool = False):
        self.llm_gen = llm_gen
        self.prompt_manager = prompt_manager
        self.verbose = verbose

    def _log(self, msg: str):
        if self.verbose:
            print(f"[Writer] {msg}")

    def draft_issue(self, review: CodeReview, instruction: Optional[str] = None) -> DraftContent:
        """Draft a GitHub issue from review or instruction."""
        self._log("Drafting issue...")

        if instruction:
            summary = instruction
        else:
            summary = f"{review.change_type.upper()}: {', '.join(review.issues_found[:2]) if review.issues_found else 'Code analysis'}"

        prompt = self.prompt_manager.get_prompt(
            "draft",
            "issue",
            summary=summary,
            issues="\n".join(review.issues_found),
            improvements="\n".join(review.improvements),
            risk_level=review.risk_level,
        )
        response = self.llm_gen(prompt)

        title, body = self._parse_draft_response(response)
        self._log("Issue draft created.")
        return DraftContent(title=title, body=body, draft_type="issue")

    def draft_pr(self, review: CodeReview, instruction: Optional[str] = None) -> DraftContent:
        """Draft a GitHub PR from review or instruction."""
        self._log("Drafting PR...")

        if instruction:
            summary = instruction
        else:
            summary = f"Refactor: {review.change_type}"

        prompt = self.prompt_manager.get_prompt(
            "draft",
            "pr",
            summary=summary,
            change_type=review.change_type,
            issues="\n".join(review.issues_found),
            improvements="\n".join(review.improvements),
        )
        response = self.llm_gen(prompt)

        title, body = self._parse_draft_response(response)
        self._log("PR draft created.")
        return DraftContent(title=title, body=body, draft_type="pr")

    def handle_a2a(self, msg: A2AMessage) -> A2AResponse:
        if msg.intent not in {"draft_issue", "draft_pr"}:
            return A2AResponse(
                message_id=msg.message_id,
                from_agent="writer",
                to_agent=msg.from_agent,
                ok=False,
                payload={},
                error=f"Unsupported intent '{msg.intent}'",
            )

        review = CodeReview(**msg.payload.get("review", {}))
        instruction = msg.payload.get("instruction")
        draft = self.draft_pr(review, instruction) if msg.intent == "draft_pr" else self.draft_issue(review, instruction)
        return A2AResponse(
            message_id=msg.message_id,
            from_agent="writer",
            to_agent=msg.from_agent,
            ok=True,
            payload={"draft": draft.__dict__},
        )

    def _parse_draft_response(self, response: str) -> tuple[str, str]:
        """Parse LLM response into title and body."""
        lines = response.split("\n")
        title = ""
        body_lines = []

        for i, line in enumerate(lines):
            if i == 0 or (title and ":" in line):
                if not title and line.strip():
                    title = line.strip()
            else:
                body_lines.append(line)

        if not title:
            title = "Code Improvement"

        # Normalize markdown-style titles so GitHub receives plain text.
        title = self._clean_title(title)

        body = "\n".join(body_lines).strip()
        if not body:
            body = response.strip()

        return title, body

    def _clean_title(self, raw_title: str) -> str:
        """Strip markdown decoration and common label prefixes from title."""
        title = raw_title.strip()

        if title.lower().startswith("title:"):
            title = title.split(":", 1)[1].strip()

        # Remove heading/list prefixes from model outputs.
        while title.startswith("#"):
            title = title[1:].strip()
        if title.startswith("- ") or title.startswith("* "):
            title = title[2:].strip()

        # Remove surrounding markdown emphasis markers.
        wrappers = ("**", "__", "`", "*", "_")
        changed = True
        while changed:
            changed = False
            for wrapper in wrappers:
                if (
                    title.startswith(wrapper)
                    and title.endswith(wrapper)
                    and len(title) > (len(wrapper) * 2)
                ):
                    title = title[len(wrapper) : -len(wrapper)].strip()
                    changed = True

        return title or "Code Improvement"


class Gatekeeper:
    """Verifies safety and enforces human approval.

    Approvals are persisted to a JSON file located inside the repository the
    agent is operating on. The Gatekeeper must therefore know the repo path.
    """

    STORAGE_FILENAME = ".cca_approvals.json"

    def __init__(self, llm_gen, prompt_manager: PromptManager, repo_path: Path, verbose: bool = False):
        self.llm_gen = llm_gen
        self.prompt_manager = prompt_manager
        self.repo_path = repo_path.resolve()
        self.verbose = verbose
        self.pending_approvals: dict[str, ApprovalState] = {}
        # load from disk if present
        self._load_storage()

    def _storage_path(self) -> Path:
        # store in the root of the target repo
        return self.repo_path / self.STORAGE_FILENAME

    def _load_storage(self):
        path = self._storage_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
                for did, info in data.items():
                    # reconstruct ApprovalState
                    draft = DraftContent(**info.get("draft_content", {}))
                    reflection = ReflectionVeredict(**info.get("reflection", {}))
                    approval = ApprovalState(
                        draft_id=did,
                        draft_content=draft,
                        reflection=reflection,
                        user_approved=info.get("user_approved", False),
                        created_url=info.get("created_url"),
                    )
                    self.pending_approvals[did] = approval
            except Exception:
                # corrupted file – ignore
                pass

    def _save_storage(self):
        path = self._storage_path()
        serialized = {}
        for did, approval in self.pending_approvals.items():
            serialized[did] = {
                "draft_content": {
                    "title": approval.draft_content.title,
                    "body": approval.draft_content.body,
                    "draft_type": approval.draft_content.draft_type,
                    "is_approved": approval.draft_content.is_approved,
                },
                "reflection": {
                    "passed": approval.reflection.passed if approval.reflection else False,
                    "issues": approval.reflection.issues if approval.reflection else [],
                    "suggestions": approval.reflection.suggestions if approval.reflection else [],
                    "evidence": approval.reflection.evidence if approval.reflection else "",
                },
                "user_approved": approval.user_approved,
                "created_url": approval.created_url,
            }
        path.write_text(json.dumps(serialized), encoding="utf-8")

    def _log(self, msg: str):
        if self.verbose:
            print(f"[Gatekeeper] {msg}")

    def reflect_on_draft(self, draft: DraftContent) -> ReflectionVeredict:
        """Critique draft and check quality."""
        self._log("Reflecting on draft quality...")

        prompt = self.prompt_manager.get_prompt(
            "critique",
            "default",
            title=draft.title,
            body=draft.body,
            draft_type=draft.draft_type,
        )
        response = self.llm_gen(prompt)

        passed, issues, suggestions = self._parse_critique_response(response)
        verdict = ReflectionVeredict(
            passed=passed,
            issues=issues,
            suggestions=suggestions,
            evidence=response,
        )

        status = "PASS" if passed else "FAIL"
        self._log(f"Reflection verdict: {status}")
        return verdict

    def handle_a2a(self, msg: A2AMessage) -> A2AResponse:
        if msg.intent not in {"reflect_and_store", "approve_draft", "reject_draft"}:
            return A2AResponse(
                message_id=msg.message_id,
                from_agent="gatekeeper",
                to_agent=msg.from_agent,
                ok=False,
                payload={},
                error=f"Unsupported intent '{msg.intent}'",
            )

        if msg.intent == "approve_draft":
            draft_id = msg.payload.get("draft_id", "")
            approval = self.approve_draft(draft_id)
            if not approval:
                return A2AResponse(
                    message_id=msg.message_id,
                    from_agent="gatekeeper",
                    to_agent=msg.from_agent,
                    ok=False,
                    payload={},
                    error="Draft not found",
                )
            return A2AResponse(
                message_id=msg.message_id,
                from_agent="gatekeeper",
                to_agent=msg.from_agent,
                ok=True,
                payload={
                    "approval": {
                        "draft_id": approval.draft_id,
                        "draft_content": approval.draft_content.__dict__,
                        "reflection": approval.reflection.__dict__ if approval.reflection else None,
                        "user_approved": approval.user_approved,
                        "created_url": approval.created_url,
                    }
                },
            )

        if msg.intent == "reject_draft":
            draft_id = msg.payload.get("draft_id", "")
            self.reject_draft(draft_id)
            return A2AResponse(
                message_id=msg.message_id,
                from_agent="gatekeeper",
                to_agent=msg.from_agent,
                ok=True,
                payload={"rejected": True},
            )

        draft = DraftContent(**msg.payload.get("draft", {}))
        reflection = self.reflect_on_draft(draft)
        approval = self.store_draft_for_approval(draft, reflection)
        return A2AResponse(
            message_id=msg.message_id,
            from_agent="gatekeeper",
            to_agent=msg.from_agent,
            ok=True,
            payload={
                "approval": {
                    "draft_id": approval.draft_id,
                    "draft_content": approval.draft_content.__dict__,
                    "reflection": approval.reflection.__dict__ if approval.reflection else None,
                    "user_approved": approval.user_approved,
                    "created_url": approval.created_url,
                }
            },
        )

    def store_draft_for_approval(self, draft: DraftContent, reflection: ReflectionVeredict) -> ApprovalState:
        """Store draft and reflection, wait for user approval."""
        draft_id = str(uuid4())[:8]
        approval = ApprovalState(
            draft_id=draft_id, draft_content=draft, reflection=reflection, user_approved=False
        )
        self.pending_approvals[draft_id] = approval
        self._log(f"Draft stored: {draft_id}")
        self._save_storage()
        return approval

    def approve_draft(self, draft_id: str) -> Optional[ApprovalState]:
        """User approves draft."""
        if draft_id not in self.pending_approvals:
            return None
        approval = self.pending_approvals[draft_id]
        approval.user_approved = True
        self._log(f"Draft {draft_id} approved by user.")
        self._save_storage()
        return approval

    def reject_draft(self, draft_id: str):
        """User rejects draft."""
        if draft_id in self.pending_approvals:
            del self.pending_approvals[draft_id]
            self._log(f"Draft {draft_id} rejected. No changes made.")
            self._save_storage()

    def _parse_critique_response(self, response: str) -> tuple[bool, list[str], list[str]]:
        """Parse critique response."""
        passed = "pass" in response.lower() and "fail" not in response.lower()
        issues = []
        suggestions = []

        lines = response.split("\n")
        for line in lines:
            l = line.lower()
            if "issue:" in l or "problem:" in l:
                issues.append(line.replace("issue:", "").replace("problem:", "").strip())
            elif "suggest:" in l or "improvement:" in l:
                suggestions.append(line.replace("suggest:", "").replace("improvement:", "").strip())

        return passed, [i for i in issues if i], [s for s in suggestions if s]


class Agent:
    """Main GitHub Repository Agent orchestrating all sub-agents."""

    def __init__(self, cfg: AgentConfig):
        self.cfg = cfg
        self.repo = Path(cfg.repo).resolve()
        self.mcp_client = self._build_mcp_client(cfg)
        self.tools = Tools(self.repo, mcp_client=self.mcp_client)
        self.prompt_manager = PromptManager()
        self.a2a = A2ABus()

        # Initialize LLM generator
        def llm_gen(prompt: str) -> str:
            llm = OllamaLLM(
                model=cfg.model,
                host=cfg.host,
                temperature=cfg.temperature,
            )
            return llm.generate(prompt)

        # Initialize sub-agents
        self.reviewer = Reviewer(llm_gen, self.prompt_manager, self.tools, cfg.verbose)
        self.planner = Planner(llm_gen, self.prompt_manager, cfg.verbose)
        self.writer = Writer(llm_gen, self.prompt_manager, cfg.verbose)
        # pass repo_path so Gatekeeper can persist in the correct repository
        self.gatekeeper = Gatekeeper(llm_gen, self.prompt_manager, self.repo, cfg.verbose)

        # Register A2A handlers for each specialized agent.
        self.a2a.register("reviewer", self.reviewer.handle_a2a)
        self.a2a.register("planner", self.planner.handle_a2a)
        self.a2a.register("writer", self.writer.handle_a2a)
        self.a2a.register("gatekeeper", self.gatekeeper.handle_a2a)

        # GitHub API (optional)
        self.github = None
        if cfg.github_token and cfg.github_owner and cfg.github_repo:
            self.github = GitHubTools(
                cfg.github_token,
                cfg.github_owner,
                cfg.github_repo,
                mcp_client=self.mcp_client,
            )

    def _build_mcp_client(self, cfg: AgentConfig) -> MCPClient:
        if cfg.mcp_server_command:
            command = [cfg.mcp_server_command] + list(cfg.mcp_server_args)
        else:
            command = [
                sys.executable,
                "-m",
                "code_generation_cli_agent.mcp_server",
                "--repo",
                str(self.repo),
            ]

        client = MCPClient(command=command, repo_path=self.repo, timeout_s=cfg.mcp_timeout_s)
        try:
            client.list_tools()
            return client
        except Exception as e:
            raise RuntimeError(f"Failed to initialize MCP tooling: {e}")

    def review_changes(self, base_ref: str = "main", commit_range: Optional[str] = None) -> CodeReview:
        """Task 1: Review changes."""
        msg = A2AMessage(
            message_id=str(uuid4()),
            from_agent="orchestrator",
            to_agent="reviewer",
            intent="review_changes",
            payload={"base_ref": base_ref, "commit_range": commit_range},
        )
        resp = self.a2a.send(msg)
        if not resp.ok:
            raise RuntimeError(resp.error)
        return CodeReview(**resp.payload["review"])

    def draft_issue_or_pr(
        self, draft_type: str = "issue", review: Optional[CodeReview] = None, instruction: Optional[str] = None
    ) -> tuple[ApprovalState, Optional[CodeReview]]:
        """Task 2: Draft Issue or PR with human approval."""
        # If no review provided, analyze current changes
        if review is None:
            review = self.review_changes()

        # Planner still validates intent in the A2A flow, even for explicit draft type.
        self.a2a.send(
            A2AMessage(
                message_id=str(uuid4()),
                from_agent="orchestrator",
                to_agent="planner",
                intent="plan_action",
                payload={"review": review.__dict__},
            )
        )

        # Draft content based on explicit type
        writer_intent = "draft_pr" if draft_type == "pr" else "draft_issue"
        writer_resp = self.a2a.send(
            A2AMessage(
                message_id=str(uuid4()),
                from_agent="orchestrator",
                to_agent="writer",
                intent=writer_intent,
                payload={"review": review.__dict__, "instruction": instruction},
            )
        )
        if not writer_resp.ok:
            raise RuntimeError(writer_resp.error)
        draft = DraftContent(**writer_resp.payload["draft"])

        gatekeeper_resp = self.a2a.send(
            A2AMessage(
                message_id=str(uuid4()),
                from_agent="orchestrator",
                to_agent="gatekeeper",
                intent="reflect_and_store",
                payload={"draft": draft.__dict__},
            )
        )
        if not gatekeeper_resp.ok:
            raise RuntimeError(gatekeeper_resp.error)

        approval_raw = gatekeeper_resp.payload["approval"]
        reflection_raw = approval_raw.get("reflection") or {
            "passed": False,
            "issues": [],
            "suggestions": [],
            "evidence": "",
        }
        approval = ApprovalState(
            draft_id=approval_raw["draft_id"],
            draft_content=DraftContent(**approval_raw["draft_content"]),
            reflection=ReflectionVeredict(**reflection_raw),
            user_approved=approval_raw.get("user_approved", False),
            created_url=approval_raw.get("created_url"),
        )

        return approval, review

    def approve_and_create(self, draft_id: str) -> RunResult:
        """User approves, create on GitHub."""
        approval_resp = self.a2a.send(
            A2AMessage(
                message_id=str(uuid4()),
                from_agent="orchestrator",
                to_agent="gatekeeper",
                intent="approve_draft",
                payload={"draft_id": draft_id},
            )
        )
        if not approval_resp.ok:
            return RunResult(False, approval_resp.error or "Draft not found")

        approval_raw = approval_resp.payload["approval"]
        reflection_raw = approval_raw.get("reflection") or {
            "passed": False,
            "issues": [],
            "suggestions": [],
            "evidence": "",
        }
        approval = ApprovalState(
            draft_id=approval_raw["draft_id"],
            draft_content=DraftContent(**approval_raw["draft_content"]),
            reflection=ReflectionVeredict(**reflection_raw),
            user_approved=approval_raw.get("user_approved", False),
            created_url=approval_raw.get("created_url"),
        )

        if not self.github:
            return RunResult(False, "GitHub not configured")

        draft = approval.draft_content
        try:
            if draft.draft_type == "issue":
                result = self.github.create_issue(draft.title, draft.body)
                if result:
                    approval.created_url = result.get("html_url")
                    return RunResult(True, f"Issue created: {approval.created_url}")
                return RunResult(False, "Failed to create issue (no response from GitHub)")
            else:
                # Use current branch for PR head
                ok, current_branch = self.tools.git_get_current_branch()
                if not ok or not current_branch:
                    return RunResult(False, "Could not determine current branch for PR")
                current_branch = current_branch.strip()
                
                # Check if git remote 'origin' exists
                ok, remote_check = self.tools.run("git remote -v")
                if not ok or "origin" not in remote_check:
                    # Try to add origin automatically
                    if self.github and self.github.owner and self.github.repo:
                        git_url = f"https://github.com/{self.github.owner}/{self.github.repo}.git"
                        if self.cfg.verbose:
                            print(f"[Agent] Adding git remote origin: {git_url}")
                        ok, msg = self.tools.run(f"git remote add origin {git_url}")
                        if not ok and "already exists" not in msg:
                            return RunResult(False, f"Failed to add git remote: {msg}")
                    else:
                        return RunResult(False, "Git remote 'origin' not configured. Run: git remote add origin <your-repo-url>")
                
                # Fetch from remote to ensure we have latest refs
                if self.cfg.verbose:
                    print(f"[Agent] Fetching from remote...")
                ok, msg = self.tools.run("git fetch origin")
                if not ok:
                    return RunResult(False, f"Failed to fetch from remote. Make sure the repository exists on GitHub and you have access: {msg}")
                
                # Check if main exists on remote
                ok, main_check = self.tools.run("git ls-remote --heads origin main")
                if not ok or "main" not in main_check:
                    return RunResult(False, "Branch 'main' does not exist on GitHub remote. Push your main branch first: git push -u origin main")
                
                # If on main branch, create a new feature branch automatically
                if current_branch == "main":
                    # Ensure local main is up to date with remote
                    if self.cfg.verbose:
                        print(f"[Agent] Ensuring main is up to date...")
                    ok, msg = self.tools.run("git pull origin main")
                    if not ok and "Already up to date" not in msg:
                        # Try reset if pull fails
                        ok2, msg2 = self.tools.run("git reset --hard origin/main")
                        if not ok2:
                            return RunResult(False, f"Failed to sync with remote main: {msg}")
                    
                    # Create feature branch name from draft title - sanitize carefully
                    import re
                    sanitized = re.sub(r'[^a-z0-9\-_]', '-', draft.title.lower()[:30])
                    sanitized = sanitized.strip('-').replace('--', '-')  # Clean up
                    
                    if not sanitized:
                        return RunResult(False, f"Could not create valid branch name from title: '{draft.title}'")
                    
                    feature_branch = f"feature/{sanitized}"
                    
                    if self.cfg.verbose:
                        print(f"[Agent] Creating branch: {feature_branch} from main")
                    
                    ok, msg = self.tools.run(f"git checkout -b {feature_branch}")
                    if not ok:
                        return RunResult(False, f"Failed to create feature branch '{feature_branch}': {msg}")
                    
                    # Make an empty commit so there's something to push
                    if self.cfg.verbose:
                        print(f"[Agent] Creating empty commit...")
                    ok, msg = self.tools.run(f'git commit --allow-empty -m "Initial commit for {feature_branch}"')
                    if not ok:
                        return RunResult(False, f"Failed to create commit: {msg}")
                    
                    current_branch = feature_branch
                
                # Check if branch exists on remote, if not push it
                if self.cfg.verbose:
                    print(f"[Agent] Checking if branch '{current_branch}' exists on remote...")
                ok, verify_msg = self.tools.run(f"git ls-remote --heads origin {current_branch}")
                
                if not ok or current_branch not in verify_msg:
                    if self.cfg.verbose:
                        print(f"[Agent] Branch not on remote, pushing...")
                    ok, msg = self.tools.run(f"git push -u origin {current_branch}")
                    if not ok:
                        return RunResult(False, f"Failed to push branch '{current_branch}' to GitHub: {msg}")
                    if self.cfg.verbose:
                        print(f"[Agent] Branch pushed successfully")
                else:
                    if self.cfg.verbose:
                        print(f"[Agent] Branch already exists on remote")
                
                if self.cfg.verbose:
                    print(f"[Agent] Creating PR with head='{current_branch}', base='main'")
                    print(f"[Agent] Owner: {self.github.owner}, Repo: {self.github.repo}")
                result = self.github.create_pull_request(draft.title, draft.body, current_branch)
                if result:
                    approval.created_url = result.get("html_url")
                    return RunResult(True, f"PR created: {approval.created_url}")
                return RunResult(False, "Failed to create PR (no response from GitHub)")
        except Exception as e:
            return RunResult(False, str(e))

    def reject_draft(self, draft_id: str) -> RunResult:
        """User rejects draft."""
        self.a2a.send(
            A2AMessage(
                message_id=str(uuid4()),
                from_agent="orchestrator",
                to_agent="gatekeeper",
                intent="reject_draft",
                payload={"draft_id": draft_id},
            )
        )
        return RunResult(True, "Draft rejected. No changes made.")

    def improve_issue(self, issue_number: int) -> tuple[str, DraftContent]:
        """Task 3: Improve existing issue."""
        if not self.github:
            return "GitHub not configured", DraftContent("", "", "issue")

        issue = self.github.get_issue(issue_number)
        if not issue:
            return "Issue not found", DraftContent("", "", "issue")

        title = issue.get("title", "")
        body = issue.get("body", "")

        # Critique current issue
        prompt = self.prompt_manager.get_prompt(
            "critique", "default", title=title, body=body, draft_type="issue"
        )
        llm = OllamaLLM(
            model=self.cfg.model,
            host=self.cfg.host,
            temperature=self.cfg.temperature,
        )
        critique = llm.generate(prompt)

        # Draft improved version
        prompt_improve = self.prompt_manager.get_prompt(
            "improve", "default", original_title=title, original_body=body, critique=critique
        )
        improved_response = llm.generate(prompt_improve)
        new_title, new_body = self.writer._parse_draft_response(improved_response)

        improved_draft = DraftContent(title=new_title, body=new_body, draft_type="issue")

        return critique, improved_draft

    def improve_pr(self, pr_number: int) -> tuple[str, DraftContent]:
        """Task 3: Improve existing PR."""
        if not self.github:
            return "GitHub not configured", DraftContent("", "", "pr")

        # GitHub treats PRs as "pulls" endpoint
        pr = self.github.get_issue(pr_number)  # This works for PRs too
        if not pr:
            return "PR not found", DraftContent("", "", "pr")

        title = pr.get("title", "")
        body = pr.get("body", "")

        # Critique current PR
        prompt = self.prompt_manager.get_prompt(
            "critique", "default", title=title, body=body, draft_type="pr"
        )
        llm = OllamaLLM(
            model=self.cfg.model,
            host=self.cfg.host,
            temperature=self.cfg.temperature,
        )
        critique = llm.generate(prompt)

        # Draft improved version
        prompt_improve = self.prompt_manager.get_prompt(
            "improve", "default", original_title=title, original_body=body, critique=critique
        )
        improved_response = llm.generate(prompt_improve)
        new_title, new_body = self.writer._parse_draft_response(improved_response)

        improved_draft = DraftContent(title=new_title, body=new_body, draft_type="pr")

        return critique, improved_draft
