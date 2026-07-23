# Live-test findings — Zillow rental search enumeration (2026-07-10)

## Scope and method
This is a Researcher-Mode-D-shaped domain brief, produced from DIRECT, first-hand live
interaction with the real Zillow site via the Claude-in-Chrome MCP (Nnamdi's real,
logged-in browser), NOT from secondary documentation. Every finding below is grounded in
an actual tool call this session (`navigate`, `computer`, `javascript_tool`) and its actual
returned output — not inference. This is stronger-than-usual grounding for a domain brief:
it is primary observation of the live target system, not a citation of someone else's
claim about it.

This testing was done to validate (or falsify) the previous build's fix for
atlanta-rental-scraper SKILL.md's Zillow Step 2A, which had NOT been live-tested before
shipping (that gap was explicitly logged as OPEN in `fix_plan.md`'s
"Zillow enumeration coverage fix" entry). The previous fix assumed the root cause was
list virtualization. Live testing found FOUR separate, real defects — one of which
contradicts the original root-cause hypothesis.

## Finding 1 — The search URL silently lands in "For Sale" mode, not rentals
The exact URL currently in SKILL.md Step 2A is:
```
https://www.zillow.com/atlanta-ga/apartments/?searchQueryState={"filterState":{"beds":{"min":1,"max":1},"price":{"max":1500},"mp":{"max":1500}}}
```
Navigating to this URL live: the page loaded with the **"For sale"** filter chip active,
heading **"Atlanta GA Real Estate & Homes For Sale"**, and returned **1 result** (an
auction property). The `filterState` object has no `"fr":{"value":true}` (for-rent) flag
and no `"fsba":{"value":false}` (exclude-for-sale) flag, so Zillow defaults the search to
its "Buy" mode. This is a plausible primary explanation for the historically-reported
"~9 cards" symptom — the search was very likely never looking at rental inventory at all
in some or all prior runs, not merely under-scrolling a virtualized rental list.

**Correct URL shape (captured live via Zillow's own UI):** clicking the "For Rent" tab and
applying "Midtown", "Up to $1.5K", "1 bd" filters through the real UI produced this URL:
```
https://www.zillow.com/homes/for_rent/?searchQueryState={"filterState":{"sort":{"value":"globalrelevanceex"},"fr":{"value":true},"fsba":{"value":false},"fsbo":{"value":false},"nc":{"value":false},"fore":{"value":false},"cmsn":{"value":false},"auc":{"value":false},"mp":{"max":1500},"sf":{"value":true},"tow":{"value":true},"con":{"value":true},"apa":{"value":true},"apco":{"value":true},"r4re":{"value":true},"beds":{"min":1,"max":1}},"regionSelection":[{"regionId":269381,"regionType":8}]}&cExperienceId=jumpBackInSrp
```
A simpler, citywide-scoped variant (typing "Atlanta GA homes" in the search box with "For
rent" mode already active) produced:
```
https://www.zillow.com/atlanta-ga/rentals/?searchQueryState={"isMapVisible":true,"mapBounds":{...},"filterState":{"fr":{"value":true},"fsba":{"value":false},"fsbo":{"value":false},"nc":{"value":false},"cmsn":{"value":false},"auc":{"value":false},"fore":{"value":false},"mp":{"min":null,"max":1500},"beds":{"min":1,"max":1}},"isListVisible":true,"usersSearchTerm":"Atlanta, GA","regionSelection":[{"regionId":37211,"regionType":6}]}&cExperienceId=jumpBackInSrp
```
Both of these correctly returned rental listings (21 results for Midtown-scoped; 1,392
for citywide Atlanta with the same 1bd/$1500 filter). The minimal fix is to add
`"fr":{"value":true}` and `"fsba":{"value":false}` (and ideally `"fsbo":{"value":false}`,
`"nc":{"value":false}`, `"fore":{"value":false}`, `"cmsn":{"value":false}`, `"auc":{"value":false}`)
to the existing `filterState`, and change the path from `/atlanta-ga/apartments/` to
`/atlanta-ga/rentals/` (both were observed to work; `/rentals/` is simpler and was
produced natively by Zillow's own UI for a citywide search).

**A more robust alternative** (does not depend on knowing Zillow's exact param names,
which can drift): after navigating, check the page for the "For rent" filter chip's
active/selected state (or the page heading text) before trusting any card count; if the
page is in "For Sale" mode, click the "For Rent" tab and re-derive the URL from the
resulting page rather than trusting the constructed URL blindly. This is a self-correcting
check that survives Zillow changing its query-param schema in the future.

## Finding 2 — Card identifier scheme: `zpid` misses the majority of apartment cards
The previous fix's accumulator keys on Zillow's `zpid` (extracted via regex from
`_zpid` in the href), because individual for-rent-by-owner units use URLs like
`/homedetails/525-Parkway-Dr-UNIT-116-Atlanta-GA-30308/461762300_zpid/`.

Live DOM inspection of a real Midtown rentals results page found **apartment-community
cards — the majority of the result set — use a DIFFERENT URL shape with no zpid at
all**, e.g.:
```
/apartments/atlanta-ga/828-834-argonne-ave-ne/Cq7JSb/
/apartments/atlanta-ga/1660-peachtree/5XhtKJ/
/apartments/atlanta-ga/crest-at-midtown/CkBS72/
```
Of 18 `<article>` cards rendered on one Midtown page, 8 were `apt_shortid` (building-style,
no zpid) and only ~2-10 (varies by page) were true `zpid` links. The `zpid`-only regex
silently ignores every `apt_shortid` card — meaning the previous fix's accumulator was
counting the wrong (and much smaller) subset of the real result set, independent of any
scrolling/virtualization behavior. **Fix: key the accumulator on the full pathname (or
equivalently, the card's `<article>` DOM node's first anchor's URL path) rather than a
zpid-specific regex** — this covers both URL shapes uniformly and does not assume which
shape the majority of cards use (that mix can change over time as Zillow's inventory
shifts between agent-managed buildings and individual owner listings).

## Finding 3 — Convergence detection fires far too early
Live-testing the previous fix's exact procedure (walk up DOM to find scrollable ancestor;
scroll by `container.clientHeight`; wait 800ms-2200ms; accumulate; stop after 3 consecutive
zero-gain steps) against a 1,392-result citywide search: the loop reported "CONVERGENCE"
after only 3 scroll steps, having accumulated just 9-17 unique cards — nowhere near
representative of 1,392 available. Manual inspection at that point showed the scrolled
container's visible content WAS genuinely changing (different addresses appeared on
screen), and a longer, separate un-batched inspection (outside the loop's own tight
step-to-step timing) found MORE cards had loaded than the loop itself detected within its
900ms-2200ms per-step wait — meaning the loop's own convergence check was measuring
too soon after each scroll to catch content that was still arriving.

Separately, on the SAME 1,392-result page, repeatedly probing showed the DOM article count
plateaus at a small number (9, then later 17) across several probes at different scroll
depths within the first ~20% of the scrollable range (`scrollTop` 643-1929 of a `scrollHeight`
of 10302-10722) — i.e. very little of the full scrollable range was ever traversed before
the 3-consecutive-zero-gain rule fired and declared victory. **The 3-consecutive-step
convergence rule is too aggressive for large result sets**: it can trip while still deep
in the "easy" early portion of the list, well before Zillow's lazy-loader has had reason to
fetch a further batch.

**Contrast case:** on a SMALL result set (21 total, Midtown-scoped, single unfiltered
1bd/$1500 search), the DOM held all 18 available cards from initial page load onward —
scrolling all the way to the bottom (`scrollTop` = `scrollHeight`) never changed the
article count at all. This page was genuinely NOT virtualized/lazy-loaded — everything
was already in the DOM. This means the "termination too early" failure mode in Finding 3
is a LARGE-RESULT-SET-ONLY problem, and the mechanism needs to behave correctly in BOTH
regimes: converge quickly (and correctly) on a small page where nothing more will ever
load, but not falsely converge early on a large page where a lazy-loader is still
fetching more content.

## Finding 4 — Repeated `scrollTop` writes can blank the results list
During a stress test (15 forced scroll iterations back-to-back with ~1.2s waits, no early
exit), the Zillow results list panel went completely blank (zero cards, zero content) while
the map panel remained functional. A page reload fully recovered normal listing display —
no lasting damage, and this was not observed during more moderate (3-6 step) scrolling —
but it demonstrates the scroll-and-accumulate mechanism has NO fallback if the list panel
enters a broken/blank state mid-loop. A production procedure needs to detect "the list
panel now shows zero cards where it previously showed some" as an anomaly (not a
legitimate result) and recover (reload the page and resume, or abort with a flagged
partial result) rather than either hanging or silently reporting a low/zero count as if it
were real.

## Summary of what needs to change (informs the spec)
1. Fix the search URL construction (or add a self-correcting for-rent-mode check) so the
   scraper never silently reads For-Sale-mode results as if they were rentals.
2. Change the per-card accumulator key from a zpid-only regex to the full card URL
   pathname (or equivalent), so building/apartment-community cards are not silently
   dropped from the count.
3. Redesign the termination rule so it does not fire prematurely on large result sets
   while still terminating promptly on small, fully-loaded ones. Options to consider in
   the spec: a longer per-step settle wait combined with a secondary "re-check after an
   idle pause" step before accepting convergence; scrolling in larger jumps; comparing the
   accumulated count against the page's own displayed "N rentals available" total (when
   parseable) as an corroborating signal rather than trusting the scroll loop alone; or
   raising the consecutive-no-gain threshold specifically for large declared totals.
4. Add a defensive check for "the list panel went blank" mid-loop (DOM article count
   dropped to zero after previously being nonzero) with an explicit recovery step (reload)
   rather than silently reporting whatever count had accumulated so far as final.

## What was NOT tested (be honest about remaining gaps)
- Neighborhoods other than Midtown and citywide Atlanta were not separately live-tested
  this pass (Virginia-Highland, Poncey-Highland, Old Fourth Ward, Inman Park, Candler Park,
  Buckhead Village were not individually exercised).
- The bot-wall/PerimeterX detection path (Step 2A.1 in the current SKILL.md) was not
  triggered or tested this pass — no bot-wall was encountered on any of the pages visited.
- Pagination behavior (Zillow's own "next page" control, if any, versus infinite-scroll
  lazy-loading) was not directly investigated — the citywide search's own lazy-load
  behavior (Finding 3) was observed via scrolling only; whether Zillow also exposes an
  explicit page-number control for this list was not checked.
