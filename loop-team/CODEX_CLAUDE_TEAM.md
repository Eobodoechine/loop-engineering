# Codex + Claude Code Loop-Team Bridge

This is the recommended local shape when building from Codex:

- Codex/Oga stays in this chat as coordinator, primary builder, integrator, and final local verifier.
- Claude Code supplies independent non-Coder roles through `claude -p`.
- Claude Code is not used as a same-checkout Coder by this bridge. If Claude should write code, use a separate worktree and merge deliberately.

## Preflight

Check whether the local Claude Code CLI is usable:

```bash
python3 loop-team/harness/claude_role_runner.py --check
```

If it reports `claude_not_logged_in` or `loggedIn: false`, run Claude Code login outside this runner:

```bash
claude auth login
```

## Plan-Check Verifier

```bash
python3 loop-team/harness/claude_role_runner.py \
  --role plan-check-verifier \
  --prompt-file loop-team/runs/<run>/specs/spec.md \
  --output loop-team/runs/<run>/claude_plan_check.txt
```

The runner validates that the last non-empty line is exactly one of:

```text
LOOP_GATE: PLAN_PASS
LOOP_GATE: PLAN_FAIL
```

## Post-Build Verifier

```bash
python3 loop-team/harness/claude_role_runner.py \
  --role post-build-verifier \
  --prompt-file loop-team/runs/<run>/verify_handoff.md \
  --output loop-team/runs/<run>/claude_verify.txt
```

The runner validates that the last non-empty line is exactly one of:

```text
VERDICT: PASS
VERDICT: FAIL
VERDICT: FALSE-PASS
```

## Claude-Backed Coder

Coder remains isolated behind the Coder-specific launcher, not `claude_role_runner.py`:

```bash
python3 loop-team/harness/claude_coder_runner.py \
  --spec loop-team/runs/<run>/specs/spec.md \
  --spec-sha256 <sha256> \
  --transcript <current-transcript.jsonl> \
  --coder-worktree <distinct-git-worktree> \
  --artifact-dir loop-team/runs/<run>/claude_coder_artifacts \
  --repo-health-classification hardening-bugfix \
  --repo-health-repo loop \
  --prompt-file loop-team/runs/<run>/coder_prompt.md
```

This launcher requires prior same-spec plan-check credit before `claude -p` starts, rejects dangerous permission bypass flags, and requires a distinct git worktree passed through `--add-dir`. Its artifacts keep the Coder's Decision Log and raw output for Oga/Researcher diagnosis only; Verifier handoff must exclude that reasoning and any green/pass hints.

Do not use direct `claude -p` Coder calls outside this launcher, `@steipete/claude-code-mcp`, or `--dangerously-skip-permissions` as the durable loop-team Coder path. Claude auth/config presence alone is not readiness; if auth is missing, the status is blocked external setup.

## Native Codex Coder Handoff

For native Codex sub-agent dispatch, the `spawn_agent` `message` must begin with the
same repo-health marker pair used by the Claude-backed launcher prompt:

```text
REPO_HEALTH_CLASSIFICATION=<new-capability|continuing-phase|hardening-bugfix>
REPO_HEALTH_REPO=<repo-id>
SPEC: loop-team/runs/<run>/specs/spec.md
SPEC_SHA256=<sha256>

You are the loop-team Coder for ...
```

Required machine syntax is `KEY=value`. Do not use colon-separated marker syntax
as valid marker syntax. Human-readable `this dispatch is:` reasoning may appear
later in the message, but the live guard only accepts the two `REPO_HEALTH_*=`
lines. Include exactly one of each marker in every Coder `message`.
`new-capability` requires a current-turn `repo_health_gate.py <repo-id>` `CLEAR`
verdict before `spawn_agent`; `continuing-phase` and `hardening-bugfix` do not
require a fresh repo-health gate run.

## Other Roles

Supported non-Coder roles:

- `test-writer`
- `researcher`
- `gold-judge`
- `live-smoke`

The `coder` role is intentionally not supported by `claude_role_runner.py`. Keeping one writer in one checkout prevents the shared-worktree collisions this project has already hit.
