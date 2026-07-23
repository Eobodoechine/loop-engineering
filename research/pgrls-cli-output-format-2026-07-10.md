# Domain brief: pgrls CLI output format (Mode D)

**Requested by:** Oga, for the padsplit-cockpit "backtest pgrls against our historical RLS bugs" spec.
**Date:** 2026-07-10
**Researcher honesty note on method:** Sources were retrieved via `WebFetch` (which summarizes fetched HTML/markdown through a secondary small model, not a raw byte dump) against `github.com/pgrls/pgrls` and `raw.githubusercontent.com/pgrls/pgrls/main/README.md`, plus `WebSearch` lead-snippets. I did not get a raw terminal/tool-output transcript of `pgrls lint` actually executing — everything below is what the project's own README documents its output to look like, corroborated across two independent fetches (rendered GitHub page vs. raw README markdown) whose quotes matched near-verbatim, which is the best available grounding without installing and running the tool myself (out of scope for a research-only dispatch). **Flagging this explicitly per the honesty bar: this is document-grounded, not execution-grounded.** The Coder's own AC (run it live, quote verbatim) is the actual execution-grounding step — this brief tells them what to expect and where the spec's own wording is wrong.

---

## CRITICAL CORRECTION TO THE SPEC'S WORDING — READ FIRST

**There is no `pgrls check` subcommand.** I searched for it directly (`WebSearch` query `"pgrls check" OR "pgrls lint" command usage subcommands`) and it does not appear anywhere in the README's documented command list. The actual subcommand that runs the lint ruleset against a live database is:

```
pgrls lint --database-url "postgres://user:pass@host:5432/db"
```

or, with `DATABASE_URL` exported as an env var, just `pgrls lint`.

The README's full subcommand list (as summarized from the repo): `lint`, `fix`, `generate`, `snapshot`, `diff`, `verify`, `report`, `matrix`, `perf`, `coverage`, `history`, `explain`, `mcp`. No `check`.

**Action for the spec author:** the AC text "run `pgrls check` against a live Postgres instance" needs to be corrected to `pgrls lint` before it's handed to a Coder — otherwise the Coder's first action will be a shell error (`No such command 'check'`), which could get misread as "the tool is broken" rather than "the spec has a typo." Recommend Oga fix this in the spec now rather than let the Coder discover and silently patch it (silent AC-text patching by a Coder is itself a red flag per prior loop-team findings).

---

## Q1: Structured (JSON/machine-parseable) or plain-text?

**Answer:** Both — plain text is the default, JSON is an explicit opt-in flag, and several other structured formats also exist.

- Default: `--format text` — human-readable, git-diff-style.
- Supported `--format` values (per README): `text` (default), `json`, `sarif`, `markdown`, `pr-comment` (GitHub PR comment), `github` (GitHub Actions annotations), `junit` (JUnit XML), `html`.

**Source:** github.com/pgrls/pgrls README (fetched via WebFetch, corroborated by a second fetch of `raw.githubusercontent.com/pgrls/pgrls/main/README.md`). Quote: *"Output is git-diff-style by default (`--format text`)."*

## Q2: Stable rule IDs — are SEC047 / SEC001 / SEC015 / SEC040 real, and what does SEC047 check?

**Answer: yes, all four are real, documented rule IDs**, not fabricated. Verbatim (or near-verbatim, per the two-fetch cross-check) descriptions pulled from the README's rule catalog:

- **SEC001** — "Tables in scanned schemas with RLS disabled and no policies (a table with policies but RLS off is SEC032)"
- **SEC015** — "SECURITY DEFINER function exposed to `pg_temp` search-path shadowing"
- **SEC040** — "Permissive `FOR ALL` policy whose `USING` scopes by a tenant/owner key but whose explicit `WITH CHECK` binds no identity column at all — a `FOR ALL` insert is governed by WITH CHECK alone" — **this is directly relevant to the padsplit-cockpit RLS finding in memory** (`feedback_rls_over_permissive_10_tables.md`: "FOR ALL USING with no WITH CHECK on sources + 9 sibling tables"), so SEC040 is the rule to specifically look for when backtesting that known bug.
- **SEC047** — "A foreign key whose parent (referenced) table has RLS enabled is a cross-tenant *existence* covert channel when a low-trust role can write the child: FK validation bypasses RLS [so referencing a guessed parent key succeeds (row exists) or errors (it doesn't), even though RLS hides that row from the role's SELECT]. The rule fires only when the parent has RLS on and the child is low-trust-writable (INSERT/UPDATE grant + RLS-off or an anon write policy)."

The SEC047 description came through consistently across both the direct README WebFetch and an independent WebSearch snippet (near-identical phrasing: "cross-tenant existence covert channel," "FK validation bypasses RLS") — two independently-generated summaries converging on the same wording is reasonable (not certain) triangulation that this is the tool's actual documented text rather than a fetch hallucination.

**Rule count caveat (minor inconsistency, flag it):** different fetches reported the total rule count inconsistently — the GitHub repo description says "47 lint rules," one WebFetch pass said "51 rules," another WebSearch snippet said "forty-nine rules." This is likely version drift in the README (`pip install pgrls` is at 0.10.0 per PyPI, an actively-changing pre-1.0 tool) rather than fabrication, but I could not pin an exact authoritative count — treat "SEC047 exists" as solid (converged from 2 independent fetch paths) and "total rule count" as soft.

**Source:** github.com/pgrls/pgrls README rule catalog (WebFetch, 2 passes) + WebSearch corroboration for SEC047.

## Q3: Does a finding name the specific table/policy/column, in a way matchable against a known bug?

**Answer:** Yes — the documented text-format example names the schema-qualified table directly in the finding header line, and the JSON schema carries a structured `location`-type field plus a `rule_id`:

Text format (as documented):
```
  ERROR  SEC001  public.users
         Table public.users does not have row-level security enabled.
```

JSON format (as documented):
```json
{
  "violations": [
    {
      "rule_id": "SEC001",
      "severity": "error",
      "title": "RLS not enabled on table",
      "message": "Table public.users does not have row-level security enabled."
    }
  ],
  "summary": { "errors": 1, "warnings": 0, "infos": 0 }
}
```

For rules like SEC040 (missing `WITH CHECK` identity binding) the finding's table+policy identification would be in the same `message`/header slot, naming the table (and, per the rule's own semantics, implicitly the policy being evaluated on it) — but **I did not find a verbatim README example specifically for SEC040 or SEC047's finding-line format** (only their rule-description prose, not a captured sample finding). This matters for the Coder's AC: they should not assume the exact wording/column-naming granularity of a SEC040 finding until they've actually run `pgrls lint` and read the real line — the AC's own instruction ("quote the matching finding verbatim... do not round an ambiguous or partial match up to a clean hit") is the right posture precisely because the column-level granularity is unconfirmed from docs alone.

**Source:** github.com/pgrls/pgrls README, "Output formats" / rule catalog sections (WebFetch, 2 passes, consistent).

## Q4: Is there a `--format json` (or similar) machine-readable mode?

**Answer:** Yes, confirmed — `--format json` is one of the documented format flags (see Q1 list), alongside `sarif`, `junit`, `github`, etc. This is a real flag, not inferred from the tool's name/purpose — it's the same README section quoted above.

**Source:** github.com/pgrls/pgrls README (WebFetch).

## Q5: What Python version does pgrls require?

**Answer: Python 3.11+.** Quoted directly from the README (converged identically across both WebFetch passes): *"pgrls needs **Python 3.11+** (and Postgres 15+ to lint against)."*

**Constraint flag for the spec:** the dispatch context states this machine has only **Python 3.9.6** available. 3.9.6 does not satisfy pgrls's stated 3.11+ floor. If the AC requiring a Python-version check is written against "can this machine run pgrls," the answer per the README's stated requirement is **no** — the Coder will need a Python 3.11+ interpreter (via `pyenv`, a Docker container, `uv python install 3.11`, or similar) before `pip install pgrls` will even resolve/run correctly. This should be surfaced to Oga as a blocking constraint on that AC, not something for the Coder to discover mid-build and quietly work around.

**Source:** github.com/pgrls/pgrls README, "Installation" section (WebFetch, 2 independent passes, identical quote).

---

## Not found / could not verify

- **No raw execution transcript.** I did not install and run `pgrls lint` myself (out of scope for this research-only dispatch, and this machine's Python 3.9.6 wouldn't support it anyway per Q5). Everything above is what the README *documents* the output to look like — the Coder's live-run AC is still the real verification step, and per the AC's own wording, they should not treat this brief as a substitute for reading the actual output.
- **No verbatim example finding-line for SEC040 or SEC047 specifically** (only the two rules' descriptive prose was found, not a captured sample CLI line showing exactly how they'd name a table/policy/column in output). If the Coder needs to know the *exact* string shape before running it, that's not available from docs — only from the live run.
- **Total rule count is soft** (47 vs 49 vs 51 across different fetched summaries — likely README version drift on a fast-moving pre-1.0 tool, not settled).
- **No `pgrls check` command exists anywhere I could find** — treat the spec's use of that phrase as a bug in the spec text, not a fact about the tool (see correction section above).
- I did not attempt to browse the tool's actual Python source (e.g., a `formatters.py` or `cli.py` file) via the GitHub API/raw file fetch to confirm the output-formatting logic at the code level, beyond what the README documents. If Oga wants source-level (not just doc-level) confirmation of the JSON schema or the exact text-formatter string templates, a follow-up fetch of the repo's file tree (e.g. `https://api.github.com/repos/pgrls/pgrls/contents/` or a raw fetch of a specific `src/pgrls/.../format*.py` file) would be the next step — I did not do this pass.

---

## Summary for the Coder (actionable)

1. Fix the spec text: it's `pgrls lint`, not `pgrls check`.
2. Requires Python 3.11+ — this machine's default 3.9.6 will not run it; provision a 3.11+ interpreter first (this is a real blocking constraint, escalate if not already planned for).
3. Default output is human-readable text with a `RULE_ID  schema.table` header line + message; use `--format json` for a `{"violations": [{"rule_id", "severity", "title", "message", ...}], "summary": {...}}` structure if the AC wants programmatic matching instead of human quoting.
4. SEC040 is the rule most directly relevant to padsplit-cockpit's known bug (FOR ALL policy, USING scopes tenant, WITH CHECK doesn't bind identity) — that's the rule ID to specifically look for in the `pgrls lint` output when backtesting the `sources` table + 9 siblings finding.
5. SEC001/SEC015/SEC040/SEC047 are all real documented rules, not fabricated — safe to cite in the spec as real pgrls rule IDs.
6. Treat all of the above as doc-grounded, not execution-grounded — the Coder's own live run is what actually settles whether a specific known bug gets flagged, and the AC's caution against rounding an ambiguous match up to a clean hit is well-founded given I could not find a captured real finding-line for SEC040/SEC047 to compare against in advance.
