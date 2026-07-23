# TaxAhead Session N+1 Spec — Mode D Research Brief

**Date:** 2026-07-19
**Project:** `<HOME>/Claude/Projects/taxahead`
**Scope:** 9 questions on data shapes, edge functions, schema, and profile page state.

---

## 1. adaptConnections return shape

**File:** `src/lib/real-data-adapters.ts:93-138`

```ts
export function adaptConnections(
  sources: ConnectedSource[] | undefined | null,
  providers: ConnectorProvider[] | undefined | null,
): Connection[] {
```

**The `discovered` field is hardcoded to `0`** at line 134:
```ts
discovered: 0,
```

- **Type:** `number` (from the `Connection` type imported from `@/lib/mock-data`)
- **Data source:** None — it is a static stub. The adapter never reads any document count from the `ConnectedSource` or `ConnectorProvider` inputs. The `sources` data (from `listSources()` edge function) provides `id`, `provider_key`, `status`, `label`, `last_sync_at` — but no document/discovery count.
- **Implication:** The dashboard's `documentsFound` counter (see Q3) will always sum to `0` regardless of real data.

The `extracted` field is also stubbed to `[]` at line 135.

---

## 2. adaptFeedItems return shape

**File:** `src/lib/real-data-adapters.ts:72-87`

```ts
export function adaptFeedItems(
  feed: TaxPackageResult["feed"] | undefined | null,
): FeedEntry[] {
  if (!feed || feed.length === 0) return [];
  return feed.map((item): FeedEntry => ({
    id: item.id,
    title: item.title,
    body: item.body ?? "",
    kind: (item.type as FeedEntry["kind"]) ?? "discovery",
    group: "Today",
    timestamp: formatTimestamp(item.created_at),
    source: undefined,
    impact: undefined,
    actions: (Array.isArray(item.actions) ? item.actions : []) as FeedEntry["actions"],
  }));
}
```

**Transformation:**
- Maps `feed_messages` DB rows (via `TaxPackageResult.feed`) 1:1 into `FeedEntry` shape
- `type` → `kind` (cast), defaults to `"discovery"` if missing
- `created_at` → `timestamp` (formatted via `formatTimestamp`)
- `body` defaults to `""` if null
- `source` and `impact` are always `undefined` (hardcoded)
- **Every item gets `group: "Today"`** — there is no date-based grouping logic

**Deduplication:** **None.** The adapter is a pure `.map()` — no dedup by id, title, or content. If the edge function returns duplicates, they pass through verbatim.

---

## 3. Dashboard doc count derivation

**File:** `src/routes/app.dashboard.tsx:87-88`

```ts
const activeConnections = (connections ?? []).filter((c) => c.status === "Connected");
const documentsFound = activeConnections.reduce((n, c) => n + (c.discovered ?? 0), 0);
```

**How it works:**
1. Filters connections to only `"Connected"` status
2. Sums `c.discovered` across active connections

**Since `adaptConnections` hardcodes `discovered: 0` (see Q1), `documentsFound` is always `0`.**

**Display location:** `ImproveProfileCard` at line 149/748:
```tsx
{connectedCount} connected · {documentsFound} docs
```

The dashboard does **not** independently query a document count from the DB or edge functions. It relies entirely on the per-connection `discovered` field.

There is also a `useDashboardDocuments` hook in `real-data-hooks.ts:116-128` that fetches `pkg.documents` from `getTaxPackage`, but this hook is **not imported or used** by the dashboard page.

---

## 4. Feed duplicate source

### Client-side (app.feed.tsx)

**File:** `src/routes/app.feed.tsx:102, 216-224`

The feed page consumes `useFeed(filingUnitId)` which returns `FeedEntry[]`. It splits them into:
```ts
const reversed = [...feed].reverse();
return {
  earlierEntries: reversed.filter((e) => e.group !== "Today"),
  todayEntries: reversed.filter((e) => e.group === "Today"),
};
```

**No client-side dedup.** Since `adaptFeedItems` sets `group: "Today"` on every item (see Q2), `earlierEntries` is always `[]` and everything lands in `todayEntries`.

Feed items are rendered as `<li key={m.id}>` in `messages` array (line 726-729). React's `key` prop prevents DOM duplication but does not deduplicate data.

### useFeed hook (real-data-hooks.ts:61-73)

```ts
export function useFeed(filingUnitId: string | null) {
  const { signedIn } = useSession();
  return useQuery({
    queryKey: ["feed", "edge", filingUnitId],
    queryFn: async (): Promise<FeedEntry[]> => {
      if (!filingUnitId) return [];
      const pkg = await getTaxPackage(filingUnitId);
      return adaptFeedItems(pkg.feed);
    },
    enabled: signedIn && !!filingUnitId,
  });
}
```

- **Refetch:** Standard TanStack Query behavior — no `staleTime` set, so it refetches on mount/window focus. No caching beyond TanStack defaults.
- **Data source:** Calls `getTaxPackage(filingUnitId)` which reads `feed_messages` table (see Q6).

**Duplicate risk:** If `feed_messages` has duplicate rows (e.g., from repeated pipeline runs), they will all appear in the chat. The only dedup would need to happen server-side in the edge function or the pipeline that writes feed_messages.

---

## 5. Profile page current state

**File:** `src/routes/app.profile.tsx:42-161`

### Data sources:
- `useMember()` — session-derived stub (see below)
- `useSession()` → `sessionProfile.filing` + `sessionProfile.spouseFirstName`
- `resolveFilingProfile(scenario, filing, spouseFirstName)` — scenario-based lookup from `filing-profile.ts`

### Fields displayed:

| Surface | Fields | Editable? |
|---------|--------|-----------|
| **Identity** | Avatar (upload/remove), preferredName, email, joinedAt, membership status | Avatar only (localStorage) |
| **Legal name** | legalFirstName, legalMiddleName, legalLastName | **No** — all `readOnly disabled` inputs (line 79-83). "Contact support" to change. |
| **Filing intent** | filing status (single/joint/unsure), spouseFirstName | **No** — display-only. "Change through support or the chat." |
| **Filing profile** | status, complexity, dependents, primaryState, household, lastUpdated | **No** — display-only. From scenario fixture. |
| **Account** | Settings link, Billing ($49/year), Support, Sign out | Actions only |

### Form inputs:
- Legal name fields are `<TAInput readOnly disabled />` — **display only, not editable**
- No form submission anywhere on the page
- The only user-editable element is the avatar uploader (client-side localStorage, line 362-473)

### useMember() return shape (real-data-hooks.ts:26-55):
```ts
{
  id: userId,
  legalFirstName: preferredName,  // derived from email prefix
  legalMiddleName: "",
  legalLastName: "",
  fullLegalName: preferredName,
  preferredName,
  email,
  avatarInitials,
  taxYear: 2024,
  joinedAt: new Date().toISOString(),  // always "now"
  filingDeadline: "2025-04-15",
}
```
All fields are **session-derived stubs** — no DB call. `legalFirstName` = capitalized email prefix. `joinedAt` = current timestamp on every query (though `staleTime: Infinity` prevents re-execution).

---

## 6. get-tax-package edge function

**File:** `supabase/functions/get-tax-package/index.ts:100-315`

### feed[] return shape (line 171-172):
```ts
supabase.from("feed_messages")
  .select("id, type, priority, title, body, actions, state, created_at")
  .eq("filing_unit_id", filing_unit_id)
  .order("created_at", { ascending: false })
  .limit(50)
```

Returns up to **50 most recent** `feed_messages` rows for the filing unit, newest first. The response includes these columns:
```ts
feed: {
  id: string;
  type: string;       // "discovery"|"missing"|"readiness"|"opportunity"|"risk"
  priority: number;
  title: string;
  body: string | null;
  actions: unknown[];  // jsonb, default '[]'
  state: string;       // feed_state enum
  created_at: string;
}[]
```

**Data source:** Reads stored data from `feed_messages` table — this is **persisted data**, not generated on each call. Feed messages are written by upstream pipelines (discovery, sync, compute-scores). The edge function is a pure read.

### documents[] return shape (line 163-166):
```ts
supabase.from("documents")
  .select("id, source_id, filename, doc_type, tax_year, status, classification_confidence, issuer, storage_path, created_at, source:sources(type,label)")
  .eq("filing_unit_id", filing_unit_id)
  .order("created_at", { ascending: false })
```

Each document row includes an embedded `source` join (from `sources` table) providing `{ type, label }`. Also stored/persisted data.

### Other returned fields:
- `filing_unit` — `{ id, tax_year, filing_status, jurisdiction }` from `filing_units`
- `scores` — latest row from `scores` table (or `null`)
- `facts_by_category` — facts grouped by category with `{v:...}` unwrapped
- `potential_deductions_total` — sum of high-confidence deduction/credit facts
- `tax_estimate` — computed by `computeFederalTaxEstimate()` (deterministic, not AI)
- `extracted_inputs` — documents that passed the `contractStatusFor()` check (classified + supported doc type)
- `unsupported_or_excluded_items` — documents that didn't pass
- `expected_items` / `missing_items` — from `expected_items` table
- `insights` — active insights from `insights` table
- `sources` — connected sources from `sources` table

---

## 7. extract-document edge function

**File:** `supabase/functions/extract-document/index.ts:74-364`

### Classification categories:

Defined in `_shared/extraction.ts:5-10`:
```ts
export const DOC_TYPES = [
  "w2_2025",
  "1099_int_2025",
  "1099_div_2025",
  "unknown_tax_document",
] as const;
```

Only **3 supported doc types** + the catch-all `unknown_tax_document`.

### Confidence thresholds:

**`_shared/extraction.ts:147`:**
```ts
export const REVIEW_THRESHOLD = 0.6;
```

**Decision logic** (`_shared/extraction.ts:169-201`, `normalizeSundayMvpExtraction`):
- `is_tax_relevant === true` **AND**
- `classification_confidence >= 0.6` **AND**
- `doc_type` is in the supported set (`w2_2025`, `1099_int_2025`, `1099_div_2025`)

→ If all three: `status = "classified"`, `checkpointStatus = "extracted"`, facts are persisted.
→ Otherwise: `status = "needs_review"`, `checkpointStatus = "needs_preparer_review"`, `doc_type = "unknown_tax_document"`, facts are NOT persisted.

**`_shared/profiles.ts:46`:**
```ts
export const CONFIRMED_THRESHOLD = 0.6; // fact confidence at/above this counts as 'confirmed'
```
Used in `get-tax-package` when summing deduction/credit facts for `potential_deductions_total`.

### Pipeline steps:
1. Load document (RLS-scoped)
2. Idempotency guard: skip if already `classified` or `duplicate`
3. Concurrency guard: atomic `UPDATE...WHERE status IN ('pending','needs_review','ignored')` claim
4. Download bytes from storage
5. **Dedup by SHA-256 content hash** within filing unit (line 156-185)
6. Call Claude API with forced tool use (`record_tax_document`)
7. Persist evidence + facts (with idempotent cleanup of prior rows)
8. Set terminal document status

---

## 8. Filing unit data model

### DB schema (`supabase/migrations/0001_init.sql:23-38`):

```sql
create table filing_units (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  tax_year int not null default 2024,
  filing_status text not null default 'single',   -- single|mfj|mfs|hoh
  jurisdiction text not null default 'US-FED',
  created_at timestamptz not null default now()
);

create table filing_unit_members (
  id uuid primary key default gen_random_uuid(),
  filing_unit_id uuid not null references filing_units(id) on delete cascade,
  role member_role not null default 'primary',    -- primary|spouse|dependent
  display_name text,
  user_id uuid references auth.users(id)          -- null for spouse/dependent until invited
);
```

**Current fields:**
- `filing_status` — `text`, default `'single'`. Supports `single|mfj|mfs|hoh` (comment says P1 uses the rest)
- **No dependents column** on `filing_units` — dependents are modeled as `filing_unit_members` with `role = 'dependent'`
- **No profile fields** (legal name, state, etc.) on `filing_units` — those live in `profiles` (just `full_name`) and are mostly client-side stubs

**Constraint** (migration 0004):
```sql
alter table filing_units add constraint filing_units_owner_id_unique unique (owner_id);
```
One filing unit per user.

### Client-side:
- `useFilingUnitId()` (`src/lib/filing-unit.ts`) calls `bootstrapFilingUnit()` edge function once per session, caches with `staleTime: Infinity`
- The bootstrap edge function is idempotent — creates if not exists, returns existing otherwise

---

## 9. Supabase schema (migrations)

**16 migration files** in `supabase/migrations/`:

| # | File | Key tables/changes |
|---|------|-------------------|
| 0001 | `0001_init.sql` | Core schema: `profiles`, `filing_units`, `filing_unit_members`, `sources`, `documents`, `evidence`, `facts`, `fact_evidence`, `expected_items`, `detected_profiles`, `scores`, `insights`, `feed_messages`. RLS policies. |
| 0002 | `0002_storage.sql` | Storage bucket setup |
| 0003 | `0003_document_issuer.sql` | Adds `issuer` column to `documents` |
| 0004 | `0004_filing_unit_unique_owner.sql` | Unique constraint: one FU per user |
| 0005 | `0005_connector_platform.sql` | Connector platform tables (provider registry, etc.) |
| 0006 | `0006_oauth_connection_states.sql` | `oauth_connection_states` table with `filing_unit_id` FK |
| 0009 | `0009_secret_vault_rpc.sql` | Secret vault RPC |
| 0010 | `0010_smoke_live_proof_audit.sql` | Smoke test audit trail |
| 0011 | `0011_oauth_finalize_rpc.sql` | OAuth finalize RPC, writes to `sources` |
| 0012 | `0012_source_sync_singleflight.sql` | Sync singleflight (jobs table) |
| 0013 | `0013_sources_authenticated_select.sql` | Authenticated select on sources |
| 0014 | `0014_authenticated_owner_read_grants.sql` | Read grants |
| 0015 | `0015_connector_generation_guards.sql` | Connector generation guards |
| 0016 | `0016_secret_vault_rpc_guarded.sql` | Guarded secret vault RPC |

**Key tables for profile/filing/documents:**
- `profiles` — `id` (auth.users FK), `full_name`, `created_at`
- `filing_units` — `id`, `owner_id`, `tax_year`, `filing_status`, `jurisdiction`
- `filing_unit_members` — `id`, `filing_unit_id`, `role` (primary/spouse/dependent), `display_name`, `user_id`
- `documents` — `id`, `filing_unit_id`, `source_id`, `owner_member_id`, `storage_path`, `filename`, `mime_type`, `dedupe_hash`, `tax_year`, `doc_type`, `status`, `classification_confidence`, `issuer`, `created_at`
- `feed_messages` — `id`, `filing_unit_id`, `type`, `priority`, `title`, `body`, `actions` (jsonb), `state`, `created_at`

**No migration adds:** dependent count fields, state-of-residence, legal name fields beyond `profiles.full_name`, or any editable profile fields.

---

## Summary of key gaps for Session N+1 spec

1. **`discovered` is always 0** — dashboard doc count is a dead counter. Needs a real aggregation (e.g., `COUNT(documents) GROUP BY source_id` joined into connections).
2. **No feed dedup** — neither adapter nor edge function deduplicates `feed_messages`. Relies entirely on upstream write correctness.
3. **Profile page is read-only** — all fields are either session-derived stubs or scenario fixtures. No editable form inputs for filing status, dependents, state, etc.
4. **`useMember()` is a stub** — legal name = email prefix, joinedAt = now(), no DB call.
5. **`filing_units` is minimal** — only `filing_status` (text default 'single') and `jurisdiction`. No dependents count, no state, no profile metadata.
6. **Classification is narrow** — only W-2, 1099-INT, 1099-DIV for TY2025 are "supported." Everything else → `unknown_tax_document` / `needs_review`.
7. **Feed messages are persisted** — `get-tax-package` reads from `feed_messages` table (not generated on the fly), so duplicates must be prevented at write time.
