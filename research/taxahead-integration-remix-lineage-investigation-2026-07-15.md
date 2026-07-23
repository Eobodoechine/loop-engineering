# Investigation: is `taxahead-integration` / `remix-of-taxahead.ai` a live 5th lineage or a dead exploration?

**Date:** 2026-07-15
**Requested by:** Nnamdi (CTO/cofounder, TaxAhead), read-only investigation, no modify/commit/push.
**Feeds:** Open Question #4 in `~/Claude/Projects/taxahead/loop-team/runs/2026-07-15_connector-reconciliation/spec.md`
(that spec explicitly names this as a pending, non-blocking investigation — this file is the answer to it;
NOT written back into the spec, per the read-only constraint on this dispatch).

## Verdict: (a) DEAD, ABANDONED EXPLORATION — safe to fully ignore for the 4-way reconciliation.

No evidence anywhere (GitHub API, filesystem mtimes, deploy config, env vars, or the real product's own
history) supports treating this as a live 5th lineage. Full evidence below.

---

## Tool-access correction (task item 1)

The dispatch assumed no live GitHub/internet access might exist in this sandbox. That assumption was
**wrong** — `gh auth status` shows an authenticated session (`gh api user` → login `Eobodoechine`, token
scopes include `repo`), so every claim below about the remote repo's real, current state is a live API
read, not a guess from local git remotes.

## 1. Does `github.com/Eobodoechine/remix-of-taxahead.ai` really exist?

Yes — confirmed via `gh api repos/Eobodoechine/remix-of-taxahead.ai`:
- Private repo, owner `Eobodoechine`, default branch `main`.
- `created_at: 2026-07-13T14:32:42Z`, `pushed_at: 2026-07-13T14:32:46Z`, `updated_at: 2026-07-13T14:35:33Z`
  — the **entire remote lifetime is a ~3-minute window on one day**, nothing since.
- `stargazers_count`/`forks_count`/`watchers_count`/`open_issues_count`: all **0**.
- `gh api .../branches` → **only `main` exists on the remote**, at `bab4b1b226...` ("Created shared tax
  files" — the last of the original Lovable-platform commits).
- `gh api .../deployments` → `[]` (empty). `gh api .../pages` → 404 (no Pages site). `gh api .../actions/runs`
  → `{"total_count":0}`. `gh api .../hooks` → `[]` (no webhooks, so no Vercel/Netlify/Cloudflare GitHub
  integration was ever connected to this repo). This is a repo with **zero infrastructure attached to it
  via any GitHub-native signal.**

## 2. The local "reconciled" commit was never pushed

This is the single most decisive fact. In `~/Claude/Projects/taxahead-integration`:
- Local HEAD is `a78f135` ("Reconcile Lovable UI with verified TaxAhead behavior") on branch
  `codex/taxahead-canonical-reconciled`.
- `git branch -r --contains a78f135` → **empty**. This commit is not on any remote branch.
- `git log origin/main..HEAD` → exactly one commit: `a78f135`.
- `git status -sb` → `## codex/taxahead-canonical-reconciled` with no upstream configured, working tree clean.

So the entire "reconciliation" work product exists on exactly one laptop, was never pushed anywhere, and
the GitHub repo's own `main` branch stops one commit earlier, at the original Lovable-era `bab4b1b`.

## 3. Deploy config: what platform, and does it point at anything live? (task item 2)

Read in full: `README.md`, `package.json`, `AGENTS.md`, `.lovable/project.json`, `.wrangler/deploy/config.json`,
`.output/server/wrangler.json`, `supabase/config.toml`, `.env` (values only, no secrets reproduced here),
`docs/reconciliation-lovable-local.md`. No `vercel.json`, `netlify.toml`, or committed `wrangler.toml`/
`wrangler.jsonc` exist anywhere in the tree (checked at repo root and via `find`, node_modules excluded);
no `.github/workflows/*` exist either (only third-party packages' own workflow files under `node_modules`,
irrelevant).

- **AGENTS.md** (identical text in both repos): *"This project is connected to Lovable... Commits you push
  to the connected branch sync back to Lovable and show up in the editor"* — Lovable is the platform this
  scaffold is wired to, not an independent host.
- **package.json** devDependency `@lovable.dev/vite-tanstack-config@2.7.0` supplies a bundled Nitro
  `cloudflare` preset, which is why a Cloudflare-shaped `.output/server/wrangler.json` gets generated at
  build time — but this is inherited scaffold behavior, not a deliberate independent Cloudflare deploy setup.
- **`.output/server/wrangler.json`** (build-generated, not committed) — the one place a concrete deploy
  identity shows up:
  - `taxahead-integration`: `"name": "eobodoechine-remix-of-taxahead-ai"`
  - `taxahead` (real, live): `"name": "tanstack-start-ts"` — matches the confirmed-live
    `https://tanstack-start-ts.taxahead.workers.dev`.
  These are **different Workers project names**. Even in the most generous reading (someone ran
  `wrangler deploy` from this checkout at some point, leaving no trace in git/CI), it would publish to a
  differently-named Worker, never to the real product's URL.
- **`.env`** — the decisive backend-identity check:
  - `taxahead-integration`: `SUPABASE_PROJECT_ID="xqravevixepsgywsjrvt"` /
    `SUPABASE_URL="https://xqravevixepsgywsjrvt.supabase.co"`
  - `taxahead` (real, live): `SUPABASE_PROJECT_ID="zljqlposhekyegwamqyn"` — the confirmed migrated,
    self-managed production project.
  These are **different Supabase projects**. `xqravevixepsgywsjrvt` is Lovable's own auto-provisioned
  "Lovable Cloud" database for the Remix project (this exact ref is independently corroborated in the real
  repo's own `loop-team/session_handoff_2026-07-08.md`, where it caused a real CLI env-var collision bug
  during the migration — see below). Even if `taxahead-integration` were deployed somewhere, it would read/
  write a stale, throwaway Lovable-managed database, not the real product's data.
- **No `supabase/.temp/` directory at all** in `taxahead-integration` (the real repo has one, with
  `project-ref` = `zljqlposhekyegwamqyn` and `linked-project.json` naming the org). This means the Supabase
  CLI was **never linked/authenticated against any live backend** from this checkout — no `supabase link`,
  `db push`, or `functions deploy` was ever run here.
- **`docs/reconciliation-lovable-local.md`** (the repo's own account of itself, written 2026-07-13) frames
  this checkout explicitly as an **"integration candidate,"** not a deploy target: *"Lovable remains
  authoritative for the approved visual surface... The local TaxAhead checkout remains authoritative for
  verified product behavior."* Its own stated verification boundary: `bun run build` PASS, `bun run test`
  PASS (10 tests), `test:frontend-wiring` PASS (69 tests), **but `npx tsc --noEmit` FAIL** (typed contract
  issues) and **`bun run lint` FAIL** (formatting/lint debt across the imported tree) — with the document
  itself stating *"do not imply product readiness."* This is a self-documented, incomplete experiment.

## 4. Any activity in the last 2 days? (task item 3)

None. `find ~/Claude/Projects/taxahead-integration -newermt "2026-07-13 23:59:59" -type f` (excluding
`node_modules`/`.git`) returns **zero files**. The latest touched files in the whole tree (excluding
`.output` build junk) are `docs/reconciliation-lovable-local.md` (Jul 13 11:23) and a wrangler deploy-config
cache file (Jul 13 13:06) — both inside the same single working session the GitHub API timestamps also
bound (`pushed_at`/`updated_at` both 2026-07-13, ~14:32–14:35 UTC). Git status is clean; nothing since.

The three `codex/taxahead-reverify-{connectors,core,ui}` branches (matching the `taxahead-reverification`
directory's 3 checkouts) all point at the **same** `a78f135` HEAD — no independent later commits, just
different working-directory splits of the identical reconciled snapshot. `taxahead-reverification` itself
is **not a git repository at all** (no `.git`; confirmed by directory listing) — a plain directory of
categorized file copies, already correctly characterized as "not a code lineage" in the real product's
own reconciliation spec (see next section).

## 5. Cross-references in the real product's own history (task item 4)

- `~/Claude/Projects/taxahead/loop-team/session_handoff_2026-07-08.md` (the real product's own migration
  log) is where this whole lineage's **origin story** lives: cofounder Henry owned the original Lovable
  project (`bdb916e3-3452-4665-93e1-661fb2e75a46`, marketing page only, no app screens); direct GitHub
  access to it was blocked, so the session **remixed it into Nnamdi's own Lovable workspace**
  (`504df136-88f5-43ee-8b49-45c9d28cbee8`, display name **"Remix of taxahead.ai"**, workspace "Nnamdi's
  Lovable") to unblock building real screens. That Lovable *project* is the same thing that later got
  `git`-exported as the `remix-of-taxahead.ai` GitHub repo this investigation covers.
  - Same day, Nnamdi decided to migrate fully off Lovable. The frontend (148 files + 16 images) was
    extracted **directly from that Lovable Remix project via the Lovable MCP's read-only `list_files`/
    `read_file`** and written verbatim into the real `taxahead` repo — independently verified (file-count
    parity, byte-diffed samples, SHA-256 checks). This is *why* `README.md`, `package.json`,
    `.lovable/project.json`, and `AGENTS.md` are byte-identical between `taxahead-integration` and the real
    `taxahead` repo: **both are separate extractions of the same underlying Lovable snapshot**, not one
    derived from the other via git — consistent with the "zero shared git ancestor" finding from the prior
    investigation.
  - The same doc independently corroborates the `xqravevixepsgywsjrvt` Supabase ref found in
    `taxahead-integration`'s `.env`: it's "Lovable's own underlying Supabase Cloud project ref," which
    leaking into the real repo's working directory via the inherited `.env` caused a real CLI bug during
    the migration (Functions API preferred the env var over the properly-linked `zljqlposhekyegwamqyn`
    ref) — independently confirming this project ref belongs to Lovable's throwaway Cloud backend, not any
    product database.
  - Migration completed same day: schema + 6 edge functions live on `zljqlposhekyegwamqyn`; frontend
    repointed and deployed to Cloudflare Workers at `tanstack-start-ts.taxahead.workers.dev` (external curl
    confirmed 200, zero `__l5e` [Lovable-hosting-specific] references).
- After 2026-07-08, the real product's `fix_plan.md` mentions "the live Lovable preview" exactly once more,
  historically, as a one-time frontend-recon source used to find two UI-parity gaps (H13/H14) — not as an
  ongoing sync target or dependency.
- The **only** place `taxahead-integration` / `canonical-reconciled` is mentioned anywhere in the real
  product's docs is `loop-team/runs/2026-07-15_connector-reconciliation/spec.md`, Open Question #4 (written
  today, 2026-07-15) — which explicitly frames it as "PENDING — separate investigation dispatched
  2026-07-15, does not block this spec's plan-check" and is the exact question this file answers. No older
  document references it at all — grepped across all of `~/Claude/Projects/taxahead*/loop-team/*.md` and
  `~/Claude/Projects/taxahead*/research/**/*.md` for "remix-of-taxahead", "taxahead-integration",
  "canonical-reconciled", "taxahead-reverification", and the Lovable project ID `504df136-...` — zero other
  hits.

## 6. Do the two repos even claim to be the same product? (task item 5)

`package.json` `name` field is **identical** in both: `"tanstack_start_ts"` — but this is a wash, not a
signal either way: it's the generic Lovable TanStack-Start starter-template name, present because both
repos are extractions of the same Lovable scaffold (see #5), not because anyone asserted product identity
via this field. The `package.json` files are byte-identical in full (`diff` exit 0). What *does*
discriminate product identity is the runtime config underneath — Supabase project ref, Cloudflare Workers
name, and `supabase/.temp/` link state — all of which point away from `taxahead-integration` being a live,
in-use instance of the real product (see #3).

## 7. Recommendation and what would remove all remaining doubt (task item 6)

**Recommendation: ignore it. Treat as dead.** This is not a hedge — seven independent, concrete facts all
point the same direction, with no counter-evidence found anywhere:
1. The one meaningful commit (`a78f135`) was never pushed — it's a single-laptop artifact.
2. The GitHub repo's entire lifetime is a 3-minute window on 2026-07-13, with zero Actions/Deployments/
   Pages/webhooks/stars — no infrastructure was ever attached to it.
3. Its backend config points at a different Supabase project (Lovable's own throwaway Cloud DB), not the
   real product's `zljqlposhekyegwamqyn`.
4. Its generated Cloudflare Workers name differs from the real, confirmed-live Workers name.
5. No `supabase/.temp` link state — the Supabase CLI was never run against a live backend from this
   checkout.
6. Zero file activity anywhere in the tree after 2026-07-13.
7. The repo's own internal documentation self-describes as an incomplete "integration candidate" with
   failing typecheck/lint, explicitly disclaiming production readiness — and the real product's history
   independently explains this repo's entire origin as a now-closed, one-time frontend-extraction source
   from 2026-07-08, whose only valuable content (148 frontend files) was already copied into the real repo
   that same day.

**What would remove any remaining doubt (Nnamdi would need to check these himself; not resolvable from
this sandbox):**
- Whether a Cloudflare Worker/Pages project literally named `eobodoechine-remix-of-taxahead-ai` (or any
  other name) exists and serves traffic in Nnamdi's own Cloudflare account dashboard — I have no Cloudflare
  account API access, only what's inferable from committed config, which shows no trace of a deploy having
  happened. Nothing found suggests this was ever deployed, but a purely manual, untracked `wrangler deploy`
  from a machine/session outside this one could in principle not leave local traces — checking the
  Cloudflare dashboard directly is the only way to be 100% certain, and even if found live, it would be
  serving stale demo data against Lovable's throwaway Supabase project, not the real product's data.
- Whether the Lovable project itself (`504df136-88f5-43ee-8b49-45c9d28cbee8`, "Remix of taxahead.ai") is
  still an active workspace project anyone (Nnamdi or Henry) is still editing inside Lovable's own SaaS
  editor — a distinct question from "is there a git-based deployment," and only checkable via Lovable's own
  dashboard or the Lovable MCP's `get_project`/`list_connectors` (available in a different, separately-
  authenticated Claude Code session per the real product's own handoff notes — not something I have
  credentialed access to confirm as current fact here, only as historical record from 2026-07-08).
- Whether Henry's own separate repo (`github.com/henrynneji22-coder/taxahead.ai`, confirmed empty as of
  2026-07-08) has had anything pushed to it since — a third, distinct entity from both repos in this
  investigation, worth a quick gut-check if Henry has been independently active.

## Sources / commands used (all read-only)

- `gh api repos/Eobodoechine/remix-of-taxahead.ai` (+ `/branches`, `/deployments`, `/pages`, `/actions/runs`,
  `/hooks`) — live, authenticated GitHub API reads.
- `git log`, `git branch -a`, `git branch -r --contains`, `git status -sb`, `git log origin/main..HEAD` in
  `~/Claude/Projects/taxahead-integration` and `~/Claude/Projects/taxahead`.
- `Read`: `taxahead-integration/{README.md,package.json,AGENTS.md,.lovable/project.json,
  .wrangler/deploy/config.json,.output/server/wrangler.json,supabase/config.toml,.env,
  docs/reconciliation-lovable-local.md}` and the same paths in `taxahead` (real) for comparison.
- `find -newermt`, `stat -f "%m %Sm %N"` for mtime sweeps.
- `grep -rniE` across `~/Claude/Projects/taxahead*/loop-team/` and `~/Claude/Projects/taxahead*/research/`.
- `~/Claude/Projects/taxahead/loop-team/session_handoff_2026-07-08.md` (full read) — the real product's own
  migration log, source of the origin story in section 5.
- `~/Claude/Projects/taxahead/loop-team/runs/2026-07-15_connector-reconciliation/spec.md` (Open Question #4)
  — the consuming artifact this investigation answers.
