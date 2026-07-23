# no_tests_project

A project with no tests at all and no `package.json`. `verify.py` should report
`passed: False` ("No tests detected") — a build that proved nothing is not a pass.
