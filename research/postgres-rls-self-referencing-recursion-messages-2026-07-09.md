# Domain brief: Postgres RLS self-referencing-subquery recursion (padsplit-cockpit `messages` policy)

**Date:** 2026-07-09
**Mode:** D (domain research for a build)
**Requested by:** Oga, verifying a plan-check Verifier lens's DESIGN-gap claim on
`<HOME>/Claude/loop/loop-team/runs/20260709_112517-padsplit-cockpit-rls-cross-fk-fix/specs/spec.md`,
section "6. `messages`" under "Exact policy text per table."
**Postgres version tested against:** PostgreSQL 17.10 (Homebrew, aarch64-apple-darwin), local dev DB
`127.0.0.1:5433` / `padsplit_cockpit`, confirmed live via `SELECT version();`.

---

## Question

Does a *direct* self-referencing `EXISTS` subquery inside a table's own RLS policy (same
table, different alias, one level — the `messages.aiDraftOfId` self-join in the spec's
proposed `messages` policy) trigger Postgres's `ERROR: infinite recursion detected in
policy for relation "messages"`? If so, is the Verifier lens's proposed fix (a
`SECURITY DEFINER` SQL function) correct, and is it the best fix?

## Answer (short version)

**The recursion claim is CORRECT — confirmed both from the Postgres source/regression
tests and by reproducing the exact error live against the real target database.** The
spec's proposed `messages` policy as written **will fail on every query that touches
`messages`** with `ERROR: infinite recursion detected in policy for relation "messages"`.

**The Verifier lens's proposed fix (a `SECURITY DEFINER` function wrapping the
self-referencing check) is directionally correct and does work** — but its stated
*reason* is imprecise, and the reasoning matters for picking the cleanest variant. Live
testing established two separate, previously-conflated facts:

1. **Avoiding the recursion ERROR only requires wrapping the self-reference in ANY
   function call** (SQL or PL/pgSQL, `SECURITY DEFINER` or not, `SET search_path` or
   not, even a function eligible for planner inlining). This is because Postgres's
   recursion guard is a **query-rewrite-time** check for a raw `SubLink` (subquery) node
   in the policy's parsed qual — a `FuncExpr` (function call) is not a `SubLink`, and
   rewriting completes before any function inlining could occur at planning time, so the
   guard never fires regardless of what the function contains internally. Confirmed live
   with a minimal, maximally-inlinable `LANGUAGE sql STABLE` function (no `SECURITY
   DEFINER`, no `SET` clause) — zero recursion error.
2. **`SECURITY DEFINER` (owned by a role that actually bypasses RLS on `messages`, e.g.
   has `BYPASSRLS` or the table lacks `FORCE ROW LEVEL SECURITY` for that owner) IS
   required for CORRECTNESS**, not to avoid the Postgres error. Without it, the wrapped
   self-check is *itself* subject to the full `tenant_isolation` policy (including the
   `contactId`/`conversationId` ownership clauses) when evaluating the **referenced**
   row — over-constraining the check to "does the referenced message ALSO pass its own
   full policy" rather than the intended "does the referenced message's `orgId` match."
   Live-reproduced: a non-`SECURITY DEFINER` wrapper function incorrectly hid a
   legitimate same-org draft message when the *referenced* (non-draft) message had an
   unrelated data-integrity problem on its own `contactId` — a false negative, not a
   security leak, but a real correctness bug a security fix should not introduce.

**A secondary claim found via web search (a dev.to article) — that `LANGUAGE sql
SECURITY DEFINER` functions get inlined and lose their `SECURITY DEFINER` context,
requiring `LANGUAGE plpgsql` instead — is FALSE for Postgres 17.10 and is refuted both
by the Postgres source (`clauses.c`'s `inline_function()` explicitly excludes
`prosecdef` functions from inlining — see Source #5 below) and by live testing: a
`LANGUAGE sql STABLE SECURITY DEFINER` function behaved identically (correct results,
no recursion) to a `LANGUAGE plpgsql SECURITY DEFINER` function in every test run.
Flag this claim as UNVERIFIED-AND-NOW-REFUTED if it resurfaces; do not cite the dev.to
article as grounding.**

**Recommended fix:** a `LANGUAGE sql STABLE SECURITY DEFINER` helper function (simpler
syntax than PL/pgSQL, empirically equivalent, matches the actual Postgres inlining rule)
owned by the same role that owns/migrates the table (`DATABASE_URL_OWNER`, which in this
repo already has `BYPASSRLS` — confirmed via `\du`), called from the `aiDraftOfId`
clause only. The `contactId`/`conversationId` clauses do not need wrapping — they don't
self-reference `messages`, so they never trip the guard (confirmed: the original 8-table
class's other 6 policies, which have no self-join, are unaffected by this issue).

---

## Sources (all opened and quoted, not paraphrased from memory)

### 1. Official Postgres 17 docs — do NOT document this behavior
- `https://www.postgresql.org/docs/17/sql-createpolicy.html` — fetched in full; **no
  text about recursion, self-reference, or "infinite recursion detected in policy"
  anywhere on the page.**
- `https://www.postgresql.org/docs/17/ddl-rowsecurity.html` (§5.9 Row Security
  Policies) — fetched in full; **no text about recursion detection either.** The only
  adjacent warning: *"If it is necessary to consult other rows or other tables to make
  a policy decision, that can be accomplished using sub-`SELECT`s, or functions that
  contain `SELECT`s, in the policy expressions. Be aware however that such accesses can
  create race conditions that could allow information leakage if care is not taken."*
  This is a race-condition warning, unrelated to the recursion-detection mechanism.
- **Gap flagged honestly:** the recursion-detection mechanism and its fix pattern are
  **not documented in the official Postgres manual at all** — the only authoritative
  ground truth is the Postgres source code and its own regression test suite (below),
  plus a long-standing community mailing-list thread. Anyone citing "the Postgres docs
  say X about RLS recursion" should be treated as unverified until they can point to an
  actual doc section — there isn't one.
- `https://www.postgresql.org/docs/17/ddl-rowsecurity.html` — quoted for the
  owner-bypass rule used in the fix design: *"Superusers and roles with the `BYPASSRLS`
  attribute always bypass the row security system when accessing a table. Table owners
  normally bypass row security as well, though a table owner can choose to be subject
  to row security with `ALTER TABLE ... FORCE ROW LEVEL SECURITY`."*
- `https://www.postgresql.org/docs/17/sql-createfunction.html` — quoted for
  `SECURITY DEFINER` semantics: *"`SECURITY INVOKER` indicates that the function is to
  be executed with the privileges of the user that calls it. That is the default.
  `SECURITY DEFINER` specifies that the function is to be executed with the privileges
  of the user that owns it."*

### 2. Postgres source code (`master` branch, mechanism unchanged since RLS's original
   9.5/9.6 implementation — function names/logic match what shipped and still ships in
   17.x)
- `src/backend/rewrite/rewriteHandler.c`, `fireRIRrules()`, lines ~2250–2336 (fetched
  and read directly). The exact guarded block:
  ```c
  if (securityQuals != NIL || withCheckOptions != NIL)
  {
      if (hasSubLinks)
      {
          /*
           * Recursively process the new quals, checking for infinite
           * recursion.
           */
          if (list_member_oid(activeRIRs, RelationGetRelid(rel)))
              ereport(ERROR,
                      (errcode(ERRCODE_INVALID_OBJECT_DEFINITION),
                       errmsg("infinite recursion detected in policy for relation \"%s\"",
                              RelationGetRelationName(rel))));

          activeRIRs = lappend_oid(activeRIRs, RelationGetRelid(rel));
          ...
          expression_tree_walker((Node *) securityQuals, fireRIRonSubLink, &fire_context);
          ...
          activeRIRs = list_delete_last(activeRIRs);
      }
      ...
  }
  ```
  **This is the load-bearing detail**: the check only runs `if (hasSubLinks)` — i.e.
  only when the policy's parsed qual contains a raw `SubLink` AST node (an `EXISTS(...)`,
  `IN(...)`, or scalar subquery written directly in the policy text). A function call
  (`FuncExpr`) is a different node type and never trips `hasSubLinks`, so the whole
  recursion-checking branch — including the `list_member_oid` guard — is skipped
  entirely when the self-reference is hidden inside a function body, regardless of that
  function's language or `SECURITY` mode. This is *why* wrapping in a function works
  structurally, and it is a REWRITE-phase check, strictly before planning/inlining, so
  even a function the planner *would* later inline cannot retroactively re-trigger it.
- `src/backend/optimizer/util/clauses.c`, `inline_simple_function` (or equivalent —
  the function directly preceding line 5361 in the fetched copy), lines ~5348–5359
  (fetched and read directly): the exact disqualification list for SQL-function
  inlining:
  ```c
  /*
   * Forget it if the function is not SQL-language or has other showstopper
   * properties.  (The prokind and nargs checks are just paranoia.)
   */
  if (funcform->prolang != SQLlanguageId ||
      funcform->prokind != PROKIND_FUNCTION ||
      funcform->prosecdef ||
      funcform->proretset ||
      funcform->prorettype == RECORDOID ||
      !heap_attisnull(func_tuple, Anum_pg_proc_proconfig, NULL) ||
      funcform->pronargs != list_length(args))
      return NULL;
  ```
  **This directly refutes the dev.to claim.** `funcform->prosecdef` (true for
  `SECURITY DEFINER`) is an explicit disqualifier from inlining — a `SECURITY DEFINER`
  SQL function is *never* inlined by the planner, so it can never "lose its context" via
  inlining. (Also notable: a `SET search_path = ...` clause on the function — via
  `proconfig` — independently disqualifies inlining too, which is a second, unrelated
  reason our test functions weren't inlined.)
- `src/test/regress/sql/rowsecurity.sql`, "-----   RECURSION    ----" section, lines
  637–735 (fetched and read directly). This is Postgres's OWN official regression test
  for this exact class of bug — **the authoritative confirmation that a single table's
  own policy referencing itself via a subquery is a first-class, intentionally-tested
  failure mode, not an edge case**:
  ```sql
  --
  -- Simple recursion
  --
  SET SESSION AUTHORIZATION regress_rls_alice;
  CREATE TABLE rec1 (x integer, y integer);
  CREATE POLICY r1 ON rec1 USING (x = (SELECT r.x FROM rec1 r WHERE y = r.y));
  ALTER TABLE rec1 ENABLE ROW LEVEL SECURITY;
  SET SESSION AUTHORIZATION regress_rls_bob;
  SELECT * FROM rec1; -- fail, direct recursion
  ```
  This is structurally identical to the spec's `messages` policy: one table, one
  policy, a subquery against the *same table* via a different alias (`r` here, `m2` in
  the spec). The test's own comment confirms the expected outcome is failure. The suite
  also separately tests and confirms **mutual recursion** (two tables' policies
  referencing each other, lines 650–659) and **mutual recursion via views/security-
  barrier views** (lines 662–688) as distinct, additional failure shapes — the Verifier
  lens's claim conflated "self-reference" as *one* instance of a broader class, which
  is accurate; it did not claim self-reference was the *only* trigger, and the
  regression suite confirms self-reference alone is sufficient on its own.

### 3. Community grounding for the mechanism and the historical fix pattern (mailing
   list — the closest thing to an authoritative discussion, since the manual doesn't
   cover this)
- `https://www.postgresql.org/message-id/CALgFm5hwf=HRFCcs7ZUyB6oNpmRRthVH0YmFm=Z3HxvYxCCFEQ@mail.gmail.com`
  — "Recursive row level security policy" (Simon Charette, pgsql-general). Fetched and
  quoted verbatim. The exact reported case:
  ```sql
  CREATE POLICY account_ownership ON accounts FOR SELECT
  USING (owner_id = (SELECT id FROM accounts WHERE name = current_user));
  -- ERROR: infinite recursion detected in policy for relation "accounts"
  ```
  Single table, self-referencing scalar subquery — same shape as `messages`.
- `https://www.postgresql.org/message-id/026a01d25767$669b56b0$33d20410$@swisspug.org`
  — reply from Charles Clavadetscher, fetched and quoted: *"The problem is that the
  policy for select on the table will be checked each time a select is performed. So
  having a select in the using condition will check the policy again, and so on."* His
  proposed workarounds (views, or "a security definer function where you temporarily
  disable row level security," noting this is *"quite a nasty thing to do"*) are the
  same two directions modern practitioner writeups converge on.

### 4. Practitioner corroboration (secondary sources — treated as leads only, verified
   or refuted against source/live testing before being trusted; flagged per honesty
   bar)
- `https://dev.to/bairescodeai/infinite-recursion-in-postgres-rls-a-security-definer-gotcha-1916`
  — confirms the trigger shape (self-referencing `EXISTS` inside a policy on the same
  table) and the exact error text `42P17: infinite recursion detected in policy for
  relation "profiles"`. **Its specific claim that `LANGUAGE sql SECURITY DEFINER`
  functions get inlined and lose their security context is REFUTED** by
  `clauses.c`'s `prosecdef` inlining exclusion (Source #2) and by live testing (below).
  Do not cite this article for the inlining claim; its recursion-shape description is
  otherwise accurate.
- `https://github.com/orgs/supabase/discussions/32579` — a Supabase user hit the exact
  error on a `profiles` table; a maintainer's diagnosis (quoted): *"You are likely
  selecting from the same table in a select policy which then tries to run the RLS
  again on the select."* Consistent with the mechanism above; the thread does not
  include the OP's literal SQL, so it's corroborating but not independently
  verifiable beyond the maintainer's stated diagnosis.

### 5. Live testing against the REAL target database (the strongest evidence — this is
   not a secondary source, it is a direct, reproduced observation)

All tests run via `psql "$PGURL_OWNER"` (owner role `eobodoechine`, superuser +
`BYPASSRLS`, confirmed via `\du`) against `127.0.0.1:5433`/`padsplit_cockpit`, inside a
`BEGIN; ... ROLLBACK;` block every time. **Every transaction ended in `ROLLBACK`, never
`COMMIT` — verified after the fact by re-reading `\d messages` and confirming the
policy text and row set were unchanged from before testing.** The raw password was
never printed to output; the connection string was extracted with `grep '^DATABASE_URL_OWNER='
.env | cut -d= -f2- | sed 's/^"//;s/"$//'` into a shell variable, never echoed
(an initial attempt using `node -e "require('dotenv')..."` was abandoned after it
turned out this repo's `dotenv` wrapper prints a banner line to stdout that corrupted
the captured value — noted here in case it trips up a future agent in this repo).

**Test 1 — reproduce the spec's exact proposed policy, verbatim, as `app_user`:**
```sql
BEGIN;
DROP POLICY tenant_isolation ON "messages";
CREATE POLICY tenant_isolation ON "messages"
  USING ( "orgId" = current_setting('app.org_id', TRUE)
    AND EXISTS (SELECT 1 FROM "contacts" c WHERE c."id" = "messages"."contactId" AND c."orgId" = current_setting('app.org_id', TRUE))
    AND EXISTS (SELECT 1 FROM "conversations" conv WHERE conv."id" = "messages"."conversationId" AND conv."orgId" = current_setting('app.org_id', TRUE))
    AND ( "aiDraftOfId" IS NULL OR EXISTS (
        SELECT 1 FROM "messages" m2 WHERE m2."id" = "messages"."aiDraftOfId" AND m2."orgId" = current_setting('app.org_id', TRUE) ) ) )
  WITH CHECK ( -- identical text );
SET SESSION AUTHORIZATION app_user;
SELECT set_config('app.org_id', (SELECT id FROM orgs LIMIT 1), TRUE);
SELECT * FROM messages LIMIT 1;
```
**Verbatim result:**
```
ERROR:  infinite recursion detected in policy for relation "messages"
ERROR:  current transaction is aborted, commands ignored until end of transaction block
ROLLBACK
```
**Confirmed: this fires on the FIRST query touching `messages` under the app_user role
(a plain `SELECT * FROM messages LIMIT 1`), exactly as the Verifier lens predicted —
not a rare or data-dependent case.**

**Test 2 — `SELECT ... FROM ONLY "messages" m2 ...` variant (per the task's own
hypothesis that `ONLY` won't help since it only affects inheritance):** identical
result — `ERROR: infinite recursion detected in policy for relation "messages"`.
**Confirmed: `ONLY` does not avoid the guard** (the recursion check keys on relation
OID, which `ONLY` does not change — it only sets an RTE inheritance flag).

**Test 3 — Candidate A2: bare `LANGUAGE sql STABLE` function, no `SECURITY DEFINER`,
`SET search_path = public`, wrapping only the `aiDraftOfId` self-check:** No recursion
error; correct rows returned for the happy path (both a plain message and its draft,
same org, both visible).

**Test 4 — Candidate A2 correctness probe (the false-negative case):** Temporarily
(owner role, rolled back) set an existing message `m1`'s `contactId` to a contact
belonging to a *different* org (`m1.orgId` unchanged, still org A) — simulating an
unrelated data-integrity issue on the referenced row. Then, as `app_user` scoped to
org A, queried for `m2` (a legitimate, same-org draft of `m1`):
```sql
SELECT id, "aiDraftOfId" FROM messages;
-- returned: 0 rows
```
**`m2` was incorrectly hidden**, even though `m2.orgId = m1.orgId = A` (the only thing
that should matter for the `aiDraftOfId` check) — because the non-`SECURITY DEFINER`
wrapper function's internal query is itself subject to the full policy, including
`m1`'s own (unrelated) `contactId` check. This is the correctness bug predicted above.

**Test 5 — Candidate B (`LANGUAGE plpgsql SECURITY DEFINER`) under the same corrupted-
data probe:** same setup, same query —
```sql
SELECT id, "aiDraftOfId" FROM messages;
-- returned: 1 row (cmrdk4ur10009q512n1cm2nd6 | cmrdk4uq40008q512ps5tx6v4)
```
**`m2` correctly visible** — the `SECURITY DEFINER` function bypasses RLS entirely for
its internal check (owner role has `BYPASSRLS`), so it only evaluates the intended
`orgId` equality, not the referenced row's own full policy.

**Test 6 — Candidate A (`LANGUAGE sql STABLE SECURITY DEFINER`) under the same probe:**
identical correct result — `1 row` returned. `pg_proc` confirms `prosecdef = t`.
**This directly refutes the "SQL functions get inlined, losing SECURITY DEFINER"
claim** — a `LANGUAGE sql SECURITY DEFINER` function behaves identically to the
`plpgsql` version in this Postgres 17.10 instance, consistent with `clauses.c`'s
explicit `prosecdef` inlining exclusion (Source #2).

**Test 7 — control: a minimal, maximally inlining-eligible `LANGUAGE sql STABLE`
function (no `SECURITY DEFINER`, no `SET` clause, `pg_proc.prosecdef = f`,
`pg_proc.proconfig = NULL`), wrapping the self-check:** No recursion error;
`EXPLAIN (COSTS OFF)` showed the function call preserved as a `FuncExpr` in the final
plan (`Filter: (("orgId" = current_setting(...)) AND (("aiDraftOfId" IS NULL) OR
message_org_matches_inlinable("aiDraftOfId", current_setting(...))))`) — **confirms
the recursion guard is avoided purely by the qual being a `FuncExpr` at REWRITE time,
independent of whether the function is later inlined at planning time** (the rewrite
phase, where the guard lives, completes before planning/inlining ever runs).

**Test 8 — full end-to-end validation of the recommended fix** (Candidate A, all three
clauses, exact intended shape for the spec):
- Seeded (as owner, bypassing RLS) a deliberately-broken row: `orgId = org A`,
  valid same-org `contactId`/`conversationId`, but `aiDraftOfId` pointing at a message
  belonging to a *different* org B — i.e., exactly the cross-org gap this whole spec
  exists to close.
- As `app_user` scoped to org A: legitimate same-org messages (`m1`, `m2`) remained
  visible — **no regression on the happy path.**
- As `app_user` scoped to org A: the seeded cross-org-gap row was **invisible** via
  `USING` — `SELECT id, "aiDraftOfId" FROM messages WHERE id = 'test-crossorg-draft';`
  returned **0 rows**.
- As `app_user` scoped to org A: attempting to `INSERT` that exact cross-org-gap row
  directly (testing `WITH CHECK`) was **rejected**:
  ```
  ERROR:  new row violates row-level security policy for table "messages"
  ```
- Final state verified clean: `\d messages` after the last `ROLLBACK` showed the
  original bare `"orgId" = current_setting(...)` policy text, `SELECT count(*) FROM
  messages WHERE id LIKE 'test-crossorg%'` returned `0`, and `SELECT proname FROM
  pg_proc WHERE proname LIKE 'message_org_matches%'` returned `0` rows — **no
  persistent changes were made to the database at any point in this research.**

---

## Recommended `code_pattern` — ready to drop into the spec's section 6

Replace the spec's proposed `messages` policy (and the migration file's corresponding
block) with the following. The `contactId`/`conversationId` clauses are unchanged
(they don't self-reference `messages`, so they were never affected). Only the
`aiDraftOfId` clause changes, plus one new helper function that must be created
*before* the policy in the same migration file, using the SAME owner-role connection
(`DATABASE_URL_OWNER`) the migration already runs as:

```sql
-- Helper: checks whether a message row (by id) belongs to the given org, bypassing
-- RLS for this single lookup so the self-referencing aiDraftOfId check in the
-- messages policy below does not trip Postgres's RLS recursion guard (a table's own
-- policy may not contain a literal subquery against the same table — see
-- ~/Claude/loop/research/postgres-rls-self-referencing-recursion-messages-2026-07-09.md
-- for the full grounding). SECURITY DEFINER makes this run as the function owner
-- (the migrating/owner role, which has BYPASSRLS) rather than the calling app_user
-- role, so the lookup only checks orgId equality — it does NOT also require the
-- referenced row to independently satisfy the full tenant_isolation policy (that
-- would be an unintended, over-strict coupling — see Test 4/5 in the linked research).
CREATE FUNCTION message_org_matches(p_msg_id text, p_org text)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $fn$
  SELECT EXISTS (SELECT 1 FROM "messages" WHERE id = p_msg_id AND "orgId" = p_org);
$fn$;

-- Explicit grant (Postgres grants EXECUTE to PUBLIC by default on function creation,
-- so this is not strictly required given this repo's scripts/db-roles.sql does not
-- REVOKE EXECUTE FROM PUBLIC anywhere — but keep it explicit, matching this repo's
-- existing convention of never relying on an implicit/default grant for app_user).
GRANT EXECUTE ON FUNCTION message_org_matches(text, text) TO app_user;

DROP POLICY tenant_isolation ON "messages";
CREATE POLICY tenant_isolation ON "messages"
  USING (
    "orgId" = current_setting('app.org_id', TRUE)
    AND EXISTS (
      SELECT 1 FROM "contacts" c
      WHERE c."id" = "messages"."contactId"
        AND c."orgId" = current_setting('app.org_id', TRUE)
    )
    AND EXISTS (
      SELECT 1 FROM "conversations" conv
      WHERE conv."id" = "messages"."conversationId"
        AND conv."orgId" = current_setting('app.org_id', TRUE)
    )
    AND (
      "aiDraftOfId" IS NULL
      OR message_org_matches("aiDraftOfId", current_setting('app.org_id', TRUE))
    )
  )
  WITH CHECK (
    "orgId" = current_setting('app.org_id', TRUE)
    AND EXISTS (
      SELECT 1 FROM "contacts" c
      WHERE c."id" = "messages"."contactId"
        AND c."orgId" = current_setting('app.org_id', TRUE)
    )
    AND EXISTS (
      SELECT 1 FROM "conversations" conv
      WHERE conv."id" = "messages"."conversationId"
        AND conv."orgId" = current_setting('app.org_id', TRUE)
    )
    AND (
      "aiDraftOfId" IS NULL
      OR message_org_matches("aiDraftOfId", current_setting('app.org_id', TRUE))
    )
  );
```

**Rollback text** (for the migration's documentation-only rollback trailer, matching
the repo convention): drop the policy back to the bare `orgId`-only text (as in the
spec's existing rollback pattern for the other 6 tables), then also
`DROP FUNCTION IF EXISTS message_org_matches(text, text);`.

## Constraints

- **Version-general, not version-pinned**: the recursion-detection mechanism
  (`rewriteHandler.c`'s `activeRIRs`/`hasSubLinks` guard) has existed since RLS
  shipped in Postgres 9.5/9.6 and is unchanged on the current `master` branch checked
  here — this is a structural, long-standing behavior, not a 17.x-specific quirk. Safe
  to assume it applies to any Postgres version this repo might run.
- **The helper function must be created by (and callable only through) a role that
  actually bypasses RLS on `messages`.** In this repo that's `DATABASE_URL_OWNER`
  (superuser + `BYPASSRLS`, confirmed via `\du`). If a future deployment changes the
  owner role to a non-superuser role WITHOUT `BYPASSRLS`, the function will silently
  stop working correctly for the `aiDraftOfId` check — this repo's own `messages`
  table already has `FORCE ROW LEVEL SECURITY` set (confirmed via `\d messages` →
  "Policies (forced row security enabled)"), which means an ordinary table-owner role
  WITHOUT `BYPASSRLS` would NOT be exempt from `messages`'s own RLS even via table
  ownership alone — `BYPASSRLS` (or superuser) is specifically required, not just
  ownership. **Flag this as a documentation inaccuracy already present in this repo's
  own `README.md` Tenancy section**, which states the owner role "bypasses RLS
  unconditionally (Postgres rule: superuser/BYPASSRLS/table-owner roles are exempt
  from FORCE ROW LEVEL SECURITY)" — this conflates three distinct exemptions; per the
  Postgres 17 docs quoted above, *table ownership alone does NOT exempt from FORCE ROW
  LEVEL SECURITY* — only superuser or `BYPASSRLS` does. It's harmless today only
  because this repo's actual owner role happens to also be superuser.
- **Grant EXECUTE to `app_user` explicitly** (Postgres's default already grants
  EXECUTE to PUBLIC on function creation and this repo's `scripts/db-roles.sql` never
  revokes it, so the explicit grant is technically redundant right now — but keep it
  for self-documentation and defense against a future `REVOKE ... FROM PUBLIC` on this
  schema).
- **Only the `aiDraftOfId` clause needs the wrapper.** The `contactId` and
  `conversationId` clauses reference `contacts`/`conversations` (different tables, no
  self-reference) and are unaffected by this issue — do not wrap those.
- **This is a `messages`-only fix.** None of the other 6 policies in the spec
  (`tasks`, `occupancy_events`, `incidents`, `contact_inboxes`, `conversations`,
  `contacts`) self-reference their own table, so none of them are subject to this
  recursion guard — confirmed by inspection of the spec's proposed SQL for all 7
  tables (only `messages`'s `aiDraftOfId` clause queries `"messages"` from within the
  `messages` policy).

## not_found

- No official Postgres documentation page (manual, wiki, or release notes) discusses
  the RLS self-reference recursion guard or its fix pattern at all — confirmed by
  reading both `sql-createpolicy.html` and `ddl-rowsecurity.html` in full. The only
  authoritative grounding is the source code, the regression test suite, and a 2016
  mailing-list thread; there is no "official recommended pattern" doc to point the
  Coder at beyond this brief and the source citations above.
- Could not find a Postgres wiki page or blog post specifically discussing
  "hierarchical/threaded-message RLS" as a named pattern (searched "postgres rls self
  join same table", "postgres row level security hierarchical", "postgres rls thread
  parent message policy") — results converged on the same
  SECURITY-DEFINER-function pattern already covered above, no additional named
  pattern was found. Not treated as a gap in the recommendation (the tested fix is
  sound), just noting the search didn't surface a distinct alternative.
