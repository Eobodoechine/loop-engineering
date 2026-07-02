# Keep pytest from collecting the eval FIXTURES as real tests. The fixture
# projects under fixtures/ are inputs to verify.py (one is intentionally failing,
# one collects zero tests); they must not run in the suite's own test session.
# _shims/ holds the pytest-blocking shim used to force the unittest path.
collect_ignore_glob = ["fixtures/*", "_shims/*"]
