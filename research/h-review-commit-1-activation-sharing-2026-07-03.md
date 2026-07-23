# Domain brief: sharing `_activation()`'s `(target, session_id)` tuple between
# `micro_step_gates.run()` and a new gate in `loop_stop_guard.py` (H-REVIEW-COMMIT-1)

Mode D domain brief. Date: 2026-07-03. Researcher for Oga, H-REVIEW-COMMIT-1 build.

## Scope

Question from Oga: is there a third option, better than (a) a second independent
`_activation()` call from the new gate, or (b) changing `micro_step_gates.run()`'s
tested 2-tuple return contract, for getting the new git-show gate in
`loop_stop_guard.py` the `(target, session_id)` tuple that `run()` already computes
internally via `_activation(data)`?

---

## Question 1 — Is a Stop hook guaranteed to be a fresh, short-lived subprocess per firing?

**Answer: Yes, confirmed from three independent sources — official docs, this
repo's own registration config, and this repo's own test-harness invocation
pattern. No persistent server, no cross-invocation module-import caching.**

**Source 1 — official Claude Code hooks docs** (`https://code.claude.com/docs/en/hooks`):
> "Handlers run in the current directory with Claude Code's environment."
> Timeout is specified per hook invocation: "Defaults: 600 for `command`, `http`,
> and `mcp_tool`; ... `UserPromptSubmit` lowers the `command`... default to 30..."

The docs describe command hooks as receiving JSON on stdin and returning a
decision via exit code / stdout per firing, with a per-invocation timeout. There
is no mention anywhere of hook processes persisting, being pooled, reused, or
caching state/imports across firings — the model is stateless, ephemeral
subprocess execution, one process per event.

**Source 2 — this repo's own registration config** (`hooks/README.md` lines 21-49):
```json
"Stop": [
  { "hooks": [ { "type": "command",
      "command": "python3 '/absolute/path/to/loop-engineering/hooks/loop_stop_guard.py'" } ] }
]
```
This registers a literal `python3 <script>.py` command as the Stop hook. Claude
Code's `command`-type hook contract (per source 1) invokes this as a subprocess
per event — there is no flag or mechanism in the hooks system for a persistent
`command` hook process.

**Source 3 — this repo's own file and test-harness confirm the same model directly:**
- `loop_stop_guard.py` itself (lines 27-30) does `data = json.load(sys.stdin)` at
  **module scope**, immediately on import, and the file's own docstring (lines
  1-14) says: "On Stop, Claude Code passes `{transcript_path, stop_hook_active}`."
  A module that reads its own input from stdin unconditionally at import time can
  only work correctly if each firing is a fresh Python process — if the process
  were reused, a second firing's `json.load(sys.stdin)` would block waiting for
  new stdin bytes on a process whose stdin was already consumed/closed, or worse,
  silently reuse module-level state from the previous invocation (e.g. `data`
  itself is a plain module-level global, line 28).
- `hooks/README.md` line 98-100, the `subagent_stop_gate.py` "Logic check", *is
  itself* a literal fresh-subprocess invocation used to test the hook:
  `subprocess.run([sys.executable,'hooks/subagent_stop_gate.py'], input=json.dumps(...),
  capture_output=True, text=True)` — the project's own test convention for every
  hook in this directory is "pipe JSON into a brand-new `python3 hookfile.py`
  process and read stdout/exit code," matching the docs exactly.
- `hooks/test_micro_step_gates.py`'s `TestLiveGuardEndToEnd` and
  `TestDefensiveWrapper` classes (lines 277-317) test the LIVE
  `loop_stop_guard.py` the same way: `subprocess.run([sys.executable, guard],
  input=stdin, ...)`. There is no fixture anywhere in this test file that invokes
  the guard twice against the same process/interpreter to test cross-invocation
  state — the entire test suite's model is one subprocess per hook firing.

**Conclusion for option 3's safety precondition:** confirmed true. Each Stop hook
firing is a brand-new `python3 loop_stop_guard.py` process. `loop_stop_guard.py`
imports `micro_step_gates` fresh (line 859, `import micro_step_gates as _msg_mod`)
every single firing — Python's module cache (`sys.modules`) does NOT survive
between separate `python3` invocations; it only survives within one process's
lifetime. So any module-level variable set during `_msg_mod.run(data)` inside
this one process is guaranteed to still be `_msg_mod`'s own attribute later in
the SAME process/turn (the new "git show" gate runs after, later in the same
file execution), and is guaranteed to be gone before the NEXT firing (a brand-new
process re-imports the module from scratch, re-executing top-level code and
resetting all module-level state to its initializer). This closes the race
completely: no second call, no redundant disk read, no cross-session leak.

---

## Question 2 — Module-level "last computed" cache pattern: real, idiomatic, safe?

**Answer: Yes — this is the "module-scoped last-result cache" pattern, a standard
and safe way to share already-computed state across two callers within one
process without changing a tested public function's return contract. Given
Question 1's confirmed fact (fresh process per hook firing), it is safe here.**

### Concretely, what it looks like

In `hooks/micro_step_gates.py`, inside `_activation(data)` (currently lines
158-183), add a side-effect assignment right before each `return`:

```python
_LAST_ACTIVATION = None  # module-level, reset to None on every fresh import

def _activation(data):
    """Return (target, session_id) when gates are armed, else None."""
    global _LAST_ACTIVATION
    tpath = data.get("transcript_path")
    if not tpath or not os.path.exists(tpath):
        _LAST_ACTIVATION = None
        return None
    ...
    if not os.path.isdir(os.path.join(target, ".git")):
        _LAST_ACTIVATION = None
        return None
    _LAST_ACTIVATION = (target, session_id)
    return target, session_id
```

`run(data)` already calls `_activation(data)` as its first line (line 218:
`act = _activation(data)`) on every invocation, on every code path, before
anything else — so `_LAST_ACTIVATION` is unconditionally freshened by every
`run()` call, whether it resolves to `None` or a real tuple. `run()`'s own
signature, return type, and all 9 return sites are untouched — zero test
breakage, confirmed by re-reading `hooks/test_micro_step_gates.py`'s 4
strict-equality assertions (`assert msg.run(data) == (False, "")` at lines
88, 93, 99, 105) against the proposed change: none of them inspect
`_LAST_ACTIVATION`, and `run()`'s bytecode-level behavior (what it returns to
its caller) is identical before and after.

The new gate in `loop_stop_guard.py` (after line 864, following the existing
`_msg_blocked, _msg_text = _msg_mod.run(data)` call) then reads:

```python
_act = getattr(_msg_mod, "_LAST_ACTIVATION", None)
if _act:
    _target, _session_id = _act
    # ... run `git show` against _target ...
```

### Is this idiomatic/safe for "share already-computed state across two callers
within one process without changing a tested public contract"?

Yes. This is a well-known variant of the **module-level cache / sentinel
pattern** — the same family as Python stdlib's own `functools.lru_cache` (state
lives on the wrapped function object, an attribute of the module-loaded
callable, reset on reimport) and `re`'s internal compiled-pattern cache. The key
properties that make it safe and idiomatic here:

1. **Scoped correctly to the actual invariant.** The invariant this needs is
   "shared within one process's single Stop-hook execution," and Question 1
   proved that's exactly the lifetime of the module here — no broader, no
   narrower. A pattern is only "idiomatic" if its lifetime assumption matches
   the real process model; here it does, by direct confirmation, not by
   assumption.
2. **Additive, not contract-changing.** `_activation()` is already a private
   (`_`-prefixed) helper, not part of `run()`'s tested public 2-tuple contract.
   Adding a documented side effect to a private helper is a strictly local,
   additive change — nothing that calls `_activation()` or `run()` today needs
   to change how it calls them.
3. **No new disk I/O, no new race window.** Unlike option (a) (second
   independent `_activation()` call), which re-reads `$LOOP_GATE_DIR/<session>_target`
   from disk a second time and is thus exposed to a concurrent session
   rewriting that file between the two reads, option 2 has exactly ONE read of
   that file per process (inside the one `_activation()` call already made by
   `run()`), and both the micro-step gate's decision and the new git-show
   gate's decision are computed from the *identical* resolved `target` value.
   This is strictly stronger than option (a): option (a) narrows the race to
   "a very small window," option 2 removes the second read entirely.

### Real risks worth naming

1. **Ordering dependency — `run()` must execute before the new gate reads
   `_LAST_ACTIVATION`.** This is true today (the new gate is being added AFTER
   the existing `_msg_mod.run(data)` call at line 860, per Oga's own plan), but
   it is a structural assumption the code must defend, not just get right by
   accident of placement. Concretely:
   - Initialize `_LAST_ACTIVATION = None` at module level so an out-of-order
     read (or a read after `run()` raised before reaching the `_activation()`
     call — not currently possible since it's `run()`'s first line, but worth
     defending anyway) fails safe: `getattr(_msg_mod, "_LAST_ACTIVATION", None)`
     with an explicit `if _act:` None-check, exactly as sketched above. Never
     assume the attribute exists or is non-None.
   - `run()`'s existing `try/except SystemExit: raise / except Exception:` wrapper
     in `loop_stop_guard.py` (lines 856-880) means if `_msg_mod.run(data)` itself
     raises for some OTHER reason after `_activation()` already set
     `_LAST_ACTIVATION`, the new gate (if placed inside the same try block)
     would never run at all (whole block falls into the `except Exception` and
     writes the fail-open warning) — so this isn't actually a hazard for the
     new gate specifically, but it does mean the new gate must NOT be placed
     ahead of the `run()` call, and should probably be placed inside the SAME
     try/except for consistent fail-open behavior (matching this file's
     existing pattern for the "shadow slop report" sub-block at lines 865-876,
     which already does its own extra `_msg_mod._activation(data)` call inside
     a nested `try/except Exception: pass`).
   - Add one clarifying code comment at the `_LAST_ACTIVATION` declaration
     stating the ordering invariant explicitly, since nothing in Python enforces
     it structurally (this is the "instructional, not structural" residual —
     see honesty-bar note below).

2. **If this module were ever imported by something with a longer process
   lifetime** (e.g. a future persistent test runner, a long-lived daemon, or a
   pytest session that imports `micro_step_gates` once and calls `run()` many
   times across many "logical" hook firings within one Python process — this is
   NOT hypothetical, it is EXACTLY what `test_micro_step_gates.py` already does
   today at the unit-test level, e.g. `TestRetryCapGate.test_third_same_signature_blocks`
   calls `msg.run(data)` multiple times in a single test-process body), then
   `_LAST_ACTIVATION` would carry state across those calls within that one
   pytest process. This is **not a correctness hazard for the new gate's own
   logic** (each call to `run()` still freshens `_LAST_ACTIVATION` to that
   call's own true activation result, since `_activation()` runs unconditionally
   at the top of every `run()` call) — but it does mean: (a) any NEW test that
   asserts on `_LAST_ACTIVATION` directly must call `run()` immediately before
   checking it (never assume it reflects an "old" call), and (b) if some future
   caller reads `_LAST_ACTIVATION` WITHOUT having just called `run()` in the
   same logical turn (violating risk #1's ordering invariant) inside a
   long-lived process, it could read a stale value from a PRIOR turn/session
   rather than `None` — this is the actual escalated version of risk #1 and
   confirms the ordering invariant must be enforced at the new gate's call
   site, not assumed from the process model alone. Given Question 1's finding
   that the PRODUCTION path is one-process-per-firing, this composite risk is
   real only for a hypothetical future re-architecture, not for
   H-REVIEW-COMMIT-1's actual deployment — but the code comment from risk #1
   should say this explicitly so a future editor doesn't get surprised.

3. **Thread-safety:** not a concern here. Stop hooks are one process handling
   one JSON stdin payload synchronously, top to bottom (confirmed by
   `loop_stop_guard.py`'s own module-level, non-threaded, straight-line
   execution from line 28 to line 883) — there is no concurrent-thread access
   to `_LAST_ACTIVATION` within a single firing.

4. **Naming/`global` clarity:** using the `global _LAST_ACTIVATION` statement
   inside `_activation()` is required (Python's default is to treat an
   assigned-to name in a function scope as local unless declared `global`) and
   is a well-known, explicit, greppable idiom — not a hidden or surprising
   side effect once the docstring documents it, which it must.

**Transfer-condition check (per role-brief requirement):**
- (a) Execution context required: exactly what this repo's own hook
  infrastructure already provides — one fresh `python3` process per Stop-hook
  firing, straight-line synchronous execution, no threads, no persistent
  server.
- (b) Does the target context satisfy it? Yes, confirmed directly (Question 1,
  three sources: official docs, this repo's registration config, this repo's
  own test-harness invocation idiom).
- (c) Is the guarantee structural or instructional? **Mixed.** The "no
  cross-invocation leakage" half is STRUCTURAL — Python's `sys.modules` cache
  cannot survive a process exit, so this is enforced by the OS/interpreter, not
  by a participant following instructions; it cannot be silently violated by a
  future Coder forgetting something. The "new gate reads `_LAST_ACTIVATION`
  only AFTER `run()` has been called in the same process" half is
  **INSTRUCTIONAL** — nothing in Python stops a future edit from reordering the
  two blocks or adding a new call site that reads `_LAST_ACTIVATION` before
  `run()` runs. Per the role brief's flag criterion: would a compliance failure
  here be silent and load-bearing? With the `if _act:` / `getattr(..., None)`
  None-check as specified above, a reordering failure degrades to "the new git-
  show gate silently does nothing this turn" (fails open, matching this file's
  own house style throughout — e.g. the testmon gate's "degraded DB: fail-open"
  at micro_step_gates.py line 407) rather than acting on stale/wrong data. That
  is the safe failure direction and should be called out explicitly in code
  comments as the reason the None-check is mandatory, not optional.

---

## Question 3 — Precedent check: is this pattern already used in this repo?

**Answer: Yes, a real, directly-analogous precedent exists: `loop-team/harness/log.py`'s
`get_logger()`.**

`loop-team/harness/log.py` (read directly, lines 1-50 docstring + line 90):
```python
_cache = {}
_cache_lock = threading.Lock()
```
and its own docstring states the design intent explicitly (lines 44-47):
> "IDEMPOTENT: `get_logger` is cached/keyed by `(name, run_dir)`: repeated calls
> return the same instance and never attach duplicate handlers / double-write.
> Any backend configuration is performed at most once per process (guarded), so
> a second `get_logger` can never reset state mid-run."

This is the same underlying technique — a **module-level dict/variable holding
already-computed state, read by later callers within the same process to avoid
redundant work/recomputation** — applied to a different concrete problem
(avoiding duplicate logger handler attachment vs. avoiding a duplicate
`_activation()` disk read), but the same idiom family and the same "at most
once per process" framing that Question 1's fresh-process model licenses. This
means the proposed `_LAST_ACTIVATION` pattern is NOT foreign to this codebase's
own style — it mirrors an existing, deliberately-designed module-level cache
already shipped and in production use in the harness layer.

No other module in `hooks/` or `loop-team/harness/` uses a bare module-level
`_LAST_*`-named variable for this exact "expose one already-computed value to a
second caller" shape (the grep for `_LAST_\|_last_` across both directories
returned no other hits besides `log.py`'s differently-named `_cache`), so
`log.py`'s `_cache` is the closest and only real precedent — worth mirroring its
style (a clearly-named module-level container, a docstring stating the
idempotency/lifetime guarantee explicitly) rather than inventing new
conventions.

---

## Question 4 — Any other real, known Python pattern for this exact problem shape?

Problem shape: "memoize/share one already-computed value, scoped to a single
process invocation, between two call sites in the same call chain, without
changing a tested function's return signature."

Options surveyed, evaluated against this specific shape:

1. **Module-level cache/sentinel (Question 2/3's answer)** — the standard
   solution for "two callers in the same process, no contract change." Already
   has in-repo precedent (`log.py`). **Recommended.**

2. **`functools.lru_cache` / `functools.cache` on `_activation` itself** —
   Python stdlib's memoization decorator. Would technically also solve "call
   `_activation(data)` a second time from the new gate without re-doing the
   disk I/O," since a cached call with the same `data` dict would return the
   cached result instantly. **Rejected for this exact case**: `lru_cache`
   requires its arguments to be hashable, and `data` here is `json.load(sys.stdin)`
   output — an arbitrary-shaped `dict` (unhashable) parsed from the hook's JSON
   payload (`loop_stop_guard.py` line 28). Wrapping `_activation` in `lru_cache`
   would raise `TypeError: unhashable type: 'dict'` on the very first call in
   production. Would require an argument-adapter (e.g. cache on
   `data.get("session_id")` + `data.get("transcript_path")` as a hashable tuple
   key instead of the raw dict) to work at all — strictly more invasive than
   the direct module-level variable, for no additional benefit given Question
   1's confirmed one-process lifetime (an LRU eviction policy is solving a
   multi-call, multi-key caching problem this code doesn't have — there is
   exactly one relevant `data` per process here).

3. **Dependency injection via a shared context object passed through the call
   chain** — e.g. change `run(data)` to `run(data, ctx)` where `ctx` is a
   mutable object the caller pre-creates and both `run()` and the new gate
   read/write. **Rejected**: this DOES change `run()`'s signature (its
   parameter list, not just return value) — same category of tested-contract
   change as option (b), just moved from the return side to the argument side.
   The 4 existing tests call `msg.run(data)` with exactly one positional arg
   (`test_micro_step_gates.py` lines 88, 93, 99, 105, and every other call site
   in the file) — adding a required second parameter breaks all of them exactly
   like changing the return tuple would; making it optional
   (`run(data, ctx=None)`) avoids breaking calls but then the new gate in
   `loop_stop_guard.py` must construct and pass `ctx` BEFORE calling `run()`,
   which is more code and more surface than reading a module attribute
   afterward, for no extra safety (Question 1 already establishes the process
   lifetime is safe for the simpler pattern).

4. **A wrapper/orchestrating function that calls `_activation()` once and passes
   the tuple to both `run()`'s internals and the new gate explicitly** (i.e.
   restructure so `loop_stop_guard.py` calls `_activation(data)` itself once,
   then passes the resolved tuple into a refactored `run(data, act)`).
   **Rejected for the same reason as #3** — still changes `run()`'s signature,
   and additionally requires exposing `_activation` (currently private,
   `_`-prefixed) as a quasi-public contract of the module, growing the tested
   surface rather than shrinking it.

**Conclusion: option 2 (module-level `_LAST_ACTIVATION` side effect, per
Question 2) is the best available option** — it is the only one that (a)
changes neither `run()`'s return contract nor its parameter list (zero test
breakage, confirmed against all 4 existing assertions), (b) has a real,
already-shipped precedent in this exact codebase (`log.py`'s `_cache`), (c)
is licensed by a directly-confirmed fact about the actual execution model
(fresh process per Stop-hook firing — not an assumption), and (d) is strictly
safer than option (a) (zero additional disk reads/race window, vs. option
(a)'s narrow-but-nonzero concurrent-write race). It should replace option (a)
in the spec, with the two ordering/None-check risks from Question 2 written
into the implementation explicitly (module-level `_LAST_ACTIVATION = None`
initializer + `global` statement inside `_activation()` + a `getattr(...,
None)` / truthiness check at every read site + a docstring/comment stating the
"freshened unconditionally by every `run()` call, in the same process only"
invariant).

---

## not_found

Nothing load-bearing was left unanswered. One minor gap: I did not find an
official Claude Code doc page that uses the words "one process per hook
invocation" verbatim — the docs describe the command/stdin/exit-code contract
and per-invocation timeouts, which imply (and this repo's own registration +
test-harness pattern directly confirm via subprocess.run) fresh-process
semantics, but the docs stop short of a single explicit sentence saying so.
Given the repo's OWN code depends on this (unconditional module-scope
`json.load(sys.stdin)` at `loop_stop_guard.py` line 28, which cannot work
correctly under a persistent/reused-process model), and the repo's OWN
registration + test conventions match the docs' described contract exactly,
this is treated as conclusively confirmed rather than "not found" — flagged
here only for completeness per the honesty-bar requirement.
