# Phase 1: Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md -- this log preserves the alternatives considered.

**Date:** 2026-03-26
**Phase:** 01-foundation
**Areas discussed:** Project structure, CLI design, Evaluation reporting, CallerInfo model shape

---

## Project Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Flat src/ package | src/phonebot/ with modules: pipeline/, evaluation/, models/, observability/, prompts/ | ✓ |
| Domain-driven layout | Separate packages per concern | |
| Minimal flat | Everything in root | |

**User's choice:** Flat src/ package
**Notes:** None

### Prompts location

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid | Field descriptions in code, system prompt externalized | |
| All in Pydantic model | Docstring + field descriptions all in Python code | ✓ |
| All externalized | System prompt and field descriptions from YAML/text files | |

**User's choice:** All in Pydantic model
**Notes:** GEPA will inject/modify at runtime

### Config management

| Option | Description | Selected |
|--------|-------------|----------|
| Environment vars + .env | DEEPGRAM_API_KEY, ANTHROPIC_API_KEY via .env file | ✓ |
| Settings class (Pydantic) | pydantic-settings BaseSettings class | |
| You decide | Claude picks | |

**User's choice:** Environment vars + .env
**Notes:** None

---

## CLI Design

### CLI framework

| Option | Description | Selected |
|--------|-------------|----------|
| Typer | Type-hint-based CLI from Pydantic ecosystem | |
| Click | Decorator-based CLI framework | |
| argparse | Standard library | |
| You decide | Claude picks | |

**User's choice:** Rich CLI library (Other)
**Notes:** User specifically requested Rich for CLI output

### Arg parsing

| Option | Description | Selected |
|--------|-------------|----------|
| Typer + Rich | Typer handles arg parsing, Rich under the hood | |
| argparse + Rich | Standard library args, Rich for output | |
| Rich only | Rich Console and manual arg handling | ✓ |

**User's choice:** Rich only
**Notes:** Maximum control over output formatting

### CLI arguments

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal | --model, --recordings-dir, --output | ✓ |
| Extended | Minimal + --prompt-file, --cache-dir, --verbose, --dry-run, --eval-only | |
| You decide | Claude designs args | |

**User's choice:** Minimal
**Notes:** None

### Progress display

| Option | Description | Selected |
|--------|-------------|----------|
| Rich progress bar | Progress bar X/30 with status updates | |
| Rich live table | Live-updating table per recording status | ✓ |
| Simple log lines | One line per recording completion | |
| You decide | Claude picks Rich display | |

**User's choice:** Rich live table
**Notes:** None

### Processing concurrency

| Option | Description | Selected |
|--------|-------------|----------|
| Sequential | One recording at a time, simpler to debug | |
| Async concurrent | Multiple recordings in parallel with asyncio | ✓ |
| You decide | Claude picks based on LangGraph | |

**User's choice:** Async concurrent
**Notes:** None

---

## Evaluation Reporting

### Display format

| Option | Description | Selected |
|--------|-------------|----------|
| Rich table + JSON file | Console table + outputs/eval_results.json | ✓ |
| Rich table only | Console output only | |
| JSON file only | Machine-readable only | |

**User's choice:** Rich table + JSON file
**Notes:** None

### Granularity

| Option | Description | Selected |
|--------|-------------|----------|
| Per-field + per-recording | Per-field accuracy AND per-recording breakdown | ✓ |
| Per-field only | Aggregate percentages only | |
| Full matrix | Per-field + per-recording + confusion details | |

**User's choice:** Per-field + per-recording
**Notes:** None

---

## CallerInfo Model Shape

### Confidence field

| Option | Description | Selected |
|--------|-------------|----------|
| Entity fields only for now | Add confidence in Phase 7 | |
| Include confidence from start | Add confidence field now | ✓ |

**User's choice:** Include confidence from start
**Notes:** None

### Confidence type

| Option | Description | Selected |
|--------|-------------|----------|
| Per-field confidence dict | confidence: dict[str, float] | ✓ |
| Single overall confidence | confidence: float | |
| Per-field enum | confidence: dict[str, Literal['high','medium','low']] | |

**User's choice:** Per-field confidence dict
**Notes:** e.g., {"first_name": 0.95, "email": 0.6}

### Prompting system

| Option | Description | Selected |
|--------|-------------|----------|
| Docstring = extraction context, Field desc = per-field instructions | Docstring explains context, field descriptions say how to extract | ✓ |
| Docstring = full system prompt, Field desc = format hints | Docstring has detailed rules, field descriptions focus on format | |
| You decide | Claude designs prompt split | |

**User's choice:** Docstring = extraction context, Field desc = per-field instructions
**Notes:** None

---

## Claude's Discretion

- Exact Rich table styling and column widths
- .env loading implementation
- Exact module names within src/phonebot/
- Evaluation JSON schema structure

## Deferred Ideas

None -- discussion stayed within phase scope
