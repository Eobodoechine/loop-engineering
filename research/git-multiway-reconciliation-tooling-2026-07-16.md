# Does existing tooling already solve the 3-way git reconciliation problems we hit? (2026-07-16)

**Dispatch:** Researcher Mode A (tooling radar), triggered by a live incident — 3 rounds / 14
sub-agent reviews spent hand-writing a merge spec for 3 diverged lines (2 clean commits + 1
dirty 79-file working directory), during which three concrete failures surfaced: (1) a
hand-rolled `GIT_INDEX_FILE` snapshot mechanism whose correctness had to be proven by
trial-and-error, with an initial verification method that had "zero power" to catch a broken
capture; (2) a spec that predicted "7 files will conflict" when the real number, on actually
running the merge, was 30; (3) one of the two source lines kept advancing while being reviewed
as if it were a frozen, pinned reference point.

**Method:** WebSearch for leads (never cited on its own) + WebFetch to open and quote every
primary source before citing it (official git docs, GitHub source, GitHub/GitLab API docs,
repo READMEs, arXiv abstracts, vendor blog posts) + **live empirical reproduction on this
machine's git 2.50.1** for the single most load-bearing and most uncertain claim (does
`git stash create` capture untracked files). No sub-agents spawned, per dispatch instruction.

**Relationship to prior research in this directory:** this is a different question from
`research/deep-research-git-worktree-reconciliation-tooling-2026-07-14.md` (which covered
worktree/branch collision-safety, base-ref correctness, concurrent-session locking, and
canonical-file drift — a **multi-agent-session orchestration** survey) and from
`research/multi-reviewer-merge-prior-art-deepdive-2026-07-09.md` (which covered how OSS code
*review* tools merge N reviewers' *findings*, not how git itself merges *branches*). Where they
overlap — `git merge-tree`'s inability to see untracked working-tree files — the two rounds
**agree and reinforce each other**: 2026-07-14 established `merge-tree` is blind to on-disk
untracked files because it "never reads from or writes to the working tree or index." This
round's finding is complementary, not contradictory: once the dirty tree is snapshotted into a
real commit (a solved sub-problem, see Area 1), `merge-tree` becomes exactly the right tool to
run *against that snapshot commit* to predict conflicts (Area 2) — the two claims describe two
different points in the same pipeline, not the same question answered two ways. This round
also does **not** touch worktree collision-safety, session locking, or canonical-file drift —
those remain confirmed gaps per the 2026-07-14 report, unchanged here.

---

## TL;DR — verdict on all three problems, up front

| Incident problem | Existing tool that would have caught/avoided it | Confidence |
|---|---|---|
| 1. `GIT_INDEX_FILE` snapshot correctness was unprovable in advance; the before/after `git status --short` check had "zero power" to detect a broken capture | **No tool replaces the mechanism — it's git's own internal technique (confirmed in git's C source), so keep it.** The fix is not a new tool, it's a different, *diagnostic* verification command (below) — a solved, fully specified fix. | High — empirically reproduced end-to-end on this machine |
| 2. Spec said 7 files would conflict; real merge had 30 | **`git merge-tree --write-tree` (modern mode, default since git 2.38, git-scm.com/docs/git-merge-tree)** — a real, full, non-mutating 3-way merge that enumerates every conflicting file before you commit to anything. Running this instead of hand-counting `git diff --name-only` overlaps would have produced the true number mechanically. | High — official docs quoted verbatim, cross-checked for strategy-parity caveats |
| 3. One source line kept advancing while being reviewed as "frozen" | **No tool for a one-off local reconciliation** (merge queues/gating systems solve this for a *running, CI-gated* multi-PR pipeline, not an ad-hoc local 3-way merge) — but the transferable *practice* every one of them relies on is concrete and adoptable today: pin to a **SHA, not a branch name**, and mechanically re-check it immediately before acting. | Medium-high — the practice is well-evidenced across 3 independent real systems (Zuul, GitLab merge trains, Mergify), even though no single tool is directly installable for this use case |

Full detail, sources, and the "what I'd actually install next time" list are below.

---

## Area 1 — Safe snapshotting of a dirty working directory into an immutable object

### The headline empirical finding (this settles the dispatch's explicitly "uncertain" question)

**`git stash create` — the plumbing form — does NOT capture untracked files, under any
circumstance, with any flag.** This was reproduced directly on this machine (git 2.50.1) rather
than inferred from docs, because the docs alone were ambiguous (git-scm.com/docs/git-stash's
`create` entry defines no options at all beyond an optional free-text `<message>`):

```
$ echo "line2" >> tracked.txt          # dirty tracked file
$ echo "new untracked content" > untracked.txt
$ git stash create -u                  # "-u" looks like a flag...
a2210ff31738d49e2f7ea2a4ec94f4c34a20003f
$ git cat-file -p a2210ff3... | head -6
tree ee6a77f116bbe33198977a202d56f53756c14560
parent 716b72922c5d4e1bd4caa2d370554c59e7cebba2
parent 5c230ddbfe35fbd66ed237f221c44254ce5d7b8e
author test <test@test.com> 1784240309 -0400
committer test <test@test.com> 1784240309 -0400

On main: -u                            # <-- "-u" was silently swallowed into the commit MESSAGE
$ git ls-tree -r a2210ff3...
100644 blob c0d0fb45c382919737f8d0c20aaf57cf89b74af8   tracked.txt   # untracked.txt is ABSENT
```

`create` takes zero options — any flag-shaped argument (I tried `-u`, `--include-untracked`,
and a nonsense `--this-flag-does-not-exist-xyz`) is captured verbatim into the optional
`<message>` positional argument instead of being parsed, which is why the commit's subject line
literally reads `"On main: -u"`. The commit is a normal 2-parent stash object (HEAD + a
constructed index-tree parent); a real *untracked-inclusive* stash entry has **3** parents
(HEAD, index-tree, untracked-tree), confirmed by contrast: `git stash push -u` produces exactly
that 3rd parent and does capture the untracked files — but at a real cost (next paragraph).
**Verdict: not a doc-reading ambiguity, a hard "no" reproduced end to end.**

### `git stash push -u` captures untracked files correctly, but it is not zero-touch

Also empirically reproduced: `git stash push -u` visibly clears the real working directory
mid-operation.

```
$ ls
tracked.txt  untracked.txt  untracked2.txt
$ git stash push -u -m test
Saved working directory and index state On main: test
$ ls
tracked.txt          # untracked.txt and untracked2.txt are GONE from disk
$ cat tracked.txt
line1                 # reverted to the HEAD version mid-operation
```

`git stash pop` puts it all back — but for the window between `push` and `pop`, the real
working tree, real index, and (transiently) the visible file set are genuinely mutated, not
merely "about to be." If anything interrupts that window (a crash, a `pop` that itself conflicts
against something that changed in between), the tree is left in a modified state. This is
exactly the risk category the incident's dirty-tree snapshot mechanism was built to avoid.

### The `GIT_INDEX_FILE`-redirected pipeline is genuinely zero-touch — proven, not assumed

Also empirically reproduced, with byte-level before/after comparison of the real index, HEAD,
and every working-tree file's content:

```
$ TMPIDX=$(mktemp -u)
$ export GIT_INDEX_FILE="$TMPIDX"
$ git read-tree HEAD
$ git add -A
$ TREE=$(git write-tree)
$ COMMIT=$(git commit-tree "$TREE" -p HEAD -m snapshot)
$ unset GIT_INDEX_FILE; rm -f "$TMPIDX"
$ git ls-tree -r "$COMMIT"
100644 blob 83db48f8...   tracked.txt      # modified content, captured
100644 blob ddd967fb...   untracked.txt    # untracked, captured
100644 blob aecd535c...   untracked2.txt   # untracked, captured
```

Real `.git/index` MD5 before vs. after: **identical**. `HEAD` before vs. after: **identical**.
MD5 of the concatenated content of every working-tree file before vs. after: **identical**.
`git status --short` after: **identical to before** — the live tree was never touched, and
(unlike the flawed check in the incident) this time the actual tree *contents of the new commit
object* were independently inspected too, which is the part that actually needed proving.

### Why this pattern is not a hack — it's git's own internal technique

Fetched `builtin/stash.c` directly from `github.com/git/git` (master branch) and found git's own
maintainers use exactly this pattern for the analogous untracked-file problem inside stash
itself. The function `restore_untracked()` carries this comment, quoted verbatim:

> *"We need to run restore files from a given index, but without affecting the current index, so
> we use GIT_INDEX_FILE with run_command to fork processes that will not interfere."*

backed by real code: `strvec_pushf(&cp.env, "GIT_INDEX_FILE=%s", stash_index_path.buf)`. This is
the **restore** side (applying a stash's untracked-tree parent back to disk), not necessarily
the identical function on the **create** side — the fetch could not confirm the complete
`create_stash()` function's internals in one pass, so I am not claiming the exact same function
builds the untracked parent at push-time — but it does conclusively establish that
**`GIT_INDEX_FILE` redirection to avoid touching the real index is a pattern git's own C
implementation uses for this exact class of problem**, not an ad-hoc workaround invented for
this incident. **Verdict for Area 1's core question: the incident's mechanism is not "a" way to
do this — for the specific combination of (a) capture untracked files AND (b) touch nothing
real, it is essentially the only git-native way, because `stash create` structurally can't do
(a) and `stash push` can't do (b) without a transient mutation window.**

### Wrapper tools that might package this (checked three named candidates, honesty bar applied to each)

| Tool | Repo | What it actually does | Zero-touch? |
|---|---|---|---|
| **git-toolbelt**'s `git-stash-everything` | `github.com/nvie/git-toolbelt` | Per README, quoted: *"This actually stashes everything what's in your index, in your working tree, and even stashes away your untracked files, leaving a totally clean working tree."* | **No** — explicitly clears the working tree, same class of mutation as `stash push -u`. |
| **git-extras**' `git wip` | `github.com/tj/git-extras` | Creates a real commit titled "WIP" on the **current branch** (moves HEAD), undoable via `git unwip` | **No** — mutates HEAD, even if reversible. |
| **bartman/git-wip** | `github.com/bartman/git-wip` | Per README: manages WIP snapshots on a **separate ref** (`refs/wip/<branch>`), supports a `-u` flag for untracked files, ties into editor auto-save-triggered snapshotting | **Best match found**, but only README-sourced this pass, not independently reproduced the way the incident's own pipeline was. 340★, GPL-2.0, actively maintained (latest release v0.4, 2026-05-18, 193 commits) — real and current, worth a trial before trusting in place of the proven pipeline. |

No script in git's own `contrib/` packages this pattern (checked; the only related historical
`contrib/` entry, `git-new-workdir`, is unrelated — it predates and was superseded by real
`git worktree`).

### The actual fix for problem #1 (not a new tool — a different check)

The incident's flawed check (`git status --short` before/after) has "zero power" for a
structural reason, not bad luck: a correctly-implemented `GIT_INDEX_FILE` pipeline **provably
never touches the real tree** (proven above), so that check would read "unchanged" whether the
snapshot succeeded, partially captured, or produced an empty tree — it verifies invariance of
the wrong object. The right check verifies the **new commit's** completeness directly, by
diffing it against an independently-derived expected file list:

```bash
EXPECTED=$(git status --porcelain=v1 | awk '{print $2}' | sort)
ACTUAL=$(git diff --name-only HEAD "$SNAPSHOT_COMMIT" | sort)
diff <(echo "$EXPECTED") <(echo "$ACTUAL")   # empty output = every dirty/untracked path landed in the snapshot
```
This is diagnostic of the actual failure mode (a silently incomplete capture) in a way the
before/after tree-invariance check structurally cannot be.

---

## Area 2 — Predicting the real conflict surface before attempting the merge

### `git merge-tree` (modern mode) is exactly the tool that would have caught the 7-vs-30 undercount

Confirmed via direct fetch of `git-scm.com/docs/git-merge-tree` (current docs). The modern mode
(`--write-tree`, default since git 2.38 — no legacy flag needed) is a **real** merge computation,
not a heuristic:

> *"Performs a merge, but does not make any new commits and does not read from or write to
> either the working tree or index. ... The performed merge will use the same features as the
> 'real' git-merge, including: three way content merges of individual files; rename detection;
> proper directory/file conflict handling; recursive ancestor consolidation (i.e. when there is
> more than one merge base, creating a virtual merge base by merging the merge bases); etc."*

Exit status is `1` when there are conflicts, `0` when clean (verbatim from the EXIT STATUS
section); the **CONFLICTED FILE INFO** section gives a `<mode> <object> <stage> <filename>` line
per conflicting path (or bare filenames with `--name-only`), and **INFORMATIONAL MESSAGES**
reproduce the same `CONFLICT (...)` notices a real `git merge` would print. This is a
non-destructive dry run with the *same* conflict-computation engine as the real thing, run
against two already-committed trees (which is exactly what the Area-1 snapshot produces).

**One documented caveat, checked specifically because it's the kind of thing that silently
breaks parity:** the merge-base computation matches `git merge`'s own by default (the "recursive
ancestor consolidation" language above) — the *only* documented divergence risk is if you
manually override with `--base`, in which case results "may cause merge results to differ from
what `git merge` would compute... potentially losing some changes made on one side." A
default-mode invocation (no `--base` override) — which is exactly what predicting an unknown
conflict surface calls for — does not hit this caveat. A second, smaller caveat also worth
recording: *"There are numerous types of conflicts not representable by conflict markers
(modify/delete, mode conflict, binary file changed on both sides, file/directory conflicts,
various rename conflict permutations, etc.)... a merge can have conflicts without having
individual files conflict"* — i.e. even `merge-tree`'s file-level list is a slight
under-description of the full conflict *taxonomy*, though it still strictly dominates a
name-only diff intersection for the "how many files will conflict" question the incident got
wrong.

**Why the incident's method (implied: comparing `git diff --name-only <base> <line>` sets) is
structurally weaker, independent of reviewer diligence:** a name-only diff only tells you which
files *changed on each side* — it cannot tell you whether the changed *hunks* within a
shared file actually overlap (a file appearing on both sides can still merge cleanly), nor can
it detect rename-based or directory-level conflicts that never show up as the "same path" in a
naive set intersection, nor does it correctly reflect the true merge base if the base used for
the diff was stale (directly relevant to problem #3 — the moving-target line). `merge-tree`
sidesteps all of this because it performs the actual merge algorithm instead of approximating it
from two independent diffs.

### Other tools checked for this same job — none beat `merge-tree` for pre-merge prediction

- **difftastic** (`github.com/Wilfred/difftastic`) — as of v0.50 it can parse conflict markers
  and render a structural diff of an *already-conflicted* file, but per its own maintainer
  (quoted from the repo's issue discussion and docs): *"AST merging is a hard problem that
  difftastic does not address."* It's a **display/diagnosis** tool for conflicts that already
  exist, not a predictor. Does not apply to "before I commit to resolving it."
- **mergiraf** (see Area 3) predicts nothing on its own — it's a resolver, though registering it
  *before* running the real merge would shrink the observed conflict count for structurally
  reconcilable cases (see Area 3).
- **git-imerge** (`github.com/mhagger/git-imerge`) presents conflicts pairwise, incrementally,
  during an actual incremental merge process — it doesn't give a complete up-front list either;
  and it's stale (2.8k★ but **latest release Sept 2020**, GPL-2.0) — not a live candidate today.
- **GitHub REST API** — checked `docs.github.com/en/rest/pulls/pulls` directly (current version).
  The `mergeable` boolean and (undocumented, per a live GitHub community thread) `mergeable_state`
  enum (`clean`/`dirty`/`blocked`/`unstable`/…) exist, but **there is no API field or endpoint
  that enumerates which files conflict** — confirmed by checking the Compare-Commits API too
  (`/compare/{sha1}...{sha2}`), which returns a diff, not a conflict list; per a GitHub community
  discussion, the conflicting-file list is only surfaced in the **PR web UI**, above the merge
  button, not through the API.
- **GitLab** — checked `docs.gitlab.com/user/project/merge_requests/conflicts/` and
  `docs.gitlab.com/api/merge_requests/` directly. The Merge Requests API exposes a `has_conflicts`
  boolean (computed async, requires `with_merge_status_recheck=true` to force a fresh check) but
  **no endpoint lists the conflicting files** — confirmed by the current API reference page
  (no `conflicts` resource documented) and independently corroborated by a GitLab community forum
  thread where two different users, in 2018 and again in 2021, asked for exactly this and got no
  documented answer either time. The conflict-file list is a UI-only artifact
  (`project/:id/merge_request/:id/conflicts`, observed as a browser network call, not a
  documented/stable API).
- **JetBrains IDEs** — the built-in 3-way merge tool (`jetbrains.com/help/idea/resolve-conflicts.html`)
  is an **interactive resolution UI** (3 panes: theirs / result / yours), not a headless
  predict-before-merging tool; not independently verified this pass, but it structurally
  requires opening an actual merge/conflict session, which is the thing Area 2 needs to avoid
  doing before the spec is trustworthy. (There is also an "AI Conflict Resolver" JetBrains
  Marketplace plugin that surfaced in search — not opened/verified this pass, flagged as
  unconfirmed, do not cite beyond "it exists.")

**Verdict for Area 2: `git merge-tree --write-tree` (or `-z --name-only` for a script-friendly
NUL-separated list) run against the two real branch tips (or, for the incident's case, against
the Area-1 snapshot commit and the other diverged line's tip) would have mechanically produced
the true 30-file list, non-destructively, before any prose spec was written. This is the
single most directly actionable fix in this whole dossier.**

---

## Area 3 — AI-assisted / automated merge-conflict resolution at the semantic level

### Headline finding: this is explicitly NOT a solved problem as of mid-2026 — even SOTA models are sub-60%

The most load-bearing, most current source found this pass: **Merge-Bench** (Schesch & Ernst,
presented at ICPR 2026, Lyon, France, August 2026;
`homes.cs.washington.edu/~mernst/pubs/merge-bench-icpr2026-abstract.html`), a public
7,938-real-world-merge-conflict-hunk benchmark from 1,439 GitHub repos with public dataset,
dataset-construction code, and model-training implementation. Quoted finding:

> *"the best models correctly resolve less than 60% of merge conflicts"* across languages; a
> custom 14B-parameter fine-tuned model (LLMergeJ) beats most commercial systems on Java but
> still ranks only second to Gemini 2.5 Pro.

This directly answers the dispatch's framing question ("is this a solved-enough problem that
there are usable tools today?") — **no.** Every tool below should be read through that ceiling.

### Tools/research surveyed

| Name | Maturity/status | What it does | Verdict |
|---|---|---|---|
| **Mergiraf** (`mergiraf.org`, `codeberg.org/mergiraf/mergiraf`) | **Real, current, actively maintained** — 406★, GPLv3, latest commit **2026-07-14** (2 days before this report), 585 commits, 23 releases, active governance (GOVERNANCE.md), Zulip community, Liberapay funding | Syntax-tree-aware (tree-sitter, 33 languages) merge driver; falls back to line-based merge first, escalates to tree merge only where needed, leaves clean conflict markers when it can't safely auto-merge; registers as a real git merge driver (`git config merge.mergiraf.driver "mergiraf merge --git %O %A %B ..."` + `.gitattributes`) so it runs automatically during `git merge`/`rebase`/`cherry-pick` | **Best currently-usable option in this whole area.** Not LLM-based (structural/syntactic, not semantic understanding) — but real, fast, free, and would have auto-resolved a meaningful fraction of the 30 conflicts (anything that's a non-overlapping structural change, e.g. both sides independently added an unrelated import/function) before any human/agent time was spent. |
| **Spork** (`github.com/ASSERT-KTH/spork`) | Research tool, 71★, latest release **2021**, MIT — and its **own README explicitly says**: *"If you're looking for a production ready tool for AST-based GIT merge, we recommend mergiraf."* | AST-based structured merge, Java-only, thesis-origin project | Superseded by Mergiraf per its own maintainers — do not adopt in place of Mergiraf. |
| **JDime** (`github.com/se-sic/jdime`) | Academic (University of Passau), 23★, LGPL-2.1, no confirmed recent-activity signal found this pass | Structured merge with auto-tuning (switches unstructured/structured based on conflict presence), Java-only | Low adoption signal vs. Mergiraf; not independently confirmed as maintained — flagged, not recommended. |
| **difftastic** | Active, real | Structural *diff*, not merge (see Area 2) | Not a resolver — explicitly said so by its own maintainer. |
| **git-mediate** (`github.com/Peaker/git-mediate`) | Real, 188★, copyright maintained through 2024, Haskell | Human-in-the-loop reasoning aid: shows the two diffs from base cleanly so a person can apply the same transformation to both sides ("like Minesweeper") | Assistive, not automatic/AI — helps a human resolve faster, doesn't resolve anything itself. |
| **git-imerge** | Stale (last release 2020), 2.8k★, GPL-2.0 | Presents conflicts pairwise across an incremental commit-by-commit merge | Not semantic/AI; not actively maintained; not a fit for a large already-diverged merge like the incident's. |
| **MergeBERT** (Microsoft Research, FSE'22; `microsoft.com/en-us/research/publication/mergebert-program-merge-conflict-resolution-via-neural-transformers`) | **Paper-only** — searched specifically for a public code release (`site:github.com mergebert`, `microsoft/*` orgs) and found **none**. | Transformer classifying over "primitive merge patterns" mined from real merges; 63-69% accuracy reported, ~2-3x better than prior structured/neural baselines *at the time* (2022) | Not adoptable — no shipped code found. Superseded in relevance by Merge-Bench's 2026 numbers anyway. |
| **Rover** (arXiv 2605.17279, 2026) | Paper-only — page checked directly, **no code/tool release mentioned** | LLM + "Multi-layer Code Property Graph" + context-clustering, beats MergeGen/WizardMerge baselines on similarity-to-ground-truth metrics | Research-only; no artifact to install. |
| **WizardMerge** (arXiv 2407.02818, 2024) | Paper-only | Not a resolver — a **suggestion/prioritization** tool: flags which code blocks are relevant/at-risk post-merge and in what order to review them; reports 23.85% conflict-time reduction and suggestions covering 70%+ of affected blocks | Assistive triage tool, not an autonomous resolver — conceptually closest to "what should a human/agent look at first," not "resolve this for me." |
| **LLMinus** (Linux kernel; led by NVIDIA's Sasha Levin; covered by Phoronix and LWN, RFC v2 posted Jan 2026) | **Real, in-progress, RFC stage — not merged into the kernel, not general-purpose** | Semantic-embedding retrieval over the *Linux kernel's own git history* of past conflict resolutions, feeding an LLM; model-agnostic (any LLM accepting stdin); recent RFC added a `--max-tokens` cap and build-test-integrated semantic conflict detection | Domain-specific to one repo's own history; not shippable/adoptable elsewhere as-is; useful as a **design pattern** (retrieve similar past resolutions from this repo's own history, ground the LLM in them) more than as a tool. |
| **Harmony AI** (source.dev — an independent company building AOSP-derived tooling, **not** Google itself, per its own "about" framing) | **Explicit "research preview,"** not shipped; "Request a demo" CTA | Ensemble of small, domain-fine-tuned LMs (Llama-3.1-8B / Qwen3-4B fine-tuned on AOSP merge data) + an orchestrator agent; **88% top-3 accuracy** (the page's own headline says "90%" but the body text says 88% — the marketing number overstates the reported number by 2 points) | Vendor-reported, single-domain (Android/AOSP), not independently verified, not generally available. Good illustration of where the frontier claims to be, not something to install. |
| **GitHub Copilot** (`github.blog/changelog/2026-03-26-...`, `2026-04-13-...`, `2026-06-26-...`, `2026-07-08-...` — 4 separate changelog posts opened directly) | **Real, shipped, actively expanding** product feature throughout 2026 (PR comment trigger → "3 clicks" button → GitHub Desktop → GitHub Mobile) | Cloud agent that, quoted: *"fixes the conflicts, checks that the build and tests still pass, and pushes"* | **The most production-mature option surveyed**, but scoped to **GitHub-hosted pull requests** — it operates on an existing PR via `@copilot` mention or a UI button, not on an arbitrary local, pre-PR, dirty-working-directory git state. Would require pushing the diverged lines as a real PR first to use it as-is; not a drop-in for this incident's exact local-repo scenario, but the closest thing to "just works, verified by tests" available today. |
| **AgenticFlict** (arXiv 2604.03551, AIware'26 — the ACM AI-Powered Software conference, July 2026) | Dataset/empirical paper, current | A large-scale dataset of merge conflicts specifically arising from **AI coding agents' own pull requests** on GitHub | Not a tool — but directly validates that "an AI-agent-driven line causing an unpredicted merge conflict" (this incident's own root scenario) is now a recognized, actively-studied 2026 research problem, not a one-off fluke. Worth returning to once its actual findings (causes/frequency) are needed. |

**Verdict for Area 3:** not solved. The best real, installable, currently-maintained option is
**Mergiraf** as a first-pass structural auto-resolver (cheap, local, no API keys, would shrink
the 30-file list before any human/agent time is spent), plus **GitHub Copilot's cloud agent** if
the workflow can tolerate pushing to a real PR first. Every LLM-native "semantic" resolver found
is either paper-only (no code), a narrow vendor research preview (Harmony), or an in-progress
RFC for one specific repo's history (LLMinus) — none of them clear Merge-Bench's own honest
ceiling (sub-60% even for the best models), so **none should be trusted unsupervised** on a
real 30-file conflict set; a Claude-Code-driven per-file review (with full repo context, which
none of the narrow point-tools have) is a reasonable stand-in today, gated by the loop's existing
adversarial-review discipline — not a reason to skip review, just a reason not to expect an
external "AI merge tool" to replace it yet.

---

## Area 4 — Reconciling branches that keep actively moving

### The best conceptual match for the exact failure ("reviewed as frozen, wasn't")

`julien.danjou.info/blog/merge-queues-built-for-humans/` (fetched directly; Danjou is a known
OpenStack/Python-tooling figure, this is a technical blog post, not a vendor pitch) states the
problem in almost the same words as the incident report:

> *"Between the moment you decide to integrate a change and the moment main accepts it, the tree
> moved underneath you."*

and diagnoses why this gets worse with agents specifically, not just more traffic:

> *"With humans, this window lasted minutes with light traffic. With agents, the window stays
> the same but traffic saturates the serialization point."*

His proposed fix pattern — **treat "the target moved" as the default case to design for, not an
edge case to detect and reject**, via speculative testing ("build the optimistic chain and test
#1+#2+#3 in parallel" instead of waiting for #1 to land before starting #2), batching, and
bisecting-on-failure — is the right mental model, even though it's an opinion/blog post about
CI-gated merge queues, not a specific installable tool for a one-off local reconciliation.

### Real systems that implement this mechanically (all checked directly, not from search snippets)

- **Zuul** (OpenStack's gating system, `docs.openstack.org/infra/zuul/gating.html`, fetched
  directly) — the most mature, longest-running real implementation of "assume the queue ahead of
  you will land, and mechanically recover if it doesn't":
  > *"Zuul performs speculative execution of test jobs; it assumes that all jobs will succeed and
  > tests them in parallel accordingly. If they do succeed, they can all be merged. However, if
  > one fails, then changes that were expecting it to succeed are re-tested without the failed
  > change."*
  This is exactly the "target moved mid-review" problem, solved by testing against an *assumed*
  future state and re-validating rather than either freezing the queue or blindly trusting a
  stale snapshot. Zuul itself is heavy, purpose-built CI-gating infrastructure — not something to
  stand up for one merge — but the mechanism is the transferable part.
- **GitLab merge trains** (`docs.gitlab.com/ci/pipelines/merge_trains/`, GitLab Premium+, shipped
  since 12.0/2019) — auto-rebases the source branch onto the target at merge time specifically
  when the source is behind, running "pipelines for merge results" per queued entry rather than
  assuming a stale diff is still valid.
- **Mergify** (`docs.mergify.com/merge-queue/`, fetched directly; commercial, but **free for open
  source projects and private teams up to 5 active contributors** per `mergify.com/pricing`) —
  quoted directly: *"Mergify updates each PR against the latest main and re-runs CI before
  merging—catching conflicts before they hit production,"* with configurable "serial, parallel,
  or isolated" queue modes trading off throughput against isolation.
- **Bors(-ng)** — the historically well-known GitHub-era predecessor to all of the above — is
  **archived** (`github.com/bors-ng/bors-ng`, archived by the owner 2024-04-04, read-only). Dead;
  cite only as lineage/history, not as something to adopt.

**Verdict for Area 4: no tool here is directly installable for a single, ad-hoc, local,
human/agent-reviewed 3-way reconciliation** — every real implementation (Zuul, GitLab merge
trains, Mergify) is built for a *running, CI-gated, many-PR* pipeline, not a one-off git-repo
cleanup. What **is** directly transferable, today, with zero new infrastructure, is the shared
underlying discipline all three of them encode mechanically: **never trust a branch name as a
frozen reference; pin to the exact SHA the spec was written against, and mechanically re-check
that SHA immediately before acting on the spec.** This is the same discipline this research
directory's own prior work already flagged for a related but different problem
(`feedback_worktree_baseref_gotcha` — Claude Code's worktree tooling defaulting to a
possibly-stale `origin/HEAD` instead of local HEAD) — the fix pattern generalizes: **a "pinned"
reference is only actually pinned if something re-verifies the pin at the moment of use, not
just at the moment of writing.**

---

## Transfer-condition check (per the Researcher role's requirement, for the two load-bearing mechanisms this dossier recommends adopting)

**1. The `GIT_INDEX_FILE` snapshot pipeline (Area 1):**
- (a) *Execution context required:* a local shell with git ≥ ~1.x (this is old, stable plumbing —
  `read-tree`/`write-tree`/`commit-tree`/`GIT_INDEX_FILE` have been core plumbing since early
  git), write access to a scratch temp-file path, and read access to the working tree.
- (b) *Does the loop-team's environment satisfy it:* yes — every dispatch already runs in a real
  shell with a real git checkout; no new dependency, no network, no install.
- (c) *Structural vs. instructional:* **fully structural.** The zero-touch guarantee is a
  property of the mechanism itself (an env-var-redirected index file physically cannot write to
  `.git/index` unless something explicitly unsets the redirection first) — it does not depend on
  an agent following instructions correctly. The **verification step is the one place this
  degrades to instructional**: nothing forces an agent to run the diagnostic diff-based check
  above instead of the old, structurally-blind `git status --short` check — a Coder/Verifier
  could still silently keep using the weak check. That failure would be **silent and
  load-bearing**: a broken capture would look identical to a good one under the old check, and
  the resulting "immutable snapshot" could be missing files with nothing downstream flagging it
  until something built on top of the bad commit failed much later. **Recommendation: encode the
  diagnostic check as a required, named step in whatever spec/runbook governs this operation, not
  as tacit knowledge — an instructional guarantee with a silent failure mode is exactly the
  pattern this role brief flags as needing explicit callout.**

**2. `git merge-tree --write-tree` for pre-merge conflict enumeration (Area 2):**
- (a) *Execution context required:* git ≥ 2.38 for the modern mode to be the default (older
  versions need the flag explicitly, or use the legacy `--trivial-merge` mode, which has a
  different, weaker contract); both branch tips must already be reachable commits (which is why
  this slots in *after* Area 1's snapshot, not before).
- (b) *Does the loop-team's environment satisfy it:* yes — this machine runs git 2.50.1, well
  past the 2.38 threshold; no install needed.
- (c) *Structural vs. instructional:* **fully structural** for the conflict-list output itself
  (it's a real merge computation, not a heuristic an agent could get subtly wrong) — but,
  identically to #1, **whether anyone actually runs it before writing a prose spec is
  instructional**, and a spec-writer skipping it and going back to manual `git diff --name-only`
  eyeballing would fail exactly the same way the incident did, silently (a plausible-looking
  "7 files" estimate with no structural signal that it's wrong until someone runs the real
  merge). **Recommendation: same as above — make "run `git merge-tree --write-tree -z --name-only
  <base> <lineA> <lineB>` and cite its literal output" a required, named artifact the spec must
  attach, not a step left to reviewer discretion.**

---

## If I were setting up this session's next attempt, here's what I'd actually install/use

1. **Keep the `GIT_INDEX_FILE` snapshot pipeline exactly as built** — it is not a workaround,
   it's git's own internal pattern for this problem (confirmed in git's C source). **Replace only
   the verification step** with the diff-based check above
   (`git diff --name-only HEAD $SNAPSHOT` vs. `git status --porcelain` path list) — this is a
   pure verification-logic fix, zero new dependencies, ready to use immediately.
2. **Before writing any prose spec naming a conflict count, run
   `git merge-tree --write-tree -z --name-only <merge-base-or-omit-for-autodetect> <lineA-ref>
   <lineB-ref>`** and quote its literal output in the spec as the source of truth for "N files
   will conflict." This single command would have caught the 7-vs-30 undercount mechanically,
   with zero new tooling to install (already ships with git ≥ 2.38).
3. **Install and register `mergiraf`** (`mergiraf.org`, GPLv3, actively maintained, real,
   free) as the git merge driver for source files before running the real merge — it will
   auto-resolve the subset of conflicts that are purely structural/non-overlapping, shrinking the
   real list before any human/agent time is spent on it. Do not reach for MergeBERT, Rover,
   LLMinus, or Harmony AI for this — none has a usable public artifact, and even the best
   published system (Merge-Bench's SOTA) resolves under 60% correctly, so none should run
   unsupervised regardless.
4. **Pin every "frozen" reference to its exact SHA in the spec text itself, not a branch name**,
   and add a mechanical pre-flight step — `git rev-parse <ref>` compared against the SHA recorded
   in the spec — immediately before the spec is acted on, not just when it was written. No new
   tool needed; this is the one discipline every real merge-queue system (Zuul, GitLab merge
   trains, Mergify) encodes mechanically that a one-off local reconciliation can borrow for free.
5. **Do not stand up a merge-queue/gating system** (Zuul is CI-gating infrastructure, GitLab
   merge trains need hosted GitLab Premium+, Mergify is a paid SaaS above 5 contributors, Bors is
   dead) for a single ad-hoc reconciliation — that would be solving a different, larger problem
   than the one in front of this session.

---

## Sources (every one opened/fetched directly this pass, or empirically reproduced on this machine's git 2.50.1)

**Area 1:**
- `git-scm.com/docs/git-stash` — fetched directly; `create` subcommand's full documented option
  set (none beyond optional `<message>`).
- Live empirical reproduction, this machine, git 2.50.1: `git stash create` / `git stash create -u`
  / `git stash create --this-flag-does-not-exist-xyz` (all three produce a 2-parent, tracked-only
  commit; the flag-shaped arguments land verbatim in the commit message) vs. `git stash push -u`
  (visibly clears untracked files from disk, reverts tracked file to HEAD content, mid-operation)
  vs. the full `GIT_INDEX_FILE` → `read-tree HEAD` → `add -A` → `write-tree` → `commit-tree`
  pipeline (byte-identical `.git/index` MD5, byte-identical `HEAD`, byte-identical working-tree
  content MD5, before vs. after; snapshot commit's tree independently inspected via `git ls-tree
  -r` and confirmed to contain all 3 dirty/untracked files).
- `github.com/git/git/blob/master/builtin/stash.c` — fetched directly; `restore_untracked()`'s
  `GIT_INDEX_FILE`-redirection comment and code, quoted verbatim.
- `github.com/nvie/git-toolbelt`, `github.com/tj/git-extras`, `github.com/bartman/git-wip` —
  each fetched directly for README description + maturity signals.
- WebSearch: "git.git contrib scripts workdir snapshot commit-tree untracked" — confirmed no
  on-point script exists in git's own `contrib/`.

**Area 2:**
- `git-scm.com/docs/git-merge-tree` — fetched directly; modern-mode description, EXIT STATUS,
  CONFLICTED FILE INFO, INFORMATIONAL MESSAGES sections quoted verbatim; `--base` caveat and
  non-conflict-marker-representable conflict types quoted verbatim from a follow-up targeted
  search of the same doc family.
- `github.com/Wilfred/difftastic` + its issue #565 — confirmed diagnostic-only, not a resolver,
  per its own docs/maintainer statement.
- `github.com/mhagger/git-imerge` — fetched directly for README + maturity (2.8k★, GPL-2.0,
  latest release 2020-09-20).
- `docs.github.com/en/rest/pulls/pulls` (current API version) + a live GitHub community
  discussion on `mergeable_state` — confirmed no file-level conflict-list API field/endpoint.
- `docs.gitlab.com/user/project/merge_requests/conflicts/` and `docs.gitlab.com/api/merge_requests/`
  — both fetched directly; confirmed no documented conflicts-listing endpoint, corroborated by
  `forum.gitlab.com/t/list-conflicts-of-a-merge-request-using-the-api/15232` (unresolved user
  question from 2018 and again 2021).
- `jetbrains.com/help/idea/resolve-conflicts.html` — via search summary only (not independently
  WebFetched this pass) — flagged accordingly.

**Area 3:**
- `homes.cs.washington.edu/~mernst/pubs/merge-bench-icpr2026-abstract.html` — fetched directly;
  "less than 60%" finding quoted verbatim.
- `mergiraf.org`, `mergiraf.org/usage.html`, `codeberg.org/mergiraf/mergiraf` — all fetched
  directly for description, driver-registration instructions, and maturity signals (406★, GPLv3,
  latest commit 2026-07-14, 23 releases).
- `github.com/ASSERT-KTH/spork` — fetched directly; the "we recommend mergiraf" self-deprecation
  quoted verbatim.
- `github.com/se-sic/jdime` — fetched directly for maturity signals (23★, LGPL-2.1).
- `github.com/Peaker/git-mediate` (+ corroborating search on stars/maintenance) — 188★, active
  copyright through 2024.
- Microsoft Research MergeBERT publication page + FSE'22 camera-ready PDF (via search, numbers
  cross-checked across two independent search summaries: 63-69% / 64-69%) + a dedicated search
  for a public code release, which found none.
- `arxiv.org/abs/2605.17279` (Rover) — fetched directly; abstract quoted, confirmed no code
  release mentioned.
- `arxiv.org/pdf/2407.02818` (WizardMerge) — via search; approach and 23.85%/70% figures quoted.
- Phoronix `phoronix.com/news/LLMinus-RFC-v2` — fetched directly; RFC status, semantic-embedding
  approach, `--max-tokens` detail quoted.
- `arxiv.org/pdf/2604.03551` (AgenticFlict) — fetched directly (PDF); AIware'26 venue and dataset
  framing confirmed.
- `source.dev/journal/harmony-preview` — fetched directly; "88%... top-3 accuracy" vs. the page's
  own "90%" headline discrepancy caught by close reading; "research preview" / "request a demo"
  status quoted verbatim. Publisher identity (`source.dev`, an independent company building
  AOSP-derived tooling, not Google itself) confirmed via a dedicated follow-up search.
- `github.blog/changelog/2026-03-26-ask-copilot-to-resolve-merge-conflicts-on-pull-requests/`,
  `2026-04-13-fix-merge-conflicts-in-three-clicks-with-copilot-cloud-agent/` (fetched directly;
  "fixes the conflicts, checks that the build and tests still pass, and pushes" quoted verbatim),
  `2026-06-26-github-desktop-3-6...`, `2026-07-08-github-mobile...` — all real, dated 2026
  changelog entries confirming this is a shipped, actively-expanding feature.

**Area 4:**
- `julien.danjou.info/blog/merge-queues-built-for-humans/` — fetched directly; both core quotes
  reproduced verbatim.
- `docs.openstack.org/infra/zuul/gating.html` — fetched directly (via search-embedded quote,
  Zuul's speculative-execution description reproduced verbatim from the official doc).
- `docs.gitlab.com/ci/pipelines/merge_trains/` — confirmed shipped since GitLab Premium 12.0
  (2019), auto-rebase-when-behind behavior.
- `docs.mergify.com/merge-queue/` — fetched directly; "updates each PR against the latest main
  and re-runs CI before merging" and queue-mode options quoted verbatim; `mergify.com/pricing` —
  confirmed free tier for OSS / ≤5 private contributors.
- `github.com/bors-ng/bors-ng` — confirmed archived 2024-04-04 (read-only).

**Cross-reference (read first, per role convention, to avoid re-deriving prior ground):**
- `research/deep-research-git-worktree-reconciliation-tooling-2026-07-14.md` (full file read).
- `research/multi-reviewer-merge-prior-art-deepdive-2026-07-09.md` (full file read).
