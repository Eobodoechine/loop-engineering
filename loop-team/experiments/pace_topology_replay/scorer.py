#!/usr/bin/env python3
"""Run and score the five deterministic non-IID counterfactual replays."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulator import score_results, simulate_case


HERE = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE / "fixtures" / "simulation_result.json")
    args = parser.parse_args()
    frozen = json.loads((HERE / "fixtures" / "frozen_cases.json").read_text(encoding="utf-8"))
    cases = [simulate_case(case) for case in frozen["cases"]]
    output = {"schema": "pace_topology_replay_result.v1", "cases": cases, "score": score_results(cases)}
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output["score"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
