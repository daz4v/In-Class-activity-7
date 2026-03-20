# GitHub Repository Agent

A sophisticated multi-agent AI system for analyzing code changes, drafting GitHub Issues and Pull Requests, and improving existing Issues/PRs.

## Features

### Three Core Tasks

#### Task 1: Review Code Changes
Analyzes git diffs to identify:
- Change type (feature, bugfix, refactor, docs, other)
- Risk level (low, medium, high)
- Issues and potential improvements
- Recommendation (create issue, create PR, or no action)

```bash
agent review --base main
agent review --range HEAD~3..HEAD
```

#### Task 2: Draft and Create Issue or PR
Drafts GitHub Issues or Pull Requests with:
- AI-generated titles and descriptions
- Gatekeeper verification (reflection critique)
- Human approval workflow before creation
- Integration with GitHub API

```bash
agent draft issue --instruction "Add rate limiting to login endpoint"
agent draft pr --instruction "Refactor duplicated pricing logic"
agent approve --draft <draft_id> --yes
```

#### Task 3: Improve Existing Issue or PR
Analyzes and improves existing GitHub Issues/PRs:
- Identifies unclear or vague language
- Suggests better structure and acceptance criteria
- Provides improved version for comparison

```bash
agent improve issue --number 42
agent improve pr --number 17
```

## Multi-Agent Architecture

The system uses four specialized agents:

1. **Reviewer** - Analyzes code changes and identifies issues
2. **Planner** - Decides what action to take based on review
3. **Writer** - Drafts Issue or PR content
4. **Gatekeeper** - Reflects on draft quality and enforces human approval

### A2A Protocol

The orchestrator now uses an A2A (Agent-to-Agent) message envelope for all
intra-agent calls:

- `orchestrator -> reviewer` (`review_changes`)
- `orchestrator -> planner` (`plan_action`)
- `orchestrator -> writer` (`draft_issue` / `draft_pr`)
- `orchestrator -> gatekeeper` (`reflect_and_store`)

This keeps sub-agent integration explicit and protocol-driven.

### MCP Tooling

Tool calls now support MCP (Model Context Protocol) over stdio for git
operations used by the reviewer/orchestrator. The app starts an internal MCP
server module by default and requires MCP initialization to succeed.

You can also provide your own MCP server command.  

## Installation
Go into the code_generation_agent   
```bash
.venv\Scripts\Activate.ps1
```  

```bash
pip install -e .
```
Then CD to src/code_generation_cli_agent  

## Usage

### Setup Environment Variables

```bash
$env:OLLAMA_MODEL="llama2"
$env:OLLAMA_HOST="http://localhost:11434"
$env:GITHUB_TOKEN ="your_github_token"
$env:GITHUB_OWNER ="your_github_org"
$env:GITHUB_REPO ="your_repo_name"
```

### Example Workflow
CD to the local of the repo you want to edit   

```bash
# 1. Review recent changes
agent review --base main

# 2. If issues found, draft an issue
agent draft issue --instruction "Add input validation to login form"

# 3. Review the draft (auto-reflected by Gatekeeper)
# 4. Approve and create on GitHub
agent approve --draft <draft_id> --yes

# 5. Improve an existing issue
agent improve issue --number 42
```

### Interactive Mode

Run without arguments to enter interactive mode:

```bash
agent
```

## Configuration

### Command-Line Options

- `--repo` - Repository path (default: current directory)
- `--model` - Ollama model to use (default: llama2)
- `--host` - Ollama host (default: http://localhost:11434)
- `--temperature` - LLM sampling temperature (default: 0.0)
- `--verbose` - Enable verbose output
- `--github-token` - GitHub API token
- `--github-owner` - GitHub owner/organization
- `--github-repo` - GitHub repository name
- `--mcp-server-command` - External MCP server command
- `--mcp-server-arg` - Extra args for MCP command (repeatable)
- `--mcp-timeout` - MCP timeout in seconds

### Prompts

All prompts are stored in `prompts/` as YAML files:

- `review.yaml` - Code review analysis
- `critique.yaml` - Draft quality critique
- `draft.yaml` - Issue and PR drafting
- `improve.yaml` - Improvement suggestions

## Design Patterns

### Planning Pattern
Structured analysis before any action (review → plan → decide)

### Tool Use Pattern
Real git commands (git diff, git log) and GitHub API calls

### Reflection Pattern
Gatekeeper critiques drafts and checks:
- Clarity and completeness
- Evidence and support
- Adherence to guidelines

### Multi-Agent Pattern
Four distinct roles with clear responsibilities:
- Reviewer analyzes
- Planner decides
- Writer creates
- Gatekeeper verifies

## Exit Status Codes

- `0` - Success
- `1` - General error
- `130` - Interrupted by user (Ctrl+C)

## Version

1.0.0

## License

UNLICENSED
