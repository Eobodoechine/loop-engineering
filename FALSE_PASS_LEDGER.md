# False-Pass Ledger — TaxAhead and PMS Cockpit

Accounting for claims recorded as passing without a proof-of-run receipt.
Companion to `MERGE_GATE_PLAN.md` (Phase 7, historical retest) and
`MERGE_GATE_SPEC.md` §5 (receipt schema).

Audit date: 2026-08-09. Sources audited: `control-plane/projects/taxahead.json`,
`control-plane/projects/padsplit-cockpit.json`, and the `artifacts/` tree, all
at commit `14a6a57`.

## 1. What makes a pass false

A claim is a **false pass** when its recorded outcome is `PASS` but nothing on
record proves a run ever produced that result.

Every claim in both contracts carries an `evidence_path`. In every case that
path is **a source file** — a test file, a script, or a temp file — not a
record of an execution. A path to `session.test.ts` proves that a test *exists*.
It does not prove the test *ran*, that it *passed*, which *commit* it ran
against, or *when*. Those four facts are exactly what a receipt carries and
what the contract schema has no field for.

Concretely, the contract schema has no `run_url`, no `commit_sha`, no
`run_timestamp`, and no `exit_code`. **A PASS in this system is currently
unfalsifiable by construction.** That is the mechanism, and it is not a
matter of anyone being careless.

## 2. Root cause: the machinery exists and was bypassed

This repository already solved this problem — for a different consumer.

`loop-team/harness/run_and_record.py` executes a command as a real subprocess
and records "the exact argv, exit code, a hash of the combined stdout+stderr,
sha256 hashes of any argv token that resolves to a real on-disk file, and
whether the git worktree was dirty." Its own docstring states its purpose: it
"turns a hand-typed, unverifiable closure claim into something a script can
independently re-check."

`loop-team/harness/evidence_ledger.py` goes further, and its design note is the
governing principle here:

> If a ledger file exists at all, it must be machine-derived from the inline
> Proof blocks, never a second hand-authored source of the same fact.

The control-plane project contracts are precisely that forbidden thing: a
second, hand-authored source of claim outcomes, never derived from a recorded
run. The fix is therefore **not** to invent a new receipt format — it is to
route project claims through the recorder that already exists.

Two supporting defects found while auditing:

- `control-plane/README.md` documents every validation command against
  `loop-team/harness/mission_control.py`. **That file does not exist in this
  repository.** The documented way to validate these contracts is not runnable,
  so the contracts have no enforced schema at all.
- Contract `last_activity` is `2026-07-13`, but `artifacts/taxahead-e2e-2026-07-20/`
  is newer and the contracts entered git on 2026-07-23. The claims were never
  reconciled against the later evidence.

## 3. The clearest false pass: the 2026-07-20 E2E report

`artifacts/taxahead-e2e-2026-07-20/VERIFICATION_REPORT.md` records a
commit-by-commit table of **15 of 18 commits PASS, 3 PARTIAL**. The raw command
output sitting in that same directory says otherwise:

| Artifact in the same folder | What it actually records |
|---|---|
| `vitest-output.txt` | `Tests 7 failed \| 161 passed (168)` |
| `vitest-output-final.txt` | **The same 7 failures** — only the start time differs (11:50:12 → 12:35:05). The re-run fixed nothing |
| `tsc-output.txt` | 7 TypeScript errors (`business_activities` types in `app.profile.tsx`) |
| `tsc-output-final.txt` | **0 bytes. Empty.** |
| Interactive feature table (report lines 68–71) | **4 of 4 actions FAILED** — filing status save, add dependent, add business, save address, all 400/404 from missing migrations |
| `console-errors.txt` | 404s, 400s, and a persisting React hydration error #418 |

Three things make this the sharpest example in the audit:

1. **A 15/18 PASS verdict was recorded over evidence of 7 failing tests, 7 type
   errors, and every interactive action failing.** No re-reading of the report
   is needed to see the contradiction; the contradicting files are adjacent.
2. **An empty file was treated as a clean result.** `tsc-output-final.txt` is
   zero bytes. An empty capture is not proof of zero errors — it is proof of
   nothing, and is indistinguishable from a command that never ran or whose
   redirect failed. Any "-final" artifact that is empty must be read as
   `NOT_RUN`, never as green.
3. **The "-final" re-run reproduced the identical failures.** The presence of a
   second run created the *appearance* of remediation while changing no result.

There is also a baseline mismatch. This report cites baseline SHA
`55c90319e4e499d069ee9f3350e1a7ec001f2962`, while the contract's canonical
baseline is `a78f13598cf7a425de4bd20e92d6b97f140eedb3` and the reconciliation
register records that same canonical SHA. **The E2E evidence was produced
against a different commit than the one the contract calls canonical**, so even
its passing rows do not attach to the baseline the project claims.

Finally, a repo-wide search for any schema-conformant receipt — a JSON carrying
a 40-hex commit SHA plus named check conclusions — returns **zero hits**. Not
one recorded evidence receipt exists for either project. The `record-evidence`
concept the original issue describes has never produced a stored artifact here.

## 4. TaxAhead claim ledger (12 claims)

| # | Claim | Recorded | Evidence field points to | Verdict |
|---|---|---|---|---|
| 1 | `core-auth-bootstrap` | **PASS** | `core/tests/lib/session.test.ts` — a test file | **FALSE PASS** — no run recorded. Its own `next_action` is "Run credentialed Supabase smoke", i.e. unfinished |
| 2 | `core-upload-extraction` | **PASS** | `functions/extract-document/index.test.ts` — a test file | **FALSE PASS** — no run recorded. `next_action`: "Exercise a real storage and document fixture" |
| 3 | `frontend-wiring` | **PASS** | `ui/tests/routes/get-started.test.tsx` — a test file | **FALSE PASS, scope-inflated** — stage is `E2E`, yet the explanation concedes "protected routes still need credentialed smoke". A partial pass recorded at full-stage scope |
| 4 | `core-tax-package` | FAIL / REQUIREMENTS | `scripts/reality-check.mjs` — a script | Honest FAIL. Evidence still unretrievable (script, not output) |
| 5 | `core-grounded-qa` | FAIL / NAVIGATION | `src/lib/edge-functions.ts` — source | Honest FAIL |
| 6 | `ui-admin-deep-links` | FAIL / NAVIGATION | `ui/src/routes/admin.tsx` — source | Honest FAIL |
| 7 | `ui-hydration` | FAIL / ASSERTION | `ui/src/routes/__root.tsx` — source | Honest FAIL |
| 8 | `ui-harness` | FAIL / HARNESS | `ui/package.json` — source | Honest FAIL (1,872 ESLint problems; Vitest could not start) |
| 9 | `typescript` | FAIL / COMPILE | **`/tmp/taxahead-core-tsc.txt`** | Honest FAIL, but evidence is in `/tmp` — **ephemeral and almost certainly gone**. Unreproducible either way |
| 10 | `connector-adapters` | FAIL / REQUIREMENTS | `_shared/adapter-registry.ts` — source | Honest FAIL |
| 11 | `connector-live` | BLOCKED_EXTERNAL / ENVIRONMENT | `connectors/.env` | Correctly typed. Not fixable by code |
| 12 | `core-live` | BLOCKED_EXTERNAL / ENVIRONMENT | `scripts/reality-check.mjs` | Correctly typed. Not fixable by code |

**TaxAhead: 3 false passes in the contract (claims 1, 2, 3), plus the 15/18 PASS verdict in §3.** All four slices remain
`IN_PROGRESS` or `NOT_RUN`, and project progress reads `0/4, 0%` — the three
PASS claims never advanced any slice, which is itself a signal they were not
load-bearing proof.

## 5. PMS Cockpit ledger (5 claims)

| # | Claim | Recorded | Verdict |
|---|---|---|---|
| 1 | `pms-live-workflow` | BLOCKED_EXTERNAL / ENVIRONMENT | Correctly typed |
| 2 | `pms-sync` | FAIL / ASSERTION | Honest FAIL |
| 3 | `pms-integrity` | BLOCKED_EXTERNAL / ENVIRONMENT | Correctly typed |
| 4 | `pms-extension` | BLOCKED_EXTERNAL / ENVIRONMENT | Correctly typed |
| 5 | `pms-readiness` | FAIL / REQUIREMENTS | Honest FAIL — **and it is itself the record of prior false passes** |

**PMS Cockpit: 0 current false passes.** Every claim is `FAIL` or
`BLOCKED_EXTERNAL`; none asserts an unproven pass.

But claim 5 documents that false passes *did* occur historically: retained
evidence records a non-green suite of **6 failures, 1,052 passes, 11 skips**,
against which "claims of fully verified/live/ready are unsupported." So PMS's
history contains readiness statements made over a red suite. Those statements
are the same defect as TaxAhead's three, caught one layer later.

This is the pattern worth naming: **PMS is not cleaner than TaxAhead — it is
further along in the same audit.** Its false passes have already been converted
into an honest FAIL. TaxAhead's have not yet.

## 6. Dispositions

None of the three TaxAhead false passes can be closed by re-reading the
contract. Each requires a recorded run.

| Claim | Required action | Blocking? |
|---|---|---|
| `core-auth-bootstrap` | Re-run the focused auth/session/bootstrap suite under `run_and_record.py` against a named SHA. Downgrade to `NOT_RUN` until then | No — mechanical |
| `core-upload-extraction` | Same, for the extraction/scoring suite | No — mechanical |
| `frontend-wiring` | Re-run the wiring suite under `run_and_record.py`; additionally **split the claim** so the unproven protected-route portion is its own claim rather than riding on a partial pass | No — mechanical |
| `typescript` | Re-capture `tsc` output to a durable path; `/tmp` evidence must never be cited again | No |
| All `BLOCKED_EXTERNAL` (4) | Not code-fixable. Owner + missing input + date, per `MERGE_GATE_SPEC.md` §10. Never a required check until the input exists | Yes — external |

Interim status: all three false passes MUST be downgraded to `NOT_RUN` — not to
`FAIL`, because no run established failure either. `NOT_RUN` is the honest
state for "we do not know."

## 7. The same defect at the test layer: false coverage from the publish pipeline

The claim-level false passes in §3–§5 have a structural twin, found while
burning down this repository's own suite. Both are unverified transformations
that leave something *looking* proven.

`scripts/snapshot-publish.sh:245` (`redact_generated_home_paths`) rewrites
`$HOME` to the literal string `<HOME>` across every non-binary file in the
published tree — **including Python test source**. Where a test's fixture data
was an absolute path, redaction silently turns it into a non-absolute string:

`loop-team/runner/tests/test_codex_subscription_pilot.py:1242` parametrizes
`test_packet_work_roots_cannot_equal_or_descend_from_canonical_protected_root`
with `"<HOME>/Claude/Projects/taxahead"`. Because `os.path.isabs("<HOME>/…")`
is `False`, the packet is rejected by an *earlier* guard ("frozen packet roots
are incomplete") before the protected-root check is ever reached. The test
still raises `PilotBlockedError`, so `pytest.raises` is satisfied on type and
only the `match=` fails.

The consequence: a test named and documented for `[PROTECTED-ROOTS] Product
attempts cannot run inside canonical repositories` **does not exercise that
protection at all**. Had the `match=` been looser, it would have passed while
testing nothing — a green check over absent coverage, which is the §1 defect
one layer down.

A second publish-pipeline effect: the published history is squashed into
`snapshot: publish tracked tree` commits, so tests pinning baseline SHAs
(`98ecb27b…`, `e8ed8b8e…`, and one more) fail with "exists on disk, but not in
`<sha>`". **The publish discards the history those tests depend on.** They can
never pass anywhere except the original working repository.

Both are fixes at the publish step, not the test:

- Redaction MUST NOT rewrite executable source. Restrict it to generated
  artifacts and documentation, or fail the publish when a substitution lands
  inside a `.py`/`.ts` file.
- Either preserve the referenced commits, or make pinned-SHA tests resolve the
  baseline by tag/content rather than by a SHA the publish will discard.

## 8. Preventing recurrence

The mechanism, not the three claims, is the fix:

1. **Extend the claim schema** with `commit_sha`, `run_url` or proof-snapshot
   path, `run_timestamp`, and `exit_code`, all required when `outcome` is
   `PASS`. A PASS without them fails validation.
2. **Derive, don't hand-author.** Per `evidence_ledger.py`'s own rule, claim
   outcomes should be machine-derived from recorded proof snapshots, never
   typed into JSON by hand.
3. **Restore the validator.** `mission_control.py` is referenced by
   `control-plane/README.md` but absent; without it nothing enforces the
   schema. Either restore it or repoint the README at what actually exists.
4. **A test file path is never evidence.** Reject any `evidence_path` that
   resolves to a source file rather than a recorded run artifact.
5. **An empty artifact is `NOT_RUN`, never green.** `tsc-output-final.txt` (0
   bytes) must fail validation rather than read as "no errors". This is a
   two-line check and would have caught §3 on its own.
6. **Bind evidence to the claimed SHA.** Reject evidence produced against a
   commit other than the one the claim names — the §3 baseline mismatch
   (`55c90319…` vs canonical `a78f1359…`) passes every other check.
5. `evidence-preflight` (spec §4) enforces this pre-merge, so a claim can
   never again reach `main` asserting a pass it cannot prove.

Item 1 and item 4 are each a small, testable change and are the highest-value
work remaining in this area.
