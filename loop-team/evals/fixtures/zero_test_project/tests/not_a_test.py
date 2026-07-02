# A tests/ dir that collects ZERO tests — the H-LOOPTEAM-1 false-green trap.
# unittest discover prints "Ran 0 tests / OK / exit 0"; the harness MUST still FAIL.
x = 1
