# Domain brief: Gmail API 403 error-body shape (retryable vs terminal reasons)

Mode D research for TaxAhead Gmail connector spec revision. 2026-07-09.

## question
What is the actual JSON error-body shape the Gmail API returns on a 403 response,
and which exact field/path carries the machine-readable `reason` string
(`rateLimitExceeded`, `userRateLimitExceeded`, `dailyLimitExceeded`, `domainPolicy`)?
Is it the older Discovery-based `error.errors[0].reason`, or the newer
`google.rpc.Status`-style `error.status`/`error.details[].reason`? Could a single
403 ever contain multiple `errors[]` entries with different reasons?

## answer
Gmail API still uses the **older, Discovery-based Google API error format** — not
`google.rpc.Status`. The reason string lives at **`error.errors[0].reason`**
(a sibling field `error.errors[0].domain` disambiguates further; there is no
`error.status` or `error.details[]` in Gmail's documented 403 bodies).

Verified verbatim JSON for all four reasons named in the spec, straight from
Google's own Gmail error-handling guide
(https://developers.google.com/workspace/gmail/api/guides/handle-errors, fetched 2026-07-09):

**rateLimitExceeded** (retryable):
```json
{
  "error": {
    "errors": [
      { "domain": "usageLimits", "message": "Rate Limit Exceeded", "reason": "rateLimitExceeded" }
    ],
    "code": 403,
    "message": "Rate Limit Exceeded"
  }
}
```
Doc's own resolution text: "Use exponential backoff to retry" / "Request a quota increase."

**userRateLimitExceeded** (retryable):
```json
{
  "error": {
    "errors": [
      { "domain": "usageLimits", "reason": "userRateLimitExceeded", "message": "User Rate Limit Exceeded" }
    ],
    "code": 403,
    "message": "User Rate Limit Exceeded"
  }
}
```
Doc's resolution text: "optimize your application code to make fewer requests or use
exponential backoff." Doc also separately notes "Per-user limits cannot be increased
for any reason" — relevant constraint, this one never gets a quota bump, only backoff.

**dailyLimitExceeded** (terminal/blocking for the day):
```json
{
  "error": {
    "errors": [
      { "domain": "usageLimits", "reason": "dailyLimitExceeded", "message": "Daily Limit Exceeded" }
    ],
    "code": 403,
    "message": "Daily Limit Exceeded"
  }
}
```
Doc's resolution text: "raise the quota in the Google Cloud project" — i.e. not
retryable by backoff; requires a project-level quota change, resets at the daily
boundary. This is the class the spec calls terminal/blocking.

**domainPolicy** (terminal/blocking, admin-side):
```json
{
  "error": {
    "errors": [
      { "domain": "global", "reason": "domainPolicy", "message": "The domain administrators have disabled Gmail apps." }
    ],
    "code": 403,
    "message": "The domain administrators have disabled Gmail apps."
  }
}
```
Doc's resolution text: inform the user that their domain administrator must grant
access — not something the client can retry its way past.

Note the `domain` field itself differs between the two classes too:
`usageLimits` for all three quota-related reasons (`rateLimitExceeded`,
`userRateLimitExceeded`, `dailyLimitExceeded`), but `global` for `domainPolicy`.
The oracle in the spec should key off `reason`, not `domain` (domain is not a clean
discriminator between retryable/terminal since `usageLimits` covers both
`rateLimitExceeded` and the terminal `dailyLimitExceeded`).

### Is this the legacy format or google.rpc.Status?
Confirmed legacy/Discovery-based format. Cross-checked against the same "errors[]"
+ `domain`/`reason`/`message`/`locationType`/`location` shape used by sibling Google
Workspace/consumer APIs (Drive: https://developers.google.com/workspace/drive/api/guides/handle-errors,
Calendar: https://developers.google.com/workspace/calendar/api/guides/errors,
Search Ads 360: https://developers.google.com/search-ads/v2/standard-error-responses
— fetched, showed identical `error.errors[].{domain,reason,message,locationType,location}`
shape). This is a different, older convention than the `google.rpc.Status`
(`code`/`message`/`details[]`, surfaced in REST as `error.status`/`error.details[]`)
used by newer Google Cloud gRPC-transcoded APIs — see Google's AIP-193 errors design
doc (https://cloud.google.com/apis/design/errors). Gmail is not one of those APIs;
its documented 403 bodies never show `status` or `details` fields.

### Real-world client-library confirmation (not just docs)
Fetched the actual `googleapiclient` (Google's official Python API client) source,
`googleapiclient/errors.py`, `HttpError._get_reason()`
(https://github.com/googleapis/google-api-python-client/blob/main/googleapiclient/errors.py):
it parses `data["error"]["message"]` for the top-level reason string and separately
stashes `data["error"]["errors"]` (or `detail`/`details`/`message`, whichever key is
present) into `self.error_details` — i.e. the official client treats
`error.errors` as the structured-detail array, consistent with the Discovery format,
not `google.rpc.Status`.

### Can `errors[]` have multiple entries with different reasons?
**Not found — no Google doc explicitly confirms or rules this out for Gmail 403s.**
What I can state:
- Every documented Gmail 403 JSON example (all four reasons above, and
  `insufficientPermissions` too) shows exactly **one** entry in `errors[]`.
- The official `googleapiclient` source code (quoted above) only ever reads
  `data[0]` / treats `errors[0]`-style access as sufficient when the top-level
  shape is a list-wrapped error; for the dict-shaped `{"error": {...}}` body (which
  is what Gmail returns) it reads the single top-level `message`, not per-entry.
  It does not iterate `errors[]` to reconcile multiple reasons.
- The multi-entry `errors[]` case IS real for OTHER Google APIs (e.g. batch
  validation errors returning one entry per invalid field on a 400), but that is a
  different failure family (structured validation, not quota/policy blocking) and I
  found no documented or code-level case of a single Gmail 403 carrying two
  different quota/policy reasons simultaneously.
- **Recommendation given the gap:** treat `errors[0].reason` as authoritative (matches
  official docs and official client library behavior) but do not silently drop the
  rest of the array — if `errors.length > 1`, log the full array so a future
  discrepancy is observable rather than swallowed. Do not build retry logic that
  requires scanning all entries; there is no documented case that needs it, and
  building for an unconfirmed case now risks a wrong assumption baked into the oracle.

## source
- Primary: https://developers.google.com/workspace/gmail/api/guides/handle-errors — fetched 2026-07-09, quoted JSON above verbatim for all 4 reasons plus their prose resolution text.
- Corroborating (identical error shape, other Google Workspace APIs): https://developers.google.com/workspace/drive/api/guides/handle-errors ; https://developers.google.com/workspace/calendar/api/guides/errors ; https://developers.google.com/search-ads/v2/standard-error-responses
- Newer-format contrast: https://cloud.google.com/apis/design/errors (AIP-193, google.rpc.Status / `error.status`+`error.details[]`, confirmed as the DIFFERENT convention Gmail does not use)
- Client-library ground truth: https://github.com/googleapis/google-api-python-client/blob/main/googleapiclient/errors.py — `HttpError._get_reason()`, fetched and quoted 2026-07-09.

## recommended_code_pattern
```typescript
// Gmail API 403 error body (Discovery-based legacy format — confirmed, not google.rpc.Status)
interface GoogleApiErrorDetail {
  domain: string;   // "usageLimits" for rate/daily limits, "global" for domainPolicy
  reason: string;   // the machine-readable code to switch on
  message: string;
}

interface GoogleApiErrorBody {
  error: {
    errors: GoogleApiErrorDetail[]; // documented Gmail 403s always contain exactly 1 entry
    code: number;                   // e.g. 403
    message: string;
  };
}

const RETRYABLE_REASONS = new Set(["rateLimitExceeded", "userRateLimitExceeded"]);
const TERMINAL_REASONS = new Set(["dailyLimitExceeded", "domainPolicy"]);

function classifyGmail403(body: GoogleApiErrorBody): "retry" | "terminal" | "unknown" {
  const entries = body?.error?.errors ?? [];
  if (entries.length === 0) return "unknown";

  // errors[0] is authoritative per official docs + googleapiclient source (no
  // multi-reason case is documented for Gmail 403s); log if >1 for visibility.
  if (entries.length > 1) {
    console.warn("Gmail 403 had multiple errors[] entries", entries);
  }
  const reason = entries[0].reason; // NOT error.status / error.details[] — Gmail doesn't use that shape

  if (RETRYABLE_REASONS.has(reason)) return "retry";
  if (TERMINAL_REASONS.has(reason)) return "terminal";
  return "unknown"; // e.g. insufficientPermissions — different problem class, not in this spec's scope
}
```

## constraints
- Field path is `error.errors[0].reason` (array element), not `error.reason` and not `error.status`.
- `domain` is NOT a reliable retry/terminal discriminator: `usageLimits` covers both
  `rateLimitExceeded`/`userRateLimitExceeded` (retryable) AND `dailyLimitExceeded`
  (terminal) — must switch on `reason`, not `domain`.
- `userRateLimitExceeded`: per-user limits documented as never increasable — backoff
  is the only lever, no quota-request escalation path exists for this one.
- `dailyLimitExceeded` resets at the project's daily quota boundary (Pacific time,
  per Google's quota docs) — not retryable within the same day; needs a quota raise.
- `domainPolicy` is an admin-side block; no client action can clear it.
- This shape is Gmail-specific confirmation; do not assume other/newer Google Cloud
  APIs use the same array-based format — many now use `google.rpc.Status`.

## not_found
- No official doc or source could confirm or rule out whether a single Gmail 403
  response can carry multiple `errors[]` entries with *different* reasons
  simultaneously. All documented examples show exactly one entry, and the official
  Python client library does not defensively iterate/reconcile multiple entries for
  this dict-shaped error body. Treat `errors[0]` as authoritative per that
  precedent, but log the full array defensively (see code pattern) rather than
  assume the gap is closed.
