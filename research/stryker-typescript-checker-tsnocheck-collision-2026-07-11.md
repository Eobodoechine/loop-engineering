# Stryker `@ts-nocheck` sandbox-injection collision — root mechanism, and the sound fix

**Date:** 2026-07-11
**Mode:** D (domain research for an active build)
**Build:** padsplit-cockpit Stryker mutation-testing adoption, worktree
`~/Claude/loop-worktrees/padsplit-stryker-mutation-testing/web/`
**Installed versions (confirmed from `node_modules/@stryker-mutator/*/package.json`):**
`@stryker-mutator/core` 9.6.1, `@stryker-mutator/typescript-checker` 9.6.1,
`@stryker-mutator/vitest-runner` 9.6.1.

## TL;DR answer to the dispatch question

**`checkers: []` is NOT a sound fix.** It targets the wrong mechanism. The
`@ts-nocheck` injection that broke `tests/airbnb-calendar-ui-actions.test.ts` is
driven entirely by a *separate*, always-on, top-level Stryker option called
**`disableTypeChecks`** (default `true`), not by the `checkers` array or the
`@stryker-mutator/typescript-checker` package. Emptying `checkers` would not stop
the injection, and — separately, as a bonus finding — the `checkers` array is
*already inert* during a dry run/coverage-analysis pass regardless of its
contents, because the checker's actual `.check()` call only happens later, per
mutant, in the real mutation-testing phase. The correct, narrowly-targeted,
documented fix is to set `disableTypeChecks: false` (or a glob scoped only to
`src/lib/db-rls.ts`) as a sibling option next to `checkers`/`mutate` in
`stryker.config.mjs`, and — as a complementary safety measure for the
one-time derivation run specifically — pair it with the documented
`dryRunOnly: true` option, which guarantees the run stops after the dry run and
never reaches real per-mutant mutation testing at all.

---

## 1. Does Stryker support disabling the typescript-checker while keeping the test runner? Does `checkers: []` stop the `@ts-nocheck` injection?

**No — `checkers: []` does not stop the injection, because the injection is not
part of the checker plugin at all.** This is confirmed by reading the actual
installed source, not the checker package (`@stryker-mutator/typescript-checker`
has no reference to `ts-nocheck` anywhere in its own `dist`/`src` — confirmed by
`grep -ril "nocheck"` returning zero hits in that package's tree). The mechanism
lives in **`@stryker-mutator/core`**:

- `node_modules/@stryker-mutator/core/src/sandbox/disable-type-checks-preprocessor.ts:21`
  — class `DisableTypeChecksPreprocessor implements FilePreprocessor`. Its doc
  comment (lines 17-20):
  ```
  /**
   * Disabled type checking by inserting `@ts-nocheck` atop TS/JS files and removing other @ts-xxx directives from comments:
   * @see https://github.com/stryker-mutator/stryker-js/issues/2438
   */
  ```
  It reads `this.options.disableTypeChecks` (line 34: `new FileMatcher(this.options.disableTypeChecks)`), NOT `this.options.checkers`.

- `node_modules/@stryker-mutator/core/src/sandbox/create-preprocessor.ts:18-27`
  — `createPreprocessor()` unconditionally builds a `MultiPreprocessor` containing
  `DisableTypeChecksPreprocessor` (line 21-24) plus `TSConfigPreprocessor`
  (line 25). There is no branch on `checkers` here at all.

- `node_modules/@stryker-mutator/core/src/process/2-mutant-instrumenter-executor.ts:76-78`
  — the instrumentation/preprocessing phase (step 2 of Stryker's pipeline,
  which runs on **every** Stryker invocation, before the dry run):
  ```
  const preprocess = this.injector.injectFunction(createPreprocessor);
  this.writeInstrumentedFiles(instrumentResult);
  await preprocess.preprocess(this.project);
  ```
  This runs regardless of whether `checkers` is `[]`, `['typescript']`, or
  anything else — `checkers` is never read anywhere in this file.

- Separately, the checker's actual `.check()` invocation lives only in
  `node_modules/@stryker-mutator/core/src/process/4-mutation-test-executor.ts:237`
  (`this.checkerPool.schedule(group$, (checker, group) => checker.check(checkerName, group))`)
  — step 4, the real per-mutant mutation-testing phase. It is **not** called
  anywhere in step 3 (`3-dry-run-executor.ts`, the dry run/coverage-analysis
  phase). Confirmed by `grep -n "checkerPool\|check(" 4-mutation-test-executor.ts`
  returning the only `.check(` call site in the whole `core/src/process/` tree.

**Consequence:** during a dry run (or a `dryRunOnly` pass — see §5), the
`checkers` array is never consulted at all. Setting it to `[]` changes nothing
about the crash, and is simultaneously a no-op for that specific run (harmless,
but not a fix).

## 2. Is there a documented, narrower alternative to turning the checker off entirely?

**Yes — the actual, documented lever is the top-level `disableTypeChecks`
option**, which is a sibling of `checkers` in the config schema, not nested
inside it:

- Schema definition, `node_modules/@stryker-mutator/core/schema/stryker-schema.json:456-470`:
  ```
  "disableTypeChecks": {
    "description": "Set to 'true' to disable type checking, or 'false' to
    enable it. For more control, configure a pattern that matches the files of
    which type checking has to be disabled. This is needed because Stryker
    will create (typescript) type errors when inserting the mutants in your
    code. Stryker disables type checking by inserting `// @ts-nocheck` atop
    those files and removing other `// @ts-xxx` directives (so they won't
    interfere with `@ts-nocheck`). The default setting allows these directives
    to be stripped from all JavaScript and friend files in `lib`, `src` and
    `test` directories.",
    "oneOf": [{"type": "boolean"}, {"type": "string"}],
    "examples": ["{test,src,lib}/**/*.{js,ts,jsx,tsx,html,vue,cts,mts}"],
    "default": true
  }
  ```
- The matcher logic that consumes this option,
  `node_modules/@stryker-mutator/core/src/config/file-matcher.ts:12-23`:
  ```js
  constructor(pattern, allowHiddenFiles = true) {
    if (typeof pattern === 'string') {
      this.pattern = normalizeFileName(path.resolve(pattern));
    } else if (pattern) {
      this.pattern = '**/*.{js,ts,jsx,tsx,html,vue,mjs,mts,cts,cjs}';
    } else {
      this.pattern = pattern; // false → matches nothing
    }
  }
  ```
  So: `disableTypeChecks: false` matches **zero** files (injection fully off).
  `disableTypeChecks: 'src/lib/db-rls.ts'` (a glob/path string) matches
  **only** that file, leaving every other file's sandbox content byte-identical
  to source. Either is a documented, first-class, narrower alternative to
  touching `checkers` at all.
- Official docs page (`stryker-mutator.io/docs/stryker-js/configuration/`)
  confirms the same description text and default (`true`) — fetched and
  cross-checked against the local schema, they match verbatim.
- **Official troubleshooting page corroborates this is the documented fix for
  this exact class of problem**, and — importantly — treats it as a *separate*
  troubleshooting scenario from the checker:
  `stryker-mutator.io/docs/stryker-js/troubleshooting/` states (quoted from the
  fetched page): "The initial test run might fail when you're using ts-jest or
  tsx. The reason for this is that Stryker will mutate your code and, by doing
  so, introduce type errors into your code," and the recommended fix is to
  **override `disableTypeChecks`** with a wider/narrower glob, e.g.
  `"disableTypeChecks": "app/**/*.{js,ts,jsx,tsx,html,vue}"` — not to touch
  `checkers`. The same page's *separate* section on surviving mutants that
  compile but aren't caught recommends the opposite direction — **adding**
  `checkers: ["typescript"]` — confirming the two options solve two distinct
  problems and are documented independently of one another.

## 3. Real prior-art instances of this exact collision

- **`stryker-mutator/stryker-js` issue #2438** — "Discussion: TypeScript
  compile errors with mutation switching"
  (https://github.com/stryker-mutator/stryker-js/issues/2438) — this is the
  issue the `DisableTypeChecksPreprocessor` source comment itself cites
  (`disable-type-checks-preprocessor.ts:19`). A maintainer quote surfaced by
  fetching the issue: "In a mutation switching world, we will create
  (typescript/flow) type errors. This is by design; it would be almost
  impossible to prevent it," and: "Note that errors can also be produced by
  test files, even though they're not mutated. Mutating production code can
  change the return type" — i.e. the `@ts-nocheck` sandbox-wide injection was
  designed and confirmed by the maintainers to intentionally reach test files
  and non-mutated files, not just the mutated file itself. This is the origin
  of the exact mechanism causing the collision.
- **`stryker-mutator/stryker-js` issue #2569** — "Stryker breaks the jest
  environment change and tests fail" — a close structural cousin of this
  exact bug class: Stryker's injected `// @ts-nocheck` line landed above a
  `/** @jest-environment jsdom */` docblock comment and broke that directive's
  effect, because the directive depended on being the literal first line/
  first docblock of the file — the same "first-line-content-assertion breaks"
  shape as this codebase's `startsWith("'use server'")` check. The documented
  workaround cited for it is the same one: narrow `disableTypeChecks` via glob
  to exclude the affected files.
- I could not find a GitHub issue reporting *literally* a test asserting
  `'use server'`/first-line-content specifically (this codebase's exact
  assertion is project-specific), but #2438 and #2569 together establish this
  is a known, recurring collision class with an established, maintainer-
  endorsed fix pattern (narrow the `disableTypeChecks` glob), not a novel edge
  case this build hit for the first time.

## 4. Does `checkers: []` for a coverage-only/dry-run pass interact with `coverageAnalysis`?

**No interaction — they are fully independent subsystems, confirmed both from
source and from official docs:**

- `coverageAnalysis` (`off` / `all` / `perTest`) is read and passed straight
  into the test runner's `dryRun()` call in
  `node_modules/@stryker-mutator/core/src/process/3-dry-run-executor.ts:166-172`:
  ```js
  const result = await testRunner.dryRun({
    timeout: dryRunTimeout,
    coverageAnalysis: this.options.coverageAnalysis,
    disableBail: this.options.disableBail,
    files: dryRunFiles,
    testFiles,
  });
  ```
  This is entirely handled by the **test runner** (here,
  `@stryker-mutator/vitest-runner`), not by any checker.
- Per the official docs (`stryker-mutator.io/docs/stryker-js/configuration/`,
  fetched and quoted): "**Off:** Stryker does no optimization. All tests are
  executed for each mutant." / "**All:** Stryker will determine the mutants
  covered by your tests during the initial test run phase..." / "**PerTest:**
  Stryker will determine which tests cover which mutant during the initial
  test run phase. Only the tests that cover a specific mutant are executed for
  each mutant." None of these three modes' descriptions reference `checkers`.
- Structurally: the checker's `.check()` call lives only in step 4
  (`4-mutation-test-executor.ts:237`), which never runs during the dry run
  (step 3) that produces the coverage map. So `checkers: []` (or any value)
  has **zero** effect on `coverageAnalysis`/`perTest` derivation, in either
  direction — it is neither required nor harmful for that purpose. It's just
  the wrong lever entirely for the actual bug.

## 5. Alternative if `checkers: []` is unsound: is there a way to bound the exposure of a `testFiles`-unset dry run without a cheaper coverage mechanism?

**There is no cheaper "list covering tests for file X" command** distinct from
an actual dry run — `perTest` coverage analysis fundamentally requires one real
execution of the discovered test files with coverage instrumentation active;
that IS the empirical discovery mechanism the build wants, and there's no
documented shortcut around executing it once.

**But there is a documented, first-class option that bounds the *exposure* of
that one execution — `dryRunOnly`:**

- Schema: `node_modules/@stryker-mutator/core/schema/stryker-schema.json:329-333`:
  ```
  "dryRunOnly": {
    "description": "Execute the initial test run only without doing actual
    mutation testing. Dry run only will still mutate your code before doing
    the dry run without those mutants being active, thus can be used to test
    that StrykerJS can run your test setup. This can be useful, for example,
    in CI pipelines.",
    "type": "boolean",
    "default": false
  }
  ```
- Confirmed wired into both pipeline stages:
  - `3-dry-run-executor.ts:146-150` — when true, only logs "running the
    dry-run only. No mutations will be tested," and otherwise runs the dry
    run identically (still with real `coverageAnalysis`/`perTest` instrumentation, so the
    consumer-file discovery this build needs still happens in full).
  - `4-mutation-test-executor.ts:90-95` — short-circuits immediately:
    ```js
    if (this.options.dryRunOnly) {
      this.log.info('The dry-run has been completed successfully. No mutations have been executed.');
      return [];
    }
    ```
    This means the real per-mutant mutation-testing phase — and therefore
    every `checker.check()` call — **never executes at all** when
    `dryRunOnly: true`. This is a second, independent confirmation that
    `checkers` truly cannot matter for this derivation run: with
    `dryRunOnly: true`, checkers are provably inert regardless of their
    contents.
- Also present in the CLI (`node_modules/@stryker-mutator/core/src/stryker-cli.ts:210`,
  registers `--dryRunOnly` as a CLI flag), and documented as intended for
  exactly this kind of low-risk, discovery-only pass ("useful in CI
  pipelines" — i.e. a sanctioned, non-hacky use case, not a misuse of an
  internal flag).

**Recommended combination for the one-time derivation run:** add both
`disableTypeChecks: false` (or `disableTypeChecks: 'src/lib/db-rls.ts'` if you
want to keep the injection narrowly active on just the mutated file) **and**
`dryRunOnly: true` to `stryker.config.mjs`, alongside the existing
`mutate: ['src/lib/db-rls.ts']` / `checkers: ['typescript']` /
`testFiles` unset. This:
1. Eliminates the crash (fixes the actual mechanism — `disableTypeChecks`, not
   `checkers`).
2. Still lets Stryker's real `coverageAnalysis`/`perTest` dry run empirically
   enumerate every consumer test file across the full un-narrowed `testFiles`
   set (the actual goal of this pass) — unaffected by either change.
3. Additionally guarantees the run stops after the dry run and never proceeds
   into real per-mutant mutation testing against the wider 66-file suite at
   all — a second, independent safety net beyond just fixing the crash,
   confirmed structurally inert to `checkers` regardless of its contents.
4. Both are one-line additions removed after this derivation run, exactly like
   the existing "TEMPORARY" comment block already at the top of
   `stryker.config.mjs` describes for `testFiles`/`mutate`.

## Sources (all opened/fetched directly)

- `web/stryker.config.mjs` (worktree) — current config + existing comment
  block documenting the 2 prior `@ts-nocheck` collisions this codebase already
  worked around via `testFiles` narrowing.
- `node_modules/@stryker-mutator/core/src/sandbox/disable-type-checks-preprocessor.ts`
- `node_modules/@stryker-mutator/core/src/sandbox/file-preprocessor.ts`
- `node_modules/@stryker-mutator/core/src/sandbox/create-preprocessor.ts`
- `node_modules/@stryker-mutator/core/src/config/file-matcher.ts`
- `node_modules/@stryker-mutator/core/src/process/2-mutant-instrumenter-executor.ts`
- `node_modules/@stryker-mutator/core/src/process/3-dry-run-executor.ts`
- `node_modules/@stryker-mutator/core/src/process/4-mutation-test-executor.ts`
- `node_modules/@stryker-mutator/core/src/stryker-cli.ts`
- `node_modules/@stryker-mutator/core/schema/stryker-schema.json` (lines
  275-333, 456-470)
- `node_modules/@stryker-mutator/typescript-checker/package.json` (confirmed
  v9.6.1; confirmed zero `nocheck`-related content anywhere in that package)
- https://stryker-mutator.io/docs/stryker-js/configuration/ — `disableTypeChecks`,
  `checkers`, `coverageAnalysis`, `dryRunOnly` official descriptions (fetched,
  match local schema verbatim)
- https://stryker-mutator.io/docs/stryker-js/troubleshooting/ — the official
  fix pattern for initial-test-run type-error failures (narrow
  `disableTypeChecks`), presented as distinct from the `checkers` add-on fix
  for surviving compile-error mutants
- https://stryker-mutator.io/docs/stryker-js/typescript-checker/ — checker
  plugin description ("Type check each mutant. Invalid mutants will be marked
  as `CompileError`" — confirms it's a per-mutant mechanism)
- https://github.com/stryker-mutator/stryker-js/issues/2438 — "Discussion:
  TypeScript compile errors with mutation switching," the issue the
  preprocessor's own source comment cites as its origin/rationale
- https://github.com/stryker-mutator/stryker-js/issues/2569 — "Stryker breaks
  the jest environment change and tests fail," a structurally identical
  first-line/docblock collision with the same documented `disableTypeChecks`
  glob-narrowing fix

## Not found / could not verify

- No GitHub issue matching this exact codebase's literal assertion
  (`startsWith("'use server'")`) — expected, since that's project-specific;
  the taxonomy match (#2438, #2569) is what establishes this as a known
  collision class rather than this specific string.
- Could not find an official doc page stating in one place, explicitly, "the
  checker never runs during the dry run" — this is a source-code-level fact
  (confirmed by grepping call sites across `3-dry-run-executor.ts` and
  `4-mutation-test-executor.ts`), not something the prose docs state directly;
  flagging so this claim is understood as source-derived, not doc-quoted.
