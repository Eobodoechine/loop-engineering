# V9 hermetic dependency-closure architecture

Date: 2026-07-14  
Mode: Researcher Mode D  
Scope: architecture research only; no implementation or plan edits

## Question

How can the V9 evaluator execute its seven exact historical scorer suites and its
synthetic pipeline from a source-unavailable, authenticated dependency snapshot,
without opening semantic Oracle payloads, exposing historical fixtures to real
candidate/custody execution, weakening exact test bytes, or treating Python audit
hooks as a security sandbox?

## Answer

Use a detached, hash-pinned CPython bootstrap to authenticate and materialize one
content snapshot into **two separately rooted allowlisted views**:

1. A **reviewer/regression view** containing the exact V9 evaluator, the seven
   historical test/scorer closures, the exact visible/nonsemantic development
   dependencies, deterministic relocated command records, and two generated
   metadata-only size witnesses at the historical semantic paths. It contains no
   semantic Oracle bytes.
2. A **candidate/custody view** containing only the exact V9 runtime and the exact
   V7 public contract closure plus current run inputs/state/scratch. It contains no
   historical tests, development fixtures, historical package outputs, semantic
   witnesses, or sibling reviewer view.

The views must be separate fresh directories, not sibling subdirectories under a
common project-visible root. Project code is not imported until the detached
bootstrap has verified a detached closure-root hash, descriptor-walked and hashed
every governed byte, rejected symlinks and hard links, and captured executable
Python bytes in memory. Run CPython as `python3 -I -S -B <bootstrap>` and record the
exact interpreter identity. The bootstrap then installs narrow, manifest-bound
adapters for the three absolute reference constants, the two historical command
records, and V2's one nested subprocess call site.

Audit hooks enforce and record fail-closed invariants for this authenticated code;
they are not the sandbox. This distinction is required by Python's own
documentation, which says Python-level audit hooks can be bypassed by malicious
code. The threat model therefore excludes malicious native code, `ctypes`, dynamic
extensions, and a compromised CPython/kernel. Real candidate/custody execution
gets structural filesystem separation in addition to auditing, but the design does
not claim same-UID macOS process isolation against arbitrary hostile native code.

Two existing requirements need explicit reconciliation before implementation:

- Exact tests require a regular file with an exact historical size at each of two
  semantic paths, while the proposed plan also forbids those exact paths. Both
  cannot be literally true. Permit a governed role named
  `metadata_absence_witness`: a newly generated, sparse, zero-filled regular file
  with the required logical size, no copied source bytes, mode `000`, and an audit
  rule that denies every open/read. Continue to forbid the role `semantic_file` and
  all semantic content. If even a nonsemantic witness at the path is forbidden,
  the exact historical tests are unsatisfiable without changing test behavior.
- The historical command JSON bytes contain the old absolute run root, while the
  exact scorer requires `cwd` and the input-root argument to resolve inside the
  relocated view. Preserve and authenticate the original command-record hash as
  source evidence, then authenticate a canonical derived record at the expected
  execution path. “Exact command bytes at the expected execution path” and
  “source-unavailable relocation” are otherwise mutually exclusive.

## What the current code actually requires

### Historical suite denominator

The V9 regression wrapper names exactly seven scripts, but currently checks only
their subprocess exit codes
([test_historical_scorer_regressions.py:9-37](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v9/test_historical_scorer_regressions.py:9)).
Direct inspection of the exact files gives this immutable denominator:

| Suite | Exact tests |
|---|---:|
| recovery | 9 |
| V1 | 6 |
| V2 | 13 |
| V3 | 6 |
| V4 | 11 |
| V5 | 5 |
| V6 | 9 |
| **Total** | **59** |

The hermetic runner must discover these exact IDs before execution and reject any
missing, added, duplicated, skipped, errored, expected-failure, unexpected-success,
or renamed test. Exit status alone is not sufficient evidence.

### Dependency facts that drive the design

- Recovery hard-codes the canonical PACE path
  ([recovery_scorer.py:45](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v4/recovery/recovery_scorer.py:45)).
  V4, V5, and V6 hard-code the PACE and acceptor reference paths
  ([V4:42-43](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v4/oracle_v2_scoring_v4/oracle_v2_scorer.py:42),
  [V5:29-30](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v4/oracle_v2_scoring_v5/oracle_v2_scorer.py:29),
  [V6:30-31](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v4/oracle_v2_scoring_v6/oracle_v2_scorer.py:30)).
  These are the only path constants that require a module-object adapter.
- Recovery authenticates the old corpus root as an 83-member denominator, but for
  the semantic row performs only `lstat`, regular-file, and size checks; all other
  rows are hashed
  ([recovery_scorer.py:141-168](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v4/recovery/recovery_scorer.py:141)).
- V2 likewise authenticates nonsemantic root/validation metadata and then only
  checks that the semantic member is a nonsymlink regular file of the declared
  size
  ([oracle_v2_scorer.py:85-157](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v4/oracle_v2_scoring_v2/oracle_v2_scorer.py:85)).
- V4 explicitly skips the semantic row while capturing and hashing the visible
  corpus
  ([V4 scorer:206-230](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v4/oracle_v2_scoring_v4/oracle_v2_scorer.py:206)).
- V2 launches the exact public reference once per visible valid case using a
  nested `subprocess.run` with no explicit child environment or `cwd`
  ([V2 scorer:263-286](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v4/oracle_v2_scoring_v2/oracle_v2_scorer.py:263)).
  That call site needs its own governed child adapter.
- V5/V6 already capture root-listed bytes and `compile`/`exec` them, but their
  final-file `O_NOFOLLOW` readers do not descriptor-walk parents and do not reject
  hard links
  ([V5 scorer:66-95](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v4/oracle_v2_scoring_v5/oracle_v2_scorer.py:66)).
  Their internal checks are useful but cannot replace the outer bootstrap.
- The recovery command check requires exactly two command filenames, exact argv
  prefixes, relocated `cwd`, and a relocated input-root argument
  ([recovery_scorer.py:171-195](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v4/recovery/recovery_scorer.py:171)).
- The current V9 freeze lists 18 direct members and self-excludes its root, reads
  members by pathname, and does not authenticate transitive dependencies
  ([freeze_evaluator.py:19-67](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v9/freeze_evaluator.py:19)).
- The real V9 wrapper launches candidate and custody with `sys.executable`, the
  live run root as `cwd`, and a copy of the full parent environment
  ([approved_execution_wrapper.py:56-59](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v9/approved_execution_wrapper.py:56),
  [177-208](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v9/approved_execution_wrapper.py:177)).
  Hermetic execution must replace that boundary with a minimal explicit
  environment and the candidate/custody view root.
- The synthetic pipeline imports V9 and V7 code before checking any transitive
  closure and reads a V7 development case as its template
  ([synthetic_v9_pipeline.py:24-33](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v9/synthetic_v9_pipeline.py:24),
  [70-73](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v9/synthetic_v9_pipeline.py:70)).
  It creates one local `socketpair`
  ([400-430](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v9/synthetic_v9_pipeline.py:400)).

Observed manifest denominators, without opening prohibited semantic or arm-output
members:

- V4 public contract: 39 members.
- V7 public contract: 44 members.
- Old development corpus: 83 governed paths total; the reviewer view materializes
  82 authenticated visible/nonsemantic members plus one generated witness at the
  semantic path, preserving the 83-path shape without semantic bytes.
- Visible input: 74 valid cases, 6 ingress fixtures, 148 expected result rows.
- Historical development package manifest: 227 rows: 148 arm-artifact rows,
  74 canonical cases, and one each for execution environment, ingress, input
  before, input after, and result. Recovery preflight requires the entire package
  closure in the reviewer view, even though this research did not open arm-output
  members.
- V9 direct root: 18 listed members plus the self-excluded root itself. The new
  closure must make this `18 + 1` denominator explicit and must not infer members
  by glob. Nongoverned logs/review artifacts are not copied.

## Proposed trust and execution architecture

### 1. Detached trust bootstrap

The bootstrap must live outside every project-controlled snapshot. Its expected
SHA-256, the expected closure-root SHA-256, and the expected V9 evaluator-root
SHA-256 are supplied out of band. A root manifest inside the same editable tree is
not a trust root because an attacker could replace both member and manifest.

Invoke the platform CPython 3.9 interpreter as:

```text
/absolute/pinned/python3 -I -S -B /absolute/pinned/v9_bootstrap.py \
  --closure-root /fresh/reviewer-view/closure_root.json \
  --expected-closure-sha256 <detached-sha256> \
  --mode historical-and-synthetic
```

Record `sys.implementation`, the exact version tuple, executable path and hash,
platform, architecture, and active flags. Fail if the observed runtime does not
match the closure policy. `-I` ignores `PYTHON*`, excludes the script directory and
user site from `sys.path`, and implies `-E -s`; `-S` disables `site`; `-B` prevents
bytecode writes. These are startup hygiene controls, not a sandbox.

### 2. Immutable snapshot and two materialized views

The packager reads an authenticated source snapshot once, using the descriptor
algorithm below, and creates two fresh destinations with exclusive creation. It
must never hard-link or reflink project files into either destination.

**Reviewer/regression view**

- V9's exact 18 direct members and root.
- The seven exact test scripts, scorers, configs, nested frozen roots, public V4
  39-member closure, PACE and acceptor references.
- The 82 visible/nonsemantic corpus members, exact nonsemantic V2 metadata, the
  two generated size witnesses, and the historical package members required by
  preflight.
- The two canonical derived command records plus their transformation receipts.
- A scratch root that is the only writable subtree.

**Candidate/custody view**

- Only V9 runtime files required by real execution.
- Exact V7 44-member public contract and root.
- Current corpus inputs that the approved run is authorized to see.
- Fresh state/output/scratch locations.
- No reviewer view path, development corpus, historical package, seven test
  scripts, witness, or prior run artifact.

Do not place these under a shared parent that project code can enumerate. Construct
one, run it, destroy it, then independently construct the other when practical.
For the synthetic pipeline, candidate/custody calls are mocked, so it runs in the
reviewer view; real candidate/custody processes run only in the second view.

### 3. Closure manifest model

Use a canonical JSON root with sorted, unique rows and exact denominators:

```json
{
  "schema_version": 1,
  "generation_id": "...",
  "direct_v9": {"count": 18, "root_included_separately": true, "rows": []},
  "views": {
    "reviewer": {"manifest_sha256": "...", "file_count": 0},
    "candidate_custody": {"manifest_sha256": "...", "file_count": 0}
  },
  "historical_suites": {
    "exact_total": 59,
    "counts": {"recovery": 9, "v1": 6, "v2": 13, "v3": 6, "v4": 11, "v5": 5, "v6": 9}
  },
  "nested_roots": {"public_v4": 39, "public_v7": 44, "corpus_paths": 83},
  "adapters": [],
  "witnesses": [],
  "source_unavailable_replay_required": true
}
```

Every file row contains view-relative path, role, byte count, SHA-256, mode,
expected owner, source identity, and whether it may be opened after bootstrap.
Every directory is separately allowlisted. Roots that self-exclude are themselves
ordinary rows in the parent closure. No runtime trace may add an undeclared member;
tracing is an assertion against the static closure, not a way to discover the
denominator after execution.

### 4. Stable descriptor read

```python
def capture_regular(root_fd, rel, expected):
    assert safe_posix_relative(rel) and rel in exact_manifest_rows
    parent_fd = os.dup(root_fd)
    for part in PurePosixPath(rel).parts[:-1]:
        next_fd = os.open(part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW,
                          dir_fd=parent_fd)
        assert_dir_policy(os.fstat(next_fd))
        os.close(parent_fd)
        parent_fd = next_fd
    fd = os.open(parts[-1], O_RDONLY | O_NOFOLLOW, dir_fd=parent_fd)
    before = os.fstat(fd)
    require(S_ISREG(before.st_mode), before.st_nlink == 1)
    require(expected_owner_mode_size(before, expected))
    raw = read_to_eof(fd)
    after = os.fstat(fd)
    require(stable(before, after,
        fields=("st_dev", "st_ino", "st_nlink", "st_size",
                "st_mtime_ns", "st_ctime_ns")))
    require(len(raw) == expected.bytes)
    require(sha256(raw) == expected.sha256)
    return raw
```

Apply the same rules to source and destination. Destination creation uses a new
directory, `O_CREAT|O_EXCL|O_NOFOLLOW`, `st_nlink == 1`, `fsync` on files and
directories, and readback verification. Do not trust mode `0444`/directory `0555`
alone against the same owner. Rehash the complete view after every suite and at
finalization to detect post-bootstrap substitution.

### 5. Metadata-absence witnesses

Create the two witnesses from no source content:

```python
fd = os.open(name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o000, dir_fd=parent_fd)
os.ftruncate(fd, declared_logical_size)  # sparse/zero-filled bytes only
os.fsync(fd)
assert os.fstat(fd).st_nlink == 1
```

The closure records only the witness recipe, path, type, and logical size. It must
not claim the historical semantic SHA-256 as the witness hash. Audit policy permits
`lstat`/metadata inspection for the exact scorer call sites and denies every
`open`, content read, mmap, copy, or subprocess inheritance of a witness. The
candidate/custody view has no witnesses.

### 6. Narrow adapters

**Reference-constant adapter.** After authenticating and loading the exact module
bytes, but before preflight/test assertions, verify each old constant equals the
expected historical absolute value and replace only:

- `recovery.CANONICAL_PACE`
- V4/V5/V6 `PACE_REFERENCE`
- V4/V5/V6 `ACCEPTOR_REFERENCE`

Patch both directly loaded modules and the V5/V6 captured runtime module objects.
Each target is manifest-listed and hash-verified. Record module identity, attribute,
before value, after value, and target hash. Do not patch a function or scorer rule.

**Command-record relocation adapter.** Require the exact original source hash and
exact old values, parse strict JSON, and rewrite only these JSON pointers:

- entry command: `/cwd`, `/argv/3`, `/argv/7`
- custody command: `/cwd`, `/argv/3`, `/argv/5`, `/argv/9`

Every rewritten value must be the declared old root or a child of it and must map
to the exact reviewer view target. Reject any other absolute string or changed
field. Canonically serialize, bind source hash + recipe + derived hash in the
closure, and place the derived bytes at the historical expected path.

**V2 child adapter.** Replace only the captured V2 module's `subprocess.run` object
with `controlled_run`. Accept exactly:

```text
[sys.executable, <manifest reference_derivation.py>, "--case", <manifest case>]
```

Map that one call to the detached bootstrap in `reference-child` mode using the
pinned interpreter with `-I -S -B`, an explicit reviewer `cwd`, a minimal explicit
environment, `close_fds=True`, and only a dedicated audit descriptor in
`pass_fds`. Reject shell use, extra argv, another executable, unlisted cases, or
another child. The child authenticates its own required closure before executing
the exact captured reference bytes. Merge its canonical audit record into the
parent transcript. Apply this adapter to direct V2 and V5/V6's captured
`runtime["v2"]` module objects.

### 7. Audit policy and local socket allowance

Install the Python audit hook before any authenticated project code is compiled or
executed. It is a defense and evidence surface only. Allow project reads only for
the current view's openable manifest rows, writes only beneath scratch/state/output,
and subprocess creation only for the exact V2 child bootstrap or separately
approved real candidate/custody boundary. Deny `ctypes`, dynamic extension loading,
unlisted imports, shell execution, environment mutation that changes semantics,
and arbitrary compilation/execution outside captured governed code.

Deny DNS, `connect`, `bind`, `listen`, AF_INET, and AF_INET6. The synthetic pipeline
gets one scoped exception: exactly two `socket.__new__` audit events created by one
`socket.socketpair`, each with AF_UNIX, SOCK_STREAM, protocol 0, no pathname, and no
network operation. The local observed CPython 3.9/macOS trace produced precisely
those two events. Python documents that `socketpair` returns two connected,
non-inheritable sockets and defaults to AF_UNIX where available.

### 8. Exact suite runner and source-unavailable proof

For each historical suite, start a clean child from the detached bootstrap,
authenticate its closure, discover IDs without running tests, compare the canonical
ID list and count, run once, and emit a canonical result containing every ID and
outcome. The parent accepts only the exact expected list with all outcomes success.
It rejects `SystemExit` masking, skips, xfail/xpass, loader errors, duplicates, and
count drift. Rehash the view between suites.

Then prove source independence:

1. Materialize the view into a fresh unrelated temporary root.
2. Make the original run root inaccessible for the controlled replay (rename it in
   a disposable copy/namespace where possible, or enforce OS denial) and confirm an
   explicit `lstat/open` probe of the old path fails.
3. Run all 59 tests and synthetic pipeline only from the view.
4. Require the audit transcript to contain zero access attempts to the source root,
   zero undeclared reads/writes, only declared children, and only the scoped local
   socket events.
5. Rehash and verify both the view and canonical result transcript.

An audit denial alone is weaker than actually making the source unavailable; use
both. `chroot` may be an optional independent strengthening when privileges permit,
but is not the portable primary design on macOS.

## Trust roots

1. Detached bootstrap bytes and independently stored expected SHA-256.
2. Detached expected closure-root SHA-256 and expected V9 root SHA-256.
3. The pinned CPython executable and its standard library, including recorded
   version/platform/hash identities.
4. Kernel filesystem descriptor/stat semantics and AF_UNIX socketpair semantics.
5. The fresh-view packager/reviewer that creates and attests destinations.
6. Separate human authorization for real candidate/custody execution; reviewer
   regression success does not grant that authorization.

The project-local root JSON, Python audit transcript, and test exit codes are
evidence, not independent trust roots.

## Threat model and constraints

Covered:

- project-file tampering, stale/missing/extra manifest members;
- symlink and hard-link substitution, parent-component redirection, and many
  pathname TOCTOU attacks;
- undeclared file access, source-root fallback, environment-dependent imports,
  arbitrary child processes, and ordinary Python socket/network attempts;
- accidental exposure of historical fixtures to candidate/custody code;
- hidden test weakening through skips, renamed tests, or exit-code-only wrappers;
- semantic-content inclusion disguised as an Oracle metadata dependency.

Not covered/claimed:

- compromised CPython, standard library, kernel, packager, or detached-hash store;
- arbitrary hostile native code, `ctypes`, injected dynamic extensions, debugger
  attachment, or another same-UID process with filesystem/process-control access;
- confidentiality against an administrator or process with broader OS authority;
- semantic equivalence of deterministically relocated command records to their
  original byte strings. Their derivation is authenticated, not byte-identical.

The current observed runtime is Apple CPython 3.9.6 on arm64 macOS. Implementation
must pin and re-check the actual target runtime rather than assuming this remains
true.

## Rejected alternatives

| Alternative | Why rejected |
|---|---|
| Copy semantic files but make them unreadable | Still includes prohibited semantic bytes; mode bits are not confidentiality against the owner. |
| Literal absence at both semantic paths | Fails exact recovery/V2 `lstat` regular-file and size assertions. Only a governed nonsemantic witness reconciles the exact tests. |
| Global `Path`/VFS monkeypatch | Too broad; silently changes `resolve`, `lstat`, imports, inspection, and unrelated scorer behavior. |
| Transform historical Python/test source | Violates exact-byte execution and can weaken assertions. Narrow post-load constant/call-boundary adapters preserve the source bytes. |
| Keep original command JSON at expected paths | Old absolute roots fail relocation. A source-hash-bound deterministic derived view is required. |
| One combined reviewer/candidate tree | Lets real candidate/custody enumerate or open historical fixtures and witnesses. |
| Audit hooks as the sandbox | Python explicitly says Python-level hooks are bypassable by malicious code. |
| Runtime trace as closure discovery | Misses unexercised branches and turns an allowlist into an observed subset. Static exact manifests remain authoritative. |
| Trust nested roots without a detached parent | A member and its same-tree manifest can be replaced together. |
| Copy only seven test scripts | Misses scorer modules, nested roots, reference code, visible corpus, historical package, command evidence, and V2 child execution. |
| Pre-freeze attestation without replay | Does not prove source-unavailable execution and cannot detect post-freeze substitution. |
| `chroot`/OS namespace as the only solution | Requires platform-specific privileges and does not solve manifest completeness or exact test accounting. Useful only as an extra layer. |
| Weaken or remove historical tests | Destroys the claimed regression contract rather than closing dependencies. |

## Mutation matrix

Each mutation is required to fail before any success claim:

| Mutation | Expected failure/evidence |
|---|---|
| Bootstrap byte changed | Detached bootstrap hash failure before project code. |
| Closure root changed with members | Detached closure hash failure. |
| V9 member added/removed/duplicated | Exact `18 + root` denominator failure. |
| Historical test renamed/deleted/added | Exact test-ID/count mismatch before execution. |
| Test skip/xfail/xpass/error masked by exit 0 | Canonical per-ID outcome rejection. |
| Nested root row omitted or duplicated | Static sorted/unique denominator failure. |
| Final member replaced by symlink | `O_NOFOLLOW`/regular-file failure. |
| Parent directory replaced by symlink | Descriptor-walk `O_DIRECTORY|O_NOFOLLOW` failure. |
| Member hard-linked | `st_nlink != 1` failure. |
| File swapped/truncated during read | Pre/post identity, timestamps, size, or hash failure. |
| Destination preexists | `O_EXCL` failure. |
| Post-suite file mutation | Inter-suite/final root rehash failure. |
| Witness is missing, symlinked, wrong type, or wrong logical size | Exact metadata gate failure. |
| Witness content open/read attempted | Audit abort naming witness and call phase. |
| Semantic source bytes used to create witness | Packager recipe/provenance failure; witness is generated only by `ftruncate`. |
| Original command source hash differs | Transformation refuses to run. |
| Nonallowlisted command JSON field changes | Canonical structural diff failure. |
| Relocated command path escapes reviewer view | Safe-relative/mapping failure. |
| Old reference constant differs | Adapter precondition failure. |
| New PACE/acceptor target hash differs | Target closure hash failure. |
| V2 child has extra argv, wrong case, executable, cwd, or environment | Controlled child adapter rejection. |
| V2 child omits audit descriptor/result | Parent rejects missing child transcript. |
| Any other subprocess starts | Audit/adapter abort on `subprocess.Popen`. |
| Parent environment injects `PYTHONPATH` or user site | `-I -S` plus explicit-env evidence; no inherited value. |
| `.pyc` write attempted | `-B` and write allowlist rejection. |
| AF_INET/AF_INET6 socket created | Audit abort. |
| `connect`, `bind`, `listen`, or DNS attempted | Audit abort. |
| More/fewer than two scoped AF_UNIX socket creations | Socket event-count mismatch. |
| Candidate process reads reviewer/development path | Path absent from candidate view and audit abort. |
| Reviewer process reaches original source root | Source-unavailable probe/replay failure. |
| Scratch write uses `..`, symlink, or absolute escape | Descriptor-relative write policy failure. |
| Child stdout is noncanonical/malformed or record ID differs | Strict child-result parser failure. |
| Audit hook missing or added too late | Bootstrap self-test/order attestation failure. |

## `not_found`

- No architecture can simultaneously preserve literal absence at the two semantic
  paths and pass the exact current metadata assertions. A policy choice approving
  nonsemantic witnesses is required.
- No architecture can keep the old command bytes at their expected paths and also
  satisfy the scorer's relocated `Path.resolve()` checks. An authenticated derived
  command view is required.
- No stdlib-only, unprivileged, portable CPython mechanism on the observed macOS
  runtime provides hostile same-UID native-code isolation. Audit hooks do not fill
  that gap.
- The current V9 regression wrapper does not prove exact test IDs/outcomes or a
  transitive dependency closure; it proves only seven child exit codes.
- The current V9 root does not bind the historical/transitive dependency views.
- No existing source-unavailable replay evidence or detached bootstrap trust root
  was found in the inspected architecture surface.

## Implementation acceptance conditions

Implementation is justified only if all of these become explicit plan/spec gates:

1. Approve `metadata_absence_witness` as distinct from prohibited semantic content.
2. Approve source-hash-bound deterministic transformation of the two command
   records, while leaving all test/scorer Python bytes exact.
3. Pin detached bootstrap, closure root, V9 root, interpreter, and platform.
4. Build and authenticate separate reviewer and candidate/custody views.
5. Enforce exact 59-test IDs/outcomes, not exit codes alone.
6. Implement descriptor-walk, hard-link rejection, pre/post stability, fresh-copy
   verification, and inter-suite rehashing.
7. Implement the three narrow adapters and reject all other substitutions.
8. Treat audit hooks as invariant/evidence controls under an authenticated-code
   threat model, never as the hostile-code sandbox.
9. Prove a replay with the original source unavailable and zero source-root access.
10. Pass the complete mutation matrix.

## Sources opened

### Local primary sources

- [V9 repair specification](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/specs/v9-executable-dependency-closure-repair-spec.md)
- [V9 freeze evaluator](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v9/freeze_evaluator.py)
- [V9 historical regression wrapper](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v9/test_historical_scorer_regressions.py)
- [V9 approved execution wrapper](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v9/approved_execution_wrapper.py)
- [V9 synthetic pipeline](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v9/synthetic_v9_pipeline.py)
- [Recovery scorer and test](<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v4/recovery/recovery_scorer.py)
- Exact V1-V6 scorer/test pairs under
  `<HOME>/Claude/loop/loop-team/runs/2026-07-14_executable-audit-pace/evaluation_v4/oracle_v2_scoring*`.
- Exact V4/V7 public roots, visible/nonsemantic corpus manifests, command/result
  records, and historical package manifest under the same run root.

Dispatch restrictions were observed: no held-out dataset, semantic Oracle payload,
key material, arm-output member, or review/release/status log was opened.

### Official platform sources

- [Python 3.9 command-line options](https://docs.python.org/3.9/using/cmdline.html):
  `-I`, `-S`, and `-B` startup behavior.
- [Python 3.9 `os` documentation](https://docs.python.org/3.9/library/os.html):
  descriptor-relative operations, `O_NOFOLLOW`, `O_DIRECTORY`, `fstat`, inode,
  device, link count, size, and non-inheritable descriptors.
- [Python 3.9 `subprocess` documentation](https://docs.python.org/3.9/library/subprocess.html#popen-constructor):
  `cwd`, explicit `env`, `close_fds`, POSIX `pass_fds`, and the
  `subprocess.Popen` audit event.
- [Python 3.9 `socket.socketpair`](https://docs.python.org/3.9/library/socket.html#socket.socketpair):
  connected non-inheritable pair and AF_UNIX default when available; the socket
  constructor raises `socket.__new__` audit events.
- [Python 3.9 `compile` and `exec`](https://docs.python.org/3.9/library/functions.html):
  governed captured-byte execution and audit events.
- [Python 3.12 `sys.addaudithook`](https://docs.python.org/3.12/library/sys.html#sys.addaudithook):
  audit hooks can log/abort but are explicitly not a sandbox; malicious code can
  bypass Python-level hooks, and security-sensitive hooks require stronger runtime
  control.

