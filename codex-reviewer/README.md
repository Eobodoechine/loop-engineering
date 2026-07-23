# Codex-as-reviewer — the simple spike

A second-opinion reviewer using Codex, with **none** of the credit-gate / worker-identity /
routing-pilot machinery. Codex reads a diff and returns a verdict. That's it. The verdict is
**advisory** — your Claude Verifier or you still own the real PASS.

Two ways to wire it. Start with A (robust, works today). Add B only if you want Claude to call
Codex inline without leaving the session.

---

## A. Artifact handoff (recommended — version-proof, no session fragility)

The reliable pattern everyone converges on: hand Codex a file, get a verdict file back. No MCP
thread-id juggling (the official Codex MCP server historically didn't return the thread id, which
is where multi-turn integrations break).

```bash
chmod +x codex-review.sh

./codex-review.sh              # review unstaged changes
./codex-review.sh --staged     # review staged changes
./codex-review.sh main         # review everything vs main
./codex-review.sh --file web/src/app/api/sync/airbnb/route.ts
```

Verdicts are written to `.codex-reviews/`. The script exits `1` if Codex says `VERDICT: FAIL`,
so you can branch on it in a pre-commit hook or a loop step.

Requires: `codex --version` works and is authed. If your CLI's flags differ, check
`codex exec --help` and adjust the two flags in the script (`--sandbox read-only`).

## B. Register Codex as an MCP server in Claude Code (optional)

If you want Claude to invoke Codex as a tool mid-session, drop this in your project's `.mcp.json`
(or run `claude mcp add codex -- codex mcp-server`):

```json
{
  "mcpServers": {
    "codex": { "command": "codex", "args": ["mcp-server"] }
  }
}
```

Then in a session you tell Claude: "hand this diff to the codex tool for an independent review."
Keep the reviewer **advisory** — don't let its output auto-satisfy a gate. That advisory boundary
is the whole reason this stays a 20-line spike instead of the 380KB adapter.

---

## What this deliberately does NOT do

- No "credit" for Codex's verdict — it never counts as an independent-verifier PASS on its own.
- No shared session / thread-id management (artifact handoff sidesteps it).
- No cross-provider USD routing (Codex has no billing authority to compare against).

If you later want *automatic per-task routing* (easy→cheap, hard→frontier) rather than a manual
reviewer, evaluate the off-the-shelf `CodeRouter` project instead of hand-building it.

## Honesty note

This scaffold was written but **not executed** — there's no Codex CLI or your repo in the
session it was authored in. Run step A once on a throwaway diff to confirm your CLI's `exec`
flags match before wiring it into anything.
