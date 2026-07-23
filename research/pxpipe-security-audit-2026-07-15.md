# Security audit: pxpipe / pxpipe-proxy (2026-07-15)

Independent, adversarial follow-up to `pxpipe-domain-brief-2026-07-15.md`. Dispatched
separately (general-purpose agent, read-only WebFetch/WebSearch only, no install/execute)
specifically to stress-test the domain brief's claims before recommending install, given
pxpipe is a local reverse proxy designed to sit in front of ANTHROPIC_BASE_URL traffic.

## Verdict: LOOKS LEGITIMATE — full byte audit (2026-07-15, 100% coverage) closes the sampling gap; one minor gap (Socket.dev/npm-web 403s) remains open

## Byte audit (added 2026-07-15, later pass)

Full end-to-end audit of the shipped `dist/node.js` bundle (8,504,957 bytes, sha256
`916e52edbd658ba9acb6a3b49725ab628d2dd1c3d7dd0d9758d88b3844a66c8d`, fetched from
`unpkg.com/pxpipe-proxy@0.9.0/dist/node.js`), split into 19 sequential 450KB chunks and
independently semantic-audited chunk-by-chunk (19/19 returned, zero missing) — 100%
coverage, not a sample.

**Deterministic full-file scan (every byte, pattern-matched):** only 9 distinct URL-like
literals in the entire file: two loopback forms (`127.0.0.1`, `127.0.0.1:47821`, all in
log/help-text template literals), the SVG XML namespace (inside vendored Alpine.js, used
for the local dashboard UI), `alpinejs.dev/plugins/${r}` (a template literal inside
Alpine's own plugin-missing warning string — never fetched), `api.anthropic.com` and
`api.openai.com` (default upstream constants + help text), two `github.com` doc-comment
attribution links (inside the vendored `gpt-tokenizer` library), and a plain-text
`docs.anthropic.com/.../pricing` citation label shown in the dashboard next to a computed
cost figure (a string, never fetched over the network). Nothing else, anywhere.

**The one finding worth naming:** chunk 0 surfaced a real (not string/comment)
`import { spawnSync } from "node:child_process"` at the top of the bundle — flagged
because its call sites weren't in that chunk. Located both call sites directly by byte
offset in the full file:
- `spawnSync("git", args, { cwd, encoding: "utf8", stdio: [...] })` inside a `gitRun()`
  helper, used by the CLI's `export` subcommand to read git diff/context — a documented,
  opt-in CLI feature, not something triggered by proxied request traffic.
- `spawnSync("open", [outDir], { stdio: "ignore" })` — opens the output folder in the
  OS file browser, gated behind `if (opts.open)` (an explicit CLI flag).

Both are exactly what a CLI export/reporting feature is expected to do (git integration,
"open the folder when done") — neither is reachable from proxied API traffic, neither
takes network-controlled input as its command/args. **Closes as benign.**

Every other chunk (18/19) reported `clean: true` with zero findings. No credential-shaped
strings, no unexpected domains, no eval/Function outside the already-identified vendored
Alpine.js UI code, no file writes outside `~/.pxpipe/`. Base64 blobs (~8.4MB of the file)
inspected and consistent with font/glyph atlas data for the PNG-rendering feature, not
disguised payloads.

## Evidence

**Repo (api.github.com/repos/teamchong/pxpipe, fetched directly):**
stargazers_count 6143, forks_count 523, created_at 2026-05-20T12:39:42Z,
pushed_at 2026-07-14T13:35:49Z, open_issues_count 75, license MIT.

**Star-growth corroboration (organic, not inflated):**
- HN submission by a third party ("dimitropoulos", not the author), 2026-07-03,
  314 points / 99 comments, linking directly to the repo (hn.algolia.com/api/v1/search).
- Independent multi-outlet press pickup in July 2026 (the-decoder.com, aiweekly.co,
  gitconnected/Medium, evoailabs/Medium, HyperAI, pasqualepillitteri.it).
- trendshift.io/repositories/71973 shows it indexed as a real trending repo.
- Maintainer account `teamchong`: created 2017-02-20 (9 years old), 402 public repos,
  453 followers, stated Cloudflare affiliation — not a fresh throwaway account.
- Contributors: teamchong (319 commits, dominant) + 4 minor contributors — normal
  single-maintainer-plus-community shape, not a bulk-commit dump.
- No hits anywhere for "pxpipe" + "fake stars"/"bought stars".

**package.json (raw.githubusercontent.com):** no postinstall/preinstall/install/prepare
script. Single runtime dependency (`gpt-tokenizer`). Dev deps are standard, well-known
tooling. Clean profile.

**Proxy source (src/worker.ts, src/node.ts, src/core/proxy.ts, src/core/tracker.ts):**
outbound destinations are only `api.anthropic.com`, `api.openai.com`, and an optional
user-configured Cloudflare AI Gateway URL (opt-in, not a hardcoded default). API keys are
forwarded only to the configured upstream. Local loopback secret header is deleted before
forwarding upstream. Telemetry writes to local files only (`~/.pxpipe/events.jsonl`) or
console.log on the Workers deploy path — no exfil endpoints, no eval()/Function(),
no obfuscated payload strings found in the reviewed source.

**npm (registry.npmjs.org/pxpipe-proxy):** maintainer `teamch` (teamchong@outlook.com,
matches GitHub). 24 published versions June 10 → July 14, 2026 (incremental, active dev).
Maintainer publishes 16 total npm packages including native cross-platform builds
(textsift-*) — established history, not a name-squat throwaway account.

**Security advisories:** none found (GitHub security-advisories API empty; no web hits
for "pxpipe malware/scam/vulnerability").

## Gaps NOT closed (flagged explicitly, not assumed clean)

1. ~~The shipped bundle was only sampled, not byte-audited in full~~ — **CLOSED**, see
   "Byte audit" section above (2026-07-15 later pass): full 19/19-chunk, 100%-coverage
   audit completed, one finding (`spawnSync`) fully traced to source and explained as
   benign CLI functionality unreachable from proxied traffic.
2. `socket.dev/npm/package/pxpipe-proxy` (automated supply-chain risk score) and
   `npmjs.com/package/pxpipe-proxy` (live download counts / any UI-level deprecation
   banner) both returned HTTP 403 to WebFetch — could not be independently checked.
   **Still open.**

## Inherent risk (by design, not a finding)

pxpipe is a MITM proxy for Claude Code's API traffic by construction — that's the whole
feature (it rewrites `ANTHROPIC_BASE_URL`, sees the API key in-process to forward it).
This is expected behavior for what it claims to be, not a hidden capability. It's also
lossy for byte-exact data per the README's own caveat ("IDs, hashes, secrets must stay
text") and is single-maintainer (bus-factor-1).

## Linked from
- `pxpipe-domain-brief-2026-07-15.md` (functional research, same date)
