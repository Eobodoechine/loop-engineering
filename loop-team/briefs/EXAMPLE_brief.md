# Brief

> Copy this file, fill it in, and hand it to Oga to start a build.

## goal
One or two sentences: what to build and why.
*Example: Build a Python function that parses human duration strings like "1h30m" into total seconds.*

## acceptance_criteria
Concrete, checkable conditions for "done". These become the tests.
- *Example: `parse_duration("1h30m")` returns `5400`.*
- *Example: bare units work: `"45m"` -> `2700`, `"90s"` -> `90`.*
- *Example: combined units work: `"2h15m30s"` -> `8130`.*
- *Example: empty or unrecognized input raises `ValueError`.*

## target
Exactly one:
- `existing_repo: /absolute/path/to/repo`  — modify code that already exists (Oga works on a branch/copy).
- `new_project: /absolute/path/to/new/dir` — scaffold from scratch.

## constraints
- language / runtime: *e.g. Python 3, standard library only*
- dependencies allowed: *e.g. none / pytest for tests*
- style / other: *e.g. must be importable as a single module; no network calls*

## done_means (optional)
Anything beyond the tests that defines success — performance targets, interface shape, docs.
