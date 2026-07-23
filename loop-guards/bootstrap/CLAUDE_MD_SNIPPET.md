## loop-team guards bootstrap check (Claude Code)

At the start of this session, before doing anything else, run:

    python3 loop-guards/detect_install_state.py --tool claude_code

This is an explicit, TOOL-SCOPED check (never an aggregate/combined check
across both tools) -- it reports one of `INSTALLED` / `NOT_INSTALLED` /
`PARTIAL` for Claude Code specifically.

- If it reports `INSTALLED`: say nothing further about this -- proceed
  silently.
- If it reports `NOT_INSTALLED` or `PARTIAL`: before doing anything else,
  summarize for the human, in plain language, what these guards do and
  their effect:
  - a **run-log gate** (RUNLOG_MISSING) that blocks ending a turn when a
    post-build Verifier returned `VERDICT: PASS` but no `run_log.md` exists
    for that build;
  - a **checkpoint gate** (thrash-past-green / step-size) that blocks
    ending a turn when a green verify happened but the resulting work was
    never committed, or an uncommitted diff has grown too large.

  Then explicitly ask the human to accept or reject installing them. Only
  on an explicit "yes"/accept from the human, run:

      python3 loop-guards/install.py --install --tool claude_code

  This will show a diff of exactly what would change, then prompt again at
  a real terminal for final confirmation before writing anything.

  Never install without that explicit accept. Never pass a flag or
  environment variable to skip the human-facing prompt -- there isn't one,
  by design.
