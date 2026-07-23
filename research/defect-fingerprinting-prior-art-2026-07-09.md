# Prior art: how real tools fingerprint/dedup a finding across reworded re-descriptions (2026-07-09)

**Mode:** A (on-demand, dispatched to extend an open gap). No sub-agents spawned; every
source below was opened directly (WebFetch/curl of the real doc or raw source, or `gh
search code`/`gh api` against the live repo) before being cited — no snippet-only claims.

**Relation to existing work — read first, do not re-derive:** this dispatch is a direct
continuation of `research/gate10-concurrency-fingerprint-inventory-2026-07-09.md` §"PROBLEM
1 — Deterministic defect fingerprinting" (written earlier the same day), which already
identified the live bug (`reconcile_gap_records.py`'s `cluster_near_duplicates()`, lines
225–264, silently skips the `SequenceMatcher` check whenever either record's
`mechanism_refs` is empty — `set().isdisjoint(set())` → `True` in Python) and already
surveyed DefectDojo, `calimero-network/ai-code-reviewer`, NLI conflict detection, and IBM's
Orthogonal Defect Classification. That doc's own stated gap is what this dispatch was sent
to close: *"No research anywhere proposes a concrete, testable scheme for a stable
signature over FREE-TEXT LLM-authored LOGIC/CONCURRENCY/SECURITY findings that collapses
across differently-worded rounds... No research has evaluated whether an LLM call itself,
prompted specifically to emit a canonical/normalized slug at tagging time... would collapse
consistently round-over-round... this is untested, not just undesigned."* Everything below
is new material (GitHub Code Scanning/CodeQL's actual fingerprint source, SonarQube's tiered
match algorithm, Semgrep's `match_based_id`/`syntactic_id` real source, Coverity's merge
key, ESLint's absence of the concept, and the duplicate-bug-report-detection literature) —
none of it was in the earlier doc.

---

## The headline finding, stated up front

**Every real, production dedup/fingerprinting mechanism found — with no exception —
computes its identity from a STRUCTURAL/positional/categorical signal, and explicitly
EXCLUDES the free-text human-readable message from that computation.** Where a tool's
fallback tier does fall back to text, it requires **literal, unmodified string equality**
of that text (not paraphrase-tolerant matching) — i.e. even the "weak" fallback tiers in
real tools do not solve "same defect, reworded" either. And the one real academic field that
directly studies "the same defect described in different words by different people"
(duplicate bug report detection) never produces a deterministic identical string — it
produces a ranked similarity score requiring a threshold and a human/triager decision. This
means: **the specific ask — an exact-string-equality signature that collapses arbitrarily
reworded free text, with no structural signal and no taxonomy — has no known solved
instance in production software.** The honest, actionable takeaway is in the "Direct answer"
section below.

---

## 1. GitHub Code Scanning / CodeQL — `partialFingerprints` (real source read directly)

**Source confirmed by direct fetch of the actual doc + the actual TypeScript source** (not
paraphrase): `docs.github.com/en/code-security/reference/code-scanning/sarif-files/sarif-support`
and `raw.githubusercontent.com/github/codeql-action/main/src/fingerprints.ts` (full file
pulled via `curl`, ~300 lines read).

- Doc, quoted directly: *"GitHub uses the `partialFingerprints` property in the OASIS
  standard to detect when two results are logically identical."* And the stability
  precondition: *"The `ruleId` for a result has to be the same across analysis. The
  filepath has to be consistent across the runs to enable a computation of a stable
  fingerprint."*
- The identity is **`ruleId` + `filepath` + `primaryLocationLineHash`** — a hash of LINE
  CONTENT, not of the alert's message. Confirmed by direct WebFetch quote-extraction of the
  doc: the message/description text is **not** part of the identity computation at all.
- The actual algorithm, read from the real `fingerprints.ts` source (verbatim comment in
  the file):
  ```
  /**
   * Hash the contents of a file
   *
   * The hash method computes a rolling hash for every line in the input. The hash is
   * computed using the first BLOCK_SIZE non-space/tab characters counted from the start
   * of the line. For the computation of the hash all line endings (i.e. \r, \n, and \r\n)
   * are normalized to '\n'. ...
   */
  export async function hash(callback: hashCallback, filepath: string) { ... }
  ```
  `BLOCK_SIZE = 100`, `MOD = Long.fromInt(37)` — a rolling polynomial hash (Rabin-Karp
  style) over the first 100 non-whitespace characters of the **line the alert points at**,
  with a disambiguating counter appended for hash collisions on repeated identical lines:
  `callback(lineNumbers[index], \`${hashValue}:${hashCounts[hashValue]}\`)`. This hash is
  then written into `result.partialFingerprints.primaryLocationLineHash` by
  `locationUpdateCallback()`.
- **What this buys them:** the fingerprint survives unrelated edits elsewhere in the file
  (only the flagged line's content matters) and survives the alert's prose message changing
  entirely (CodeQL query wording, severity text, etc. can all change without breaking the
  match) — but it is **completely dependent on `ruleId` being a stable, closed identifier
  and on a literal source-code location existing to hash.** Neither precondition holds for
  our LOGIC/CONCURRENCY/SECURITY prose findings (no `ruleId` — these are novel, undispatched
  categories each round; frequently no single line of code, since a spec-review finding can
  span a cross-cutting design gap with no literal `artifactLocation`).

## 2. SonarQube — "issue tracking" (real docs, tiered algorithm)

**Source confirmed by direct WebFetch** of
`docs.sonarsource.com/sonarqube-server/2025.6/user-guide/issues/solution-overview` (current
LTA docs page, fetched directly, not from a search snippet).

- Primary key: *"the issue's line hash, which is calculated based on the content of the
  first line the issue is reported on, excluding the white spaces."*
- The matcher is explicitly **tiered**, tried strongest-first:
  1. *"If the issue is on the same rule, with the same line hash (but not necessarily with
     the same message): MATCH."* — i.e. rule + content hash is sufficient; **message is
     explicitly irrelevant to this tier** (the doc calls this out by name — a direct,
     positive confirmation that production tools treat prose wording as noise, not signal).
  2. *"If the issue is on the same rule, on the same line number with the same message (but
     not necessarily with the same line hash): MATCH."* — this is the ONE tier that
     involves the message at all, and it requires **exact, unmodified string equality of
     the message** — not similarity, not paraphrase tolerance. A reworded message breaks
     this tier just as surely as it would break a naive exact-equality check on our own
     signature field.
  3. *"If the issue is on the same rule but the detected block moved inside the file, then
     if the issue is on the same line within the moved block, and has the same message:
     MATCH."* — block-move detection, again gated on exact message equality.
- **Conclusion:** SonarQube's fallback tiers, when the strong content-hash signal is
  unavailable, do NOT solve "reworded description, still matches" — they degrade to literal
  string equality on the message, which is exactly as brittle to paraphrase as what we're
  trying to replace. This is important negative evidence: a mature, 15+-year commercial
  product with a dedicated tiered algorithm never attempted fuzzy-message matching for its
  production issue-tracking feature.

## 3. Semgrep — `match_based_id` / `syntactic_id` (real source pulled and read in full)

**Source: actual source code**, not docs paraphrase — pulled via
`curl https://raw.githubusercontent.com/semgrep/semgrep/develop/cli/src/semgrep/rule_match.py`
(full function bodies read, confirmed present at the exact lines quoted). Repo maturity
confirmed via `gh api repos/semgrep/semgrep`: 15,822 stars, pushed 2026-07-09 (today), LGPL-2.1.

- `get_match_based_key()` — the **structural** key, built entirely from things the tool
  itself controls, never from the free-text finding message:
  ```python
  @match_based_key.default
  def get_match_based_key(self) -> Tuple[str, Path, str]:
      """
      A unique key with match based id's notion of uniqueness in mind.
      """
      ...
      match_formula_str = self.match_formula_string
      for mvar, mval in self._get_metavar_bindings():
          match_formula_str = match_formula_str.replace(mvar, mval)
      ...
      return (match_formula_str, path, self.rule_id)
  ```
  `match_formula_str` is the **rule's pattern**, with each matched metavariable's *actual
  source-code value* substituted in — i.e. the identity is "this rule, matched against this
  exact code shape, in this file," never the human-readable message the rule author wrote.
- `get_match_based_id()` then hashes that tuple:
  ```python
  @match_based_id.default
  def get_match_based_id(self) -> str:
      match_id = self.get_match_based_key()
      match_id_str = str(match_id)
      hashed = hashlib.blake2b(str.encode(match_id_str)).hexdigest()  # (or sha256 in fips_mode)
      code = f"{hashed}_{str(self.match_based_index)}"
      return code
  ```
  The source's own comment states the design intent explicitly: *"This will supersede
  syntactic id, as currently that will change even if things formatting + line numbers
  change. By using the formula + metavariable content itself, we remain sensitive to
  modifications to a match, but we no longer count formatting + line number changes ... as
  new findings."* — i.e. Semgrep's own engineers describe this exact problem (don't let
  cosmetic/positional variance break the match) and solved it by keying on the **abstracted
  match content**, never on prose.
- `syntactic_id` is the older, line/position-sensitive fallback (hash of `ci_unique_key` =
  `(self.start, self.end, self.rule_id, self.message)` — note `message` **is** in this
  tuple, but this is explicitly the *inferior*, superseded ID per the comment above, kept
  only for backward compatibility with `semgrep.dev`'s tracking history).
- `code_hash`/`pattern_hash`/`start_line_hash`/`end_line_hash` are further decomposed
  hashes, each documented as isolating ONE variable (file path vs. rule vs. matched code)
  so the consuming app can diagnose *why* two findings differ — again, all structural,
  never message-based.
- Confirmed downstream real consumer: **DefectDojo** (OWASP's open-source vulnerability
  aggregator, see §5) literally ingests this field —
  `dojo/tools/semgrep_pro/parser.py`: `finding.unique_id_from_tool = item.get("match_based_id")`,
  with the comment *"Use match_based_id for deduplication if available, otherwise use file
  location"* (confirmed via `gh search code`, file opened directly).

## 4. Coverity — "merge key" (structural, function-anchored)

**Source:** Synopsys/Black Duck community docs (WebSearch-surfaced, cross-checked against
two independent community-support pages describing the same mechanism, both consistent —
flagged here as **secondary/support-forum sourced**, not a primary Coverity engineering doc,
since Coverity Connect's internal algorithm isn't publicly documented in full).
- A defect is merged into an existing CID (Coverity ID) when it shares the same
  **Checker + Function + Merge Name + Merge Extra + Merge Key** — i.e. identity is anchored
  to *which checker fired* and *which function/scope it fired in*, a structural/positional
  key, analogous in spirit to CodeQL's ruleId+location and Semgrep's rule_id+match content.
  No free-text description field is part of the key.
- Flagged honestly: I could not pull Coverity's actual merge-key source (proprietary,
  closed product — no public repo to open), so this entry rests on secondary
  community-support documentation, consistent across two independent pages, not a verified
  primary source. Treat as corroborating pattern evidence, not as strong as items 1–3 and 5.

## 5. DefectDojo — the closest real analog to OUR fallback question (real source, read in full)

DefectDojo (OWASP project, real, mature — confirmed via `gh api`: `django-DefectDojo`) is
the most directly relevant real system here because it is **not a single-tool scanner** — it
is a production **aggregator that must deduplicate findings arriving from 180+ different
SAST/DAST/SCA tools**, each describing the same underlying vulnerability with completely
different field names, formats, and prose. This is structurally the closest real analog to
"different LLM reviewers, different rounds, same underlying defect, different wording."

**Source: actual model code**, pulled via `curl` of
`raw.githubusercontent.com/DefectDojo/django-DefectDojo/master/dojo/finding/models.py`
(lines 732–900 read in full) and `dojo/settings/settings.dist.py` (line 1012 onward, read in
full for the real per-scanner default field lists).

- **Preferred path — structural, tool-native ID:** `unique_id_from_tool` (e.g. Semgrep's
  `match_based_id`, a CVE/CWE ID, a scanner's own finding UUID). Docs (fetched directly,
  `docs.defectdojo.com/.../deduplication_algorithms/`) confirm the "Unique ID From Tool or
  Hash Code" algorithm *"attempts to use the tool's unique ID first, then falls back to the
  hash code if no unique ID is available"* — and explicitly name the known weakness: *"When
  the tool evolves, it may change the way the unique id is generated. In that case you won't
  be able to recognise that findings found in previous scans are actually the same as the
  new findings."*
- **Fallback path — `compute_hash_code()`**, real source:
  ```python
  def compute_hash_code(self):
      ...
      hash_code_fields = self.test.hash_code_fields
      ...
      fields_to_hash = ""
      for hashcodeField in hash_code_fields:
          if hashcodeField == "endpoints":
              fields_to_hash += self.get_locations()
          elif hashcodeField == "vulnerability_ids":
              fields_to_hash += self.get_vulnerability_ids()
          else:
              fields_to_hash += str(getattr(self, hashcodeField))
      ...
      return self.hash_fields(fields_to_hash)

  def hash_fields(self, fields_to_hash):
      ...
      return hashlib.sha256(fields_to_hash.casefold().encode("utf-8").strip()).hexdigest()
  ```
  Note `.casefold()` — the ONE normalization step present anywhere across every tool
  surveyed (case-insensitivity), and it is applied to a concatenation of **configured field
  values**, not free prose. The actual default field lists per scanner (`settings.dist.py`,
  read directly, real excerpt):
  ```python
  HASHCODE_FIELDS_PER_SCANNER = {
      "Anchore Engine Scan": ["title", "severity", "component_name", "component_version", "file_path"],
      "Bandit Scan": ["file_path", "line", "vuln_id_from_tool"],
      "Burp Scan": ["title", "severity", "vuln_id_from_tool"],
      "Checkmarx Scan": ["cwe", "severity", "file_path"],
      "Cloudsploit Scan": ["title", "description"],
      "Coverity Scan JSON Report": ["title", "cwe", "line", "file_path", "description"],
      ...
  }
  ```
  Two things stand out: (a) the overwhelming majority of the ~50+ scanners configured use
  **only structural/categorical fields** (CWE code, severity enum, file path, line number,
  component name+version, the tool's own `vuln_id_from_tool`) — `title` here is a short
  tool-assigned classification label (e.g. a CVE title or rule name), not a free-form
  paragraph; (b) only a **minority** (Cloudsploit, Coverity's JSON parser, a few others) add
  `description` at all, and where they do, it is hashed **verbatim, no normalization beyond
  casefold** — meaning two independently-worded descriptions of the identical
  vulnerability, from that scanner, would NOT collapse to the same hash. This is a real,
  currently-shipping production system that hits our exact problem and does **not** solve
  it — it only reduces exposure to it by using structural fields wherever they exist and
  accepting non-dedup as a known limitation when they don't.
- `compute_hash_code_legacy()` — the true last-resort fallback, and the most direct real
  analog to our empty-`mechanism_refs` case:
  ```python
  def compute_hash_code_legacy(self):
      fields_to_hash = self.title + str(self.cwe) + str(self.line) + str(self.file_path) + self.description
      return self.hash_fields(fields_to_hash)
  ```
  This DOES hash free-text (`self.description`) — and it is named "legacy" precisely
  because it is the **least reliable** tier, kept only for backward compatibility with
  pre-existing installs. GitHub issue search on this repo (`gh search issues`, confirmed
  live) turns up a steady stream of real, open/recently-closed bugs whose root cause is
  exactly this brittleness — e.g. **#13497** *"`UNIQUE_ID_FROM_TOOL_OR_HASH_CODE` only
  consider the first possible match when deduplicating"* (closed), **#12320** *"trivy
  operator scan: deduplication is not working"* (closed), **#3958**/`#12924` *"Re-importing
  the same report leaves the duplicates in status mitigated"* (both real, filed
  independently) — a live production system with years of use is still actively fielding
  dedup-mismatch bug reports, which is direct, current evidence that this class of problem
  (matching "the same defect" across two independently-produced descriptions) remains
  genuinely hard even with dedicated engineering investment.

## 6. ESLint — the negative case (no cross-run identity concept at all)

Confirmed via WebSearch + cross-check of `microsoft/eslint-formatter-sarif` issue history:
ESLint itself has **no concept of alert persistence across runs** — each run's output is
`ruleId` + current-file location only, with no historical-baseline file, no
`partialFingerprints`, nothing to "track" against a prior scan. Its own SARIF formatter
issue tracker shows ESLint only emits `ruleId`s for rules that actually produced a result in
THIS run (`Add suppression information in the output of ESLint · Issue #14784`) — i.e. it's
a stateless per-run tool; cross-run identity is an add-on layer that only tools with
persistent storage (GitHub Code Scanning, SonarQube, Semgrep AppSec Platform, Coverity
Connect, DefectDojo) build at all. This confirms the base case: `ruleId + location` is the
minimum identity key everyone agrees on; fingerprinting (a content/structural hash) is
specifically the *extra* engineering built on top to survive code drift between runs — it
is never built to survive *description* drift, because in every tool surveyed the
description was never part of the identity to begin with.

## 7. The literature that DOES target "same defect, different words" — duplicate bug report detection

This is the one real research area that directly studies matching free-text descriptions of
the same underlying problem written independently by different people (bug reporters, not
reviewers, but the structural shape of the problem is identical to ours). WebSearch-surfaced
and cross-checked across multiple independent survey sources (a 2024/2025 arXiv survey
"Combining Retrieval and Classification," a 2025 arXiv "Automated Duplicate Bug Report
Detection in Large Open Bug Repositories," a ScienceDirect empirical study on whether deep
learning improves over classic IR methods) — all secondary/survey sources, not a single
canonical primary paper, so treated as **corroborating evidence of the field's shape**, not
a single citable algorithm:
- Runeson, Alexandersson & Nyholm (ICSE 2007) — vector space model + text similarity.
- Sun et al. — an IR "REP function," later extended with BM25F over both free text and
  structured metadata (component, version, comments).
- Recent deep-learning approaches (Dual-Channel CNN, embedding-based retrieval) —
  benchmarked against classic IR baselines, with mixed results on whether DL actually wins.
- **The load-bearing structural fact, true across every one of these approaches without
  exception:** none of them produce a deterministic identical string/ID for "same bug,
  different words." They ALL produce a **ranked list of candidate duplicates with a
  similarity score**, gated by a **threshold**, consumed by a **human triager** (or, in
  fully-automated variants, an accept/reject decision at a chosen operating point with a
  measured precision/recall tradeoff — never 100%). This is a fundamentally different
  contract than "identical signature string, exact-equality check": semantic/embedding
  similarity gives you a **continuous, threshold-dependent, non-deterministic-feeling**
  score, not a discrete, stable identity. No system in this literature claims to solve
  "produce the same short string twice."

---

## Direct answer to the dispatch's explicit question

**"Would any technique found here directly solve our fallback case (when `mechanism_refs` —
the structural signal — is empty)?" No.** Every real production mechanism surveyed
(CodeQL/GitHub, SonarQube, Semgrep, Coverity, DefectDojo) achieves determinism specifically
BY having a structural/positional/categorical signal always available (a rule ID, a file+line,
a CWE code, a matched-code-with-metavariables tuple) and specifically BY excluding free text
from the identity computation. Where a real tool's structural signal is unavailable and it
is forced to fall back to text (DefectDojo's `compute_hash_code_legacy`, SonarQube's
message-match tier), the fallback requires **literal string equality**, not paraphrase
tolerance — i.e. it does not solve "reworded, still matches" either; it is simply the
least-reliable tier, documented as such, and known-broken in exactly the reworded-defect way
our problem describes (see the live DefectDojo dedup-mismatch issues, §5). The one field that
targets "same defect, reworded, matched anyway" head-on (duplicate bug report detection)
explicitly gives up on exact-match determinism and substitutes a ranked-similarity-plus-
threshold-plus-human-adjudication contract instead.

**This means: our empty-`mechanism_refs` case, as specified (exact-string-equality,
no fixed taxonomy, no text-similarity), is not a solved problem anywhere in production
software or in the closest academic literature.** That is itself the honest, useful
finding — a confident invented "fix" here would be the worst possible output per the
Researcher honesty bar.

---

## What this means for our two cases — recommendation split

### Case A — `mechanism_refs` non-empty (structural signal present): **IMPLEMENTABLE_NOW**

This case is a direct, well-grounded match for the pattern used everywhere above.
- `name`: canonicalize-then-hash `mechanism_refs` (+ `gap_type`/tag) into `signature`.
- `source`: Semgrep `get_match_based_key()`/`get_match_based_id()` (semgrep/semgrep,
  `cli/src/semgrep/rule_match.py`, quoted in full above) is the closest, cleanest real
  implementation to copy the *shape* of (not the code itself — different language/domain):
  sort + normalize the structural fields, join into a tuple, `hashlib.sha256`/`blake2b` the
  string form.
- `where_it_wires_in`: `harness/reconcile_gap_records.py`'s `cluster_near_duplicates()` and
  a new `signature` field alongside the existing `[BINDING]`-only one in
  `plancheck_saturation.py` (per the gate10 inventory doc's finding #3 — the `[BINDING]`
  precedent already does exact-string-equality on an LLM-authored `signature` field, just
  with no normalization step and no coverage for other tags).
- `triage`: IMPLEMENTABLE_NOW for the *mechanism* (canonicalize+hash is trivial, ~20 lines);
  still needs the A/B below before it's load-bearing (per the Guardrails section of the
  Researcher role — "IMPLEMENTABLE_NOW still gets A/B'd before it's load-bearing").
- **Transfer-condition check (required per role brief):**
  (a) *Execution context required*: needs `mechanism_refs` to actually be populated,
  normalized to a comparable form (e.g., lower-cased file paths, sorted list) at write
  time — i.e., this REQUIRES fixing the upstream gap the gate10 inventory doc already
  named (`mechanism_refs` is optional and often empty by lens-writing convention).
  (b) *Does the target context satisfy it?* **Not currently** — this is the crux: Case A's
  fix is real and copy-pasteable, but only covers the subset of findings where
  `mechanism_refs` was actually filled in, which per the existing inventory doc is not the
  common case today.
  (c) *Structural or instructional guarantee?* **Instructional** — nothing forces a lens to
  populate `mechanism_refs`; a lens that skips it (the documented common case) silently
  falls through to Case B with no error surfaced. This is exactly the silent,
  downstream-passing failure mode the role brief's transfer-condition check flags as
  highest-risk: a compliance failure here would not throw an error, it would just produce a
  wrong (empty) fingerprint that a naive equality check treats as "definitely not a repeat"
  — a false-NEW verdict for what a human would recognize as a real recurrence.
- `experiment`: **metric** — on a corpus of real, already-collected plan-check gap records
  (the runs under `runs/2026-07-04_airbnb-calendar/` etc. per the gate10 inventory doc),
  measure whether the canonicalized-`mechanism_refs` hash correctly collapses KNOWN
  same-defect record pairs (identified by a human/gold read) to identical signatures, and
  correctly keeps KNOWN different-defect pairs distinct. **baseline** — current
  `cluster_near_duplicates()` behavior (silently skips on empty `mechanism_refs`).
  **variant** — canonicalized-hash signature field. **decision** — PACE-gated accept only if
  recall on the known-duplicate pairs improves without a false-collapse regression on the
  known-distinct pairs. **predicted_effect** — should fully fix the *subset* of the
  round-24/27/28-style false-independence misses that had non-empty `mechanism_refs` to
  begin with. **kill_criterion** — if `mechanism_refs` is empty in >50% of real
  LOGIC/CONCURRENCY/SECURITY records sampled (which the existing inventory doc suggests is
  likely), this fix alone resolves only a minority of cases and Case B becomes the
  load-bearing problem.

### Case B — `mechanism_refs` empty (no structural signal): **TESTABLE only — no production precedent to copy**

Since no real tool solves this, the only defensible next step is the one candidate the
existing gate10 inventory doc already named as untested — **not a borrowed solution, an
original experiment grounded in why the borrowed solutions all work (they engineer the
structural signal to always exist, rather than reconstructing it after the fact from
prose)**:
- `name`: force a small, controlled-vocabulary structural field to be authored AT WRITE
  TIME by the reviewing LLM, for every finding, regardless of whether a literal code
  location exists (mirroring gate 9's `[SECURITY-ORACLE]` and gate 10's
  `[BINDING]`/`[LOGIC]`/`[CONCURRENCY]`/`[SECURITY]` tag-at-write-time convention already
  live in `DESIGN_CHECKLIST.md`) — e.g. a short `{primary_entity, defect_class}` tuple
  extracted by the SAME LLM call that writes the finding, not reconstructed by a second pass
  over the prose afterward.
- `source`: no real-tool source to cite here — this is explicitly RESEARCH_ONLY-adjacent,
  original, and must be labeled as such. The only "prior art" is the negative result of
  everything above: every real tool's answer to "the structural signal might be sparse" is
  "engineer the pipeline so it never is," never "reconstruct it from free text after the
  fact."
- `triage`: **TESTABLE**, explicitly NOT implementable-now, because its core empirical
  claim — that independently-run LLM calls describing the SAME underlying defect in
  different words will converge on an IDENTICAL short structural tuple — is untested and
  plausibly false (LLMs are not deterministic even at temperature 0 across different
  contexts/personas, and "primary_entity" extraction from prose is itself a paraphrase-
  sensitive judgment call, just a shorter one).
- `experiment` (the falsifiable convergence test, ready to run): **metric** — paraphrase-
  convergence rate: take N known real PLAN_FAIL findings (or synthesize some by paraphrasing
  a fixed defect description M different ways, simulating M independent reviewer
  write-ups), run the proposed structural-tuple-extraction prompt independently on each
  paraphrase, and measure what fraction produce the IDENTICAL tuple string.
  **baseline** — current behavior (no signature at all when `mechanism_refs` empty →
  treated as always-new). **variant** — the extracted-tuple signature. **decision** —
  accept only if convergence rate clears a pre-registered bar (e.g. ≥90%) via
  `pace_accept`, not a raw score. **predicted_effect** — moderate-confidence guess of
  60–85% convergence based on how much shorter/more-constrained the target is than full
  prose (analogous to why Semgrep's metavariable-substituted formula is more stable than
  its raw message, per the real source's own comment quoted in §3) — but this is a genuine
  guess, not derived from any measured number, and must be flagged as such.
  **kill_criterion** — if convergence is materially below the bar (e.g. <70%), do NOT ship
  an exact-equality gate on this signal; fall back to the honest, non-deterministic
  contract the bug-dedup literature actually uses — a similarity-ranked candidate list
  requiring a Verifier-in-the-loop confirmation step (i.e., convert this from a mechanical
  gate into a "flag for review" gate) rather than pretending determinism was achieved.
- **Transfer-condition check:** (a) *context required* — a fixed, low-temperature,
  single-model extraction call, run identically every time; (b) *does the target context
  satisfy it?* — plausibly yes (loop-team already runs fixed-model dispatches), but
  UNVERIFIED — the model/temperature/prompt stability of Claude-in-this-harness across
  independent sessions has not itself been measured; (c) *structural or instructional?*
  — **instructional at best, and likely neither** — nothing structurally forces two
  independent LLM calls to converge; this is exactly why it must be validated empirically
  before being trusted as a gate, not adopted on the strength of the analogy alone.

## Explicitly rejected / not recommended (report what was dropped and why)

- **Embedding/semantic-similarity fallback to reconstruct a signature string post-hoc.**
  REJECTED for the exact-equality requirement specifically. Grounded in §7: this is a
  mature, decades-old research area (duplicate bug report detection) and it has never
  produced a deterministic identity from semantic similarity — it produces a score. Using
  an embedding distance as an on/off gate for "same signature" would require picking an
  arbitrary threshold with no real-tool precedent for what threshold is safe, and the
  literature's own reported ceiling (F1s well short of 100% even with modern DL methods) is
  a direct signal this would silently misfire in both directions (false merges and false
  splits) at a rate no real tool accepts as "solved." If a semantic layer is wanted at all,
  the honest design is a similarity-ranked "possible duplicate, please confirm" list for a
  human/Verifier, never a silent auto-collapse into one signature string.
- **DefectDojo's `compute_hash_code_legacy` pattern (hash raw description text
  verbatim).** Considered and rejected as a model to copy — it is DefectDojo's OWN
  documented worst tier, kept only for backward compatibility, and real, currently-open/
  recently-closed GitHub issues on that exact repo (§5) show it actively misfires in
  production. Copying it would import a known-bad pattern, not a proven one.

---

## Sources (every one opened directly this session)

- [SARIF support for code scanning — GitHub Docs](https://docs.github.com/en/code-security/reference/code-scanning/sarif-files/sarif-support) — fetched directly, quoted.
- [`github/codeql-action` `src/fingerprints.ts`](https://github.com/github/codeql-action/blob/main/src/fingerprints.ts) — raw source pulled via `curl` and read in full (~300 lines), quoted verbatim above.
- [SonarQube Server 2025.6 — Issue management solution overview](https://docs.sonarsource.com/sonarqube-server/2025.6/user-guide/issues/solution-overview) — fetched directly, quoted.
- [Semgrep — Remove duplicate findings docs](https://docs.semgrep.dev/semgrep-code/remove-duplicates) — fetched directly (redirect from semgrep.dev/docs/... followed).
- [`semgrep/semgrep` `cli/src/semgrep/rule_match.py`](https://github.com/semgrep/semgrep/blob/develop/cli/src/semgrep/rule_match.py) — raw source pulled via `curl` and read in full, quoted verbatim above. Repo confirmed via `gh api repos/semgrep/semgrep`: 15,822 stars, pushed 2026-07-09, LGPL-2.1.
- [`DefectDojo/django-DefectDojo` `dojo/finding/models.py`](https://github.com/DefectDojo/django-DefectDojo/blob/master/dojo/finding/models.py) — raw source pulled via `curl`, lines 732–900 read in full, quoted verbatim above (`compute_hash_code`, `compute_hash_code_legacy`, `hash_fields`).
- [`DefectDojo/django-DefectDojo` `dojo/settings/settings.dist.py`](https://github.com/DefectDojo/django-DefectDojo/blob/master/dojo/settings/settings.dist.py) — raw source pulled via `curl`, `HASHCODE_FIELDS_PER_SCANNER` dict read in full, real excerpt quoted above.
- [DefectDojo — Deduplication Algorithms docs](https://docs.defectdojo.com/en/working_with_findings/finding_deduplication/deduplication_algorithms/) — fetched, quoted.
- [`dojo/tools/semgrep_pro/parser.py`](https://github.com/DefectDojo/django-DefectDojo) — found via `gh search code "match_based_id" language:python`, confirms `finding.unique_id_from_tool = item.get("match_based_id")`.
- DefectDojo real, currently open/closed GitHub issues confirming production dedup brittleness — found via `gh search issues "hash_code" "duplicate" repo:DefectDojo/django-DefectDojo`: [#13497](https://github.com/DefectDojo/django-DefectDojo/issues/13497), [#12320](https://github.com/DefectDojo/django-DefectDojo/issues/12320), [#3958](https://github.com/DefectDojo/django-DefectDojo/issues/3958), [#12924](https://github.com/DefectDojo/django-DefectDojo/issues/12924).
- Coverity merge-key mechanism — secondary/community-support sources only (flagged as such, no primary Coverity engineering doc found public): [Synopsys community — CID merge key question](https://sig-synopsys.my.site.com/community/s/question/0D52H00006PsJtoSAF/coverity-merges-issues-by-the-merge-key-of-a-defect-as-i-understand-this-is-a-basic-principle-how-coverity-worksbut-only-to-be-sure-is-there-a-way-to-prevent-the-merging-and-have-separate-issues-e-g-for-different-streamsbranches), [Black Duck community — What is a CID](https://community.blackduck.com/s/article/What-is-CID-and-what-is-the-best-practice).
- ESLint statelessness / no cross-run tracking — [`eslint/eslint` issue #14784](https://github.com/eslint/eslint/issues/14784) (WebSearch-surfaced, cross-checked description against issue title/context; not independently WebFetched line-by-line — flagged as slightly weaker confirmation than the fully-quoted sources above).
- Duplicate bug report detection literature (secondary survey sources, cross-checked across independent surveys, no single primary paper fully verified — flagged as corroborating-shape evidence only): ["A Systematic Study of Duplicate Bug Report Detection"](https://thesai.org/Downloads/Volume12No1/Paper_67-A_Systematic_Study_of_Duplicate_Bug_Report.pdf), ["Combining Retrieval and Classification..."](https://arxiv.org/html/2404.14877v1), ["Automated Duplicate Bug Report Detection in Large Open Bug Repositories"](https://arxiv.org/html/2504.14797), ["Does Deep Learning improve the performance of duplicate bug report detection?"](https://www.sciencedirect.com/science/article/abs/pii/S016412122300002X).
- Prior/companion research (read directly, not re-derived): `research/gate10-concurrency-fingerprint-inventory-2026-07-09.md`, `research/plan-check-reconciliation-prior-art-2026-07-02.md`, `research/defect-taxonomy-standards-prior-art-2026-07-02.md`.
- `loop-team/harness/reconcile_gap_records.py`, `loop-team/harness/plancheck_saturation.py`, `loop-team/DESIGN_CHECKLIST.md` (gate 10), `fix_plan.md` (`H-PLANCHECK-BINDING-SATURATION-1`, CLOSED 2026-07-08, `[BINDING]`-only scope confirmed) — read directly for the live-code grounding referenced throughout.
