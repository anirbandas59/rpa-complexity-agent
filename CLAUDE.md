# RPA Complexity Assessment Agent — Claude Code Project Memory

## Project Mission

Build an AI-powered multi-agent system that automates RPA process complexity
assessment by analyzing Process Design Documents (PDDs - Word/PDF), eliminating
the manual 2-4 hour assessment process.

## Current Phase
>
> UPDATE THIS LINE at the start of each phase session.
> Example: "Phase 1 — Scoring Engine. Task 1.1 in progress."
Phase 0 — Complete. Phase 1 — Scoring Engine — Complete. Phase 2 — LLM Layer — In Progress.

## Architecture Summary

- **Orchestration**: LangGraph (StateGraph per agent)
- **LLM Layer**: Multi-provider abstraction via LLMManager (never call providers directly)
- **Scoring**: Fully deterministic, zero LLM involvement
- **Output**: openpyxl Excel (3 sheets) + reportlab PDF
- **API**: FastAPI async background tasks
- **Frontend**: Streamlit 3-page app
- **Package Manager**: UV (always use `uv run` not `python`)

## Project Structure (Key Directories)

```text
core/           → Pure business logic, no framework dependencies
  scoring/      → Deterministic weight matrix, classifier, effort table
  models/       → All Pydantic models (shared across all layers)
agents/         → LangGraph StateGraphs (orchestration only)
tools/          → Single-responsibility tool functions
llm/            → Provider abstraction (LLMManager + providers)
api/            → FastAPI routes and middleware
frontend/       → Streamlit pages and components
data/reference/ → JSON source-of-truth files (weight_matrix, effort_table)
data/templates/ → output_template.xlsx (the Excel workbook to mirror)
tests/          → unit/ + integration/ + fixtures/
config/         → pydantic-settings, logging config
scripts/        → validation and seeding scripts
```

## NON-NEGOTIABLE RULES — Never Violate These

1. **Scoring engine never calls an LLM** — core/scoring/ is pure Python math
2. **Business logic never lives in agent files** — agents only call tools
3. **All LLM prompts live in prompts.py** — never inline in agent or tool code
4. **Every tool is independently importable and testable** — no circular imports
5. **All function inputs/outputs use Pydantic models** — no raw dicts as interfaces
6. **Fail loudly with typed exceptions** — never return None silently
7. **Always use `uv run` to execute Python** — never bare `python`
8. **Log at every agent node transition** using structured logging with session_id

## Scoring Domain Knowledge (Critical)

The 5 assessment attributes and their weights:

| Attribute          | XS | S | M | L | XL |
|--------------------|----|---|---|---|----|
| #1 Activities      | 2  | 2 | 4 | 6 | 8  |
| #2 Business Rules  | 2  | 2 | 4 | 6 | 8  |
| #3 Layouts         | 1  | 1 | 2 | 3 | 4  |
| #4 Interfaces      | 1  | 1 | 2 | 3 | 4  |
| #5 Add. Technology | 1  | 1 | 2 | 3 | 4  |

Classification bands: S=7-8, M=9-15, L=16-22, XL=23-28
XS = special case: max 2 attributes selected, all in XS column

Effort table (days):
XS=10, S=20-40, M=50, L=60, XL=80
Sprints: XS=1, S=2-4, M=5, L=6, XL=8

SP conversion: 1 hour = 0.0666 SP (1 SP ≈ 15 hours)

## Ground Truth Validation Case

From the actual project in the Excel file:

- Activities: XL (41-60) → weight 8
- Business Rules: XL (5-6) → weight 8
- Layouts: L (4-6) → weight 3
- Interfaces: S (1-2) → weight 1
- Technology: S (0) → weight 1
- Total score: 21 → Classification: L

Any scoring tool must reproduce this exactly.

## Typed Exception Hierarchy

Define these in core/exceptions.py:

- DocumentProcessingError
- ScoringValidationError  
- LLMProviderError
- AgentExecutionError
- OutputGenerationError

## Testing Requirements

- Every new file must have a corresponding test
- Tests live in tests/unit/ (for tools/core) or tests/integration/ (for agents)
- Use pytest fixtures for shared setup
- Ground truth test case must pass before any phase is considered complete
- Run tests with: `uv run pytest tests/ -v`

## How to Run the Project

```bash
# Run tests
uv run pytest tests/ -v

# Run validation script
uv run python scripts/validate_matrix.py

# Start API
uv run uvicorn api.main:app --reload

# Start frontend
uv run streamlit run frontend/app.py
```

## Environment

- No conda/mamba — UV manages Python and all dependencies directly
- Python 3.11 managed by UV (auto-downloaded on first uv sync)
- Always prefix commands with `uv run` — never use bare `python` or `python3`
- To enter an interactive shell: `uv run python`
- UV virtual env lives in .venv/ inside the project root

## Dependency Management

- Runtime deps go in [project] dependencies = [...] in pyproject.toml
- Dev deps go in [dependency-groups] dev = [...] — NOT [tool.uv.dev-dependencies]
- Always use: uv sync (never pip install)
- To add a new dep: `uv add <package>` (runtime) or `uv add --group dev <package>` (dev)

## Git Commit Convention

Format: `type(scope): description`
Types: feat | fix | test | refactor | docs | chore
Examples:

- feat(scoring): add weight matrix loader
- test(scoring): add boundary tests for classifier
- fix(parser): handle encrypted PDFs gracefully

## Current Known Ground Truth

File: data/templates/output_template.xlsx
3 sheets: Calculator | Steps | Feature and delivery timeline
This file is the single source of truth for all domain logic.
