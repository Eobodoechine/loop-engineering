# Bug-fix dossier: PII/publish gate blocked by `full_history_scan.py` / `test_full_history_scan.py` (Mode B, Coder-unblock)

**Researcher mode:** B (Coder-unblock bug-fix dossier). Read-only investigation; no files edited in
the real repo. All validation below was done against scratch copies in
`/private/tmp/claude-501/.../scratchpad/pii_fix_test/` (not `~/Claude/loop`), per the read-only
constraint on this dispatch.

**Date:** 2026-07-09

**Scope of this dossier:** the two-file NONKEY_PAT/REALKEY_PAT false-positive question the
dispatch asked me to resolve (Options A/B/C) — **plus a materially bigger finding the prior
diagnosis missed**: fixing only these two files will **not** unblock `snapshot-publish.sh`. See
§0 before anything else.

---

## 0. CRITICAL — the prior diagnosis is correct but incomplete: 11 OTHER already-committed files also block this gate, unrelated to full_history_scan.py

The task background said "two new files were added... [they] trip the gate." That much is true and
I confirmed it (§2 below). But a live `--dry-run` right now blocks on **13 files total**, not 2:

```
$ cd ~/Claude/loop && bash scripts/snapshot-publish.sh --dry-run 2>&1 | grep -E '^\s+~/loop-public' \
    | sed -E 's#^\s+~/loop-public/##' | cut -d: -f1 | sort | uniq -c | sort -rn

  14  research/loop-stop-guard-misfire-dossier-2026-07-08.md
  11  research/false-status-mechanical-verification-2026-07-08.md
   9  research/padsplit-cockpit-slice6b-ui-serveraction-reference-patterns-2026-07-08.md
   9  research/coder-detection-structural-signal-subagentstop-2026-07-08.md
   9  loop-team/harness/full_history_scan.py
   6  research/padsplit-cockpit-slice6-airbnb-research-2026-07-04.md
   6  loop-team/harness/test_full_history_scan.py
   3  research/taxahead-tts-lovable-dependency-2026-07-08.md
   3  loop-team/learnings.md
   2  research/padsplit-cockpit-slice6b-airbnb-calendar-research-2026-07-04.md
   2  research/compiler-gate-design-recommendation-2026-07-08.md
   2  SESSION_NOTES.md
   1  research/workflow-subdispatch-isolation-design-2026-07-03.md
```

**44 of these 57 hit-lines have nothing to do with `full_history_scan.py`/`test_full_history_scan.py`.**
They are genuine, real personal-path leaks — literal `~/...` absolute paths
written as prose in already-committed research dossiers, `SESSION_NOTES.md`, and `learnings.md`
(e.g. `learnings.md:1519`: `` hook in `~/.claude/settings.json`: `caffeinate...` ``).
These are **not** tooling/detection-pattern source text — they are exactly the class of thing
NONKEY_PAT is designed to catch, and it is catching it correctly.

**Timeline proof (from `.git/hooks/auto-publish.log`, cross-referenced with `git log`):**

| commit | time (UTC) | what it added | publish result |
|---|---|---|---|
| `a567c7e` | 00:48:36 | (unrelated fix) | **`publish OK`** — last known-good publish |
| `43da532` | 00:49:10 | `learnings.md` caffeinate-incident writeup (`git blame` confirms lines 1503/1506/1519 were authored by this commit) | **FAILED** — blocked on `learnings.md` alone, before `full_history_scan.py` existed |
| `59055cf` | 00:49:50 | **adds `full_history_scan.py`/`test_full_history_scan.py`** | FAILED (now `learnings.md` + the 2 new files) |
| `91823dd` | 00:50:30 | adds `research/loop-stop-guard-misfire-dossier-2026-07-08.md` + 3 more research docs | FAILED (adds more real-path hits) |
| `ee50192` | 00:59:24 | adds `SESSION_NOTES.md` | FAILED (adds 2 more) |
| `3f5efb7` (HEAD) | 03:03:34 | plan-check saturation gate (unrelated) | hook fired but **no completion ever logged** (see note below) — publish still blocked live, confirmed by my own `--dry-run` |

So: **`learnings.md` broke the gate first, before the harness files existed.** The harness-file
commit (`59055cf`) landed on top of an *already-broken* publish pipeline. Fixing `full_history_scan.py`
and `test_full_history_scan.py` (§5-6 below) is necessary but **only removes 15 of the 57 current
hit-lines**. `--dry-run` will still exit 1 afterward, blocked on the other 11 files, until someone
separately redacts or otherwise handles the literal home-path prose in `learnings.md`,
`SESSION_NOTES.md`, and the `research/*.md` corpus.

**Why this is a real, structural tension, not just stale content:** this repo's own conventions
(`roles/researcher.md` "Persistence" section, and the user's own memory
`feedback_researcher_pull_real_data.md` — "Researcher must fetch actual code/repo links with
file/line refs, not summaries") **mandate** that research dossiers cite exact absolute file paths
as evidence. Every future research dossier saved under `research/` will, by convention, contain
`~/Claude/loop/...`-shaped citations. `research/` is not excluded from the
publish tree (only `public/`, `loop-team/runs/`, `runs/` are, at
`scripts/snapshot-publish.sh:180`) — so this is not a one-off cleanup, it is a **recurring
collision** between two of this repo's own standing rules: "always cite absolute file paths in
research" vs. "no `/Use` + `rs/` string may ever appear in a published file." That tension is out of
scope for a two-file Coder fix and needs its own decision (redact paths at write-time going
forward? make citations repo-relative? exclude `research/` from publish?) — **I am flagging it,
not solving it**, per the Researcher role's "you don't promote anything... hand to Oga" rule. I did
not find any existing `fix_plan.md` entry covering this (`grep -i 'NONKEY\|home-path\|snapshot-publish'`
found only the original gate design entries, nothing about this collision) — this is new.

**Minor secondary anomaly, not investigated further (not blocking, noted for completeness):** the
log's last line is `2026-07-09T03:03:34Z post-commit fired on 3f5efb7` with no matching
`publish OK`/`publish FAILED` line after it, and no running `snapshot-publish`/`auto-publish`
process currently exists (`ps aux` clean). The hook run for the current HEAD commit appears to
have been interrupted before it finished logging, rather than having failed cleanly. This doesn't
change the diagnosis (my direct, fresh `--dry-run` invocation reproduces the block live either
way) but Oga/a future session should know the log's tail is not a reliable "did it finish"
signal for that one entry.

---

## 1. Live reproduction (confirms the failure is real and current)

```
$ cd ~/Claude/loop && bash scripts/snapshot-publish.sh --dry-run
  ⛔  PUBLISH BLOCKED — personal data / real key found in the extracted tree:
      ~/loop-public/research/loop-stop-guard-misfire-dossier-2026-07-08.md:18:...
      ... [57 lines total across 13 files, see §0] ...
      ~/loop-public/loop-team/harness/full_history_scan.py:45:  - a home-path prefix, e.g. `/Use` + `rs/<name>/...`
      ~/loop-public/loop-team/harness/full_history_scan.py:99:    ("builtin:home-path-prefix", re.compile(rb"/Use` + `rs/[^\s\x00]+")),
      ~/loop-public/loop-team/harness/test_full_history_scan.py:26:...home-path prefix like `/Use` + `rs/`...
      ~/loop-public/loop-team/harness/test_full_history_scan.py:64:      - a home-path prefix pattern, e.g. `/Use` + `rs/`
      ~/loop-public/loop-team/harness/test_full_history_scan.py:158:HOME_PATH_MARKER = "~/synthetic-user/secret/path.txt"
      ~/loop-public/loop-team/harness/test_full_history_scan.py:162:FAKE_SUBMODULE_URL_LEAK = "~/synthetic-user/some/local/repo"
      ~/loop-public/loop-team/harness/full_history_scan.py:47:  - an API-key-shaped string (sk-ant` + `-api..., sk-proj-...)
      ~/loop-public/loop-team/harness/full_history_scan.py:53:`sk-ant` + `-api` / `sk-proj-` as ITS OWN regex source ...
      ~/loop-public/loop-team/harness/full_history_scan.py:59:(`builtin:api-key-sk-ant` + `-api`, `builtin:api-key-sk-proj`): ...
      ~/loop-public/loop-team/harness/full_history_scan.py:103:    ("builtin:api-key-sk-ant` + `-api", re.compile(rb"sk-ant` + `-api[A-Za-z0-9_\-]*")),
      ~/loop-public/loop-team/harness/full_history_scan.py:112:# builtin hit (sk-ant` + `-api / sk-proj-) is expected ...
      ~/loop-public/loop-team/harness/full_history_scan.py:128:    "builtin:api-key-sk-ant` + `-api",
      ~/loop-public/loop-team/harness/full_history_scan.py:254:    A hit on a REALKEY-shaped builtin pattern (sk-ant` + `-api / sk-proj-) whose
      ~/loop-public/loop-team/harness/test_full_history_scan.py:27:...email + an API-key-shaped pattern like `sk-ant` + `-api...`/
      ~/loop-public/loop-team/harness/test_full_history_scan.py:66:      - an API-key-shaped pattern, e.g. `sk-ant` + `-api` / `sk-proj-` prefixes

  NOTHING was staged, committed, or pushed. Scrub the source in MAIN, commit, then re-run.
  ⛔  snapshot-publish: PUBLISH BLOCKED — see above
```
Confirmed real, current, and (for the two harness files specifically) matching the claimed cause.

---

## 2. `scripts/snapshot-publish.sh` — read in full (295 lines); exact mechanics

- **`TOOLING_EXCLUDE` array — lines 63–74** (comment 63–65, array 66–74):
  ```
  63  # Detection-tooling files that legitimately contain the key-prefix literals /
  64  # regexes and would self-trip the REAL-KEY portion of the gate. Same rationale
  65  # as pii-guard.sh excluding itself. Paths are relative to PUBLIC root.
  66  TOOLING_EXCLUDE=(
  67    "loop-team/evals/verify_build.py"
  68    "loop-team/evals/test_verify_build.py"
  69    "scripts/pii-guard.sh"
  70    "scripts/pii-markers.example"
  71    "scripts/test_publish.py"
  72    "scripts/snapshot-publish.sh"
  73    "scripts/test_snapshot_publish.py"
  74  )
  ```
  **Confirmed: `loop-team/harness/full_history_scan.py` and `loop-team/harness/test_full_history_scan.py`
  are NOT in this list.** This is why REALKEY_PAT flags them (see below).

- **`HOMES_PREFIX` self-avoidance trick — line 206**: `HOMES_PREFIX="/Use""rs/"` — two adjacent
  bash string literals with no operator between them; bash concatenates adjacent quoted strings
  automatically, so the runtime value is `"/Use` + `rs/"`, but the **source file's own bytes** never
  contain the contiguous 7-byte run `/Use` + `rs/`. Introduced in commit `dedd155` ("PII gate: build
  home-path marker dynamically so the gate can publish its own tooling", 2026-07-01) specifically
  because committing `snapshot-publish.sh` itself used to self-trip. This is the established,
  working precedent my recommended fix reuses.

- **NONKEY_PAT construction — lines 207–211**:
  ```
  207  NONKEY_PARTS=("$MARKER_PAT")
  208  [ -n "$SCAN_EMAIL" ] && NONKEY_PARTS+=("$SCAN_EMAIL")
  209  NONKEY_PARTS+=("$HOMES_PREFIX")
  210  [ -n "$HOME_USER" ] && NONKEY_PARTS+=("$HOMES_PREFIX$HOME_USER")
  211  NONKEY_PAT="$(IFS='|'; echo "${NONKEY_PARTS[*]}")"
  ```
  Note line 209 includes the **bare** `HOMES_PREFIX` ("/Use` + `rs/") in the alternation, not just
  `HOMES_PREFIX+HOME_USER` — so **any** `/Use` + `rs/` anywhere in the tree trips this, not only the
  real user's own home directory. This is why generic test-fixture paths like
  `~/synthetic-user/...` are flagged exactly the same as a real leaked `~/...`
  path — the scanner cannot distinguish them, by design.

- **REALKEY_PAT — line 214**: `REALKEY_PAT='sk-ant` + `-api|sk-proj-[A-Za-z0-9]{12,}'`. Note `sk-proj-`
  requires 12+ trailing alnum chars to match; bare `sk-proj-` text (as appears in both harness
  files' docstrings, e.g. line 104's `re.compile(rb"sk-proj-[A-Za-z0-9_\-]*")`) does **not** match
  REALKEY_PAT because the next char after `sk-proj-` is a regex-metacharacter `[`, not an
  alphanumeric — this is why the dry-run's hit list under REALKEY only shows `sk-ant` + `-api`-bearing
  lines, never bare `sk-proj-`-only lines, even though `sk-proj-` also appears literally in the
  source.

- **`_is_tooling()` — lines 216–223**: exact-match helper against `TOOLING_EXCLUDE`.

- **The two scans — lines 225–256**:
  ```
  225  HITS=""
  226
  227  # Non-key scan: ANY hit anywhere is a real hit (no tooling exemption — personal
  228  # markers / email / home paths must never appear in ANY published file).
  229  nonkey_hits="$(grep -rInE "$NONKEY_PAT" "$PUBLIC" --exclude-dir=.git 2>/dev/null)"
  230  [ -n "$nonkey_hits" ] && HITS+="$nonkey_hits"$'\n'
  231
  232  # Real-key scan: hits in tooling files are the regex/literals themselves — drop
  233  # them; a remaining hit in a NON-tooling file is a genuine leaked key.
  234  while IFS= read -r line; do
  235    [ -z "$line" ] && continue
  236    file="${line%%:*}"
  237    rel="${file#"$PUBLIC"/}"
  238    if _is_tooling "$rel"; then
  239      continue
  240    fi
  241    HITS+="$line"$'\n'
  242  done < <(grep -rInE "$REALKEY_PAT" "$PUBLIC" --exclude-dir=.git 2>/dev/null)
  ```
  **I confirmed by direct code read (not just the comment) that line 229–230 (the NONKEY scan) has
  ZERO exemption logic of any kind — no call to `_is_tooling`, no filtering, nothing.** The
  comment at 227–228 accurately describes the actual code. This fully confirms the prior
  diagnosis's central claim: NONKEY_PAT truly has no tooling-exemption path in the current code,
  and REALKEY_PAT truly does (lines 232–243).

**Conclusion of §2:** the prior diagnosis's mechanical claims about `snapshot-publish.sh` are
100% accurate, verified line-by-line against the live file.

---

## 3. `scripts/pii-guard.sh` — read in full (58 lines); the design precedent

This is a **separate** gate (a pre-push hook, distinct from `snapshot-publish.sh`'s filesystem
scan) but is the explicit "same rationale" precedent `snapshot-publish.sh`'s own comment cites.

- **Its own self-exemption — lines 33–42**:
  ```
  33  # Scan all tracked files EXCEPT the key-detection TOOLING itself, which legitimately
  34  # contains the key-prefix literals and would otherwise self-trip (same reason the
  35  # guard excludes itself): this guard + verify_build.py's PII lint + its tests. The
  36  # local markers file is gitignored, so git grep never scans it.
  37  hits="$(git grep -IniE "$PATTERN" -- \
  38    ':!scripts/pii-guard.sh' \
  39    ':!scripts/.pii-markers.local' \
  40    ':!scripts/pii-markers.example' \
  41    ':!loop-team/evals/verify_build.py' \
  42    ':!loop-team/evals/test_verify_build.py' 2>/dev/null)"
  ```
  Its `PATTERN` (line 26: `PATTERN='sk-ant|sk-proj'`, extended with `.pii-markers.local` content)
  is **REALKEY-shaped only** — this script has no separate "home path"/email scan at all, so there
  is no NONKEY-style precedent to mirror here; the whole file is analogous to
  `snapshot-publish.sh`'s REALKEY_PAT half only.

**Relevance to this fix:** `pii-guard.sh` exempts itself via git-grep pathspec exclusions
(`:!path`), a different mechanism from `snapshot-publish.sh`'s `TOOLING_EXCLUDE` array, but the
**same underlying policy**: known tooling files that legitimately contain key-prefix literals are
excluded from the REALKEY-shaped scan, by exact path, never by content heuristic. Neither this
file nor `snapshot-publish.sh` has ever exempted a file from a *personal-identity/home-path* scan
by filename — that pattern does not exist anywhere in this codebase's git history. This absence is
itself evidence for §5's Option A analysis.

---

## 4. `full_history_scan.py` / `test_full_history_scan.py` — every literal occurrence, read in full (372 + 741 lines)

### 4a. `loop-team/harness/full_history_scan.py`

**Literal `/Use` + `rs/` occurrences (NONKEY-triggering) — exactly 2, both are detection-pattern source/prose, NEITHER is test-fixture data:**

| Line | Content | Category |
|---|---|---|
| 45 | `  - a home-path prefix, e.g. `` `/Use` + `rs/<name>/...` `` ` (module docstring, listing the built-in patterns) | Prose/docstring — purely descriptive, zero runtime effect. Freely rewritable. |
| 99 | `    ("builtin:home-path-prefix", re.compile(rb"/Use` + `rs/[^\s\x00]+")),` (in `BUILTIN_PATTERNS`) | **Actual runtime regex source.** Must preserve identical compiled-pattern behavior. |

**Literal `sk-ant` + `-api` occurrences (REALKEY-triggering) — 7 lines, all prose/docstring or the actual regex source, none is fixture data:**
Lines 47, 53, 59, 103 (`re.compile(rb"sk-ant` + `-api[A-Za-z0-9_\-]*")` — the actual pattern), 112, 128,
254. (`sk-proj-` also appears in the same lines' prose plus line 104's regex source, but as noted
in §2, `sk-proj-` alone never matches REALKEY_PAT because it lacks the required 12+ trailing
alnum chars in this context.)

This file **already has its own internal, narrower analogue of `TOOLING_EXCLUDE`** —
`TOOLING_EXCLUDE_PATHS` (lines 114–122) and `REALKEY_BUILTIN_PATTERN_NAMES` (lines 126–130), used
by `_is_tooling_exempt()` (lines 133–142) inside its own `scan_repo()` (for when *this scanner*
walks the *entire git history* of a repo, per its AC5 purpose). **Critically, its own docstring
(lines 49–75) explicitly states the design rationale I was asked to investigate for
`snapshot-publish.sh`, verbatim, already decided, for this file's own internal mechanism:**

> "This exemption applies ONLY to the two REALKEY-shaped builtins, by exact path match against
> TOOLING_EXCLUDE_PATHS -- it does NOT apply to identity-marker hits, the home-path/email
> builtins, or any path not in the list (a real key found in a non-tooling file is still a hit)."
> (lines 64–67)

This is **strong internal precedent, in the very file under repair, against extending a
filename-based exemption to the home-path pattern** — the file's own author already reasoned
through this exact tradeoff for an analogous scanner and explicitly excluded home-path/email from
any tooling exemption. See §5, Option A.

**Self-referential gap noted in passing (not part of this bug, flagging for completeness):**
`full_history_scan.py`'s own `TOOLING_EXCLUDE_PATHS` (lines 114–122) does not list itself or
`test_full_history_scan.py`. If this scanner is ever actually run against `~/Claude/loop`'s full
history (its stated purpose), it would flag its own REALKEY-shaped lines the same way
`snapshot-publish.sh` currently does. Its docstring says this list is "kept in sync with
`scripts/snapshot-publish.sh`'s `TOOLING_EXCLUDE` array" (line 110) — so if `TOOLING_EXCLUDE` gets
the two new entries (§6), `TOOLING_EXCLUDE_PATHS` should get them too, to honor that stated
sync invariant. This is a "while you're in there" consistency fix, not required to unblock the
current `snapshot-publish.sh --dry-run` failure (that gate never calls into
`full_history_scan.py`) — I recommend including it anyway since it costs one line.

### 4b. `loop-team/harness/test_full_history_scan.py`

**Literal `/Use` + `rs/` occurrences — exactly 4, split evenly between prose and genuine fixture data:**

| Line | Content | Category |
|---|---|---|
| 26 | `` (identity strings from AC1 + a home-path prefix like `/Use` + `rs/` + an `` (module docstring) | Prose — rewritable freely. |
| 64 | `` - a home-path prefix pattern, e.g. `/Use` + `rs/` `` (module docstring) | Prose — rewritable freely. |
| 158 | `HOME_PATH_MARKER = "~/synthetic-user/secret/path.txt"` | **Genuine fixture data** — see below. |
| 162 | `FAKE_SUBMODULE_URL_LEAK = "~/synthetic-user/some/local/repo"` | **Genuine fixture data** — see below. |

**How the fixture constants are actually used (I read every call site, lines 158–741):**

- `HOME_PATH_MARKER` is used exactly once, at line 287, interpolated into synthetic leaked-file
  content: `"leaked home path: %s\nmarker: %s\n" % (HOME_PATH_MARKER, MARKER_HISTORICAL)`. The
  test (`TestACaHistoricalLeakCaughtEvenAfterFix`) only asserts detection of `MARKER_HISTORICAL`
  (an `extra_patterns` entry) — it does **not** independently assert that the scanner's
  `builtin:home-path-prefix` pattern fires on `HOME_PATH_MARKER`'s content. So this constant's
  *string value* must still be a real home-path-shaped string (`~/synthetic-user/...`) for the
  fixture to be realistic, but no assertion actually keys off its exact text or off the builtin
  pattern being triggered by it specifically.
- `FAKE_SUBMODULE_URL_LEAK` is used at line 466 (embedded into synthetic `.gitmodules` content)
  and passed as an `extra_patterns` marker at line 490. The test explicitly asserts
  `FAKE_SUBMODULE_URL_LEAK in _all_hit_patterns(report)` at line 521 — **this assertion only
  requires that the same Python-level string value used to build the markers file also appears in
  the hit report; it is self-consistent regardless of how that value is constructed in the source
  file**, since both the write-side and the assert-side reference the same name/value.

**Conclusion: rewriting these two constants' *source-level representation* (not their *runtime
string value*) cannot break either test**, because neither test's pass/fail condition depends on
the literal on-disk byte layout of the constant's declaration — only on the runtime string value,
which is preserved exactly by Python's own adjacent-string-literal concatenation (see §5/§7 for
the mechanical proof).

**Literal `sk-ant` + `-api`/`sk-proj-` occurrences — 2 lines (27, 66), both pure docstring prose,
no fixture data uses these substrings at all** (no test constructs a real API-key-shaped test
string anywhere in this file).

---

## 5. Fix-option analysis

### Option A — extend NONKEY_PAT's exemption to cover these 2 files

**My verdict: reject.** Reasons, in order of weight:

1. **It reverses an explicit, deliberate, currently-enforced design invariant.** `snapshot-publish.sh:227-228`'s comment ("no tooling exemption — personal markers / email / home paths must never appear in ANY published file") is not stale prose describing old behavior — I confirmed by reading the actual code (§2) that it is exactly what the code does today. Loosening it is a security-model change, not a bug fix.
2. **The same codebase already made and documented this exact call, in the very file under repair, and decided against it.** `full_history_scan.py`'s own docstring (§4a, lines 64-67) explicitly scopes its own analogous tooling-exemption to REALKEY-shaped builtins only, and explicitly excludes "the home-path/email builtins... any path not in the list." Extending Option A here would put `snapshot-publish.sh` at odds with the very tool it's trying to unblock — the tool's own author already rejected this generalization for itself.
3. **A filename-level exemption is structurally coarser than a REALKEY exemption**, and worse, coarsest in exactly the wrong place. A REALKEY hit is provably ambiguous (a key-shaped string in a detector file plausibly *is* the detector's own pattern, not a live secret). A home-path hit has no such ambiguity — any `/Use` + `rs/<name>/...` in a tracked file is either genuinely someone's real path (a leak) or synthetic test data; there is no "it's just describing the concept" reading the way there is for a regex literal. Exempting a whole file from this scan (even scoped to "just the home-path sub-pattern") means any OTHER real path pasted into that file later — e.g. a future maintainer copy-pasting a real stack trace into a docstring while debugging, which is exactly the kind of file these two are — would never be caught. These two files are, ironically, the single worst candidates in the repo to blind the home-path scan on, since their entire purpose is to talk about home-path leaks.
4. **No implementation benefit over Option B/C exists to justify the risk.** Option B (below) is a zero-risk, already-precedented, already-validated fix. There is no case where Option A is cheaper or safer.

If it were to be attempted despite the above (e.g. under time pressure), the narrowest possible
scoping would be: exempt only these two exact relative paths, only from the `HOMES_PREFIX`
sub-pattern (never `MARKER_PAT`/`SCAN_EMAIL`), and only file-line-level (not whole-file) — but
implementing line-level exemption for a merged single-regex `grep -rInE "$NONKEY_PAT"` scan
requires restructuring the NONKEY scan into the same per-pattern/per-hit-line loop REALKEY_PAT
already uses (lines 234-243), i.e., building the entire generic exemption machinery from scratch
for a benefit Option B already gives for free with an order of magnitude less change and no new
attack surface. Not recommended even in its narrowest form.

### Option B — rewrite `full_history_scan.py`'s own source to avoid the literal substrings

**Mechanically validated, see §7 below.** Apply the exact same construction trick
`snapshot-publish.sh` already uses on itself (`HOMES_PREFIX="/Use""rs/"`, adjacent string-literal
concatenation) to the 2 NONKEY-triggering lines in `full_history_scan.py` and the 4 in
`test_full_history_scan.py`. I confirmed:
- The rewritten regex compiles to a **byte-identical** `re.Pattern.pattern` as the original.
- Functional matching behavior is unchanged (tested against 4 sample inputs, all identical
  before/after).
- All 10 tests in `test_full_history_scan.py` pass identically before and after the rewrite
  (baseline: 10 passed; after fix: 10 passed).
- The rewrite does **not** need to touch the REALKEY (`sk-ant` + `-api`) lines at all if combined with
  Option C's `TOOLING_EXCLUDE` addition (see below) — narrowing the diff further.

**Precedent already exists as a standing rule for exactly this situation:** `fix_plan.md:1048`:
> "PII-gate self-match (2026-07-01): committing snapshot-publish.sh made the gate flag its own
> source — a detector's tooling can never contain its own contiguous detection literal (same class
> as the oga-guard markers). Fixed by runtime concatenation... **Standing rule: any new detector
> ships with a no-contiguous-literals sweep over its own home directory.**"

`full_history_scan.py`/`test_full_history_scan.py` are exactly "a new detector" that should have
shipped with this sweep already, per this **pre-existing, already-adopted** project rule — this is
not a new judgment call, it's applying an existing policy that was simply missed when these two
files were added in commit `59055cf`.

### Option C (recommended) — hybrid: TOOLING_EXCLUDE for REALKEY + Option B for NONKEY

Add both files to `snapshot-publish.sh`'s `TOOLING_EXCLUDE` array (necessary regardless, per the
diagnosis — mirrors the existing, narrow, well-established REALKEY exemption mechanism, identical
in kind to the 7 entries already there) **combined with** Option B's construction-trick applied
only to the 2+4 NONKEY-triggering lines (since that scan has no exemption path at all, and none
should be added).

**This is what I recommend, and it is the option I mechanically validated end-to-end (§7):
zero hits from either file, byte-identical regex, all tests green, zero change to the NONKEY_PAT
scan's own logic/security model.**

---

## 6. Line-anchored spec (ready for a Coder to implement directly)

### File 1: `scripts/snapshot-publish.sh`

**Change: add 2 entries to `TOOLING_EXCLUDE` (lines 66–74).**

Before (lines 66–74):
```bash
TOOLING_EXCLUDE=(
  "loop-team/evals/verify_build.py"
  "loop-team/evals/test_verify_build.py"
  "scripts/pii-guard.sh"
  "scripts/pii-markers.example"
  "scripts/test_publish.py"
  "scripts/snapshot-publish.sh"
  "scripts/test_snapshot_publish.py"
)
```
After:
```bash
TOOLING_EXCLUDE=(
  "loop-team/evals/verify_build.py"
  "loop-team/evals/test_verify_build.py"
  "scripts/pii-guard.sh"
  "scripts/pii-markers.example"
  "scripts/test_publish.py"
  "scripts/snapshot-publish.sh"
  "scripts/test_snapshot_publish.py"
  "loop-team/harness/full_history_scan.py"
  "loop-team/harness/test_full_history_scan.py"
)
```
(No other change needed in this file. This only affects the REALKEY_PAT scan, lines 232-243 — the
NONKEY_PAT scan at lines 225-230 remains completely untouched, preserving its "no exemption" invariant.)

### File 2: `loop-team/harness/full_history_scan.py`

**Change 2a — line 45 (docstring prose):**
Before: `` `  - a home-path prefix, e.g. \`/Use` + `rs/<name>/...\`` ``
After: `` `  - a home-path prefix, e.g. \`/Us\`+\`ers/<name>/...\`` ``

**Change 2b — line 99 (runtime regex source):**
Before:
```python
    ("builtin:home-path-prefix", re.compile(rb"/Use` + `rs/[^\s\x00]+")),
```
After:
```python
    ("builtin:home-path-prefix", re.compile(rb"/Us" rb"ers/[^\s\x00]+")),
```
(Adjacent bytes-literal concatenation — Python concatenates these at parse time into the identical
`b"/Use` + `rs/[^\s\x00]+"` bytes object. Verified byte-identical `.pattern` attribute, see §7.)

**Optional, recommended consistency fix (not required to unblock the current failure — this
scanner is not invoked by `snapshot-publish.sh` — but honors this file's own "kept in sync"
comment at line 110):**
Add the same 2 entries to `TOOLING_EXCLUDE_PATHS` (lines 114–122):
```python
TOOLING_EXCLUDE_PATHS = frozenset([
    "loop-team/evals/verify_build.py",
    "loop-team/evals/test_verify_build.py",
    "scripts/pii-guard.sh",
    "scripts/pii-markers.example",
    "scripts/test_publish.py",
    "scripts/snapshot-publish.sh",
    "scripts/test_snapshot_publish.py",
    "loop-team/harness/full_history_scan.py",
    "loop-team/harness/test_full_history_scan.py",
])
```

### File 3: `loop-team/harness/test_full_history_scan.py`

**Change 3a — line 26 (docstring prose):**
Before: `` `         (identity strings from AC1 + a home-path prefix like \`/Use` + `rs/\` + an` ``
After: `` `         (identity strings from AC1 + a home-path prefix like \`/Us\`+\`ers/\` + an` ``

**Change 3b — line 64 (docstring prose):**
Before: `` `      - a home-path prefix pattern, e.g. \`/Use` + `rs/\`` ``
After: `` `      - a home-path prefix pattern, e.g. \`/Us\`+\`ers/\`` ``

**Change 3c — line 158 (fixture constant):**
Before:
```python
HOME_PATH_MARKER = "~/synthetic-user/secret/path.txt"
```
After:
```python
HOME_PATH_MARKER = "/Us" "ers/testuser/secret/path.txt"
```

**Change 3d — line 162 (fixture constant):**
Before:
```python
FAKE_SUBMODULE_URL_LEAK = "~/synthetic-user/some/local/repo"
```
After:
```python
FAKE_SUBMODULE_URL_LEAK = "/Us" "ers/testuser/some/local/repo"
```

**No other lines in either harness file need to change.** The `sk-ant` + `-api`/`sk-proj-` occurrences
(full_history_scan.py lines 47,53,59,103,104,112,128,254; test_full_history_scan.py lines 27,66,
28,66) are fully handled by the `TOOLING_EXCLUDE` addition in File 1 and require zero source
changes.

### Falsifiable check (run after the Coder applies the above)

```bash
cd ~/Claude/loop
grep -n '/Use` + `rs/' loop-team/harness/full_history_scan.py loop-team/harness/test_full_history_scan.py
# must print NOTHING (exit 1, no matches)

python3 -m pytest loop-team/harness/test_full_history_scan.py -q
# must still show: 10 passed

bash scripts/snapshot-publish.sh --dry-run 2>&1 | grep -c 'harness/full_history_scan.py\|harness/test_full_history_scan.py'
# must print 0 (zero remaining hit-lines attributable to these 2 files)
```

**IMPORTANT — do not stop at a green `--dry-run` exit code.** Per §0, the overall `--dry-run` will
still exit 1 after this fix, blocked on the 11 other pre-existing files. The correct falsifiable
signal for **this specific fix** is "0 hit-lines attributable to the 2 harness files" (the grep
-c check above), not "`--dry-run` exits 0" — that second, larger condition needs a separate,
explicitly-scoped follow-up (redacting/handling `learnings.md`, `SESSION_NOTES.md`, and the
`research/*.md` corpus) that should go through its own plan-check, not be silently bundled into
this dispatch.

---

## 7. Validation performed (scratch copies only, real repo untouched)

All work done in `/private/tmp/claude-501/-Users-eobodoechine/d2e2edd8-dd54-4fef-8684-09983385aa35/scratchpad/pii_fix_test/`:

1. Copied both harness files; applied exactly the changes in §6 (2a/2b/3a-3d) to `_FIXED` copies.
2. `grep -n '/Use` + `rs/' full_history_scan_FIXED.py test_full_history_scan_FIXED.py` → **zero matches** (exit 1).
3. `python3 -c "import ast; ast.parse(...)"` on both fixed files → **both parse cleanly**, no syntax error.
4. Compiled-pattern equivalence check:
   ```
   orig.pattern  : b'/Use` + `rs/[^\\s\\x00]+'
   fixed.pattern : b'/Us' + b'ers/[^\\s\\x00]+'  (source) -> compiles to
   fixed.pattern : b'/Use` + `rs/[^\\s\\x00]+'
   byte-identical: True
   ```
   Functional match test against 4 sample byte-strings (a real-shaped path, no-match text, bare
   prefix, embedded mid-string) — **all 4 identical results** before/after.
5. Ran the real test suite against the fixed files in isolation: `python3 -m pytest
   test_full_history_scan.py -q` → **10 passed** (same count as the unmodified baseline, which I
   also ran independently to confirm: **10 passed**, confirming no accidental regression or
   accidental new pass).
6. Built a faithful bash re-implementation of `snapshot-publish.sh`'s exact NONKEY_PAT/REALKEY_PAT/
   `_is_tooling` logic (mirroring lines 206, 216-223, 227-243 verbatim) and ran it against 4
   scenarios, using the real relative path `loop-team/harness/` so `TOOLING_EXCLUDE` matching is
   exact:
   - **Original files, `TOOLING_EXCLUDE` NOT extended** → BLOCKED (15 hits) — matches live repro.
   - **Original files, `TOOLING_EXCLUDE` extended (REALKEY-only, no NONKEY rewrite)** → still
     BLOCKED (5 NONKEY hits remain) — proves the REALKEY-only fix alone is insufficient.
   - **Fixed files (NONKEY rewritten), `TOOLING_EXCLUDE` NOT extended** → still BLOCKED (9 REALKEY
     hits remain) — proves the NONKEY-only fix alone is insufficient.
   - **Fixed files + `TOOLING_EXCLUDE` extended (the full Option C recommendation)** → **CLEAN,
     exit 0.** Zero hits.

This is a complete, falsifiable, end-to-end proof that the §6 spec is necessary, sufficient (for
these two files specifically), and non-regressive.

---

## Summary for Oga

- **`candidate_fixes` (ranked):**
  1. **[Recommended] Option C hybrid** — `TOOLING_EXCLUDE` += 2 entries (File 1) + adjacent-literal
     construction trick on 6 lines across the 2 harness files (Files 2-3). Fully specified in §6,
     fully validated in §7. Zero security-model change; reuses 2 mechanisms already established and
     precedented in this exact codebase (`dedd155`'s `HOMES_PREFIX` trick; the existing
     `TOOLING_EXCLUDE`/`TOOLING_EXCLUDE_PATHS` REALKEY exemption).
  2. Option B alone (no `TOOLING_EXCLUDE` change) — insufficient by itself; leaves 9 REALKEY hits
     unresolved (confirmed in §7). Not recommended as a standalone.
  3. Option A (extend NONKEY_PAT exemption) — rejected, see §5. Would reverse a deliberate,
     currently-enforced, already-internally-precedented (by `full_history_scan.py`'s own
     docstring) design decision, for no benefit over Option C.
- **`falsifiable_check`:** see §6 — grep for zero remaining `/Use` + `rs/` matches, pytest 10/10, and a
  scoped hit-count check on the 2 harness files (NOT overall `--dry-run` exit code, see next bullet).
- **`if_not_found` / open scope, requires a separate decision before `snapshot-publish.sh
  --dry-run` will actually pass end-to-end:** §0's finding — 11 other already-committed files
  (`learnings.md`, `SESSION_NOTES.md`, 9 files under `research/`) carry 44 more NONKEY_PAT hits,
  unrelated to these two harness files, some predating them. This is a distinct, larger scope
  (content redaction across a growing corpus of research dossiers that are conventionally required
  to cite absolute paths) that deserves its own plan-check and its own Coder dispatch — I recommend
  Oga log this as a new `fix_plan.md` entry (I did not find an existing one) rather than silently
  fold it into the two-file fix this dossier was scoped to answer.

---

# APPENDIX (appended 2026-07-09) — full-scope fix: the other 11 blocking files

**Scope change:** the requester reviewed §0-§7 above and expanded scope — fix all 13 blocking files now
(not just the 2 harness files), so `bash scripts/snapshot-publish.sh --dry-run` goes fully green.
This appendix covers the 11 non-harness files. Everything above (§0-§7) is unchanged and still
correct; this section supersedes only the *count* stated in §0/§1 ("57 hit-lines... 44 unrelated"),
which was an approximation — the precise, re-verified figure is **77 total hit-lines across 13
files, of which 62 are the 11 non-harness files** (confirmed twice: once by direct per-sub-pattern
grep, once by an independent live `--dry-run` count: `grep -cE '^\s+~/loop-public/'`
→ 77). Same read-only discipline as above: all validation on scratch copies in
`/private/tmp/claude-501/-Users-eobodoechine/d2e2edd8-dd54-4fef-8684-09983385aa35/scratchpad/pii_fix_test/`,
no real-repo files touched, no sub-agent delegation.

## A.1 — Complete hit inventory (62 lines, 11 files) and classification

**Every one of the 62 hits fires on the same NONKEY_PAT sub-pattern: `HOME_PATH`** (the bare
`/Use` + `rs/` / `~` alternatives at `snapshot-publish.sh:209-210`). I checked each
hit line individually against every other sub-pattern in `NONKEY_PAT` — the personal-name markers
(`person_a`, `example_llc`, `requester`), the project-slug markers (`Job Tool`, `rental_rules`,
`applicant_record`, `career_tool`, `marketplace_feed`, `market_profile` — from
`scripts/.pii-markers.local`), and the email (`<noreply-email>`) —
**none of those ever co-fire on these 62 lines.** REALKEY_PAT (`sk-ant` + `-api`/`sk-proj-...`) also
never fires in any of these 11 files (confirmed by direct grep, 0 matches in all 11). I also swept
all 11 files for credential/secret-shaped strings (`password[:=]`, `api[_-]?key[:=]`, `AKIA...`,
`-----BEGIN`, bearer tokens, etc.) — the only hits are `research/taxahead-tts-lovable-dependency-2026-07-08.md`
at lines 23/355/371/379, and every one is an **environment-variable name reference or a
placeholder shell example** (`process.env.LOVABLE_API_KEY`, `Deno.env.get("ANTHROPIC_API_KEY")`,
`supabase secrets set ANTHROPIC_API_KEY=sk-ant-...` with a literal `...` placeholder, not a real
key) — **zero actual secrets/credentials found in these 11 files.**

**Classification result: all 62 hits are bucket 2** ("the specific path IS the point — these are
literal `Researcher pulls real data`-convention evidence citations, i.e. `- \`<path>\` (read in
full)" statements whose entire purpose is to say exactly which file was read). The repo-relative
suffix after the home directory (e.g. `Claude/loop/hooks/loop_stop_guard.py`) is the meaningful
content; only the `~` prefix is the leak. A few lines are closer to bucket 1
(the path is more incidental to a narrative sentence than a citation — `SESSION_NOTES.md` L1/L2,
and the bare `"cwd": "~"` JSON fields at `coder-detection...:77`/`:592`) but the
**same redaction placeholder works correctly for both buckets**, so I did not need two different
treatments. **Zero bucket-3 (name/email marker) or bucket-4 (secrets/credentials) hits exist among
these 62** — see §A.5 below for a *separate*, more serious finding that is bucket-3/4-adjacent but
does not appear in this 62-line set (because it currently escapes the gate entirely).

**Redaction convention chosen — and why it's not a new invention:** replace the literal
`~` prefix with `~` (tilde, POSIX home-directory shorthand), preserving 100% of
the repo-relative suffix. I checked whether this is consistent with the rest of the codebase's own
style before choosing it: `loop-team/orchestrator.md` uses `~/Claude/loop/...`-style paths 3 times
and **never once** uses a literal `~` path; every `roles/*.md` file also never
uses one. The only file in this repo that legitimately uses the literal
`~` form today is `fix_plan.md`, and `fix_plan.md` is itself explicitly listed as one
of this repo's **private, gitignored, never-published** files (its own banner: `~/Claude/loop` "holds
private files (`fix_plan.md`, `VERIFIER.md`, ..., all gitignored)"). So the tilde convention is
already this repo's exclusive, deliberate style for every tracked/published doc — the 11 files
below are simply inconsistent with a convention already established everywhere else in the
publishable tree, not being asked to adopt something new.

Per-file tables below: **Line** | **Before** | **After**. (Sub-pattern is `HOME_PATH` for all 62;
omitted per-row for space since it never varies.)

### `loop-team/learnings.md` (3 hits)

| L | Before | After |
|---|---|---|
| 1503 | `` incident, the first persistent fix was to back up `~/.claude.json` and `` | `` incident, the first persistent fix was to back up `~/.claude.json` and `` |
| 1506 | `` Desktop also reads `~/Library/Application Support/Claude/claude_desktop_config.json`, `` | `` Desktop also reads `~/Library/Application Support/Claude/claude_desktop_config.json`, `` |
| 1519 | `` hook in `~/.claude/settings.json`: `caffeinate -dis -w $PPID &` `` | `` hook in `~/.claude/settings.json`: `caffeinate -dis -w $PPID &` `` |

### `SESSION_NOTES.md` (2 hits)

| L | Before | After |
|---|---|---|
| 1 | `2026-07-08: Claude Desktop multichat hanging was traced to MCP/local-agent fanout, not the loop-team hook; the durable fix required disabling bad stdio MCP entries in both ~/.claude.json and ~/Library/Application Support/Claude/claude_desktop_config.json, then restarting Claude Desktop and verifying mcp.log no longer initialized facebook-marketplace or secondhand.` | `2026-07-08: Claude Desktop multichat hanging was traced to MCP/local-agent fanout, not the loop-team hook; the durable fix required disabling bad stdio MCP entries in both ~/.claude.json and ~/Library/Application Support/Claude/claude_desktop_config.json, then restarting Claude Desktop and verifying mcp.log no longer initialized facebook-marketplace or secondhand.` |
| 2 | ``2026-07-08: Follow-up diagnosis found the remaining Claude Code hang was caused by the user-level SessionStart hook `caffeinate -dis -w $PPID &` in ~/.claude/settings.json. Direct unsandboxed probes proved safe mode worked, normal mode without user settings worked, session_start.sh alone worked, loop_guard.py alone worked, caffeinate alone timed out, and full normal mode worked after removing caffeinate plus its Stop pkill cleanup. Backup: ~/.claude/settings.json.codex-backup-before-caffeinate-hook-removal-20260708-013638.`` | ``2026-07-08: Follow-up diagnosis found the remaining Claude Code hang was caused by the user-level SessionStart hook `caffeinate -dis -w $PPID &` in ~/.claude/settings.json. Direct unsandboxed probes proved safe mode worked, normal mode without user settings worked, session_start.sh alone worked, loop_guard.py alone worked, caffeinate alone timed out, and full normal mode worked after removing caffeinate plus its Stop pkill cleanup. Backup: ~/.claude/settings.json.codex-backup-before-caffeinate-hook-removal-20260708-013638.`` |

### `research/loop-stop-guard-misfire-dossier-2026-07-08.md` (14 hits)

| L | Before | After |
|---|---|---|
| 15 | `` - `~/Claude/loop/hooks/loop_stop_guard.py` (1360 lines) `` | `` - `~/Claude/loop/hooks/loop_stop_guard.py` (1360 lines) `` |
| 16 | `` - `~/Claude/loop/hooks/verifier_hygiene_scan.py` (151 lines) `` | `` - `~/Claude/loop/hooks/verifier_hygiene_scan.py` (151 lines) `` |
| 17 | `` - `~/Claude/loop/fix_plan.md` (5072 lines; targeted sections read in full) `` | `` - `~/Claude/loop/fix_plan.md` (5072 lines; targeted sections read in full) `` |
| 18 | `` - `~/Claude/loop/hooks/test_loop_stop_guard.py` (targeted sections, ~6300+ lines total) `` | `` - `~/Claude/loop/hooks/test_loop_stop_guard.py` (targeted sections, ~6300+ lines total) `` |
| 19 | `` - `~/Claude/loop/hooks/test_verifier_hygiene_gate.py` (targeted sections) `` | `` - `~/Claude/loop/hooks/test_verifier_hygiene_gate.py` (targeted sections) `` |
| 20 | `` - `~/.claude/settings.json`, `~/.claude/settings.local.json` `` | `` - `~/.claude/settings.json`, `~/.claude/settings.local.json` `` |
| 21 | `` - `~/Claude/loop/loop-team/evals/run_evals.py` (top of file, cases dir listing) `` | `` - `~/Claude/loop/loop-team/evals/run_evals.py` (top of file, cases dir listing) `` |
| 73 | `` $ grep -rn "subagent_type" ~/Claude/loop/hooks/loop_stop_guard.py ~/Claude/loop/hooks/verifier_hygiene_scan.py `` | `` $ grep -rn "subagent_type" ~/Claude/loop/hooks/loop_stop_guard.py ~/Claude/loop/hooks/verifier_hygiene_scan.py `` |
| 552 | `` **Quoted directly from `~/.claude/settings.json`** (the file that `` | `` **Quoted directly from `~/.claude/settings.json`** (the file that `` |
| 564 | JSON hook snippet: `"command": "python3 '~/Claude/loop/hooks/loop_guard.py'"` | `"command": "python3 '~/Claude/loop/hooks/loop_guard.py'"` |
| 567 | same shape, `loop_stop_guard.py` | same shape, `~/Claude/loop/hooks/loop_stop_guard.py` |
| 570 | same shape, `session_start.sh` (with `"matcher": "startup"` prefix + `statusMessage`) | same shape, `~/Claude/loop/hooks/session_start.sh` |
| 573 | same shape, `subagent_stop_gate.py` | same shape, `~/Claude/loop/hooks/subagent_stop_gate.py` |
| 576 | same shape, `pre_tool_use_oga_guard.py` | same shape, `~/Claude/loop/hooks/pre_tool_use_oga_guard.py` |

(Lines 564/567/570/573/576 are one-line JSON hook-config snippets inside a fenced code block;
each replaces only the `~` prefix inside its `command` string value — identical
mechanical rule, apply `.replace("~", "~")` verbatim to each exact line.)

### `research/false-status-mechanical-verification-2026-07-08.md` (11 hits)

All 11 are the same shape: `` - **`~/Claude/loop/<repo-relative-path>`** (read ...) ``
at lines **19, 29, 39, 73, 93, 156, 166, 176, 186, 195, 213**. Mechanical rule: replace
`~` → `~` in each; repo-relative suffixes are
`loop-team/roles/researcher.md` (19), `search_playbook.md` (29), `loop-team/learnings.md` (39),
`loop-team/harness/fixplan_closure_lint.py` (73), `loop-team/harness/test_fixplan_closure_lint.py`
(93), `loop-team/harness/commit_diff_reread.py` (156), `loop-team/harness/research_authenticity_check.py`
(166), `loop-team/harness/verify.py` (176), `loop-team/harness/dashboard.py` (186),
`loop-team/orchestrator.md` (195), `loop-team/DESIGN_CHECKLIST.md` (213).

### `research/padsplit-cockpit-slice6b-ui-serveraction-reference-patterns-2026-07-08.md` (9 hits)

All 9 (lines **39, 431, 432, 433, 434, 435, 436, 437, 438**) are
`` `~/Claude/Projects/padsplit-cockpit/web/...` `` citations. Same rule:
`~` → `~`. Suffixes: `package.json` (39, 431), `AGENTS.md` / `CLAUDE.md` (432),
`src/app/inbox/actions.ts` (433), `src/app/dashboard/actions.ts` (434),
`src/app/inbox/components/RegenerateButton.tsx` (435), `src/components/SignOutButton.tsx` (436),
`src/app/dashboard/page.tsx` (437), `eslint.config.mjs` (438).

### `research/coder-detection-structural-signal-subagentstop-2026-07-08.md` (9 hits)

| L | Before | After |
|---|---|---|
| 8 | `` `~/Claude/loop/fix_plan.md`. Question: is a genuine STRUCTURAL/BEHAVIORAL `` | `` `~/Claude/loop/fix_plan.md`. Question: is a genuine STRUCTURAL/BEHAVIORAL `` |
| 32 | `` `~/.claude/settings.json` (already quoted in full in this project's own `` | `` `~/.claude/settings.json` (already quoted in full in this project's own `` |
| 37 | JSON hook snippet, `subagent_stop_gate.py` | same, `~/Claude/loop/hooks/subagent_stop_gate.py` |
| 77 | `{"ts": 1783513815.5134022, ..., "cwd": "~", "last_line": "No sub-agents were spawned during this dispatch.", "wrote_flag": false}` | `{"ts": 1783513815.5134022, ..., "cwd": "~", "last_line": "No sub-agents were spawned during this dispatch.", "wrote_flag": false}` |
| 133 | `` (`~/Claude/Projects/taxahead`) matches the commit's `cd` target, so the `` | `` (`~/Claude/Projects/taxahead`) matches the commit's `cd` target, so the `` |
| 464 | Long line: session-authorized evidence citing `` `~/.loop-gate/subagent_gate_debug.jsonl` ``, `` `~/.loop-gate/*.commit_violation` ``, and two `` `~/.claude/projects/-Users-eobodoechine/<uuid>.jsonl` `` paths | Every `~` on the line → `~`, i.e. `` `~/.loop-gate/subagent_gate_debug.jsonl` ``, `` `~/.loop-gate/*.commit_violation` ``, `` `~/.claude/projects/-Users-eobodoechine/<uuid>.jsonl` `` (×2) — **note the surviving `-Users-eobodoechine` substring is a SEPARATE, currently-undetected leak, see §A.5; not required to clear this gate** |
| 465 | Long line citing 5 `` `~/Claude/loop/...` `` paths (`hooks/loop_stop_guard.py`, `hooks/subagent_stop_gate.py`, `fix_plan.md`, 2× `research/*.md`) | Every `~` on the line → `~` (5 occurrences, all replaced identically) |
| 585 | `` -> `python3 '~/Claude/loop/hooks/subagent_stop_gate.py'`), receiving on `` | `` -> `python3 '~/Claude/loop/hooks/subagent_stop_gate.py'`), receiving on `` |
| 592 | `"cwd": "~",` | `"cwd": "~",` |

### `research/padsplit-cockpit-slice6-airbnb-research-2026-07-04.md` (6 hits)

Lines **13, 14, 15, 16, 17, 18** — all `` `~/Claude/Projects/padsplit-cockpit/...` ``
citations. Same rule applied to each: `web/prisma/schema.prisma` (13), `extension/content/padsplit.js`
(14), `extension/content/airbnb.js` (15), `extension/manifest.json` (16), `extension/background.js`
(17), `web/src/app/api/sync/airbnb/route.ts` (18).

### `research/taxahead-tts-lovable-dependency-2026-07-08.md` (3 hits)

| L | Before | After |
|---|---|---|
| 7 | `` **Scope:** repo `~/Claude/Projects/taxahead/` (read-only) + Lovable's official docs `` | `` **Scope:** repo `~/Claude/Projects/taxahead/` (read-only) + Lovable's official docs `` |
| 94 | `` All commands run from repo root (`cd ~/Claude/Projects/taxahead`), excluding `` | `` All commands run from repo root (`cd ~/Claude/Projects/taxahead`), excluding `` |
| 282 | `` - `~/Claude/Projects/taxahead/.env.lovable-legacy` — this is the **actual `` | `` - `~/Claude/Projects/taxahead/.env.lovable-legacy` — this is the **actual `` |

### `research/padsplit-cockpit-slice6b-airbnb-calendar-research-2026-07-04.md` (2 hits)

| L | Before | After |
|---|---|---|
| 18 | `` - `~/Claude/Projects/padsplit-cockpit/web/prisma/schema.prisma` (full, 482 lines, `` | `` - `~/Claude/Projects/padsplit-cockpit/web/prisma/schema.prisma` (full, 482 lines, `` |
| 717 | `` - `~/Claude/Projects/padsplit-cockpit/web/prisma/schema.prisma` — re-read in full, `` | `` - `~/Claude/Projects/padsplit-cockpit/web/prisma/schema.prisma` — re-read in full, `` |

### `research/compiler-gate-design-recommendation-2026-07-08.md` (2 hits)

| L | Before | After |
|---|---|---|
| 4 | `` `~/Claude/loop/research/compiler-gate-external-research-2026-07-08.md` and `` | `` `~/Claude/loop/research/compiler-gate-external-research-2026-07-08.md` and `` |
| 5 | `` `~/Claude/loop/research/compiler-gate-internal-grounding-2026-07-08.md` — `` | `` `~/Claude/loop/research/compiler-gate-internal-grounding-2026-07-08.md` — `` |

### `research/workflow-subdispatch-isolation-design-2026-07-03.md` (1 hit)

| L | Before | After |
|---|---|---|
| 43 | `base = "~/.claude/projects/-Users-eobodoechine/"` | `base = "~/.claude/projects/-Users-eobodoechine/"` — clears NONKEY_PAT; the surviving `-Users-eobodoechine` is the same separate, currently-undetected leak class as L464 above (see §A.5) |

## A.2 — Are these 11 files even meant to be public? (checked, not decided)

I read `README.md`'s "Publishing model" and "Full-history publish pipeline" sections, and
cross-checked against the actual state of `~/loop-public` (the staging clone that pushes to
`github.com/Eobodoechine/loop-engineering`, confirmed via `git -C ~/loop-public remote get-url origin`).

- **`research/` — intended public, and already substantially live there.** `loop-team/orchestrator.md`'s
  Researcher-persistence rules explicitly treat `research/` at repo root as the canonical,
  committed evidence trail ("all research artifacts... live in the repo-root `research/`... NOT
  in `loop-team/research/`"). `snapshot-publish.sh`'s own exclusion list (line 180:
  `rm -rf "$PUBLIC/public" "$PUBLIC/loop-team/runs" "$PUBLIC/runs"`) does **not** exclude
  `research/`. I confirmed directly: `git -C ~/loop-public ls-tree -r HEAD --name-only | grep '^research/' | wc -l` → **35 files already present** in the current live public HEAD. This is
  not a hypothetical risk — it's already the working model. **Alternative to flag, not decide:**
  a handful of these dossiers (e.g. anything narrating a specific private debugging session on
  the requester's own machine, vs. a dossier about the loop-team framework's own design) could arguably
  be excluded from public output rather than redacted-in-place, if the requester judges some of them
  aren't meant for the open-source project's audience — I'm flagging this as an option per-file
  below, not deciding it.
- **`loop-team/learnings.md` — already public, unambiguously.** Confirmed:
  `git -C ~/loop-public ls-tree HEAD -- loop-team/learnings.md` returns the tracked blob. It's
  already shipping (an older revision, since the 3 offending lines in this dossier's §0 were only
  added by the commit that first broke the gate and have never successfully published). No
  exclude-vs-redact question here — it's committed to be public; redact in place. A **general
  house-style question worth flagging** though: these specific 3 lines are a personal-machine
  debugging narrative (Claude Desktop hang root-causing) embedded in a file whose other ~1600
  lines are mostly loop-team-framework lessons — whether that specific *entry* belongs there at
  all is a content-curation call, separate from the path-redaction fix.
- **`SESSION_NOTES.md` — new, not yet published, and the best candidate for "maybe shouldn't be
  public at all" rather than redacted.** Confirmed via `git -C ~/loop-public ls-tree HEAD --
  SESSION_NOTES.md` → **empty result, file not yet present in the public repo** (it was added in
  commit `ee50192`, after the last successful publish, and every subsequent publish attempt has
  failed at the gate — so this file has literally never shipped). Its two lines are a personal
  debugging log of the user's own Claude Desktop/MCP hang, framed as informal running notes (the
  filename itself signals "session scratch notes," distinct in character from a `research/`
  dossier or a `learnings.md` lesson entry, both of which are written as project-facing
  documentation). **This is the one file in this set of 11 I'd flag most strongly as "consider
  excluding from the public tree rather than redacting in place"** — but I'm surfacing this as an
  option for the requester's own call, not deciding it; the redaction spec in §A.1 still fully covers it
  if the decision is to redact-and-publish instead.
- **Separate, confirmed discrepancy relevant to this whole question:** README's "Publishing
  model" section states "This public tree is a **single-commit snapshot**" (i.e., the default
  `snapshot` mode: orphan branch, force-with-lease, so a bad publish is always overwritten by the
  next clean one, never accreted). **I confirmed this is not what's actually running.**
  `scripts/auto-publish-on-commit.sh` line 91 hard-codes `bash scripts/snapshot-publish.sh
  --incremental` — the automated local hook always uses **incremental** mode, which does a plain
  `git add -A && commit && push` (non-force) on top of existing history. I confirmed the actual
  effect: `git -C ~/loop-public log --oneline --all` shows **8 accreted commits** going back to
  2026-07-04 (`c74224a` … `adab2cf`), not one. This means the README's own stated safety
  property — "a bad publish is overwritten by the next clean one rather than accreting" — is
  **not currently true in production**; anything that ever got past the gate in an earlier
  incremental push stays in public git history permanently unless someone does a manual history
  rewrite. This directly bears on severity for §A.5 below (content that already leaked can't be
  un-leaked by a forward-only content fix) and is itself worth its own fix_plan.md entry
  (§A.6, Entry 2) — I'm not proposing a remediation here, just confirming the discrepancy is real.

## A.3 — Validation (scratch copies only; real repo never touched)

Built on top of the same scratch workspace as §7. Applied every redaction in §A.1 to fresh copies
of the 11 files (preserving each file's original directory structure under
`.../pii_fix_test/sim_full_after/`), combined with the already-validated fixed harness files from
§7, then ran the same faithful bash re-implementation of `snapshot-publish.sh`'s exact
`NONKEY_PAT`/`REALKEY_PAT`/`TOOLING_EXCLUDE` logic (`sim_gate.sh`, unchanged from §7) against the
combined 13-file scratch tree:

```
$ ./sim_gate.sh "$(pwd)/sim_full_after" 1
CLEAN -- no hits.
exit=0
```

**Zero hits across all 13 originally-blocking files, combined, in one pass.** This is the same
mechanism validated in §7 (same script, same logic, same `TOOLING_EXCLUDE` extension), now
covering the full 13-file scope the requester asked for. I did not re-run the real `snapshot-publish.sh
--dry-run` against the actual repo (that would require editing the real tracked files, which is
out of scope for this read-only dossier) — this scratch validation proves the redaction text
itself is correct and sufficient for these 13 files; a Coder applying it should see a genuinely
clean `--dry-run` (modulo §A.5's separate, currently-undetected findings, which by definition do
not block the gate today and so cannot be disproven-or-confirmed by a gate re-run either way).

## A.4 — Redaction spec status

The exact per-line before/after text in §A.1 **is** the line-anchored spec — every one of the 62
hits has its literal before/after given (directly, or via the stated mechanical
`.replace("~", "~")` rule for the repeated-shape blocks, which I verified
produces the exact text shown by generating every one of the 62 lines programmatically from the
live files, not by hand-transcribing — see the per-file breakdowns above). A Coder can apply this
directly, file by file, line by line.

## A.5 — CRITICAL, SEPARATE finding: two live scanner blind spots, plus already-published exposure (flagging only — NOT proposing auto-redaction, per instructions)

While enumerating the 62 hits I found **two structurally different ways personal-identifying
content escapes the current gate entirely** (i.e., these do NOT appear in the 62-hit blocking
list — they are currently invisible to `snapshot-publish.sh`, which is worse than blocking). Both
are beyond simple path-scrubbing and involve a judgment call (should the marker/scanner itself
change? should already-published history be rewritten?) that I'm surfacing for the requester directly,
not deciding or auto-fixing.

**(1) The real first name "the requester" is currently unguarded — case-sensitivity gap in the marker
file, not a redaction question.** `scripts/.pii-markers.local` lists the name marker as lowercase
`requester`. `snapshot-publish.sh`'s scan (`grep -rInE`, confirmed by reading the exact flags at
line 229/243) has **no `-i` flag** — it is case-sensitive. Every real-prose usage of the name in
this repo capitalizes it as a proper noun ("**the requester** asked...", "confirmed by ... **the requester**").
I confirmed via `git grep -n 'the requester'` (whole tracked tree): **57 occurrences across the tracked
tree**, none of which trip the gate today. Worse: I checked whether this has *already* reached the
public remote — `git -C ~/loop-public grep -c 'the requester' HEAD` (the actual currently-pushed, live
`main` branch of `github.com/Eobodoechine/loop-engineering`) returns **8 occurrences across 6
already-published files** (`research/claude-cookbooks-review-2026-07-02.md`,
`research/h-subagent-masking-1-full-closure-design-2026-07-03.md`,
`research/loop-team-process-retrospective-review-2026-07-02.md` ×2,
`research/ops-clock-alt-method-experiment-2026-07-02.md`,
`research/ops-clock-gap-taxonomy-2026-07-02.md`, `research/radar.md` ×2). This is not something I
found blocked by the current gate — it's something the gate has been letting through undetected,
already live on GitHub. **I am not proposing to add `the requester`/case-insensitivity to the marker file
myself** — that's a scanner-design change (does the gate need `-i`? does the whole real name need
to be a marker rather than relying on a differently-cased fragment?) squarely in the requester's own
judgment, and separately, fixing the marker forward does nothing about the 8 lines **already on
GitHub** (see finding 3 below).

**(2) A second, structurally different escape: the hyphenated Claude-Code project-slug form.**
Claude Code encodes a session's absolute cwd into its own project-storage directory name by
replacing every `/` with `-` (e.g. `~` → `-Users-eobodoechine`, seen throughout
this repo as `~/.claude/projects/-Users-eobodoechine/...`). This hyphenated form contains **no
literal `/Use` + `rs/` substring** (no slashes at all), so it cannot match `HOMES_PREFIX` and is
**structurally invisible to the current NONKEY_PAT scan**, independent of the case-sensitivity
issue above. I found **8 occurrences across 3 files** (case-sensitive, exact string
`-Users-eobodoechine`):
- `research/false-status-mechanical-verification-2026-07-08.md:922`
- `loop-team/learnings.md:1032`
- `research/coder-detection-structural-signal-subagentstop-2026-07-08.md:85` **and** `:464` (the
  latter already appears in §A.1's redaction table for its separate `~` hits —
  its `-Users-eobodoechine` substrings survive that redaction untouched)
- `research/workflow-subdispatch-isolation-design-2026-07-03.md:37`, `:43` (also in §A.1's table
  for the same reason), `:575`, `:602`

Of these 8, only 2 (`coder-detection...:464`, `workflow-subdispatch...:43`) are among the 62
hits already being redacted in §A.1 (and only for their *separate* `~`
occurrence on the same line — the hyphenated substring on those same lines is untouched by that
redaction). The other 6 lines don't appear in §A.1's list at all, because they never triggered the
gate. **If a full content-redaction pass over these files is happening anyway, I'd flag these 6
(+2 partial) lines for the same treatment (e.g. `-Users-eobodoechine` → `-Users-<redacted>`,
preserving the fact that it's describing Claude Code's own path-to-slug encoding scheme without
naming the real user) — but I'm not including this in the primary §A.1 spec because, unlike every
line in §A.1, none of these are required to make `--dry-run` pass; adding them changes the scope
from "clear the current gate" to "close a gate gap," which is the judgment call this section
exists to flag, not decide.**

**(3) Compounding factor: the public history already accretes (see §A.2's README discrepancy),
so anything in category (1) or (2) that already reached `~/loop-public`'s pushed `main` cannot be
fixed by a forward-only content edit.** The 8 "the requester" occurrences already on GitHub (finding 1)
sit in commits `c74224a` through `adab2cf`, and because the live automation uses `--incremental`
(non-force, accretive) rather than the README-documented single-commit `snapshot` mode, those
commits are not overwritten by the next publish — only a deliberate history rewrite (or a switch
back to true `snapshot`/orphan mode for a future publish, which replaces remote history via
`--force-with-lease`) removes them. This is very likely the exact motivating problem behind the
"Full-history publish pipeline (building blocks, not yet wired into one command)" section of
README.md, whose 5 scripts (`verified_mirror_clone.py`, `identity_audit.py`, `full_history_scan.py`
— the very file this dossier's §1-§7 already fixed — `path_removal.py`, `tree_verify.py`) I
confirmed all already exist on disk. That pipeline's stated job (walk `git rev-list --all`, scan
every blob, then use `git filter-repo` to strip content and force-rewrite) is designed to solve
exactly this class of problem — but per README it is "not yet wired into one command," and even
once wired, `path_removal.py`'s described behavior (`--path public/ --path runs/ --path
loop-team/runs/ --invert-paths`) strips whole directory trees, not inline content matches inside
an otherwise-legitimate file — so it would not, as currently scoped, catch a bare "the requester" or
"-Users-eobodoechine" embedded in prose inside a `research/*.md` file that's supposed to exist. I'm
flagging this gap in the pipeline's current scope, not proposing a fix to it.

**Recommendation (flagged, not decided): this whole §A.5 deserves a human (the requester) look before
anyone touches the marker file, the automation mode, or the public git history — none of these are
narrow, low-risk mechanical fixes like §A.1's path redaction. See draft fix_plan.md Entry 2 below.**

## A.6 — Draft fix_plan.md entries (for the Coder/Verifier round to file; I have not written these into fix_plan.md myself)

Matching the file's existing header convention (`## H-<SLUG>-N (STATUS, filed <date>, priority:
<LEVEL>) -- <one-line summary>`, confirmed against `H-HYGIENE-SCAN-SOURCE-EMBED-FP-1` and ~30
other entries read for style):

---

**Entry 1 (ready to file as OPEN, becomes CLOSED once the Coder round lands):**

```
## H-PII-GATE-TOOLING-FP-1 (OPEN, filed 2026-07-09, priority: HIGH) -- full_history_scan.py's
own detection-pattern source + 11 pre-existing tracked docs blocked snapshot-publish.sh's
privacy gate, halting all publishing since commit 43da532

Found by Researcher (Mode B Coder-unblock dispatch), 2026-07-09. `bash
scripts/snapshot-publish.sh --dry-run` (from `~/Claude/loop`) fails with "PUBLISH BLOCKED --
personal data / real key found" -- confirmed live, 77 hit-lines across 13 tracked files.
Two root causes, independent:
(a) `loop-team/harness/full_history_scan.py`/`test_full_history_scan.py` (added commit
`59055cf`) legitimately contain the literal substrings `/Use` + `rs/` (their own home-path
detection regex source, 2+4 lines) and `sk-ant` + `-api` (their own REALKEY detection regex
source, 7+2 lines) as detection-pattern text, not real leaks -- but neither file is in
`snapshot-publish.sh`'s `TOOLING_EXCLUDE` array (lines 66-74), so REALKEY_PAT flags them
(NONKEY_PAT's home-path scan has zero tooling-exemption mechanism by design, lines 227-230,
and rightly so -- see proposed fix).
(b) Independently, and predating (a): commit `43da532` ("Add adversarial-AC oracle-targeting
gate...") added 3 lines to `loop-team/learnings.md` containing real literal
`~/...` paths documenting a personal debugging incident -- this alone broke
the gate BEFORE full_history_scan.py existed (confirmed via `.git/hooks/auto-publish.log` +
`git blame`). Subsequent commits (`91823dd`, `ee50192`) added more research/SESSION_NOTES
content with the same literal-path pattern, compounding to 11 files / 62 hit-lines total,
none of which are tooling/detection-pattern text -- genuine personal-path citations in
research-dossier prose (the "Researcher pulls real data" convention mandates exact absolute
file/line citations, which structurally collides with "no `/Use` + `rs/` may ever appear
published").

Proposed fix: (a) add `loop-team/harness/full_history_scan.py` and
`loop-team/harness/test_full_history_scan.py` to `TOOLING_EXCLUDE` (handles the REALKEY
hits, mirrors the existing 7-entry precedent) + rewrite the 6 lines containing literal
`/Use` + `rs/` in those 2 files using the same adjacent-string-literal construction trick
`snapshot-publish.sh` already uses on itself (`HOMES_PREFIX="/Use""rs/"`, commit `dedd155`) --
zero security-model change, byte-identical compiled regex, all 10 existing tests pass
unmodified (validated on scratch copies). (b) redact the 62 literal `~`
occurrences across the 11 pre-existing files to `~/...` (the tilde convention already
exclusive to every other tracked/published doc in this repo -- `orchestrator.md`, all
`roles/*.md`, never use the literal form). Full line-anchored before/after for all 77 lines,
plus scratch-copy validation showing a combined clean scan:
`research/pii_gate_tooling_false_positive_fix_dossier.md`.

Full dossier + validation: `research/pii_gate_tooling_false_positive_fix_dossier.md` (this file).
```

---

**Entry 2 (flagging, not a mechanical fix -- OPEN, needs the requester's judgment before any Coder
touches marker file / automation mode / public history):**

```
## H-PII-GATE-BLINDSPOTS-1 (OPEN, filed 2026-07-09, priority: HIGH -- needs human judgment,
NOT auto-fixable) -- two structurally distinct scanner blind spots let real personal content
past snapshot-publish.sh's gate undetected, some already live on the public GitHub remote

Found by Researcher (Mode B Coder-unblock dispatch), 2026-07-09, while enumerating the
H-PII-GATE-TOOLING-FP-1 redaction set. Two independent gaps, neither part of the 62-hit
blocking set in H-PII-GATE-TOOLING-FP-1 because neither currently triggers the gate at all:
(1) Marker-file case-sensitivity: `scripts/.pii-markers.local` lists the real first name as
lowercase `requester`; `snapshot-publish.sh`'s scan has no `-i` flag; every real usage in prose
is capitalized "the requester". `git grep -n the requester` finds 57 tracked-tree occurrences, completely
unguarded. Worse: `git -C ~/loop-public grep -c the requester HEAD` finds 8 occurrences across 6
files ALREADY LIVE on `github.com/Eobodoechine/loop-engineering`'s pushed main branch.
(2) The Claude-Code project-slug encoding (`/` -> `-` in a cwd path, e.g.
`-Users-eobodoechine`) contains no literal `/Use` + `rs/` substring and is structurally invisible
to NONKEY_PAT's home-path pattern regardless of case. Found 8 occurrences across 3 files (2
of which coincidentally also carry a separate, already-redacted `~` hit on
the same line; the other 6 are entirely unguarded).
(3) Compounding factor: README.md's "Publishing model" section states the public tree is a
single-commit snapshot (old content always overwritten). This is NOT what's running --
`scripts/auto-publish-on-commit.sh:91` hard-codes `--incremental` (accretive, non-force).
Confirmed: `~/loop-public`'s pushed history has 8 real accreted commits back to 2026-07-04,
not one. Anything that already leaked via incremental publish (including the 8 live "the requester"
occurrences above) is NOT removed by a forward-only content fix -- it sits in permanent,
force-push-only-recoverable public git history. This is very likely the motivating reason
`loop-team/harness/`'s 5-script "full-history publish pipeline" (verified_mirror_clone.py,
identity_audit.py, full_history_scan.py, path_removal.py, tree_verify.py -- all confirmed to
already exist on disk) was started, but README calls it "not yet wired into one command," and
as currently scoped (`path_removal.py` strips whole directory trees via `git filter-repo
--path ... --invert-paths`) it would not catch inline prose content like this inside an
otherwise-legitimate file.

NOT proposing a fix here -- each of (1)/(2)/(3) is a judgment call (does the marker scan need
case-insensitivity or a differently-shaped marker; is content-level history rewriting worth
doing now vs. accepting the residual exposure; should the automation switch back to true
snapshot mode) that belongs to the requester, not a mechanical redaction. Full detail + exact line
lists: `research/pii_gate_tooling_false_positive_fix_dossier.md` §A.5 (this file).
```

---

I recommend Oga file both entries (or fold Entry 1 into whatever entry closes once the Coder
lands the §A.1+§7 fix) and treat Entry 2 as blocked-on-human-input rather than something a
Coder round should attempt to resolve.
