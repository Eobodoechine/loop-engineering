# runner — Usage Guide

The `runner` package orchestrates the loop-team write→verify→fix cycle.

## Installation

No extra dependencies beyond stdlib + `anthropic` + `openai` (both optional).

## Configuration

Create `~/.loop-team-config`:

```
base_dir=~/Claude/loop
provider=anthropic
default_model=claude-haiku-4-5-20251001

# Per-role overrides (optional)
role.coder.provider=openai
role.coder.model=gpt-4o-mini
```

**Keys:**

| Key | Description | Default |
|-----|-------------|---------|
| `base_dir` | Path to the loop repo root (~ expanded) | `~/Claude/loop` |
| `provider` | Default LLM provider: `anthropic` or `openai` | `anthropic` |
| `default_model` | Default model ID | `claude-haiku-4-5-20251001` |
| `role.<name>.provider` | Provider override for a specific role | — |
| `role.<name>.model` | Model override for a specific role | — |

## Environment variables

| Variable | Required for |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Any role using `provider=anthropic` |
| `OPENAI_API_KEY` | Any role using `provider=openai` |

## CLI

```bash
# Show help
python -m runner --help

# Dispatch a single role
python -m runner dispatch --role coder --context "Write a hello-world function"

# Run the full loop (writes a per-step trace by default — see Observability)
python -m runner run --brief path/to/brief.md

# Run into a specific trace dir, or disable tracing
python -m runner run --brief brief.md --run-dir runs/2026-06-30_mybuild
python -m runner run --brief brief.md --no-trace

# Use a custom config
python -m runner run --brief brief.md --config /path/to/config
```

## Python API

```python
from runner import LoopTeam, parse_config, load_role

# Basic usage
team = LoopTeam()
result = team.run(brief_text)
print(f"success={result.success}, iterations={result.iterations}")

# Single role dispatch
response = team.dispatch_role("coder", "Write a bubble sort implementation.")

# Config only
cfg = parse_config()
print(cfg.base_dir, cfg.provider, cfg.default_model)

# Role file content
role_content = load_role("verifier", cfg.base_dir)
```

### LoopTeam constructor

```python
LoopTeam(config_path=None, llm_factory=None)
```

- `config_path`: path to config file (default: `~/.loop-team-config`)
- `llm_factory`: optional `callable(provider=..., model=...) -> llm_fn` for testing

### LoopTeam.dispatch_role

```python
team.dispatch_role(role_name: str, context: str) -> str
```

Loads the role file from `<base_dir>/loop-team/roles/<role_name>.md`, builds a prompt,
and calls it through `optimize.llm.call_with_retry`.

### LoopTeam.run

```python
team.run(brief: str, run_dir=None) -> RunResult
```

Runs the loop up to 6 iterations. Returns a `RunResult` with:
- `.success` — `True` if verifier returned `passed: true`
- `.iterations` — number of write/verify cycles executed

`run_dir` (optional): when set, the run is **observable and crash-resumable** —
it writes `trace.jsonl` (one JSON event per role dispatch + verdict, with
cumulative tokens/cost), an atomic `checkpoint.json` per iteration, and a
`run_log.md` summary. When `None` (the default for the Python API) nothing is
written and behaviour is unchanged. The CLI auto-creates `runs/<timestamp>-runner`
unless `--no-trace` is passed.

## Observability

```bash
python3 loop-team/harness/dashboard.py            # render runs/ into dashboard.html
python3 loop-team/harness/dashboard.py --root DIR --out my.html
```

`dashboard.py` reads every run dir (run logs + `trace.jsonl`) and renders a
single self-contained HTML page: pass rate, adversarial bugs caught, plan-check
rounds, and a per-run card with a live per-step trace where present. Schedule it
(cron/launchd) to keep a always-fresh "are my agents running as I want?" view.
**Note:** token/cost capture is pending (events record the model but tokens are
not yet surfaced from `optimize/llm.py`), so cost currently shows as a placeholder
— the trace structure, verdicts, and checkpoints are fully live.

## Error handling

| Error | Cause | Fix |
|-------|-------|-----|
| `RuntimeError: ANTHROPIC_API_KEY is not set` | Missing env var | `export ANTHROPIC_API_KEY=...` |
| `RuntimeError: OPENAI_API_KEY is not set` | Missing env var | `export OPENAI_API_KEY=...` |
| `FileNotFoundError: Role file not found` | Role name typo or missing .md | Check `roles/` directory |
| `ValueError: Unknown provider` | Bad provider in config | Use `anthropic` or `openai` |
