# Quickstart — from clone to your first gated build

Every command below is copy-pasteable from a fresh clone root. You will install the
hooks, prove each layer works, and watch a deterministic gate say **no** — which is
the whole point of this kit.

## 1. Clone and sanity-check the toolchain (needs only python3 + pytest)

```bash
git clone https://github.com/Eobodoechine/loop-engineering.git
cd loop-engineering
python3 loop-team/harness/verify.py loop-team/examples/duration_parser
```

(`pip install pytest` if you don't have it — without pytest the harness falls back
to unittest discovery and this example reports `"passed": false`.)

You should see the harness's JSON verdict: `"passed": true`, `"runner": "pytest"` —
the deterministic Layer-1 verifier working on the shipped example project.

```bash
python3 loop-team/evals/run_evals.py        # the verifier-for-the-verifier
python3 loop-team/evals/acceptor.py --selftest   # PACE: false-accept <= alpha
```

Expect `SUITE: GREEN` (judge-dependent cases show as pending without an LLM judge)
and `RESULT: OK -- bound holds`.

## 2. Install the hooks

Follow `hooks/README.md` — it has the full five-hook `settings.json` block, the
per-hook verification commands, and troubleshooting. Optional extras
(`pip install pytest-testmon==2.1.4 radon`) unlock the impact gate and slop metrics.

## 3. Configure

```bash
cp .loop-team-config.example ~/.loop-team-config
# edit base_dir= to this clone's absolute path
cp skills/loop-team.SKILL.template.md ~/.claude/skills/loop-team/SKILL.md  # mkdir -p first
# replace <BASE_DIR> inside it with this clone's absolute path
```

## 4. Watch a gate say no (no agent required)

This runs the **step-size gate** end-to-end through the real Stop hook. Each
ingredient below is load-bearing — the gate arms only for a genuine orchestrator
session working a genuine git target:

```bash
export LOOP_GATE_DIR=$(mktemp -d)          # gate state dir (default ~/.loop-gate)
DEMO=$(mktemp -d)                          # a target repo with an initial commit
git -C "$DEMO" init -q
git -C "$DEMO" -c user.email=demo@x -c user.name=demo commit -q --allow-empty -m init
python3 -c "print('x = 1\n' * 300)" > "$DEMO/big_module.py"
git -C "$DEMO" add big_module.py           # must be TRACKED: the gate diffs vs HEAD
echo "$DEMO" > "$LOOP_GATE_DIR/demo_target"   # ARM: session 'demo' targets $DEMO

T=$(mktemp)                                # transcript carrying the REAL playbook
python3 - "$T" << 'PY'
import json, sys
head = open("loop-team/orchestrator.md").read(2000)
open(sys.argv[1], "w").write(json.dumps(
    {"role": "user", "content": [{"type": "text", "text": head}]}))
PY

echo "{\"transcript_path\":\"$T\",\"session_id\":\"demo\"}" \
  | python3 hooks/loop_stop_guard.py; echo "exit=$?"
```

Expected output: a `[MICRO-STEP GATE: step-size]` message telling you to commit what
you have, and `exit=2` — the hook just refused to let a turn end with 300 uncommitted
code lines. Commit the file in `$DEMO` and re-run the last command: `exit=0`.

## 5. Your first real run

In a Claude Code session in your own project:

1. Invoke `/loop-team` (or describe a build task — the UserPromptSubmit hook injects
   the loop directive on build-shaped prompts).
2. The orchestrator (Oga) reads its playbook, writes a spec, and dispatches a
   **plan-check Verifier** — you'll see its verdict end with a `LOOP_GATE:` line.
   Nothing gets coded until that line says the plan passed.
3. Builds proceed as **micro-steps**: Coder dispatch → impacted tests run in the main
   transcript → green → git checkpoint. The gates from step 4 are live the whole time.
4. Every verdict ends with the structured schema from `loop-team/roles/verifier.md`
   — including `erosion_note`, fed by the shadow slop gate.

## What you just proved

- Layer B (harness + evals) runs standalone — step 1.
- Layer C (enforcement) blocks for real — step 4.
- The team process (Layer A) rides on both — step 5.

Read `loop-team/orchestrator.md` next; it is the whole method in one file.
