#!/usr/bin/env python3
"""
loop_guard.py — UserPromptSubmit hook that makes the loop-engineering discipline AUTOMATIC.
This is the deterministic "something that can say no" layer (CLAUDE.md + the skill are only nudges).

How it works: Claude Code runs UserPromptSubmit hooks before the model sees a prompt. Whatever
this script prints to stdout is injected into the model's context. So on any build/edit-a-feature
prompt, it injects a mandatory reminder to run the loop and not declare done until an independent
verifier passes. On trivial prompts it stays silent (exit 0, no output).

INSTALL: see README.md in this folder. (Add to ~/.claude/settings.json hooks.UserPromptSubmit.)
"""
import sys, json, re

try:
    data = json.load(sys.stdin)
    prompt = (data.get("prompt") or "").lower()
except Exception:
    sys.exit(0)  # never block on parse error

# Build/edit-a-feature verbs + targets
BUILD = r"(build|create|add|edit|modify|update|improve|fix|refactor|implement|automate|wire up|make it|set up|develop|code|test|write test|write a test|handle testing|add test)"
TARGET = r"(feature|skill|script|tool|automation|agent|workflow|gate|rule|parser|pipeline|loop|render|build script|hook|component|function|endpoint|\bapi\b|\bapp\b|module|service|integration|model|schema|\bpage\b|class|database|backend|frontend|bug|website|widget|dashboard|bot|plugin|test suite|tests|spec|verification)"
# 'bug' IS a trigger by design — bug fixes run the loop. EXCLUDE still suppresses genuinely trivial
# edits: typo, one-line, small/quick fix, and content/docs (resume, cover letter, plain doc).
EXCLUDE = r"(resume|cover letter|typo|wording|reword|document|\bdoc\b|one[- ]line|one line|small fix|quick fix|format the|what jobs|find jobs|apply to|summar)"

def is_feature_work(p):
    if re.search(EXCLUDE, p):
        return False
    return bool(re.search(BUILD, p) and re.search(TARGET, p))

if is_feature_work(prompt):
    print(
        "[LOOP GUARD] This is feature build/edit work. You MUST run the loop: writer -> INDEPENDENT "
        "verifier sub-agent (grades against the loop rubric, tests live) -> fix -> log fix_plan -> "
        "RE-VERIFY independently. Use the loop kit: loop-team/orchestrator.md is the method, "
        "roles/verifier.md the grader; add your private rubrics (RUN/VERIFIER files) if present. "
        "Do NOT declare the feature done or close its task until the independent verifier confirms PASS. "
        "Writer self-testing does not count."
    )
sys.exit(0)
